"""V26 desktop controls: explicit preparation, trigger, readout and recovery."""
from pathlib import Path
import json
import time
import tkinter as tk
from tkinter import filedialog,messagebox,ttk

from .core import CaptureConfig,RateMeter
from .v26_protocol import AcquisitionSettings,COMPARISONS,reason_text
from .v26_session import V26Session


class App(ttk.Frame):
    def __init__(self,root):
        super().__init__(root,padding=14);self.pack(fill='both',expand=True);self.root=root
        self.session=None;self.plot_window=None;self.meter=None;self.closing=False;self._last_sample=0
        self._last_text='';self._after=None
        root.title('AD-HOST V26 · 触发采集与波形分析 0.4.1');root.geometry('1160x850');root.minsize(980,750)
        root.protocol('WM_DELETE_WINDOW',self.on_close)
        style=ttk.Style(root)
        if 'clam' in style.theme_names():style.theme_use('clam')
        style.configure('TLabel',font=('Microsoft YaHei UI',10))
        style.configure('Title.TLabel',font=('Microsoft YaHei UI',18,'bold'))
        self.host=tk.StringVar(value='192.168.3.178');self.port=tk.StringVar(value='11235')
        self.output=tk.StringVar(value=str(Path.home()/'Documents'/'AD-HOST'/'captures'))
        self.buffer=tk.StringVar(value='64');self.timeout=tk.StringVar(value='30')
        self.len_mode=tk.StringVar(value='采样时间 ms');self.length=tk.StringVar(value='10')
        self.pre=tk.StringVar(value='30');self.mode=tk.StringVar(value='手动触发')
        self.vth=tk.StringVar(value='2048');self.ith=tk.StringVar(value='2048')
        self.vcmp=tk.StringVar(value='≥');self.icmp=tk.StringVar(value='<')
        self.enable_v=tk.BooleanVar(value=True);self.enable_i=tk.BooleanVar(value=True)
        self.gap=tk.StringVar(value='1000');self.repeat=tk.BooleanVar(value=False)
        self.estimate=tk.StringVar();self.state=tk.StringVar(value='未连接')
        self.notice=tk.StringVar(value='准备采集后，手动模式需点击“手动触发”；自动模式等待阈值条件。')
        self.metrics=tk.StringVar(value='尚未接收记录');self.path=tk.StringVar(value='尚无已保存记录')
        self.trigger=tk.StringVar(value='尚未触发');self.command=tk.StringVar(value='TST')
        self.config_widgets=[];self.connection_widgets=[]
        self._build()
        for variable in (self.len_mode,self.length,self.pre,self.vth,self.mode):variable.trace_add('write',self._estimate)
        self._estimate();self._after=self.after(100,self.refresh)

    def _field(self,parent,label,var,row,col,width=12,values=None,group=None):
        ttk.Label(parent,text=label).grid(row=row,column=col,sticky='w',padx=5,pady=5)
        widget=ttk.Combobox(parent,textvariable=var,values=values,state='readonly',width=width) if values else ttk.Entry(parent,textvariable=var,width=width)
        widget.grid(row=row,column=col+1,sticky='ew',padx=5,pady=5)
        if group is not None:group.append((widget,'readonly' if values else 'normal'))
        return widget

    def _build(self):
        header=ttk.Frame(self);header.pack(fill='x')
        ttk.Label(header,text='AD-HOST  /  V26',style='Title.TLabel').pack(side='left')
        ttk.Label(header,text='双通道 100 MSPS · 12 位 · 单次阈值 / 手动触发').pack(side='right')
        connection=ttk.LabelFrame(self,text='设备连接',padding=8);connection.pack(fill='x',pady=(10,8))
        self._field(connection,'IP',self.host,0,0,22,group=self.connection_widgets)
        self._field(connection,'端口',self.port,0,2,8,group=self.connection_widgets)
        self.connect_button=ttk.Button(connection,text='连接',command=self.connect);self.connect_button.grid(row=0,column=4,padx=6)
        self.disconnect_button=ttk.Button(connection,text='断开',command=self.disconnect,state='disabled');self.disconnect_button.grid(row=0,column=5,padx=6)
        ttk.Label(connection,text='保存到').grid(row=1,column=0,sticky='w',padx=5)
        output=ttk.Entry(connection,textvariable=self.output);output.grid(row=1,column=1,columnspan=4,sticky='ew',padx=5)
        browse=ttk.Button(connection,text='选择目录',command=self.browse);browse.grid(row=1,column=5,padx=6)
        self.connection_widgets.extend(((output,'normal'),(browse,'normal')));connection.columnconfigure(1,weight=1)
        tabs=ttk.Notebook(self);tabs.pack(fill='both',expand=True)
        acquire=ttk.Frame(tabs,padding=12);records=ttk.Frame(tabs,padding=12);diagnostic=ttk.Frame(tabs,padding=12)
        tabs.add(acquire,text='采集与触发');tabs.add(records,text='记录与波形');tabs.add(diagnostic,text='设备诊断')
        length=ttk.LabelFrame(acquire,text='记录窗口（含前触发和后触发）',padding=8);length.pack(fill='x')
        self._field(length,'按',self.len_mode,0,0,16,('采样时间 ms','采样点数'),self.config_widgets)
        self._field(length,'长度',self.length,0,2,14,group=self.config_widgets)
        self._field(length,'前触发 %',self.pre,0,4,8,group=self.config_widgets)
        ttk.Label(length,textvariable=self.estimate,wraplength=1000).grid(row=1,column=0,columnspan=6,sticky='w',padx=5,pady=6)
        conditions=ttk.LabelFrame(acquire,text='触发设置',padding=8);conditions.pack(fill='x',pady=8)
        self._field(conditions,'模式',self.mode,0,0,16,('手动触发','自动阈值触发'),self.config_widgets)
        ttk.Label(conditions,text='两路条件为“或”；手动模式忽略阈值。').grid(row=0,column=2,columnspan=4,sticky='w',padx=12)
        for row,label,enabled,cmpvar,threshold in ((1,'电压 A',self.enable_v,self.vcmp,self.vth),(2,'电流 B',self.enable_i,self.icmp,self.ith)):
            check=ttk.Checkbutton(conditions,text=label+' 参与触发',variable=enabled);check.grid(row=row,column=0,columnspan=2,sticky='w',padx=5)
            self.config_widgets.append((check,'normal'))
            self._field(conditions,'比较',cmpvar,row,2,7,COMPARISONS,self.config_widgets)
            self._field(conditions,'阈值 ADC 码',threshold,row,4,10,group=self.config_widgets)
        ttk.Label(conditions,text='阈值范围 0–4095。相等无容差；当前值比较，无边沿/迟滞，也不会等待超时后强制触发。',wraplength=1000).grid(row=3,column=0,columnspan=6,sticky='w',padx=5,pady=7)
        repeatbox=ttk.Frame(acquire);repeatbox.pack(fill='x')
        repeat=ttk.Checkbutton(repeatbox,text='重复自动记录',variable=self.repeat);repeat.grid(row=0,column=0,padx=5);self.config_widgets.append((repeat,'normal'))
        self._field(repeatbox,'组间隔 ms',self.gap,0,1,10,group=self.config_widgets)
        ttk.Label(repeatbox,text='间隔由设备从上一组释放完成时计时；默认单次。').grid(row=0,column=3,sticky='w',padx=5)
        actions=ttk.Frame(acquire);actions.pack(fill='x',pady=12)
        self.apply_button=ttk.Button(actions,text='应用配置',command=lambda:self.action('configure'));self.apply_button.pack(side='left',padx=3)
        self.start_button=ttk.Button(actions,text='准备采集',command=self.begin_capture);self.start_button.pack(side='left',padx=3)
        self.force_button=ttk.Button(actions,text='手动触发',command=lambda:self.action('force'));self.force_button.pack(side='left',padx=3)
        self.cancel_button=ttk.Button(actions,text='取消当前采集',command=lambda:self.action('cancel'));self.cancel_button.pack(side='left',padx=3)
        self.stop_repeat_button=ttk.Button(actions,text='停止后续记录',command=lambda:self.action('stop_repeat'));self.stop_repeat_button.pack(side='left',padx=3)
        self.buttons=[self.apply_button,self.start_button,self.force_button,self.cancel_button,self.stop_repeat_button]
        ttk.Label(acquire,textvariable=self.notice,wraplength=1000).pack(anchor='w',pady=5)
        ttk.Label(acquire,textvariable=self.trigger).pack(anchor='w',pady=5)
        ttk.Label(acquire,textvariable=self.metrics,wraplength=1000).pack(anchor='w',pady=8)
        self.progress=ttk.Progressbar(acquire,maximum=100);self.progress.pack(fill='x',pady=5)
        ttk.Label(records,text='每条记录保存为 HEX + JSON。请一起保留，以恢复触发位置和采集参数。',wraplength=1000).pack(anchor='w',pady=8)
        ttk.Entry(records,textvariable=self.path,state='readonly').pack(fill='x',pady=8)
        row=ttk.Frame(records);row.pack(fill='x',pady=8)
        ttk.Button(row,text='选择 HEX / 绘图',command=self.open_plot).pack(side='left',padx=5)
        self.latest_button=ttk.Button(row,text='打开最近记录',command=self.open_latest,state='disabled');self.latest_button.pack(side='left',padx=5)
        self.read_button=ttk.Button(row,text='读取设备已有记录',command=lambda:self.action('read'));self.read_button.pack(side='left',padx=5)
        self.release_button=ttk.Button(row,text='丢弃设备已有记录',command=lambda:self.action('release'));self.release_button.pack(side='left',padx=5)
        self.buttons.extend((self.read_button,self.release_button))
        ttk.Label(records,text='电压 V · 电流 A（按探头倍率换算）。\nV26 记录以触发为 t=0；100% 前触发不包含触发样本。\n大范围显示峰谷概览，放大后恢复原始点；不完整的 .partial.hex 不作为成功波形打开。',wraplength=1000).pack(anchor='w',pady=12)
        advanced=ttk.LabelFrame(diagnostic,text='连接参数（连接前设置）',padding=6);advanced.pack(fill='x')
        self._field(advanced,'写盘缓冲 MiB',self.buffer,0,0,8,('16','64','256'),self.connection_widgets)
        self._field(advanced,'GET 无进度超时 s',self.timeout,0,2,8,group=self.connection_widgets)
        ttk.Label(advanced,text='命令超时 5 s；触发等待不限时；Socket 请求缓冲 32 MiB。').grid(row=1,column=0,columnspan=4,sticky='w',padx=5)
        row=ttk.Frame(diagnostic);row.pack(fill='x',pady=8)
        self.query_buttons=[]
        for name in ('VER','FST','TST','FREG','CLEAR_EVENTS','FINIT'):
            button=ttk.Button(row,text=name,command=lambda n=name:self.send_command(n));button.pack(side='left',padx=3);self.query_buttons.append(button)
        commandrow=ttk.Frame(diagnostic);commandrow.pack(fill='x',pady=5)
        ttk.Entry(commandrow,textvariable=self.command).pack(side='left',fill='x',expand=True)
        self.send_button=ttk.Button(commandrow,text='发送单条指令',command=lambda:self.send_command(self.command.get()));self.send_button.pack(side='left',padx=6)
        ttk.Label(diagnostic,text='支持查询、CFG/ACQ 十参数及受状态约束的 ARM/FORCE/ABORT/GET/RELEASE；自动追加 CR。GET 中暂停全部命令。',wraplength=1000).pack(anchor='w')
        self.log=tk.Text(diagnostic,height=13,state='disabled',font=('Consolas',9),wrap='word');self.log.pack(fill='both',expand=True,pady=8)
        ttk.Separator(self).pack(fill='x',pady=8);ttk.Label(self,textvariable=self.state,font=('Microsoft YaHei UI',11,'bold')).pack(anchor='w')
        for button in self.buttons+self.query_buttons+[self.send_button]:button.configure(state='disabled')

    def settings(self):
        def integer(variable):
            value=variable.get().strip()
            if not value.isascii() or not value.isdecimal():raise ValueError('设置必须为无符号十进制整数')
            return int(value)
        return AcquisitionSettings(int(self.len_mode.get()=='采样点数'),integer(self.length),integer(self.pre),
                                   int(self.mode.get()=='自动阈值触发'),integer(self.vth),COMPARISONS.index(self.vcmp.get()),
                                   integer(self.ith),COMPARISONS.index(self.icmp.get()),int(self.enable_v.get())+2*int(self.enable_i.get()),integer(self.gap))

    def _estimate(self,*args):
        try:
            config=self.settings();n=config.samples;p=config.pre_samples
            self.estimate.set(f'每通道 {n:,} 点 · {n/100000:.6f} ms · HEX {n*8/1e6:.3f} MB · 前 {p:,} / 后 {n-p:,} 点（后 {100-config.pre}%）'+(' · 不含触发样本' if config.pre==100 else ''))
        except ValueError as exc:self.estimate.set(str(exc))

    def browse(self):
        directory=filedialog.askdirectory(parent=self.root)
        if directory:self.output.set(directory)

    def connect(self):
        if self.session is not None and not self.session.wait(0):return
        try:
            timeout=float(self.timeout.get())
            if not 1<=timeout<=600:raise ValueError('GET 无进度超时应为 1–600 秒')
            config=CaptureConfig(self.host.get().strip(),int(self.port.get()),Path(self.output.get()),queue_chunks=int(self.buffer.get()))
            self.session=V26Session(config,progress_timeout=timeout);self.session.start()
            self.meter=RateMeter(time.monotonic());self.notice.set('正在读取版本信息与采集状态…')
        except (ValueError,OSError) as exc:messagebox.showerror('连接设置',str(exc),parent=self.root)

    def disconnect(self):
        if self.session:self.session.stop()

    def action(self,name):
        try:
            if self.session is None:raise ValueError('请先连接设备')
            config=self.settings() if name in ('configure','start') else None
            self.session.submit(name,config,repeat=self.repeat.get() if name=='start' else False)
            self.notice.set('操作已提交；等待设备回复。')
        except (ValueError,RuntimeError) as exc:messagebox.showerror('操作未执行',str(exc),parent=self.root)

    def begin_capture(self):self.action('start')

    def send_command(self,text):
        try:
            if self.session is None:raise ValueError('请先连接设备')
            self.session.submit_command(text)
        except (ValueError,RuntimeError) as exc:messagebox.showerror('指令未执行',str(exc),parent=self.root)

    def open_plot(self):
        if self.plot_window is not None and self.plot_window.winfo_exists():
            self.plot_window.deiconify();self.plot_window.lift();return
        try:
            from .plot_window import PlotWindow
            self.plot_window=PlotWindow(self.root)
        except ImportError as exc:messagebox.showerror('缺少绘图依赖','请安装 requirements.txt 或使用便携版。\n'+str(exc),parent=self.root)

    def open_latest(self):
        if not self.session or not self.session.snapshot()['last_path']:return
        self.open_plot()
        if self.plot_window is not None:self.plot_window.load_path(self.session.snapshot()['last_path'])

    def refresh(self):
        if self._after is not None:
            self.after_cancel(self._after);self._after=None
        snap=self.session.snapshot() if self.session else None
        alive=self.session is not None and not self.session.wait(0)
        self.connect_button.configure(state='disabled' if alive else 'normal')
        self.disconnect_button.configure(state='normal' if alive else 'disabled')
        for widget,normal in self.connection_widgets:widget.configure(state='disabled' if alive else normal)
        if snap:
            self.state.set(f"{snap['state']} · {snap['phase']}")
            if snap['error']:self.notice.set(snap['error'])
            elif snap['state']=='connected':self.notice.set('已连接；版本严格检查已停用，按设备状态执行采集。')
            for button,key in ((self.apply_button,'can_start'),(self.start_button,'can_start'),(self.force_button,'can_force'),
                               (self.cancel_button,'can_cancel'),(self.read_button,'can_read'),(self.release_button,'can_release')):
                button.configure(state='normal' if snap[key] else 'disabled')
            self.stop_repeat_button.configure(state='normal' if snap['repeat'] else 'disabled')
            unlocked=not alive or snap['can_start']
            for widget,normal in self.config_widgets:widget.configure(state=normal if unlocked else 'disabled')
            query_ok=snap['state']=='connected' and not snap['busy'] and not snap['receiving']
            for button in self.query_buttons+[self.send_button]:button.configure(state='normal' if query_ok else 'disabled')
            now=time.monotonic()
            if now-self._last_sample>=1:
                rate=self.meter.sample(now,snap['rx_bytes'])['instant'] if self.meter else 0
                self.metrics.set(f"TCP {rate/1e6:.2f} MB/s · 本次已收 {snap['received']:,} / {snap['expected']:,} B · 已写 {snap['written']:,} B\n待写缓冲 {snap['pending']/1048576:.1f} / {snap['buffer_bytes']/1048576:.0f} MiB · 已完成 {snap['completed']} 条")
                self._last_sample=now
            self.progress['value']=snap['received']/max(1,snap['expected'])*100
            s=snap['status'];self.trigger.set(f"触发原因：{reason_text(s.get('REASON',0))} · 前触发位置 {s.get('ACTIVE_PRE','—')} · 组间隔剩余 {s.get('GAP_LEFT_MS','未知')} ms")
            if snap['last_path']:self.path.set(snap['last_path']);self.latest_button.configure(state='normal')
            text=json.dumps(snap['diagnostics'],ensure_ascii=False,indent=2)+'\n\n'+'\n'.join(e['time']+' '+e['message'] for e in self.session.events()[-40:])
            if text!=self._last_text:
                self.log.configure(state='normal');self.log.delete('1.0','end');self.log.insert('end',text);self.log.configure(state='disabled');self._last_text=text
        if self.closing and not alive:
            self.root.destroy();return
        self._after=self.after(100,self.refresh)

    def on_close(self):
        if self.plot_window is not None and self.plot_window.winfo_exists():self.plot_window.close()
        if self.session and not self.session.wait(0):
            self.closing=True;self.session.stop();self.notice.set('正在关闭连接并完成文件收尾…')
        else:
            if self._after:self.after_cancel(self._after)
            self.root.destroy()


def main():
    root=tk.Tk();App(root);root.mainloop()

if __name__=='__main__':main()
