/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */
typedef enum { ST_IDLE, ST_HOMING, ST_MOVING, ST_SETTLE } run_state_t;
typedef enum { EVT_NONE, EVT_ZERO, EVT_ARRIVED, EVT_STALL } run_evt_t;
/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define IN1_HIGH()   HAL_GPIO_WritePin(GPIOB, GPIO_PIN_0, GPIO_PIN_SET)
#define IN1_LOW()    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_0, GPIO_PIN_RESET)
#define IN2_HIGH()   HAL_GPIO_WritePin(GPIOB, GPIO_PIN_1, GPIO_PIN_SET)
#define IN2_LOW()    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_1, GPIO_PIN_RESET)

#define MOTOR_TO_ZERO()  do { IN1_HIGH(); IN2_LOW();  } while (0)
#define MOTOR_TO_TOP()   do { IN1_LOW();  IN2_HIGH(); } while (0)
#define MOTOR_STOP()     do { IN1_LOW();  IN2_LOW();  } while (0)

#define COUNTS_PER_MM  780.6f   /* calibrate with a caliper, see below */
#define MAX_MM         (61667.0f / COUNTS_PER_MM)
#define STILL_MS       500      /* stall wait at the zero end */
#define STILL_TOL      2
#define SETTLE_MS      300      /* wait after stopping before reading final count */
#define ZERO_TOL       40       /* warn if zero end is further than this from old zero */
#define POS()          (-(int32_t)__HAL_TIM_GET_COUNTER(&htim2))  /* + toward top */
/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
TIM_HandleTypeDef htim2;
TIM_HandleTypeDef htim6;

UART_HandleTypeDef huart2;

/* USER CODE BEGIN PV */
static volatile run_state_t state = ST_IDLE;
static volatile run_evt_t   evt = EVT_NONE;
static volatile int32_t  evt_a = 0, evt_b = 0;
static volatile uint8_t  req_home = 0, req_goto = 0, zero_valid = 0;
static volatile int32_t  req_target = 0;
static volatile int32_t  target = 0;
static volatile int32_t  brake_offset = 495;   /* counts, tune with b<n> command */
static volatile uint16_t still_ms = 0;
static int32_t  last_count = 0;
static uint8_t  goto_after_home = 0;
static int32_t  goto_after_target = 0;
static uint8_t  rx_byte = 0;
static char     rx_buf[16];
static uint8_t  rx_len = 0;
static char     cmd[16];
static volatile uint8_t cmd_ready = 0;
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_TIM2_Init(void);
static void MX_TIM6_Init(void);
static void MX_USART2_UART_Init(void);
/* USER CODE BEGIN PFP */

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_TIM2_Init();
  MX_TIM6_Init();
  MX_USART2_UART_Init();
  /* USER CODE BEGIN 2 */
  MOTOR_STOP();
  HAL_TIM_Encoder_Start(&htim2, TIM_CHANNEL_ALL);
  HAL_UART_Receive_IT(&huart2, &rx_byte, 1);
  HAL_TIM_Base_Start_IT(&htim6);
  req_home = 1;                       /* home automatically after reset */
  {
    const char *m = "Homing... then type mm (0-79), h = home, b<n> = brake offset\r\n";
    HAL_UART_Transmit(&huart2, (uint8_t*)m, strlen(m), 100);
  }
  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
	    /* ---- results from the 1 kHz state machine ---- */
	    if (evt != EVT_NONE)
	    {
	      run_evt_t e = evt;
	      int32_t a = evt_a, b = evt_b;
	      evt = EVT_NONE;
	      char msg[96];
	      int n;

	      if (e == EVT_ZERO)
	      {
	        if (b) n = snprintf(msg, sizeof(msg), "ZERO set, zero-end error = %ld counts%s\r\n",
	                            (long)a, (labs((long)a) > ZERO_TOL) ? "  <-- WARNING" : "");
	        else   n = snprintf(msg, sizeof(msg), "ZERO set (first homing)\r\n");
	      }
	      else if (e == EVT_ARRIVED)
	      {
	        int32_t err = b - a;          /* final - target */
	        n = snprintf(msg, sizeof(msg), "target = %ld  final = %ld  error = %ld counts (%ld um)\r\n",
	                     (long)a, (long)b, (long)err, (long)((float)err * 1000.0f / COUNTS_PER_MM));
	      }
	      else
	      {
	        n = snprintf(msg, sizeof(msg), "STALL at %ld counts, motor stopped\r\n", (long)a);
	      }
	      HAL_UART_Transmit(&huart2, (uint8_t*)msg, n, 100);
	    }

	    /* ---- commands typed on the terminal ---- */
	    if (cmd_ready)
	    {
	      char line[16];
	      char msg[64];
	      int n;
	      strcpy(line, cmd);
	      cmd_ready = 0;

	      if (line[0] == 'b')
	      {
	        brake_offset = atoi(&line[1]);
	        n = snprintf(msg, sizeof(msg), "brake offset = %ld counts\r\n", (long)brake_offset);
	      }
	      else if (state != ST_IDLE)
	      {
	        n = snprintf(msg, sizeof(msg), "busy, wait\r\n");
	      }
	      else if (line[0] == 'h')
	      {
	        req_home = 1;
	        n = snprintf(msg, sizeof(msg), "homing\r\n");
	      }
	      else if ((line[0] >= '0' && line[0] <= '9') || line[0] == '.')
	      {
	        float mm = (float)atof(line);
	        if (mm > MAX_MM)
	        {
	          n = snprintf(msg, sizeof(msg), "out of range, use 0 to 79\r\n");
	        }
	        else if (mm <= 0.0f)
	        {
	          req_home = 1;
	          n = snprintf(msg, sizeof(msg), "homing\r\n");
	        }
	        else
	        {
	          req_target = (int32_t)(mm * COUNTS_PER_MM + 0.5f);
	          req_goto = 1;
	          n = snprintf(msg, sizeof(msg), "going to %ld counts\r\n", (long)req_target);
	        }
	      }
	      else
	      {
	        n = snprintf(msg, sizeof(msg), "unknown command\r\n");
	      }
	      HAL_UART_Transmit(&huart2, (uint8_t*)msg, n, 100);
	    }
	  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLM = 8;
  RCC_OscInitStruct.PLL.PLLN = 360;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;
  RCC_OscInitStruct.PLL.PLLQ = 2;
  RCC_OscInitStruct.PLL.PLLR = 2;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Activate the Over-Drive mode
  */
  if (HAL_PWREx_EnableOverDrive() != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV4;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV2;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_5) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief TIM2 Initialization Function
  * @param None
  * @retval None
  */
static void MX_TIM2_Init(void)
{

  /* USER CODE BEGIN TIM2_Init 0 */

  /* USER CODE END TIM2_Init 0 */

  TIM_Encoder_InitTypeDef sConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};

  /* USER CODE BEGIN TIM2_Init 1 */

  /* USER CODE END TIM2_Init 1 */
  htim2.Instance = TIM2;
  htim2.Init.Prescaler = 0;
  htim2.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim2.Init.Period = 4294967295;
  htim2.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  sConfig.EncoderMode = TIM_ENCODERMODE_TI12;
  sConfig.IC1Polarity = TIM_ICPOLARITY_RISING;
  sConfig.IC1Selection = TIM_ICSELECTION_DIRECTTI;
  sConfig.IC1Prescaler = TIM_ICPSC_DIV1;
  sConfig.IC1Filter = 10;
  sConfig.IC2Polarity = TIM_ICPOLARITY_RISING;
  sConfig.IC2Selection = TIM_ICSELECTION_DIRECTTI;
  sConfig.IC2Prescaler = TIM_ICPSC_DIV1;
  sConfig.IC2Filter = 10;
  if (HAL_TIM_Encoder_Init(&htim2, &sConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim2, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN TIM2_Init 2 */

  /* USER CODE END TIM2_Init 2 */

}

/**
  * @brief TIM6 Initialization Function
  * @param None
  * @retval None
  */
static void MX_TIM6_Init(void)
{

  /* USER CODE BEGIN TIM6_Init 0 */

  /* USER CODE END TIM6_Init 0 */

  TIM_MasterConfigTypeDef sMasterConfig = {0};

  /* USER CODE BEGIN TIM6_Init 1 */

  /* USER CODE END TIM6_Init 1 */
  htim6.Instance = TIM6;
  htim6.Init.Prescaler = 8999;
  htim6.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim6.Init.Period = 9;
  htim6.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_Base_Init(&htim6) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim6, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN TIM6_Init 2 */

  /* USER CODE END TIM6_Init 2 */

}

/**
  * @brief USART2 Initialization Function
  * @param None
  * @retval None
  */
static void MX_USART2_UART_Init(void)
{

  /* USER CODE BEGIN USART2_Init 0 */

  /* USER CODE END USART2_Init 0 */

  /* USER CODE BEGIN USART2_Init 1 */

  /* USER CODE END USART2_Init 1 */
  huart2.Instance = USART2;
  huart2.Init.BaudRate = 115200;
  huart2.Init.WordLength = UART_WORDLENGTH_8B;
  huart2.Init.StopBits = UART_STOPBITS_1;
  huart2.Init.Parity = UART_PARITY_NONE;
  huart2.Init.Mode = UART_MODE_TX_RX;
  huart2.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart2.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart2) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN USART2_Init 2 */

  /* USER CODE END USART2_Init 2 */

}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  /* USER CODE BEGIN MX_GPIO_Init_1 */

  /* USER CODE END MX_GPIO_Init_1 */

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOH_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_0|GPIO_PIN_1, GPIO_PIN_RESET);

  /*Configure GPIO pin : PC13 */
  GPIO_InitStruct.Pin = GPIO_PIN_13;
  GPIO_InitStruct.Mode = GPIO_MODE_IT_RISING;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(GPIOC, &GPIO_InitStruct);

  /*Configure GPIO pins : PB0 PB1 */
  GPIO_InitStruct.Pin = GPIO_PIN_0|GPIO_PIN_1;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

  /* EXTI interrupt init*/
  HAL_NVIC_SetPriority(EXTI15_10_IRQn, 0, 0);
  HAL_NVIC_EnableIRQ(EXTI15_10_IRQn);

  /* USER CODE BEGIN MX_GPIO_Init_2 */

  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */

static void start_homing(int32_t p)
{
  last_count = p;
  still_ms = 0;
  MOTOR_TO_ZERO();
  state = ST_HOMING;
}

static void start_move(int32_t tgt, int32_t p)
{
  target = tgt;
  last_count = p;
  still_ms = 0;
  if ((tgt - brake_offset) <= p) { state = ST_SETTLE; return; }  /* already there */
  MOTOR_TO_TOP();
  state = ST_MOVING;
}

void HAL_GPIO_EXTI_Callback(uint16_t GPIO_Pin)      /* B1 = go home */
{
  static uint32_t last_press = 0;
  if (GPIO_Pin == GPIO_PIN_13)
  {
    uint32_t now = HAL_GetTick();
    if ((now - last_press) > 300)
    {
      last_press = now;
      if (state == ST_IDLE) req_home = 1;
    }
  }
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
  if (huart->Instance == USART2)
  {
    char ch = (char)rx_byte;
    if (ch == '\r' || ch == '\n')
    {
      if (rx_len > 0 && !cmd_ready)
      {
        rx_buf[rx_len] = 0;
        strcpy(cmd, rx_buf);
        cmd_ready = 1;
      }
      rx_len = 0;
    }
    else if (rx_len < sizeof(rx_buf) - 1)
    {
      rx_buf[rx_len++] = ch;
    }
    HAL_UART_Receive_IT(&huart2, &rx_byte, 1);
  }
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *huart)
{
  if (huart->Instance == USART2) HAL_UART_Receive_IT(&huart2, &rx_byte, 1);
}

void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim)   /* 1 kHz */
{
  if (htim->Instance != TIM6) return;

  int32_t p = POS();

  switch (state)
  {
    case ST_IDLE:
      if (req_home)
      {
        req_home = 0;
        goto_after_home = 0;
        start_homing(p);
      }
      else if (req_goto)
      {
        req_goto = 0;
        if (req_target > p)                 /* approach from below: go straight up */
        {
          start_move(req_target, p);
        }
        else                                /* home first, then go up */
        {
          goto_after_home = 1;
          goto_after_target = req_target;
          start_homing(p);
        }
      }
      break;

    case ST_HOMING:
      if (abs(p - last_count) <= STILL_TOL) still_ms++; else { still_ms = 0; last_count = p; }
      if (still_ms >= STILL_MS)
      {
        MOTOR_STOP();
        evt_a = p;                          /* zero-end position vs the old zero */
        evt_b = zero_valid;
        __HAL_TIM_SET_COUNTER(&htim2, 0);   /* re-zero */
        zero_valid = 1;
        evt = EVT_ZERO;
        if (goto_after_home)
        {
          goto_after_home = 0;
          start_move(goto_after_target, 0);
        }
        else
        {
          state = ST_IDLE;
        }
      }
      break;

    case ST_MOVING:
      if (p >= target - brake_offset)       /* stop early, the rest is coast */
      {
        MOTOR_STOP();
        last_count = p;
        still_ms = 0;
        state = ST_SETTLE;
      }
      else
      {
        if (abs(p - last_count) <= STILL_TOL) still_ms++; else { still_ms = 0; last_count = p; }
        if (still_ms >= STILL_MS)           /* jammed or hit something */
        {
          MOTOR_STOP();
          evt_a = p;
          evt = EVT_STALL;
          state = ST_IDLE;
        }
      }
      break;

    case ST_SETTLE:
      if (abs(p - last_count) <= STILL_TOL) still_ms++; else { still_ms = 0; last_count = p; }
      if (still_ms >= SETTLE_MS)
      {
        evt_a = target;
        evt_b = p;
        evt = EVT_ARRIVED;
        state = ST_IDLE;
      }
      break;
  }
}

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
