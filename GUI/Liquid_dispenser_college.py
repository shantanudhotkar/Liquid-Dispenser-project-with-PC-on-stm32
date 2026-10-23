"""Adhesive Dispenser - single-file GUI (Tkinter + pyserial).

    pip install pyserial
    python dispenser.py

Protocol with the STM32 (UART2, 115200):  D<pulses>  F  R  S   ->   DONE,theory,actual,error | STALL,moved
"""
import csv, math, os, queue, threading, time
import tkinter as tk
from tkinter import ttk, font as tkfont
import serial, serial.tools.list_ports

PORT = "COM10"            # default port, can be changed in the GUI
BAUD = 115200
PASSWORD = "0000"
COUNTS_PER_MM = 780.6     # same as the STM32 code
ERR_TOL = 300             # error if |actual - theoretical| is more than this many pulses
MAX_PULSES = 61667        # same limit as the STM32 code
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dispense_log.csv")
CSV_HEADER = ["time", "ml_requested", "theory_pulses", "actual_pulses", "error_pulses", "ml_dispensed", "result"]

# white + faint blue-grey, adhesive amber accent
BG, BG2, PANEL, FIELD, EDGE = "#F3F6FB", "#DCE7F5", "#FFFFFF", "#F7F9FC", "#D3DDEA"
TEXT, MUTED, AMBER, STEEL, INFO = "#1E2A3A", "#6B7C93", "#F2A31B", "#E3EBF6", "#B9770E"
OK, BAD, WHITE = "#1E9E6A", "#D64545", "#FFFFFF"
UI = "Segoe UI"

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

        self.pw = tk.Entry(self, show="\u25cf", justify="center", font=(UI, 20), width=10, bg=FIELD, fg=TEXT,
                           insertbackground=AMBER, relief="flat", highlightthickness=2,
                           highlightbackground=EDGE, highlightcolor=AMBER)
        self.btn = tk.Button(self, text="UNLOCK", command=self.try_unlock, bg=AMBER, fg=TEXT, activebackground="#FFB84D",
                             activeforeground=TEXT, relief="flat", font=(UI, 13, "bold"), padx=40, pady=8, cursor="hand2")
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
            col = mix(WHITE, AMBER, a * 2) if a < 0.5 else mix(AMBER, TEXT, (a - 0.5) * 2)
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
        self.geometry("920x860")
        self.minsize(820, 760)
        self.configure(bg=BG)
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
    def group(self, parent, title):
        g = tk.LabelFrame(parent, text=" " + title + " ", bg=PANEL, fg=MUTED, font=(UI, 10), bd=0,
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
        # connection row
        row = tk.Frame(f, bg=BG)
        row.pack(fill="x", padx=16, pady=(14, 6))
        self.port_var = tk.StringVar(value=PORT)
        self.port_box = ttk.Combobox(row, textvariable=self.port_var, width=9, font=(UI, 11), values=self.ports(),
                                     postcommand=lambda: self.port_box.config(values=self.ports()))
        self.port_box.pack(side="left")
        self.conn_btn = self.button(row, "Connect", self.toggle_conn)
        self.conn_btn.pack(side="left", padx=10)
        self.link_lbl = self.label(row, "Not connected", bg=BG, fg=MUTED)
        self.link_lbl.pack(side="left")

        # bottles
        g = self.group(f, "Bottles")
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
        g = self.group(f, "Dispense (total from both bottles together)")
        self.label(g, "Volume (ml)").pack(side="left", padx=(0, 10))
        self.ml = self.entry(g, 12)
        self.ml.pack(side="left", ipady=5)
        self.ml.bind("<Return>", lambda e: self.dispense())
        self.go = self.button(g, "DISPENSE", self.dispense, AMBER, TEXT)
        self.go.config(font=(UI, 13, "bold"), padx=26, pady=8, activebackground="#FFB84D")
        self.go.pack(side="left", padx=18)

        # manual jog: hold to move, release to stop
        g = self.group(f, "Manual jog (moves while the button is held)")
        for i, (text, cmd) in enumerate((("<  RETREAT", "R"), ("FORWARD  >", "F"))):
            b = tk.Button(g, text=text, bg=STEEL, fg=TEXT, relief="flat", font=(UI, 14, "bold"), pady=14,
                          cursor="hand2", activebackground=AMBER, activeforeground=TEXT)
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
        box = tk.Frame(f, bg=BG)
        box.pack(fill="both", expand=True, padx=16, pady=(10, 14))
        self.logbox = tk.Text(box, bg=PANEL, fg=TEXT, font=("Consolas", 10), relief="flat", wrap="word", state="disabled",
                              highlightthickness=1, highlightbackground=EDGE, padx=10, pady=8)
        sb = ttk.Scrollbar(box, command=self.logbox.yview)
        self.logbox.config(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.logbox.pack(side="left", fill="both", expand=True)
        for tag, color in (("dim", MUTED), ("ok", OK), ("bad", BAD), ("info", INFO), ("txt", TEXT)):
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
        self.link_lbl.config(text=f"Connected  ({port})" if ok else "Not connected", fg=OK if ok else MUTED)

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
        if delta < 1 or delta > MAX_PULSES:
            self.set_status(f"Travel {h_mm:.1f} mm is out of range", BAD)
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