"""Adhesive Dispenser - single-file GUI (Tkinter + pyserial).

    pip install pyserial
    python dispenser.py

Protocol with the STM32 (UART2, 115200):  D<pulses>  F  R  S   ->   DONE,theory,actual,error | STALL,moved
Travel limit: anything that needs more than MAX_TRAVEL_MM (75 mm) shows OUT OF RANGE and is not sent.
"""
import csv, math, os, queue, threading, time
import tkinter as tk
from tkinter import ttk, font as tkfont
import serial, serial.tools.list_ports

PORT = "COM4"            # default port, can be changed in the GUI
BAUD = 115200
PASSWORD = "0000"
COUNTS_PER_MM = 780.6     # same as the STM32 code
ERR_TOL = 300             # error if |actual - theoretical| is more than this many pulses
MAX_PULSES = 61667        # same limit as the STM32 code
MAX_TRAVEL_MM = min(75.0, MAX_PULSES / COUNTS_PER_MM)   # above this -> OUT OF RANGE (75 mm)
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dispense_log.csv")
CSV_HEADER = ["time", "ml_requested", "theory_pulses", "actual_pulses", "error_pulses", "ml_dispensed", "result"]

# professional palette: deep navy + steel blue, adhesive amber accent
BG, BG2, PANEL, FIELD, EDGE = "#EAF0F7", "#CFDDEE", "#FFFFFF", "#F4F7FB", "#C7D3E2"
TEXT, MUTED, AMBER, STEEL, INFO = "#16263A", "#5F7389", "#F2A31B", "#DDE7F3", "#2563A8"
NAVY, BLUE, WARN = "#10294A", "#2F6DB5", "#D9730D"
LINK_ON, LINK_OFF = "#5FE0A5", "#9DB2C9"
OK, BAD, WHITE = "#1E9E6A", "#D64545", "#FFFFFF"
UI = "Segoe UI"

# icons: small PNG images embedded as text, so no extra files are needed
ICON_DATA = {
    'lock_big': (
        'iVBORw0KGgoAAAANSUhEUgAAADwAAAA8CAYAAAA6/NlyAAAElElEQVR42u2aS6gcRRSGv35MblD0hkDA7BQxuSqJCVGQLDSK'
        'GowL40ZEJCpZiOaxyCIkiuJCXPjaCSoIShAEFxJw40ITSAR1FQmIUVGJhCiiYCLXx53udtH/IYdmZu7t7unOzGQaiunprq6q'
        'v86j/nOqghXXb+NSukIusWsKeAp4wq64xb4CleIkZ0Cq34kBHAGJA9evTuPA4xZMJhVYgPXATcDVevczcBI4ASwUvhk7wCbV'
        'AHgc2ANs6FP3FPAm8Abwt/t2bJyWDfha4CjwtgObAF1XMmAt8BrwOXCz6kTjAjjUgG8AjgG3CVgv+wz0m0ql12uCblcb4agD'
        'NgArgI+A1QISu/eR/se6t286mpjLgcOy82zYY4wbUOUu8BJwjcB2JEEb+BHgC9XbBNzl6sR6Piub3jrKgDsCuEZOKlH7BvZb'
        'YCdwvPDdOuAt4FYHOgHuAbZIxZcB/42SSgcCOwM8oUFn7t1vwN0CGxfKSYE7pbpm6xmwC7hsWGCHBTjU4J4CvgF2O9v7V/cv'
        'AqclqW6hLAPOAwfU3oIb13ZpxvPDGm9QMx625ecO4NMB9dYA3zsJ9nJ0VwC/DzCzHcChumt0PARVRoBTSSyWJL4DPgPmgTOL'
        'UMYMOAe8AlwlNrbRtRnJJA65Pi+q0zotkKFzUkdkz0VgDHh2UL+PCJy1Zd5/ZJzWQo9nM5rQmRLt2DedAdo0EstS0EdyZaWS'
        'OLo5TQBMAU8BN2/DoVuGetl16MpS2wv7+IRgQF+tAI4c5Zvv47nTkrTQ6v7T5123blYkriHZBLgReAjYJs/qg/b7gE8kmaV6'
        'Xau72k2qefytwMvAB8CXVUFXoZZG7XYBr5ZcZ4d1vQA8W4VmRstXXVcF7KMK6YwBBT3sLitEPmUKfdqzzOcWtX1UY8iakLCp'
        '20rgB+BKdRq1LN3MUc45RVNLVu+wpHRR7DpbA6xJKqnIqGziA+CBsjiquPi1BdUrSx0tr2X5rKSGpOfa8tJViLxpxDzwlWx/'
        'HXnCL6vQZqVgoi2mZTb3Lnn6djN5+nZOS01Ag7sNTURLi6lxpPj2scJE/wrsF0l5mgYT8G1J2HJb8wJm9DB1Kh4pZ3WGCxtq'
        'Yws4FcgTwC+67xakbzT0mPtm7KOlhUWcT7BInbEBbO1v0Npd7NPnoTe3MaamAds6Ows851ScQtSzl3ynMRl3wJ5/7wOecaDs'
        '+cPkW6VJG+Npy4aNDj5ZcGYA97sAIJgUwAb6zx7P/6KlAy0XI6fV6aPywaQBNgn+UchZhTR0lmNUJFxkWCn5JtrEATZwt8gr'
        'd8m3Uu8E7m0zkdD2SbwYeA94UIC3k+8PZ23ZcVxx4FUzFbilyNt3UGMSGwf8U01p+OReHQ+dAT82acMWxXwsdawatPujS0FF'
        'oNbO4bIRVlnAEXCWCzlh26FPWyp2LiQGXlfYWSqGLpuXNjU8DixXmiZ0IV7TxTj4O6Kppf1JFRs2kn+QfCtlB/mRwZmqjmSJ'
        'E90FvgbeBz50/ZQCXOcUT6PHfBtaKWqtw54stEUPa/dXl3gkddbECmpde2LjIQ9o5K/pGY9Jv/4HMPVMPnwrOOgAAAAASUVO'
        'RK5CYII='
    ),
    'unlock_btn': (
        'iVBORw0KGgoAAAANSUhEUgAAABYAAAAWCAYAAADEtGw7AAABuElEQVR42q3VO4sUQRQF4K97Zl3ESBdM1FSNfICBGInRguAI'
        'mmgs6DD/Zf0PBgtmBoKJmRgYCAsGYmKkiDILgojC2tMG3oY77fR0C164UFVdderUuY8ujp++oscKjFCneZXmK22s32r88o9W'
        '9jAVbKd4Fj6NtbxnMOMiLi3wBNfTt+2Y38QivWoQ4zJ0nAXILk6E78baLIBXYoyObJ36ay1Ap3iIfdzAZ3zDC9zFBF/xqhXc'
        'TsaNbmdDqvuYYyPmc9zDJq51aV2u0fhLsJgHo0bzMd7gNZ7Gej0keEVsPIjx90i3nHIfcWnFKzuBiwA8igtxwW2ci2+LFkiF'
        '5/iUCP0BSpXXHDiGlzizLurJPuAq3qfLlw41kd0O0IOUdvAjXMhS4SdO4k6cLdcF71B6csN4DxfD94JEE8h6VazKjt7QrDcX'
        '7OBd+E5+clvbIb0i6z7B4cjdSV+fGAI8Cma3cB5bMe49O+6QIo+bp+53FcPQAtkIllUCKvAozeukcxUB7wRubn0bAJutvZc7'
        'MkiU+BLzcauKyiiOGR4E+yL9jqQmvwh/HJ5zfqnyrOkb/tevadQVlDV7l+w3ViRqgG2g6nEAAAAASUVORK5CYII='
    ),
    'drop_hdr': (
        'iVBORw0KGgoAAAANSUhEUgAAABoAAAAaCAYAAACpSkzOAAABtUlEQVR42q2WLU4EQRCFv+nZBJKVOP4xBBQGgSIcYREkKOAA'
        'CA6AW8c98NwAgQCFIwFFQoIigTVgWLowr0NnmJ9ulkoq09Op6jdV9ap6CjMjUwqpz3HqkS8mzRKXYVsqkm1gN9pLS0NG6krg'
        'C7gBFoAlpS8tQjNL0VLPPfuRY+31Us5IiSgUfxq4UyQGvAFrwKvs/KQ1KnXICbCstQdmgFOt3aQ1cvr6eUXTV3SBfWNgA3jo'
        'pHxibc5Vl3FUo7C+qNjWagrIVg1IFWynC6wJpJBTYWbXCUC3snfySQYKX3bYAlIFO2qLqo4Modh94B6YVeGbmOXl8wysA+8R'
        'WVrpXcroAJjTNHAdzPRi5oF8y5Q+ChTdl1ORMWz3m5rX1aTNK22reneJw7mQTz9KZ+dkmJLmSqNfE9AIeKkrakvakM8oBch0'
        'GXrgSu8pN2m4Lq607v36wJYe2lR/fJqZb+kjLxuTT20vdTXsMAIbVwC99gLIsK1hU2bdWSWCL2ksZ3+ddUGdngMzuzSzj+jw'
        'D+0NKrZ/vmFdRIhFYEXrR+Cpxmain5MyYla1wZ3G1L/9BcUTgAzqA/AN48xjrcuFKmoAAAAASUVORK5CYII='
    ),
    'plug_btn': (
        'iVBORw0KGgoAAAANSUhEUgAAABYAAAAWCAYAAADEtGw7AAABcElEQVR42rWVPUpFMRCFv7x75aFPFB4qgqCF4AZsRMEVKNjb'
        'ugE7XYKNlXsQ7GztLcQNiJ2NKIo8RFH03sTmBGK4/2IgJJmZnExmTiZmbmWd/2i9GvkOcAxMBrppybarMMqAjcY9YB9YDXTL'
        'kh128dgDXwIZ4ALdLfAJfHUB9i1Vj/ekdXvTGmATgCWaJwX6xsB+g7/uG5BrPtJoFaJeU2ATgCxo3ACmNJ+QzUDe51q7XyAR'
        'j72nfeBMlLIFXlnZXgFbwIvkrix5iZS7As1lY6Pek25N1HNR7EtjvBTEsIo9FlhsQzfX4vW6Nqx40KHfBba5wHLJ7pt47DN8'
        'ClwrifEjSbTuAzfAifbYKo+djEbApjI+ENWOgHHgQDd6By6A1yJgU1I2Y14a4BkYAvPAY4VtbfJMEIaZgONDycbKQOtqhQsS'
        'lUV5yOSU61rdwkOyOI5/rW5OyZtt8zWlDTw1wBNwrvVdVWzbAAN86P9r3H4AXHRU+5wHQPgAAAAASUVORK5CYII='
    ),
    'bottles_grp': (
        'iVBORw0KGgoAAAANSUhEUgAAABYAAAAWCAYAAADEtGw7AAAB3ElEQVR42rXUPYsUQRAG4Gdm99aPE78CMZJThI08A03EwB+g'
        'qZloYGykgqKRgYGBYGYkguAPEIwMjC410QsMxMBMBBH17tzb3TGpgbKZvVsFG4ae7q56+623qro6ee2l/zH6M/aXsAMNKnzF'
        '538FrmM+hZV0VuEjlvEz9pq/Aa4wCaY9bKbLDsRZG8G2o07zFEfxINaDuLiP/XiOfYnEXIyrAL6PM3gWDNsLF3ERN3E3/MZF'
        'xJMsUb/Q7Bg+4XIHiTGOd+zNVRXj0LcXUbSM9yTd2wgHuIMj+IJ7WAv7pgSuUlhZ+0lxvhny3IoL4DE+hE9Tb5HU8svJXsbr'
        'BAovcDZkrbsapAmW0rxWMH6EE3iChYjgfKyHXRo3YTgspNhVXHQQb3A1+T7FhRanBN7AIaxGstqGGBVVMMHO+AZxvphyMfOt'
        'qIq515GD9SCyEXvrKQczgadFd00L8BEO40rSeIhf8zCuOiKQkrkUuubxfhbwdq9WU/yPIpJpMK9mAQ8iAV1STFLdtmC5xv/w'
        'KQv/XTgtFM0xiP23YfejsOvHuk1k1U/lU+E29uJ020Gpdl/hYdjdwO4ozXZ8x/USuNXuGy6F81Z6r+Jcsivtp3VHNfRmgPaS'
        'hnUB1qTXEPwGGWNwM6elT9MAAAAASUVORK5CYII='
    ),
    'drop_grp': (
        'iVBORw0KGgoAAAANSUhEUgAAABYAAAAWCAYAAADEtGw7AAABb0lEQVR42rWVvUoEMRSFvyRbWAhWNoqVtayNna1gZbGFnT8v'
        'sCIWW1gsyKqIhTbCPoWN4Fusha+wr7Cwjc6MzQkMmUxmdsCBYe7knntyc3JvYvrDT/7j6bXEGcABFvjRWJEKsC1InUiugSfZ'
        'rinItsi0ADaAETAEtoGsKda2mDgHboFNSXevyUxXYk+6C1zJzoEzYF+260LsZXgE1mR7fZ+7bp6TjofAqWxXGj8CjkvjrYhN'
        'ScOXmokLZd2r09smtD0HDiJZOfn3gEvZtonYCLgOPCR236/qTtg8xNmaZrhoqFe/qi1hK00TBuX6DtrUqjCDILZCbErOHf2b'
        'hnI0whLKEdMYYLnCQbYMYivEZZ1mseXVyDYL9ieasXdMIwTUjE1jx2hI7Gv2CxirASzwG7xWvrGwviOTDeLJJ8ANsBBJ+V3I'
        'N4mRpm4QX7+vwDtwAvTl+wY+gLkw2apXkz8W58Bb4qDqdOf5zGONlKUC/wBY0l3PF6P0uAAAAABJRU5ErkJggg=='
    ),
    'drop_btn': (
        'iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAYAAADgdz34AAABmklEQVR42q2Vv0oEMRDGf0nU5po7Ty0UOznhDgsLGxG01Eqw'
        '104rC4vTxk4QC/UtfJArxBc4BAtrwcLDTgt31+ZbiMv+ya0XCAmZmcz3zUwmZqGzyRjDaE1CDSzjjUTTTNqB07oPnMiJC6Ic'
        'ECIjIAkwBBaBJeDbY/QvBg6IgGOgCzSBcyAOYVHFwGg2gRdgToi/gFXgTfK4LgMr40tgXvsEaADXIQm3AZd3gVPtrXd+BGwo'
        'fK6OAyOEd8CMh9Z4+9u6ZZomdhfYy0GZyreBgzIWtgT5NHBfEudU70a6uXq2JPZnin9codeRbq5etkxTVLPAq8ozKQllLJtP'
        'YAUYeXfkMkjjuAO0StBnWbRkQzYXRca9kDaQaYC9SXTTsUeRg2ev5kOaoZFNpYNI60CJK+0zmSQPMnfkOkj7/Ai4kvynIBeJ'
        'ZFa6I9n+0XWN9jIFTp5UeutCGQlx7JWuAx6AC+91B+UgLc9DoA+864IpTaezvnRsUShD/oMEaANbwJrOh8Aj8JF9WHW+zFzq'
        'ATIQ3aoRCaXLOY+qjH8B6BBqX1SU5bsAAAAASUVORK5CYII='
    ),
    'act_grp': (
        'iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAYAAADgdz34AAABe0lEQVR42u2Vu0pDQRCGvxOPJKRQAyJYKwg2wS5vYG9pLVil'
        's7BL6xPY29lol3ews7LwBkIUMeINTfCSnLX5V4b1nCSiAYsMLLObM7Oz/8w/k6hcrTNMyTFkGQXoK3Fwjgb0cz2+RdYmDtAk'
        'P0CeZFzu7N4GSIBJ4+wyLmgDHz2QlWTz5l/i61ADToET4Aq4S1k3wBFQkd+Ygo5LbwDnwCEwA0SxXjsBbAIFBWsAFwFkdFEF'
        'WAcOzO8e0ZIQlIBpoBmbYreBvM7bwFZKCmaBS9mVhKBrtE9tR+uryE6QPQMKOscy9HWZ0n4FWNbeGaTFIGXfaGqLmQuWpWDe'
        'oB240SxzWnr5q/S79K1s9oEFYDHQeyZFLkxR0bxwVU5RRgpexLZQWvoe+7tjoXgCdoA1GZa10uQR2DU07ZpaNWRzDdwDUVSu'
        '1i0V5+WU9OjUZ/VD1uiZAx6Apu8D29pnvxwVHeA4a1S4Aaer6zOzPHVdGk2TP5jQyegf7X8F+AQpHGWGPvgpIAAAAABJRU5E'
        'rkJggg=='
    ),
    'left_btn': (
        'iVBORw0KGgoAAAANSUhEUgAAABoAAAAaCAYAAACpSkzOAAABn0lEQVR42s3WsWoUURTG8d/MDhIQQRGDEYJdDKSyEq3V3sra'
        'J7AQBX0AO/MCQayTxkoQFBtB0UoQZdPYKEZsU5jg7kyaM3AZJu7O7CZ44DZ3zsz/ft859zDZ4so1xxG5Y4q8R3521KAMJao+'
        'sLxDXoULONUHNg2oCCVXMcTHAOoCmwQaYIQlPAs1q1gOVfk8QAOMcR6vcCn2H+FDvDueFlRMAXmNtdi/h/WAlF1qVHSAPAjI'
        'Av5G3qQOLQ8D5S2QP7iLjcjZ63OPigakxEW8CEiJl/iMm9EYk6LCObzDj1BXZcmsy3ACn6KzRnGQquc0GOIy9g/rurzF75mj'
        'aHxwH7eiPkth3Qae4kwP6/Zq61JQGWq+4noCu4032OoppmqzqQyVNWwHp7GJ+5GzEK39r1U0vz04eXZZC2yA33gewEXcwC7e'
        'NiZ526qfTRxB44B9C9CX2H+Ch4nNc5neNexXqNmO/ce4kiify/Qeh987uBPWDfE9sW+moZrGKA70Pi7ybqysWYdZQXWDZPiZ'
        '3LlqXjVquw95H0gXRamy//u/7gDFt2jqoIQbsAAAAABJRU5ErkJggg=='
    ),
    'right_btn': (
        'iVBORw0KGgoAAAANSUhEUgAAABoAAAAaCAYAAACpSkzOAAABqklEQVR42r3Wu4oUQRTG8d90t5dAU9FlTXXBQCNFDV1N1sTE'
        'UDAwMVQU9AEUQX0FwXcQBH0BTUVZQxFnDYUF18vsjMkpqR1me7rbdg4U1VVdVf86db66DA4dO2cRVliQdQUN2vYtOkImGMf3'
        'fwElyEEsxXfRNyjNfglvsY6z4VnVJ6gID45iJbx6hiMYoewLtB3t3+B+1B3HKxyO/2VfMRpHn4e4HXUn8HoerJhRriLfLcE+'
        'PMWdprBixoxHkdeln9H+MW7i9wzYjrGrKdkuh5LeRXmeCku8wEncyGBr+BSwcQIl2e6PwK7gV4v4Ffge+ShgL3Eqxtnh0bTt'
        'bSmSA/NEVsUSDfADF7A6tUHrrMI3XMPlKG/gSsQx7b2/HqV4DPG8pTdXcT4G3YiJfsjjM2vpioax2YMt3MWjqPuCSwGpIl52'
        'A43zWdQEfwu3Msj7TGnlNKTLyZCW4x6eZJDVDLL9r0dQGZAzeBB1H3ERX+sgbUHpovscV8QmrocAqjqIJvdIZmkbDHE6rolh'
        'tlH1Bcphm5EGDcTT+c0wyR4nk6adKt1s0gay0HfdH9rqZ56SxsWgAAAAAElFTkSuQmCC'
    ),
    'log_grp': (
        'iVBORw0KGgoAAAANSUhEUgAAABQAAAAUCAYAAACNiR0NAAABcElEQVR42pXUsUodURAG4G/XFbmk8AWEoEkTCAQfQAtrK+tA'
        'AmmSIkmftKbOE6QJYqWNoGhtCstUsRUCkaRLFNTo3bWZhcNy1rsODLvsnvln/n/OTPHs7a6OlWjC77IivE4/VpmDtWGWTVpl'
        'KnuCL1hIKskB/cI7fIvYOldhg68Bth//64wkYyxhCw/xP1dhGziPHbycQPkj1jGDq2DSlJmD1xgN0PBBTsdcU8rI+AZPcZHo'
        '2ESyY1xm9M0CtoGLWI7AMpFlFDRPcoFVD9gMXkygvD4UsIguPsZsUE5thPM4YyjlMT5jNd7LJNEU9nB0H8oVnmMudCtwE88K'
        'p3h/nwoL/A3vs2xsece12cZPfA//FxK09JuhWer4vhmArR3gRzKO5aTl0J3V7fA+O09WWO+2qfEHK/iE6c5yGCcNWguNr1IJ'
        'qkwzXmMDHyZc7N94FYBlDrCt5BCP4gI3PfuwiJG87i7lPg1vcDZg40x1J+YWavBgfvjewtwAAAAASUVORK5CYII='
    ),
    'app_icon': (
        'iVBORw0KGgoAAAANSUhEUgAAADAAAAAwCAYAAABXAvmHAAADLUlEQVR42uWZPWsUQRjHfzt7ZxELo0bwhRQ2yWEhSAoNWAli'
        'IWKXwi5BMaCFKAbEwkYhkIDmE6hYprbwE4i1zYmlhSAickIC8XbPIv/B4biLOzczuTscWHaZ3Xmeef7P+2zWenOKcR6GMR+p'
        'Bch0ja0AHV3ZuAmQ634duCUh8iQqTuDEmYDpAB+Bk8A0sOVoZKQ1kAMFsAicASaBh0CZQgsmAfolcAh4KrRL4IG0UMTmaRIA'
        'UgKPgeN6LoGDwGoKhzYJNj8L3NOzAWpC/gZwQc/5KAqQCeE1oN4H7bVR9QHruJeBaz1Qtu8vAgsxtWAiIY9MZX2PMGk1tApM'
        'xPIHExH9m8DZPcKl9ZHTjo8EayE0kdlaZxJoAkf/AYxNZL+ABvBN8+WwNOCGzWPanPHIE2WoGZkIm58F7jph0ydTnws1JRNo'
        'PjZsHvBwyszhvR5aG5lAx+0XNquuvzTg+iABLPJ14EUAgoNqMFiAXHZ7W9XmoDbs+tAdDx8KCqOWwWHgk+4hpmjD509gBvjh'
        'RKokGrDEnyjml5Ei2RHR9DYjMwCzGWA5YoNiTXJZtL1AMQM43SM5cHAS6tJqXbS9tGA8viuAE6omYzfpuWguiEflzs14CnpV'
        'lWQRubPKRHNCPIgtgB3zsU8VehR78ymcuNC9QbrTNku30cUzWIDMQX2qq56JLYDLo5Iz/xeHuy4S3525FPbv8siq8KmqARsy'
        'myQ4Huzq1ppdPKOa0HvSHpdn4hE9Ctni6i27h7R5ZC3YxLglHpX7ZB8BcuArsOkknljDJsZN8chjC+A68zNgp6qTedDdEW0v'
        'uj4C2CrxM7AilNoRBGiL1opom5T9QMHuCdwG8FoV5O8BNdHR2rpobfD3IDhpS2kb8CXglTaQCclOxY23taYuGktOo5+8J7Y/'
        'LTo627kPbAs9K0hbm7H/BwpnPtO321q72EVzX45VOk6yeQ7MAS+BljZX0zujK3fmW/p2TmvzkOwe4yefq/pp4ApwXlXllFMe'
        'NIEPwDvgS4+1DEsAq0mf3JA7ZhM0apESUekIYpy5fvPRkmAsAeixabfGL2OgvR8C9HP2ofYDIz3+AOMS44eM6SofAAAAAElF'
        'TkSuQmCC'
    ),
}

events = queue.Queue()    # serial thread -> GUI


def mix(c1, c2, t):
    t = max(0.0, min(1.0, t))
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


# ---------------------------------------------------------------- serial ----
class Link:
    def __init__(self):
        self.ser, self.stop = None, None

    @property
    def connected(self):
        return self.ser is not None and self.ser.is_open

    def connect(self, port):
        self.disconnect()
        self.ser = serial.Serial(port, BAUD, timeout=0.2)
        self.stop = threading.Event()
        threading.Thread(target=self._read, args=(self.ser, self.stop), daemon=True).start()

    def disconnect(self):
        if self.stop:
            self.stop.set()
        if self.ser:
            try: self.ser.close()
            except Exception: pass
        self.ser = None

    def send(self, text):
        try:
            if self.connected:
                self.ser.write((text + "\n").encode())
                return True
        except (serial.SerialException, OSError):
            pass
        return False

    def _read(self, ser, stop):
        while not stop.is_set():
            try:
                raw = ser.readline()
            except (serial.SerialException, OSError, TypeError, AttributeError):   # port closed / unplugged
                if not stop.is_set():
                    events.put(("lost", ""))
                return
            if raw:
                events.put(("line", raw.decode(errors="ignore").strip()))


link = Link()


# ----------------------------------------------------------- lock screen ----
class LockScreen(tk.Canvas):
    TITLE, TRACK = "ADHESIVE DISPENSER", 4

    def __init__(self, master, on_unlock):
        super().__init__(master, bg=WHITE, highlightthickness=0)
        self.on_unlock, self.t, self.running = on_unlock, 0, True
        self.f = tkfont.Font(family=UI + " Semibold", size=34)
        self.widths = [self.f.measure(ch) for ch in self.TITLE]
        self.letters = [self.create_text(0, 0, text=ch, font=self.f, fill=WHITE, anchor="w") for ch in self.TITLE]
        self.line = self.create_line(0, 0, 0, 0, fill=AMBER, width=4, capstyle="round")
        self.sub = self.create_text(0, 0, text="Enter the operator password", font=(UI, 13), fill=WHITE)
        self.drop = self.create_oval(0, 0, 0, 0, fill=AMBER, outline="", state="hidden")
        self.ripple = self.create_oval(0, 0, 0, 0, outline=AMBER, width=2, state="hidden")
        self.msg = self.create_text(0, 0, text="", font=(UI, 12), fill=BAD)
        self.lock_icon = self.create_image(0, 0, image=master.icons["lock_big"])

        self.pw = tk.Entry(self, show="\u25cf", justify="center", font=(UI, 20), width=10, bg=FIELD, fg=TEXT,
                           insertbackground=AMBER, relief="flat", highlightthickness=2,
                           highlightbackground=EDGE, highlightcolor=AMBER)
        self.btn = tk.Button(self, text=" UNLOCK", image=master.icons["unlock_btn"], compound="left",
                             command=self.try_unlock, bg=AMBER, fg=TEXT, activebackground="#FFB84D",
                             activeforeground=TEXT, relief="flat", font=(UI, 13, "bold"), padx=34, pady=8, cursor="hand2")
        self.pw_win = self.create_window(0, 0, window=self.pw)
        self.btn_win = self.create_window(0, 0, window=self.btn)
        self.pw.bind("<Return>", lambda e: self.try_unlock())
        self.bind("<Configure>", lambda e: self.layout())
        self.animate()

    def layout(self):
        w, h = self.winfo_width(), self.winfo_height()
        self.delete("bg")
        for y in range(0, h, 4):                                  # vertical gradient
            self.create_rectangle(0, y, w, y + 4, fill=mix(WHITE, BG2, y / max(h, 1)), outline="", tags="bg")
        self.tag_lower("bg")
        ty = h * 0.28
        self.coords(self.lock_icon, w / 2, ty - 72)
        self.coords(self.sub, w / 2, ty + 78)
        self.coords(self.pw_win, w / 2, ty + 150)
        self.coords(self.btn_win, w / 2, ty + 215)
        self.coords(self.msg, w / 2, ty + 262)

    def try_unlock(self):
        if self.pw.get() == PASSWORD:
            self.running = False
            self.pw.delete(0, "end")
            self.itemconfig(self.msg, text="")
            self.on_unlock()
        else:
            self.itemconfig(self.msg, text="Wrong password")
            self.pw.delete(0, "end")

    def animate(self):
        if not self.running:
            return
        t, self.t = self.t, self.t + 1
        w, h = self.winfo_width(), self.winfo_height()
        cx, ty = w / 2, h * 0.28
        total = sum(self.widths) + self.TRACK * (len(self.widths) - 1)
        x = cx - total / 2
        for i, (item, wd) in enumerate(zip(self.letters, self.widths)):   # letters rise in one by one
            a = max(0.0, min(1.0, (t - 4 * i) / 16))
            a = 1 - (1 - a) ** 3
            col = mix(WHITE, AMBER, a * 2) if a < 0.5 else mix(AMBER, NAVY, (a - 0.5) * 2)
            self.coords(item, x, ty + (1 - a) * 20)
            self.itemconfig(item, fill=col)
            x += wd + self.TRACK
        uy = ty + 42
        u = max(0.0, min(1.0, (t - 90) / 30))
        half = total / 2 * (1 - (1 - u) ** 3)                              # underline grows from the centre
        self.coords(self.line, cx - half, uy, cx + half, uy)
        self.itemconfig(self.sub, fill=mix(WHITE, MUTED, (t - 100) / 30))
        p = (t - 120) % 160                                                # adhesive drop loop
        if t >= 120 and p < 26:
            y = -20 + (uy + 8 + 20) * (p / 26) ** 2
            self.coords(self.drop, cx - 5, y - 8, cx + 5, y + 8)
            self.itemconfig(self.drop, state="normal")
            self.itemconfig(self.ripple, state="hidden")
        elif t >= 120 and p < 62:
            q = (p - 26) / 36
            r = 8 + 190 * q
            self.coords(self.ripple, cx - r, uy - r * 0.12, cx + r, uy + r * 0.12)
            self.itemconfig(self.ripple, state="normal", outline=mix(AMBER, BG2, q))
            self.itemconfig(self.drop, state="hidden")
        else:
            self.itemconfig(self.drop, state="hidden")
            self.itemconfig(self.ripple, state="hidden")
        self.after(33, self.animate)


# ------------------------------------------------------------------ main ----
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Adhesive Dispenser")
        self.geometry("920x900")
        self.minsize(820, 800)
        self.configure(bg=BG)
        self.icons = {k: tk.PhotoImage(data=v) for k, v in ICON_DATA.items()}   # keep references alive
        self.iconphoto(True, self.icons["app_icon"])
        self.busy, self.pending, self.deadline = False, None, 0
        self.mode, self.angle, self.total_ml = "idle", 0, 0.0

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=FIELD, background=STEEL, foreground=TEXT,
                        arrowcolor=TEXT, bordercolor=EDGE, lightcolor=FIELD, darkcolor=FIELD)
        style.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", TEXT)])
        style.configure("Vertical.TScrollbar", background=STEEL, troughcolor=FIELD, bordercolor=FIELD, arrowcolor=TEXT)
        self.option_add("*TCombobox*Listbox.background", FIELD)
        self.option_add("*TCombobox*Listbox.foreground", TEXT)

        self.main = tk.Frame(self, bg=BG)
        self.main.place(relwidth=1, relheight=1)
        self.build_main(self.main)
        self.lock = LockScreen(self, on_unlock=lambda: self.main.tkraise())
        self.lock.place(relwidth=1, relheight=1)
        self.lock.pw.focus_set()

        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(50, self.poll)
        self.after(400, self.connect)
        self.migrate_csv()
        self.log(f"Log file: {LOG_FILE}", "dim")

    def close(self):
        link.send("S")                   # never leave the actuator running
        link.disconnect()
        self.destroy()

    # ----- widgets -----
    def group(self, parent, title, icon=None):
        head = tk.Frame(parent, bg=PANEL)                     # title with a small icon in front
        if icon:
            tk.Label(head, image=self.icons[icon], bg=PANEL).pack(side="left", padx=(4, 6))
        tk.Label(head, text=title, bg=PANEL, fg=NAVY, font=(UI, 10, "bold")).pack(side="left", padx=(0, 6))
        g = tk.LabelFrame(parent, labelwidget=head, bg=PANEL, bd=0,
                          highlightthickness=1, highlightbackground=EDGE, padx=16, pady=10)
        g.pack(fill="x", padx=16, pady=6)
        return g

    def label(self, parent, text, **kw):
        return tk.Label(parent, text=text, bg=kw.pop("bg", PANEL), fg=kw.pop("fg", TEXT), font=kw.pop("font", (UI, 11)), **kw)

    def entry(self, parent, width, **kw):
        return tk.Entry(parent, width=width, font=(UI, 14), bg=FIELD, fg=kw.pop("fg", TEXT), insertbackground=AMBER, relief="flat",
                        highlightthickness=1, highlightbackground=EDGE, highlightcolor=AMBER, justify="center", **kw)

    def button(self, parent, text, cmd, bg=STEEL, fg=TEXT, **kw):
        return tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg, activebackground=AMBER, activeforeground=TEXT,
                         relief="flat", font=(UI, 11, "bold"), padx=16, pady=7, cursor="hand2", **kw)

    def build_main(self, f):
        # header band: title on the left, connection on the right
        band = tk.Frame(f, bg=NAVY)
        band.pack(fill="x")
        tk.Label(band, image=self.icons["drop_hdr"], bg=NAVY).pack(side="left", padx=(18, 8), pady=12)
        tk.Label(band, text="ADHESIVE DISPENSER", bg=NAVY, fg=WHITE, font=(UI, 13, "bold")).pack(side="left")
        self.link_lbl = tk.Label(band, text="Not connected", bg=NAVY, fg=LINK_OFF, font=(UI, 11))
        self.link_lbl.pack(side="right", padx=(12, 18))
        self.conn_btn = self.button(band, "Connect", self.toggle_conn, image=self.icons["plug_btn"], compound="left")
        self.conn_btn.pack(side="right")
        self.port_var = tk.StringVar(value=PORT)
        self.port_box = ttk.Combobox(band, textvariable=self.port_var, width=9, font=(UI, 11), values=self.ports(),
                                     postcommand=lambda: self.port_box.config(values=self.ports()))
        self.port_box.pack(side="right", padx=10)
        tk.Frame(f, bg=AMBER, height=3).pack(fill="x")             # amber accent line

        # bottles
        g = self.group(f, "Bottles", "bottles_grp")
        for c, t in enumerate(("Small bottle (mm)", "Big bottle (mm)", "Ratio  big : small")):
            self.label(g, t, fg=MUTED, font=(UI, 10)).grid(row=0, column=c if c < 2 else 2, columnspan=1 if c < 2 else 3,
                                                           padx=10, sticky="w")
        self.sd = self.entry(g, 10)
        self.bd = self.entry(g, 10, state="readonly", readonlybackground="#EEF3FA", fg=INFO)
        self.rb, self.rs = self.entry(g, 5), self.entry(g, 5)
        self.rb.insert(0, "1"); self.rs.insert(0, "1")
        self.sd.grid(row=1, column=0, padx=10, pady=(2, 4), ipady=4)
        self.bd.grid(row=1, column=1, padx=10, pady=(2, 4), ipady=4)
        self.rb.grid(row=1, column=2, padx=(10, 2), ipady=4)
        self.label(g, ":", font=(UI, 14, "bold")).grid(row=1, column=3)
        self.rs.grid(row=1, column=4, padx=(2, 10), ipady=4)
        self.label(g, "Big bottle = small bottle \u00d7 ratio big \u00f7 ratio small  (filled in automatically)",
                   fg=MUTED, font=(UI, 9)).grid(row=2, column=0, columnspan=5, sticky="w", padx=10)
        for e in (self.sd, self.rb, self.rs):
            e.bind("<KeyRelease>", lambda ev: self.update_big())

        # dispense
        g = self.group(f, "Dispense (total from both bottles together)", "drop_grp")
        self.label(g, "Volume (ml)").pack(side="left", padx=(0, 10))
        self.ml = self.entry(g, 12)
        self.ml.pack(side="left", ipady=5)
        self.ml.bind("<Return>", lambda e: self.dispense())
        self.go = self.button(g, " DISPENSE", self.dispense, AMBER, TEXT, image=self.icons["drop_btn"], compound="left")
        self.go.config(font=(UI, 13, "bold"), padx=26, pady=8, activebackground="#FFB84D")
        self.go.pack(side="left", padx=18)

        # manual jog: hold to move, release to stop
        g = self.group(f, "Manual jog (moves while the button is held)", "act_grp")
        for i, (text, cmd, icon, side) in enumerate((("  RETREAT", "R", "left_btn", "left"),
                                                     ("FORWARD  ", "F", "right_btn", "right"))):
            b = tk.Button(g, text=text, image=self.icons[icon], compound=side, bg=STEEL, fg=TEXT, relief="flat",
                          font=(UI, 14, "bold"), pady=14, cursor="hand2", activebackground=AMBER, activeforeground=TEXT)
            b.grid(row=0, column=i, sticky="ew", padx=(0, 8) if i == 0 else (8, 0))
            b.bind("<ButtonPress-1>", lambda e, c=cmd, b=b: self.jog_start(c, b))
            b.bind("<ButtonRelease-1>", lambda e, b=b: self.jog_stop(b))
        g.columnconfigure((0, 1), weight=1)

        # status + total
        st = tk.Frame(f, bg=BG)
        st.pack(fill="x", padx=16, pady=(10, 0))
        self.ring = tk.Canvas(st, width=56, height=56, bg=BG, highlightthickness=0)
        self.ring.pack(side="left")
        col = tk.Frame(st, bg=BG)
        col.pack(side="left", padx=10)
        self.status = tk.Label(col, text="Ready", bg=BG, fg=TEXT, font=(UI, 17, "bold"), anchor="w")
        self.status.pack(anchor="w")
        self.total_lbl = tk.Label(col, text="Total dispensed this session: 0.000 ml", bg=BG, fg=MUTED, font=(UI, 10))
        self.total_lbl.pack(anchor="w")
        self.draw("idle")

        # log (same page, also saved to CSV)
        lh = tk.Frame(f, bg=BG)
        lh.pack(fill="x", padx=16, pady=(10, 0))
        tk.Label(lh, image=self.icons["log_grp"], bg=BG).pack(side="left")
        tk.Label(lh, text="ACTIVITY LOG", bg=BG, fg=NAVY, font=(UI, 10, "bold")).pack(side="left", padx=6)
        box = tk.Frame(f, bg=BG)
        box.pack(fill="both", expand=True, padx=16, pady=(4, 14))
        self.logbox = tk.Text(box, bg=PANEL, fg=TEXT, font=("Consolas", 10), relief="flat", wrap="word", state="disabled",
                              highlightthickness=1, highlightbackground=EDGE, padx=10, pady=8)
        sb = ttk.Scrollbar(box, command=self.logbox.yview)
        self.logbox.config(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.logbox.pack(side="left", fill="both", expand=True)
        for tag, color in (("dim", MUTED), ("ok", OK), ("bad", BAD), ("warn", WARN), ("info", INFO), ("txt", TEXT)):
            self.logbox.tag_config(tag, foreground=color)

    # ----- helpers -----
    @staticmethod
    def ports():
        return [p.device for p in serial.tools.list_ports.comports()]

    @staticmethod
    def num(e):
        try:
            v = float(e.get().replace(",", "."))
            return v if v > 0 else None
        except ValueError:
            return None

    def big_value(self):
        s, rb, rs = self.num(self.sd), self.num(self.rb), self.num(self.rs)
        return (s, s * rb / rs) if (s and rb and rs) else (s, None)

    def update_big(self):
        _, b = self.big_value()
        self.bd.config(state="normal")
        self.bd.delete(0, "end")
        if b:
            self.bd.insert(0, f"{b:.3f}".rstrip("0").rstrip("."))
        self.bd.config(state="readonly")

    def log(self, text, tag="txt"):
        self.logbox.config(state="normal")
        self.logbox.insert("end", text + "\n", tag)
        self.logbox.see("end")
        self.logbox.config(state="disabled")

    @staticmethod
    def migrate_csv():
        """If an older dispense_log.csv has different columns, keep it under a new name."""
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, newline="") as fh:
                first = fh.readline().strip()
            if first != ",".join(CSV_HEADER):
                os.replace(LOG_FILE, LOG_FILE[:-4] + time.strftime("_old_%Y%m%d_%H%M%S.csv"))

    def save_csv(self, row):
        try:
            new = not os.path.exists(LOG_FILE)
            with open(LOG_FILE, "a", newline="") as fh:
                w = csv.writer(fh)
                if new:
                    w.writerow(CSV_HEADER)
                w.writerow(row)
        except OSError:
            self.log("Could not write the CSV file (is it open in Excel?)", "bad")

    # ----- status ring -----
    def draw(self, mode):
        self.mode = mode
        c, box = self.ring, (6, 6, 50, 50)
        c.delete("all")
        c.create_oval(*box, outline=EDGE, width=5)
        if mode == "run":
            c.create_arc(*box, start=self.angle, extent=110, style="arc", outline=AMBER, width=5)
        elif mode == "ok":
            c.create_oval(*box, outline=OK, width=5)
            c.create_line(17, 29, 25, 37, 40, 20, fill=OK, width=5, capstyle="round", joinstyle="round")
        elif mode == "fail":
            c.create_oval(*box, outline=BAD, width=5)
            c.create_line(19, 19, 37, 37, fill=BAD, width=5, capstyle="round")
            c.create_line(37, 19, 19, 37, fill=BAD, width=5, capstyle="round")
        elif mode == "warn":                                   # out of range: "!" in an orange ring
            c.create_oval(*box, outline=WARN, width=5)
            c.create_line(28, 16, 28, 30, fill=WARN, width=5, capstyle="round")
            c.create_oval(25.5, 36, 30.5, 41, fill=WARN, outline=WARN)

    def spin(self):
        if self.mode == "run":
            self.angle = (self.angle - 14) % 360
            self.draw("run")
            self.after(30, self.spin)

    def set_status(self, text, color=TEXT):
        self.status.config(text=text, fg=color)

    def set_busy(self, busy):
        self.busy = busy
        self.go.config(state="disabled" if busy else "normal")

    # ----- connection -----
    def toggle_conn(self):
        if link.connected:
            link.disconnect()
            self.on_link(False)
            self.log("Disconnected", "dim")
        else:
            self.connect()

    def connect(self):
        if link.connected:
            return
        port = self.port_var.get().strip()
        try:
            link.connect(port)
        except (serial.SerialException, OSError, ValueError) as e:
            self.on_link(False)
            self.log(f"Could not open {port}: {e}", "bad")
            return
        self.on_link(True, port)
        self.log(f"Connected to {port}", "dim")

    def on_link(self, ok, port=""):
        self.conn_btn.config(text="Disconnect" if ok else "Connect")
        self.link_lbl.config(text=f"Connected  ({port})" if ok else "Not connected", fg=LINK_ON if ok else LINK_OFF)

    # ----- actions -----
    def jog_start(self, c, b):
        b.config(bg=AMBER, fg=TEXT)
        if not link.send(c):
            self.set_status("Not connected", BAD)
            return
        self.pending = None
        self.set_busy(False)
        self.draw("idle")
        self.set_status("Moving manually", INFO)

    def jog_stop(self, b):
        b.config(bg=STEEL, fg=TEXT)
        link.send("S")
        self.set_status("Ready")

    def dispense(self):
        ml = self.num(self.ml)
        s, b = self.big_value()
        if not (ml and s and b):
            self.set_status("Enter small diameter, ratio and ml", BAD)
            return
        if self.busy:
            return
        h_mm = ml * 1000.0 / (math.pi * ((s / 2) ** 2 + (b / 2) ** 2))     # V = pi * h * (r1^2 + r2^2)
        delta = round(h_mm * COUNTS_PER_MM)
        if delta < 1 or h_mm > MAX_TRAVEL_MM:                              # limit: 75 mm of travel
            if delta < 1:
                self.set_status("OUT OF RANGE - volume too small", WARN)
                self.log(f"OUT OF RANGE: {ml:g} ml is too small to move the actuator", "warn")
            else:
                max_ml = MAX_TRAVEL_MM * math.pi * ((s / 2) ** 2 + (b / 2) ** 2) / 1000.0
                self.set_status(f"OUT OF RANGE - {h_mm:.2f} mm needed (max {MAX_TRAVEL_MM:g} mm)", WARN)
                self.log(f"OUT OF RANGE: {ml:g} ml needs {h_mm:.2f} mm of travel, the limit is {MAX_TRAVEL_MM:g} mm "
                         f"(max {max_ml:.2f} ml for these bottles)", "warn")
            self.draw("warn")
            return
        if not link.send(f"D{delta}"):
            self.set_status("Not connected", BAD)
            return
        self.pending = {"ml": ml, "theory": delta, "area": math.pi * ((s / 2) ** 2 + (b / 2) ** 2)}
        self.deadline = time.time() + 90
        self.set_busy(True)
        self.set_status("Dispensing...", INFO)
        self.draw("run")
        self.spin()
        self.log(f"Dispense {ml:g} ml  (small {s:g} mm, big {b:.3f} mm)  ->  {h_mm:.3f} mm = {delta} pulses", "info")

    def finish(self, theory, actual, error, note=""):
        p = self.pending or {"ml": 0.0, "area": 0.0}
        ml = p["ml"]
        real_ml = actual / COUNTS_PER_MM * p["area"] / 1000.0      # pulses -> mm -> ml (both bottles)
        result = "Stalled" if note else ("Error" if abs(error) > ERR_TOL else "Reached")
        ok = result == "Reached"
        self.total_ml += real_ml
        self.total_lbl.config(text=f"Total dispensed this session: {self.total_ml:.3f} ml")
        head = {"Reached": "REACHED",
                "Error": f"ERROR - off by {abs(error)} pulses (limit {ERR_TOL})",
                "Stalled": "STALLED - the actuator was blocked"}[result]
        self.log(f"{head}\n"
                 f"   Theoretical : {theory} pulses\n"
                 f"   Actual      : {actual} pulses\n"
                 f"   Error       : {error:+d} pulses\n"
                 f"   Dispensed   : {real_ml:.3f} ml   (requested {ml:g} ml)", "ok" if ok else "bad")
        self.save_csv([time.strftime("%Y-%m-%d %H:%M:%S"), f"{ml:g}", theory, actual, error, f"{real_ml:.3f}", result])
        self.pending = None
        self.set_busy(False)
        self.draw("ok" if ok else "fail")
        self.set_status("Reached" if ok else (f"Error: off by {abs(error)} pulses" if result == "Error" else "Stalled"),
                        OK if ok else BAD)

    def poll(self):
        try:
            while True:
                kind, val = events.get_nowait()
                if kind == "lost":
                    link.disconnect()
                    self.on_link(False)
                    self.set_busy(False)
                    self.log("Connection lost", "bad")
                elif val.startswith("DONE,"):
                    t, a, e = (int(x) for x in val[5:].split(","))
                    self.finish(t, a, e)
                elif val.startswith("STALL,"):
                    a = int(val[6:])
                    t = self.pending["theory"] if self.pending else 0
                    self.finish(t, a, a - t, "Stalled")
                elif val.startswith(("BUSY", "ERR")):
                    self.pending = None
                    self.set_busy(False)
                    self.draw("idle")
                    self.set_status("Actuator busy - try again", BAD)
                    self.log(f"[{val}]", "bad")
                elif val not in ("OK,F", "OK,R", "OK,S"):
                    self.log(f"[{val}]", "dim")
        except queue.Empty:
            pass
        if self.busy and time.time() > self.deadline:             # no reply from the STM32
            self.pending = None
            self.set_busy(False)
            self.draw("fail")
            self.set_status("No reply from STM32", BAD)
        self.after(50, self.poll)


if __name__ == "__main__":
    App().mainloop()