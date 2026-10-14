"""Qt widgets and presentation only; commands are handled by controllers."""
from pathlib import Path
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QLineEdit,
                             QTabWidget,QCheckBox,QProgressBar,QTextEdit,QFileDialog,QScrollArea)
from .widgets.controls import button,card,spin,combo
from .widgets.theme import icon


class MainWindow(QMainWindow):
    connect_requested=pyqtSignal()
    disconnect_requested=pyqtSignal()
    action_requested=pyqtSignal(str)
    command_requested=pyqtSignal(str)
    plot_requested=pyqtSignal(bool)
    close_requested=pyqtSignal()
    settings_changed=pyqtSignal()

    def __init__(self):
        super().__init__();self.allow_close=False
        self.setWindowTitle('AD-HOST 0.5.0 · 采集与波形');self.setWindowIcon(icon('wave-square'))
        self.resize(1180,870);self.setMinimumSize(950,680)
        root=QWidget();self.setCentralWidget(root);layout=QVBoxLayout(root);layout.setContentsMargins(18,14,18,12)
        title=QLabel('AD-HOST  /  双通道采集');title.setProperty('cssClass','title');layout.addWidget(title)
        widget,box=card('设备连接');layout.addWidget(widget)
        row=QHBoxLayout();box.addLayout(row)
        self.host=QLineEdit('192.168.3.178');self.host.setMaximumWidth(210)
        self.port=spin(1,65535,11235)
        self.connect_button=button('连接','plug','primary');self.disconnect_button=button('断开','unlink')
        for item in (QLabel('IP 地址'),self.host,QLabel('端口'),self.port,self.connect_button,self.disconnect_button):row.addWidget(item)
        row.addStretch();self.state=QLabel('未连接');row.addWidget(self.state)
        row=QHBoxLayout();box.addLayout(row);row.addWidget(QLabel('保存目录'))
        self.output=QLineEdit(str(Path.home()/'Documents/AD-HOST/captures'));row.addWidget(self.output,1)
        self.browse_button=button('选择目录','folder-open');row.addWidget(self.browse_button)
        self.browse_button.clicked.connect(self.choose_directory)
        self.connect_button.clicked.connect(self.connect_requested.emit);self.disconnect_button.clicked.connect(self.disconnect_requested.emit)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        acquire,acq=self.page('采集与触发','sliders-h');records,rec=self.page('记录与波形','chart-line');diag,dia=self.page('设备诊断','stethoscope')
        self.connection_widgets=[self.host,self.port,self.output,self.browse_button]
        self.config_widgets=[];self.actions={};self.query_buttons=[]
        widget,box=card('记录窗口');acq.addWidget(widget);grid=QGridLayout();box.addLayout(grid)
        self.len_mode=combo(['采样时间 ms','采样点数']);self.length=spin(1,200,10);self.pre=spin(0,100,30,' %')
        for col,label,field in ((0,'长度方式',self.len_mode),(2,'长度',self.length),(4,'前触发',self.pre)):
            grid.addWidget(QLabel(label),0,col);grid.addWidget(field,0,col+1)
        self.config_widgets.extend([self.len_mode,self.length,self.pre])
        self.estimate=QLabel();self.estimate.setWordWrap(True);box.addWidget(self.estimate)
        widget,box=card('触发条件');acq.addWidget(widget);grid=QGridLayout();box.addLayout(grid)
        self.mode=combo(['手动触发','自动阈值触发']);grid.addWidget(QLabel('模式'),0,0);grid.addWidget(self.mode,0,1)
        hint=QLabel('两路为 OR：任一路满足条件即可触发');grid.addWidget(hint,0,2,1,4)
        self.enable_v=QCheckBox('电压 A');self.enable_v.setChecked(True)
        self.enable_i=QCheckBox('电流 B');self.enable_i.setChecked(True)
        self.vcmp=combo(['≥','>','=','≤','<']);self.icmp=combo(['≥','>','=','≤','<']);self.icmp.setCurrentIndex(4)
        self.vth=spin(0,4095,2500);self.ith=spin(0,4095,1500)
        for r,enabled,comparison,threshold in ((1,self.enable_v,self.vcmp,self.vth),(2,self.enable_i,self.icmp,self.ith)):
            grid.addWidget(enabled,r,0);grid.addWidget(comparison,r,1);grid.addWidget(QLabel('阈值 ADC'),r,2);grid.addWidget(threshold,r,3)
        self.config_widgets.extend([self.mode,self.enable_v,self.enable_i,self.vcmp,self.icmp,self.vth,self.ith])
        note=QLabel('电平比较，无边沿或超时强制触发。电流暂未标定，使用原始计数。');note.setWordWrap(True);box.addWidget(note)
        row=QHBoxLayout();acq.addLayout(row);self.repeat=QCheckBox('重复自动记录');self.gap=spin(0,600000,1000,' ms')
        row.addWidget(self.repeat);row.addWidget(QLabel('组间隔'));row.addWidget(self.gap);row.addStretch()
        self.config_widgets.extend([self.repeat,self.gap])
        row=QHBoxLayout();acq.addLayout(row)
        for action,text,glyph,css in [('configure','应用配置','check',None),('start','准备采集','play','success'),('force','手动触发','bolt','primary'),('cancel','取消当前采集','stop','danger'),('stop_repeat','停止后续记录','pause','warning')]:
            b=self.action_button(action,text,glyph,css);row.addWidget(b)
        self.trigger=QLabel('尚未触发');acq.addWidget(self.trigger)
        self.metrics=QLabel('尚未接收数据');self.metrics.setWordWrap(True);acq.addWidget(self.metrics)
        self.progress=QProgressBar();self.progress.setRange(0,1000);self.progress.setValue(0);self.progress.setFormat('%p%');acq.addWidget(self.progress);acq.addStretch()
        note=QLabel('每条记录保存为 HEX + JSON，请一起保留。波形窗口支持平移、缩放和双光标测量。');note.setWordWrap(True);rec.addWidget(note)
        self.path=QLineEdit();self.path.setReadOnly(True);self.path.setPlaceholderText('尚无已保存记录');rec.addWidget(self.path)
        row=QHBoxLayout();rec.addLayout(row)
        self.plot_button=button('选择 HEX / 波形查看','chart-line','primary');row.addWidget(self.plot_button)
        self.latest_button=button('打开最近记录','history');row.addWidget(self.latest_button);row.addStretch()
        self.plot_button.clicked.connect(lambda:self.plot_requested.emit(False));self.latest_button.clicked.connect(lambda:self.plot_requested.emit(True))
        row=QHBoxLayout();rec.addLayout(row)
        row.addWidget(self.action_button('read','读取设备已有记录','download'));row.addWidget(self.action_button('release','丢弃设备已有记录','trash-alt','danger'));row.addStretch()
        rec.addWidget(QLabel('电压按已确认公式换算为 V，电流显示原始计数。\n有记录元数据时以触发为 t=0；旧文件以记录起点计时。'));rec.addStretch()
        widget,box=card('连接参数');dia.addWidget(widget);row=QHBoxLayout();box.addLayout(row)
        self.buffer=combo(['16','64','256']);self.buffer.setCurrentText('64');self.timeout=spin(1,600,30,' s')
        row.addWidget(QLabel('写盘缓冲 MiB'));row.addWidget(self.buffer);row.addWidget(QLabel('无进度超时'));row.addWidget(self.timeout);row.addStretch()
        self.connection_widgets.extend([self.buffer,self.timeout])
        row=QHBoxLayout();dia.addLayout(row)
        for name in ('VER','FST','TST','FREG','CLEAR_EVENTS','FINIT'):
            b=button(name,'terminal');row.addWidget(b);self.query_buttons.append(b);b.clicked.connect(lambda checked=False,n=name:self.command_requested.emit(n))
        row=QHBoxLayout();dia.addLayout(row);self.command=QLineEdit('TST');row.addWidget(self.command,1)
        self.send_button=button('发送指令','paper-plane','primary');row.addWidget(self.send_button)
        self.send_button.clicked.connect(lambda:self.command_requested.emit(self.command.text()));self.command.returnPressed.connect(lambda:self.command_requested.emit(self.command.text()))
        self.log=QTextEdit();self.log.setReadOnly(True);dia.addWidget(self.log,1)
        self.notice=QLabel('连接设备后准备采集，或直接打开已记录的 HEX 文件。');self.notice.setWordWrap(True);layout.addWidget(self.notice)
        self.len_mode.currentIndexChanged.connect(self.update_length_limit)
        for w in self.config_widgets:
            signal=getattr(w,'valueChanged',None) or getattr(w,'currentIndexChanged',None) or getattr(w,'toggled',None)
            signal.connect(lambda *args:self.settings_changed.emit())
        self.set_idle()

    def page(self,title,glyph):
        content=QWidget();layout=QVBoxLayout(content);layout.setContentsMargins(14,14,14,14);layout.setSpacing(12)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.Shape.NoFrame);scroll.setWidget(content)
        self.tabs.addTab(scroll,icon(glyph),title);return content,layout

    def action_button(self,action,text,glyph,css=None):
        b=button(text,glyph,css);self.actions[action]=b;b.clicked.connect(lambda:self.action_requested.emit(action));return b

    def choose_directory(self):
        path=QFileDialog.getExistingDirectory(self,'选择保存目录',self.output.text())
        if path:self.output.setText(path)

    def update_length_limit(self,index):
        self.length.setMaximum(200 if index==0 else 20_000_000)

    def values(self):
        return dict(len_mode=self.len_mode.currentIndex(),length=self.length.value(),pre=self.pre.value(),mode=self.mode.currentIndex(),
                    vth=self.vth.value(),vcmp=self.vcmp.currentIndex(),ith=self.ith.value(),icmp=self.icmp.currentIndex(),
                    enable=int(self.enable_v.isChecked())+2*int(self.enable_i.isChecked()),gap_ms=self.gap.value())

    def set_idle(self):
        self.disconnect_button.setEnabled(False);self.latest_button.setEnabled(False)
        for w in list(self.actions.values())+self.query_buttons+[self.send_button]:w.setEnabled(False)

    def show_error(self,message):
        self.notice.setText(str(message));self.notice.setProperty('cssClass','error');self.notice.style().unpolish(self.notice);self.notice.style().polish(self.notice)

    def closeEvent(self,event):
        if self.allow_close:event.accept()
        else:event.ignore();self.close_requested.emit()
