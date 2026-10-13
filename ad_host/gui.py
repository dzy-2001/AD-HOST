"""Tkinter UI for the STM32/FPGA ASCII-HEX acquisition protocol."""
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .commands import encode_command
from .core import ASCII_BYTES_PER_MS, CaptureConfig, CaptureSession, RateMeter

STATE_NAMES = {
    "new": "未连接", "connecting": "正在连接", "receiving": "已连接",
    "stopping": "正在断开", "finishing": "正在完成文件保存",
    "finished": "已结束", "failed": "发生错误",
}


class App(ttk.Frame):
    def __init__(self, root):
        super().__init__(root, padding=14)
        self.root = root
        self.pack(fill="both", expand=True)
        self.session = None
        self.plot_window = None
        self.meter = None
        self.capture_meter = None
        self.closing = False
        self.last_events = []
        self.last_preview = None
        self.last_sample = 0.0
        self.last_capture_sample = 0.0
        self.last_capture_index = None

        self.host = tk.StringVar(value="192.168.3.178")
        self.port = tk.StringVar(value="11235")
        self.output = tk.StringVar(value=str(Path.home() / "Documents" / "AD-HOST" / "captures"))
        self.buffer = tk.StringVar(value="64")
        self.capture_ms = tk.StringVar(value="10")
        self.mode = tk.StringVar(value="UTF-8")
        self.ending = tk.StringVar(value="CR")
        self.preview_enabled = tk.BooleanVar(value=False)
        self.state = tk.StringVar(value="未连接")
        self.notice = tk.StringVar(value="自动采集：SET 时间,1 → 等 * → GET → 精确收满期望 HEX 数据 → 等最终 *。")
        self.capture_path = tk.StringVar(value="尚未采集")
        self.last_reply = tk.StringVar(value="—")
        keys = ("speed", "rx", "tx", "capture", "progress", "cap_speed", "eta", "pending")
        self.values = {k: tk.StringVar(value="—") for k in keys}

        root.title("AD-HOST STM32/FPGA · 采集与离线绘图 0.3.0")
        root.geometry("1120x900")
        root.minsize(920, 780)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        style = ttk.Style(root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TLabel", font=("Microsoft YaHei UI", 10))
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 19, "bold"))
        style.configure("Value.TLabel", font=("Segoe UI", 15, "bold"))
        self.columnconfigure(0, weight=1)
        self._build()
        self.after(200, self.refresh)

    def _build(self):
        heading = ttk.Frame(self)
        heading.grid(row=0, column=0, sticky="ew")
        ttk.Label(heading, text="AD-HOST STM32/FPGA", style="Title.TLabel").pack(side="left")
        ttk.Button(heading, text="解析 HEX / 绘图", command=self.open_plot).pack(side="right")
        ttk.Label(self, text="SET/GET 协议感知 · GET 数据独立保存 · 完整性计数 · TCP 速度监视").grid(
            row=1, column=0, sticky="w", pady=(0, 8))

        box = ttk.LabelFrame(self, text="连接", padding=10)
        box.grid(row=2, column=0, sticky="ew")
        box.columnconfigure(1, weight=1)
        ttk.Label(box, text="STM32 IP").grid(row=0, column=0, sticky="w")
        self.host_entry = ttk.Entry(box, textvariable=self.host, width=22)
        self.host_entry.grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Label(box, text="端口").grid(row=0, column=2)
        self.port_entry = ttk.Entry(box, textvariable=self.port, width=8)
        self.port_entry.grid(row=0, column=3, padx=8)
        self.connect_button = ttk.Button(box, text="连接", command=self.connect)
        self.connect_button.grid(row=0, column=4, padx=4)
        self.stop_button = ttk.Button(box, text="断开", command=self.stop, state="disabled")
        self.stop_button.grid(row=0, column=5, padx=4)
        ttk.Label(box, text="保存目录").grid(row=1, column=0, sticky="w", pady=8)
        self.output_entry = ttk.Entry(box, textvariable=self.output)
        self.output_entry.grid(row=1, column=1, columnspan=4, sticky="ew", padx=8)
        self.browse_button = ttk.Button(box, text="选择", command=self.browse)
        self.browse_button.grid(row=1, column=5)
        opts = ttk.Frame(box)
        opts.grid(row=2, column=0, columnspan=6, sticky="w")
        ttk.Label(opts, text="接收→写盘缓冲 MiB").pack(side="left")
        self.buffer_entry = ttk.Combobox(opts, textvariable=self.buffer, values=("16", "64", "256"), width=8, state="readonly")
        self.buffer_entry.pack(side="left", padx=8)
        ttk.Label(opts, text="Socket RCVBUF 固定请求 4 MiB；每次 recv 最大 256 KiB").pack(side="left", padx=12)
        self.config_widgets = [self.host_entry, self.port_entry, self.output_entry, self.browse_button, self.buffer_entry]

        protocol = ttk.LabelFrame(self, text="自动采集（推荐）", padding=10)
        protocol.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        protocol.columnconfigure(5, weight=1)
        ttk.Label(protocol, text="采集时间 ms").grid(row=0, column=0, sticky="w")
        self.ms_entry = ttk.Spinbox(protocol, from_=1, to=200, textvariable=self.capture_ms, width=8)
        self.ms_entry.grid(row=0, column=1, padx=8)
        self.capture_button = ttk.Button(protocol, text="SET + GET 开始采集", command=self.auto_capture, state="disabled")
        self.capture_button.grid(row=0, column=2, padx=4)
        self.quick_buttons = [
            ttk.Button(protocol, text="FINIT", command=lambda: self.quick("FINIT"), state="disabled"),
            ttk.Button(protocol, text="FST", command=lambda: self.quick("FST"), state="disabled"),
            ttk.Button(protocol, text="VER", command=lambda: self.quick("VER"), state="disabled"),
        ]
        self.quick_buttons[0].grid(row=0, column=3, padx=4)
        self.quick_buttons[1].grid(row=0, column=4, padx=4)
        self.quick_buttons[2].grid(row=0, column=5, sticky="w", padx=4)
        ttk.Label(protocol, textvariable=self.notice, wraplength=1000).grid(row=1, column=0, columnspan=6, sticky="w", pady=(7, 0))
        ttk.Label(protocol, text="最新设备回复：").grid(row=2, column=0, sticky="w", pady=(7, 0))
        ttk.Label(protocol, textvariable=self.last_reply).grid(row=2, column=1, columnspan=5, sticky="w", pady=(7, 0))

        ttk.Label(self, textvariable=self.state).grid(row=4, column=0, sticky="w", pady=(8, 4))
        metrics = ttk.Frame(self)
        metrics.grid(row=5, column=0, sticky="ew", pady=(0, 8))
        labels = [
            ("speed", "TCP 当前速度"), ("rx", "连接累计接收"), ("tx", "连接累计发送"), ("capture", "本次 GET"),
            ("progress", "采集进度"), ("cap_speed", "GET 当前速度"), ("eta", "预计剩余"), ("pending", "待写入 / 缓冲"),
        ]
        for i, (key, label) in enumerate(labels):
            card = ttk.LabelFrame(metrics, text=label, padding=8)
            card.grid(row=i // 4, column=i % 4, sticky="nsew", padx=3, pady=3)
            ttk.Label(card, textvariable=self.values[key], style="Value.TLabel").pack(anchor="w")
            metrics.columnconfigure(i % 4, weight=1)
        ttk.Entry(self, textvariable=self.capture_path, state="readonly").grid(row=6, column=0, sticky="ew", pady=(0, 8))

        manual = ttk.LabelFrame(self, text="手动指令（自动 GET 期间禁止发送，避免污染协议流）", padding=10)
        manual.grid(row=7, column=0, sticky="ew")
        manual.columnconfigure(0, weight=1)
        toolbar = ttk.Frame(manual); toolbar.grid(row=0, column=0, sticky="w")
        ttk.Label(toolbar, text="格式").pack(side="left")
        ttk.Combobox(toolbar, textvariable=self.mode, values=("HEX", "UTF-8"), state="readonly", width=8).pack(side="left", padx=8)
        ttk.Label(toolbar, text="结束符").pack(side="left")
        ttk.Combobox(toolbar, textvariable=self.ending, values=("NONE", "LF", "CR", "CRLF"), state="readonly", width=8).pack(side="left", padx=8)
        self.command_text = tk.Text(manual, height=2, wrap="word", font=("Consolas", 11))
        self.command_text.grid(row=1, column=0, sticky="ew", pady=8)
        self.send_button = ttk.Button(manual, text="发送", command=self.send, state="disabled")
        self.send_button.grid(row=1, column=1, padx=(10, 0))

        preview = ttk.LabelFrame(self, text="最新接收片段（调试用，默认关闭）", padding=8)
        preview.grid(row=8, column=0, sticky="ew", pady=8)
        ttk.Checkbutton(preview, text="显示最多 256 字节", variable=self.preview_enabled).pack(anchor="w")
        self.preview_text = tk.Text(preview, height=3, wrap="word", state="disabled", font=("Consolas", 9), background="#f3f6f9")
        self.preview_text.pack(fill="x", pady=(5, 0))

        events = ttk.LabelFrame(self, text="状态与异常", padding=8)
        events.grid(row=9, column=0, sticky="nsew")
        self.rowconfigure(9, weight=1)
        self.events_text = tk.Text(events, height=6, wrap="word", state="disabled", font=("Microsoft YaHei UI", 9))
        self.events_text.pack(fill="both", expand=True)

    def open_plot(self):
        if self.plot_window is not None and self.plot_window.winfo_exists():
            self.plot_window.deiconify()
            self.plot_window.lift()
            return
        try:
            from .plot_window import PlotWindow
        except ImportError as exc:
            messagebox.showerror("缺少绘图依赖", "请运行 python -m pip install -r requirements.txt，或使用打包版。\n" + str(exc), parent=self.root)
            return
        self.plot_window = PlotWindow(self.root)

    def browse(self):
        directory = filedialog.askdirectory(parent=self.root, title="选择采集保存目录")
        if directory:
            self.output.set(directory)

    def connect(self):
        if self.session and not self.session.wait(0):
            return
        try:
            if not self.output.get().strip():
                raise ValueError("请选择保存位置")
            queue_chunks = int(self.buffer.get()) * 4  # 256 KiB * 4 = 1 MiB
            config = CaptureConfig(self.host.get().strip(), int(self.port.get()), Path(self.output.get()),
                                   queue_chunks=queue_chunks)
            self.session = CaptureSession(config)
            self.session.start()
        except (ValueError, OSError) as exc:
            messagebox.showerror("无法连接", str(exc), parent=self.root); return
        self.meter = RateMeter(self.session.started_clock)
        self.capture_meter = None
        self.last_sample = self.session.started_clock
        self.last_capture_sample = 0.0
        self.last_preview = None; self.last_events = []
        for variable in self.values.values(): variable.set("—")
        self.capture_path.set(str(self.session.directory))
        self._set_active(True)
        self.state.set("正在连接…")

    def _set_active(self, active):
        for widget in self.config_widgets:
            widget.configure(state="disabled" if active else ("readonly" if widget is self.buffer_entry else "normal"))
        self.connect_button.configure(state="disabled" if active else "normal")
        self.stop_button.configure(state="normal" if active else "disabled")

    def stop(self):
        if self.session:
            self.session.stop()
            self.notice.set("正在断开。若 GET 尚未收满，本次文件会标记 complete=false。")

    def quick(self, command):
        try:
            if not self.session: raise RuntimeError("请先连接 STM32")
            self.session.send_text(command)
        except (ValueError, RuntimeError) as exc:
            messagebox.showerror("未发送", str(exc), parent=self.root)

    def auto_capture(self):
        try:
            if not self.session: raise RuntimeError("请先连接 STM32")
            ms = int(self.capture_ms.get())
            self.session.start_capture(ms)
            self.capture_meter = RateMeter(self.session.snapshot()["clock"])
            self.last_capture_sample = self.session.snapshot()["clock"]
            expected = ms * ASCII_BYTES_PER_MS
            self.notice.set("%d ms：期望 GET 数据 %d 字节（%.2f MB ASCII HEX）" % (ms, expected, expected / 1e6))
        except (ValueError, RuntimeError) as exc:
            messagebox.showerror("无法开始采集", str(exc), parent=self.root)

    def send(self):
        try:
            payload = encode_command(self.command_text.get("1.0", "end-1c"), self.mode.get(), self.ending.get())
            if not self.session: raise RuntimeError("请先连接设备")
            self.session.send(payload)
        except (ValueError, RuntimeError) as exc:
            messagebox.showerror("未发送", str(exc), parent=self.root)

    @staticmethod
    def _replace(widget, text):
        widget.configure(state="normal"); widget.delete("1.0", "end"); widget.insert("1.0", text); widget.configure(state="disabled")

    @staticmethod
    def _fmt_eta(seconds):
        if seconds is None or seconds < 0 or seconds > 24 * 3600:
            return "—"
        seconds = int(seconds)
        return "%02d:%02d:%02d" % (seconds // 3600, seconds // 60 % 60, seconds % 60)

    def refresh(self):
        if self.session:
            snap = self.session.snapshot(); done = self.session.wait(0)
            label = STATE_NAMES.get(snap["state"], snap["state"])
            seconds = int(snap["elapsed"])
            self.state.set("%s · %02d:%02d:%02d · 协议状态 %s%s" % (
                label, seconds // 3600, seconds // 60 % 60, seconds % 60, snap["protocol_state"],
                (" · " + snap["error"]) if snap["error"] else ""))
            self.values["rx"].set("%.2f MB" % (snap["rx_bytes"] / 1e6))
            self.values["tx"].set("%d B" % snap["tx_bytes"])
            if snap["clock"] - self.last_sample >= 1 or (done and snap["clock"] > self.last_sample):
                rates = self.meter.sample(snap["clock"], snap["rx_bytes"])
                self.last_sample = snap["clock"]
                self.values["speed"].set("%.2f MB/s\n%.1f Mbps" % (rates["instant"] / 1e6, rates["instant"] * 8 / 1e6))

            exp = snap["capture_expected_bytes"]; got = snap["capture_received_bytes"]
            self.values["capture"].set("%.3f / %.3f MB" % (got / 1e6, exp / 1e6) if exp else "—")
            self.values["progress"].set("%.2f %%" % (snap["capture_progress"] * 100) if exp else "—")
            self.values["pending"].set("%.2f / %.0f MiB" % (
                snap["capture_pending_bytes"] / 1048576, snap["capture_buffer_bytes"] / 1048576))
            if exp and snap["protocol_state"] in ("capture", "await_end"):
                if self.capture_meter is None:
                    self.capture_meter = RateMeter(snap["clock"])
                    self.last_capture_sample = snap["clock"]
                if snap["clock"] - self.last_capture_sample >= 1:
                    cr = self.capture_meter.sample(snap["clock"], got)
                    self.last_capture_sample = snap["clock"]
                    speed = cr["instant"]
                    self.values["cap_speed"].set("%.2f MB/s" % (speed / 1e6))
                    self.values["eta"].set(self._fmt_eta((exp - got) / speed if speed > 0 else None))
            elif exp and snap["capture_complete"]:
                elapsed = max(snap["capture_elapsed"], 1e-9)
                self.values["cap_speed"].set("%.2f MB/s avg" % (got / elapsed / 1e6))
                self.values["eta"].set("完成")
            elif exp and snap["capture_error"]:
                self.values["eta"].set("失败")

            self.last_reply.set(snap["last_reply"] or "—")
            if snap["capture_path"]:
                self.capture_path.set(snap["capture_path"])
            busy = snap["protocol_state"] != "idle"
            can_send = snap["state"] == "receiving" and not busy
            self.send_button.configure(state="normal" if can_send else "disabled")
            self.capture_button.configure(state="normal" if can_send else "disabled")
            self.ms_entry.configure(state="normal" if can_send else "disabled")
            for button in self.quick_buttons:
                button.configure(state="normal" if can_send else "disabled")

            current_preview = snap["preview"] if self.preview_enabled.get() else b""
            if current_preview != self.last_preview:
                self._replace(self.preview_text, current_preview.hex(" ").upper()); self.last_preview = current_preview
            events = self.session.events()
            if events != self.last_events:
                self._replace(self.events_text, "\n".join(e["time"] + "  " + e["message"] for e in events))
                self.events_text.see("end"); self.last_events = events
            if done:
                self._set_active(False)
                if self.closing:
                    self.root.destroy(); return
        self.after(200, self.refresh)

    def on_close(self):
        if self.session and not self.session.wait(0):
            if not messagebox.askyesno("结束", "断开连接并完成当前已收到数据的保存后退出？", parent=self.root):
                return
            self.closing = True; self.stop(); self.state.set("正在保存并退出…")
        else:
            self.root.destroy()


def main():
    root = tk.Tk(); App(root); root.mainloop()


if __name__ == "__main__":
    main()
