"""Offline voltage/current plotting popup; does not access the acquisition socket."""
import math
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from .recording import ParseCancelled, SAMPLE_RATE_HZ, load_recording, make_view
from .v26_protocol import reason_text


class PlotWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title('离线数据解析与绘图 · 电压 / 电流')
        self.geometry('1120x820')
        self.minsize(850, 650)
        self.recording = None
        self.current_view = None
        self.busy = False
        self.closed = False
        self._updating = False
        self._zoom_id = None
        self._poll_id = None
        self._cancel = threading.Event()
        self._messages = queue.SimpleQueue()
        self.path = tk.StringVar()
        self.status = tk.StringVar(value='请选择已经记录完成的 .hex 文件；原文件不会被修改。')
        self.details = tk.StringVar(value='每组 8 个 HEX 字符：电压 2 字节 + 电流 2 字节，大端、无符号。')
        self.start_index = tk.StringVar(value='0')
        self.stop_index = tk.StringVar()
        self.protocol('WM_DELETE_WINDOW', self.close)
        self._build()
        self._poll_id = self.after(100, self._poll)

    def _build(self):
        container = ttk.Frame(self, padding=14)
        container.pack(fill='both', expand=True)
        header = ttk.Frame(container)
        header.pack(fill='x')
        ttk.Label(header, text='离线波形', font=('Microsoft YaHei UI', 18, 'bold')).pack(side='left')
        ttk.Label(header, text='100 MHz / 通道 · 10 ns / 点').pack(side='right')
        file_row = ttk.Frame(container)
        file_row.pack(fill='x', pady=(12, 8))
        ttk.Entry(file_row, textvariable=self.path, state='readonly').pack(side='left', fill='x', expand=True)
        self.choose_button = ttk.Button(file_row, text='选择 HEX 文件', command=self.choose)
        self.choose_button.pack(side='left', padx=(8, 0))
        self.cancel_button = ttk.Button(file_row, text='取消解析', command=self.cancel, state='disabled')
        self.cancel_button.pack(side='left', padx=(8, 0))
        ttk.Label(container, textvariable=self.details, wraplength=1050).pack(anchor='w')
        ttk.Label(container, text='电压 V · 电流 A').pack(anchor='w', pady=(4, 8))
        self.progress = ttk.Progressbar(container, maximum=100)
        self.progress.pack(fill='x')
        ttk.Label(container, textvariable=self.status, wraplength=1050).pack(anchor='w', pady=6)
        limits = ttk.Frame(container)
        limits.pack(fill='x', pady=(0, 5))
        ttk.Label(limits, text='采样点范围 [起点, 终点)').pack(side='left')
        ttk.Entry(limits, textvariable=self.start_index, width=13).pack(side='left', padx=6)
        ttk.Entry(limits, textvariable=self.stop_index, width=13).pack(side='left', padx=6)
        self.range_button = ttk.Button(limits, text='显示范围', command=self.apply_range, state='disabled')
        self.range_button.pack(side='left', padx=4)
        self.full_button = ttk.Button(limits, text='全局概览', command=self.overview, state='disabled')
        self.full_button.pack(side='left', padx=4)
        self.fit_button = ttk.Button(limits, text='纵轴自适应', command=self.fit_y, state='disabled')
        self.fit_button.pack(side='left', padx=4)
        self.figure = Figure(figsize=(10, 5.5), dpi=100, facecolor='#ffffff')
        self.axes = self.figure.subplots(2, 1, sharex=True)
        self.figure.subplots_adjust(left=.095, right=.98, top=.96, bottom=.10, hspace=.18)
        colors = ('#1268b3', '#d56a13')
        self.lines = []
        self.trigger_lines = []
        for axis, color in zip(self.axes, colors):
            axis.set_facecolor('#f7f9fc')
            axis.grid(True, color='#dde3eb', linewidth=.6)
            axis.tick_params(labelsize=9)
            axis.ticklabel_format(axis='x', style='plain', useOffset=False)
            self.lines.append(axis.plot([], [], color=color, linewidth=.9)[0])
            self.trigger_lines.append(axis.axvline(0, color='#be3344', linestyle='--', linewidth=1, visible=False))
            axis.callbacks.connect('xlim_changed', self._on_xlim)
        self.axes[0].set_ylabel('Voltage (V)')
        self.axes[1].set_ylabel('Current (A)')
        self.axes[1].set_xlabel('Time (ms)')
        canvas_frame = ttk.Frame(container)
        canvas_frame.pack(fill='both', expand=True)
        self.canvas = FigureCanvasTkAgg(self.figure, master=canvas_frame)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
        toolbar_frame = ttk.Frame(container)
        toolbar_frame.pack(fill='x')
        self.toolbar = NavigationToolbar2Tk(self.canvas, toolbar_frame, pack_toolbar=False)
        self.toolbar.pack(fill='x')
        ttk.Label(container, text='工具栏支持缩放、平移和保存图片。大范围显示保留峰谷的抽稀曲线；放大后重新从原始数据取点。').pack(anchor='w')
        self.canvas.draw_idle()

    def choose(self):
        path = filedialog.askopenfilename(parent=self, title='选择已记录完成的 ADC HEX 文件',
                                         filetypes=[('ADC HEX', '*.hex'), ('所有文件', '*.*')])
        if path:
            self.load_path(path)

    def load_path(self, path):
        if self.busy or self.closed:
            return
        self._cancel = threading.Event()
        self.path.set(str(Path(path)))
        self.recording = None
        self.current_view = None
        for line in self.lines:
            line.set_data([], [])
        for line in self.trigger_lines:
            line.set_visible(False)
        self.canvas.draw_idle()
        self.status.set('正在读取 ASCII HEX 并解析电压、电流…')
        self.details.set('格式：每组 8 个 HEX 字符，大端无符号；采样率 100 MHz / 通道。')
        self.progress['value'] = 0
        self._set_busy(True)
        messages = self._messages
        cancellation = self._cancel

        def worker():
            try:
                def progress(done, total):
                    messages.put(('progress', done / max(total, 1) * 100))
                result = load_recording(path, cancel=cancellation, progress=progress)
                messages.put(('loaded', result))
            except ParseCancelled:
                messages.put(('cancelled', None))
            except Exception as exc:
                messages.put(('error', str(exc)))
        threading.Thread(target=worker, name='offline-hex-parser', daemon=True).start()

    def _set_busy(self, busy):
        self.busy = busy
        self.choose_button.configure(state='disabled' if busy else 'normal')
        self.cancel_button.configure(state='normal' if busy else 'disabled')
        enabled = self.recording is not None and not busy
        for button in (self.range_button, self.full_button, self.fit_button):
            button.configure(state='normal' if enabled else 'disabled')

    def cancel(self):
        self._cancel.set()
        self.status.set('正在取消解析…')

    def _poll(self):
        self._poll_id = None
        if self.closed:
            return
        while True:
            try:
                kind, value = self._messages.get_nowait()
            except queue.Empty:
                break
            if kind == 'progress':
                self.progress['value'] = value
            elif kind == 'loaded':
                if self._cancel.is_set():
                    self.status.set('已取消解析。')
                    self._set_busy(False)
                    continue
                self.recording = value
                self._set_busy(False)
                self.progress['value'] = 100
                count = len(value.samples)
                self.details.set('%s · 每通道 %s 点 · 记录时长 %.6f ms · 原始字节 %s B' % (
                    value.path.name, format(count, ','), count / SAMPLE_RATE_HZ * 1000,
                    format(count * 4, ',')))
                if value.trigger_index is not None:
                    suffix = '（触发点在记录末尾之后）' if value.trigger_index == count else ''
                    self.details.set(self.details.get() + ' · 触发位置 %s · %s%s' % (
                        format(value.trigger_index,','), reason_text(value.metadata['status'].get('REASON',0)),suffix))
                    self.axes[1].set_xlabel('Time relative to trigger (ms)')
                else:
                    self.details.set(self.details.get() + ' · 无触发元数据，时间从记录起点计算')
                    self.axes[1].set_xlabel('Time (ms)')
                for line in self.trigger_lines:
                    line.set_visible(value.trigger_index is not None)
                self.overview()
            elif kind == 'cancelled':
                self._set_busy(False)
                self.status.set('已取消解析；原文件未修改。')
            elif kind == 'error':
                self._set_busy(False)
                self.status.set('解析失败：' + value)
        self._poll_id = self.after(100, self._poll)

    def _show(self, start, stop, reset_limits):
        self.current_view = make_view(self.recording, start=start, stop=stop)
        view = self.current_view
        self._updating = True
        try:
            self.lines[0].set_data(view.time_ms, view.voltage)
            self.lines[1].set_data(view.time_ms, view.current)
            if reset_limits:
                origin = self.recording.trigger_index or 0
                rate = self.recording.sample_rate_hz
                left = (start-origin) / rate * 1000
                right = (stop - 1-origin) / rate * 1000
                if right <= left:
                    left -= .5 / rate * 1000
                    right += .5 / rate * 1000
                self.axes[0].set_xlim(left, right)
                self.fit_y()
                self.toolbar.update()
                self.toolbar.push_current()
            self.start_index.set(str(start))
            self.stop_index.set(str(stop))
            count = stop - start
            mode = '全部采样点' if len(view.indices) == count else '保留峰谷的抽稀概览'
            self.status.set('解析完成 · 当前范围 %s 点，绘制 %s 点（%s）' % (
                format(count, ','), format(len(view.indices), ','), mode))
            self.canvas.draw_idle()
        finally:
            self._updating = False

    def overview(self):
        if self.recording is not None and not self.busy:
            self._show(0, len(self.recording.samples), True)

    def apply_range(self):
        if self.recording is None or self.busy:
            return
        try:
            self._show(int(self.start_index.get()), int(self.stop_index.get()), True)
        except ValueError as exc:
            self.status.set('范围无效：' + str(exc))

    def fit_y(self):
        if self.current_view is None:
            return
        for axis, values in zip(self.axes, (self.current_view.voltage, self.current_view.current)):
            bottom, top = float(np.min(values)), float(np.max(values))
            pad = max((top - bottom) * .08, .01 if axis is self.axes[0] else 1.0)
            axis.set_ylim(bottom - pad, top + pad)
        self.canvas.draw_idle()

    def _on_xlim(self, axis):
        if self._updating or self.closed or self.busy or self.recording is None:
            return
        if self._zoom_id is not None:
            self.after_cancel(self._zoom_id)
        self._zoom_id = self.after(150, self._refresh_zoom)

    def _refresh_zoom(self):
        self._zoom_id = None
        if self.closed or self.busy or self.recording is None:
            return
        left, right = sorted(self.axes[0].get_xlim())
        count = len(self.recording.samples)
        origin = self.recording.trigger_index or 0
        rate = self.recording.sample_rate_hz
        start = max(0, min(count - 1, math.floor(left * rate / 1000 + origin)))
        stop = max(start + 1, min(count, math.ceil(right * rate / 1000 + origin) + 1))
        self._show(start, stop, False)

    def close(self):
        self.closed = True
        self._cancel.set()
        # The worker owns its original queue until it exits. Detach it so a
        # completed or late result cannot remain attached to a closed popup.
        self._messages = queue.SimpleQueue()
        for token in (self._poll_id, self._zoom_id):
            if token is not None:
                self.after_cancel(token)
        self.recording = None
        self.current_view = None
        self.destroy()
