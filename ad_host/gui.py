"""Small Tkinter UI. All socket and disk operations stay off the UI thread."""
from pathlib import Path
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .commands import encode_command
from .core import CaptureConfig, CaptureSession, RateMeter


STATE_NAMES = {
    "new": "未连接", "connecting": "正在连接", "receiving": "正在接收并保存",
    "stopping": "正在断开", "finishing": "正在完成文件保存",
    "finished": "已结束", "failed": "发生错误",
}


class App(ttk.Frame):
    def __init__(self, root):
        super().__init__(root, padding=18)
        self.root = root
        self.pack(fill="both", expand=True)
        self.session = None
        self.meter = None
        self.closing = False
        self.last_events = []
        self.last_preview = None
        self.last_sample = 0
        self.host = tk.StringVar(value="192.168.1.10")
        self.port = tk.StringVar(value="5000")
        self.output = tk.StringVar(value=str(Path.home() / "Documents" / "AD-HOST" / "captures"))
        self.roll = tk.StringVar(value="1024")
        self.buffer = tk.StringVar(value="64")
        self.mode = tk.StringVar(value="HEX")
        self.ending = tk.StringVar(value="NONE")
        self.preview_enabled = tk.BooleanVar(value=True)
        self.state = tk.StringVar(value="未连接 · 输入 STM32 地址后，连接即开始保存")
        self.notice = tk.StringVar(value="发送内容与接收内容共用同一条 TCP 连接；不会自动生成校验码。")
        self.capture_path = tk.StringVar(value="尚未开始采集")
        self.values = {key: tk.StringVar(value="—") for key in
                       ("speed", "recent", "average", "peak", "rx", "written", "pending", "tx")}
        root.title("AD-HOST · TCP 数据采集")
        root.geometry("1050x860")
        root.minsize(860, 760)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        style = ttk.Style(root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TLabel", font=("Microsoft YaHei UI", 10))
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 20, "bold"))
        style.configure("Value.TLabel", font=("Segoe UI", 16, "bold"))
        self.columnconfigure(0, weight=1)
        self._build()
        self.after(200, self.refresh)

    def _build(self):
        ttk.Label(self, text="AD-HOST", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(self, text="TCP 接收 · 原始数据保存 · 传输测速 · 指令发送").grid(
            row=1, column=0, sticky="w", pady=(0, 10))
        box = ttk.LabelFrame(self, text="连接与保存", padding=10)
        box.grid(row=2, column=0, sticky="ew")
        box.columnconfigure(1, weight=1)
        ttk.Label(box, text="STM32 IP").grid(row=0, column=0, sticky="w")
        self.host_entry = ttk.Entry(box, textvariable=self.host, width=25)
        self.host_entry.grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Label(box, text="端口").grid(row=0, column=2)
        self.port_entry = ttk.Entry(box, textvariable=self.port, width=8)
        self.port_entry.grid(row=0, column=3, padx=8)
        self.connect_button = ttk.Button(box, text="连接并开始保存", command=self.connect)
        self.connect_button.grid(row=0, column=4, padx=4)
        self.stop_button = ttk.Button(box, text="断开并完成保存", command=self.stop, state="disabled")
        self.stop_button.grid(row=0, column=5, padx=4)
        ttk.Label(box, text="保存位置").grid(row=1, column=0, sticky="w", pady=8)
        self.output_entry = ttk.Entry(box, textvariable=self.output)
        self.output_entry.grid(row=1, column=1, columnspan=4, sticky="ew", padx=8)
        self.browse_button = ttk.Button(box, text="选择文件夹", command=self.browse)
        self.browse_button.grid(row=1, column=5)
        options = ttk.Frame(box)
        options.grid(row=2, column=0, columnspan=6, sticky="w")
        ttk.Label(options, text="文件分卷 MiB").pack(side="left")
        self.roll_entry = ttk.Combobox(options, textvariable=self.roll, values=("256", "1024", "4096"),
                                      width=8, state="readonly")
        self.roll_entry.pack(side="left", padx=(8, 18))
        ttk.Label(options, text="接收队列 MiB").pack(side="left")
        self.buffer_entry = ttk.Combobox(options, textvariable=self.buffer, values=("16", "64", "256"),
                                        width=8, state="readonly")
        self.buffer_entry.pack(side="left", padx=8)
        self.config_widgets = [self.host_entry, self.port_entry, self.output_entry, self.browse_button]
        ttk.Label(self, textvariable=self.state).grid(row=3, column=0, sticky="w", pady=(10, 4))
        metrics = ttk.Frame(self)
        metrics.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        labels = [("speed", "当前速度 / Mbps"), ("recent", "近 10 秒平均"),
                  ("average", "本次平均"), ("peak", "最高采样区间速度"),
                  ("rx", "累计接收"), ("written", "累计写入"),
                  ("pending", "待写入 / 队列容量"), ("tx", "已提交发送")]
        for i, (key, label) in enumerate(labels):
            card = ttk.LabelFrame(metrics, text=label, padding=8)
            card.grid(row=i // 4, column=i % 4, sticky="nsew", padx=3, pady=3)
            ttk.Label(card, textvariable=self.values[key], style="Value.TLabel").pack(anchor="w")
            metrics.columnconfigure(i % 4, weight=1)
        path_box = ttk.Entry(self, textvariable=self.capture_path, state="readonly")
        path_box.grid(row=5, column=0, sticky="ew", pady=(0, 8))
        commands = ttk.LabelFrame(self, text="发送 TCP 指令", padding=10)
        commands.grid(row=6, column=0, sticky="ew")
        commands.columnconfigure(0, weight=1)
        toolbar = ttk.Frame(commands)
        toolbar.grid(row=0, column=0, sticky="w")
        ttk.Label(toolbar, text="格式").pack(side="left")
        ttk.Combobox(toolbar, textvariable=self.mode, values=("HEX", "UTF-8"),
                     state="readonly", width=8).pack(side="left", padx=8)
        ttk.Label(toolbar, text="追加结束符").pack(side="left")
        ttk.Combobox(toolbar, textvariable=self.ending, values=("NONE", "LF", "CR", "CRLF"),
                     state="readonly", width=8).pack(side="left", padx=8)
        ttk.Label(toolbar, text="HEX 示例：AA 55 01 FF；NONE 表示不追加").pack(side="left")
        self.command_text = tk.Text(commands, height=2, wrap="word", font=("Consolas", 11))
        self.command_text.grid(row=1, column=0, sticky="ew", pady=8)
        self.send_button = ttk.Button(commands, text="发送指令", command=self.send, state="disabled")
        self.send_button.grid(row=1, column=1, padx=(10, 0))
        ttk.Label(commands, textvariable=self.notice, wraplength=880).grid(
            row=2, column=0, columnspan=2, sticky="w")
        preview = ttk.LabelFrame(self, text="接收预览（最多 256 字节，非完整数据帧）", padding=8)
        preview.grid(row=7, column=0, sticky="ew", pady=8)
        ttk.Checkbutton(preview, text="显示最新数据片段", variable=self.preview_enabled).pack(anchor="w")
        self.preview_text = tk.Text(preview, height=4, wrap="word", state="disabled",
                                    font=("Consolas", 10), background="#f3f6f9")
        self.preview_text.pack(fill="x", pady=(5, 0))
        events = ttk.LabelFrame(self, text="状态与异常（不逐包记录）", padding=8)
        events.grid(row=8, column=0, sticky="nsew")
        self.rowconfigure(8, weight=1)
        self.events_text = tk.Text(events, height=5, wrap="word", state="disabled", font=("Microsoft YaHei UI", 9))
        self.events_text.pack(fill="both", expand=True)

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
            config = CaptureConfig(
                self.host.get().strip(), int(self.port.get()), Path(self.output.get()),
                queue_chunks=int(self.buffer.get()) * 4,
                roll_bytes=int(self.roll.get()) * 1024 * 1024,
            )
            self.session = CaptureSession(config)
            self.session.start()
        except (ValueError, OSError) as exc:
            messagebox.showerror("无法开始采集", str(exc), parent=self.root)
            return
        self.meter = RateMeter(self.session.started_clock)
        self.last_sample = self.session.started_clock
        self.last_preview = None
        self.last_events = []
        for variable in self.values.values():
            variable.set("—")
        self.capture_path.set(str(self.session.directory))
        self._set_active(True)
        self.state.set("正在连接…")

    def _set_active(self, active):
        for widget in self.config_widgets:
            widget.configure(state="disabled" if active else "normal")
        for widget in (self.roll_entry, self.buffer_entry):
            widget.configure(state="disabled" if active else "readonly")
        self.connect_button.configure(state="disabled" if active else "normal")
        self.stop_button.configure(state="normal" if active else "disabled")

    def stop(self):
        if self.session:
            self.session.stop()
            self.notice.set("正在断开并保存已收到的数据。设备尚未传到电脑的数据可能未采集。")

    def send(self):
        try:
            payload = encode_command(self.command_text.get("1.0", "end-1c"), self.mode.get(), self.ending.get())
            if not self.session:
                raise RuntimeError("请先连接设备")
            self.session.send(payload)
        except (ValueError, RuntimeError) as exc:
            messagebox.showerror("未发送", str(exc), parent=self.root)
            return
        self.notice.set("已排队：%d 字节。发送结果见状态记录；设备执行结果须根据协议回复确认。" % len(payload))

    @staticmethod
    def _replace(widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def refresh(self):
        if self.session:
            snap = self.session.snapshot()
            done = self.session.wait(0)
            label = STATE_NAMES.get(snap["state"], snap["state"])
            seconds = int(snap["elapsed"])
            self.state.set("%s · %02d:%02d:%02d%s" % (
                label, seconds // 3600, seconds // 60 % 60, seconds % 60,
                (" · " + snap["error"]) if snap["error"] else ""))
            self.values["rx"].set("%.2f MiB" % (snap["rx_bytes"] / 1048576))
            self.values["written"].set("%.2f MiB" % (snap["written_bytes"] / 1048576))
            self.values["pending"].set("%.1f / %.0f MiB" % (
                snap["pending_bytes"] / 1048576, snap["buffer_bytes"] / 1048576))
            self.values["tx"].set("%d B" % snap["tx_bytes"])
            if snap["clock"] - self.last_sample >= 1 or (done and snap["clock"] > self.last_sample):
                rates = self.meter.sample(snap["clock"], snap["rx_bytes"])
                self.last_sample = snap["clock"]
                self.values["speed"].set("%.2f MB/s · %.1f" % (rates["instant"] / 1e6, rates["instant"] * 8 / 1e6))
                for field, rate in (("recent", "recent"), ("average", "average"), ("peak", "peak")):
                    self.values[field].set("%.2f MB/s" % (rates[rate] / 1e6))
            self.send_button.configure(state="normal" if snap["state"] == "receiving" else "disabled")
            current_preview = snap["preview"] if self.preview_enabled.get() else b""
            if current_preview != self.last_preview:
                self._replace(self.preview_text, current_preview.hex(" ").upper())
                self.last_preview = current_preview
            events = self.session.events()
            if events != self.last_events:
                self._replace(self.events_text, "\n".join(e["time"] + "  " + e["message"] for e in events))
                self.events_text.see("end")
                self.last_events = events
            if done:
                self._set_active(False)
                if self.closing:
                    self.root.destroy()
                    return
        self.after(200, self.refresh)

    def on_close(self):
        if self.session and not self.session.wait(0):
            if not messagebox.askyesno("结束采集", "断开连接并等待已收到的数据保存完成后退出？", parent=self.root):
                return
            self.closing = True
            self.stop()
            self.state.set("正在保存剩余数据，完成后自动退出…")
        else:
            self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
