"""Offline plotting widgets and canvas; calculations live in the controller/model."""
from PyQt6.QtCore import pyqtSignal,Qt
from PyQt6.QtWidgets import QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QProgressBar,QFileDialog
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg,NavigationToolbar2QT
from .widgets.controls import button,spin,combo
from .widgets.styles import NORD6,NORD4,NORD10,NORD12,NORD11
from .widgets.theme import icon
from .widgets.cursor_readout import CursorReadout


class WaveformWindow(QMainWindow):
    close_requested=pyqtSignal()

    def __init__(self,parent=None):
        super().__init__(parent,Qt.WindowType.Window);self.allow_close=False
        self.setWindowTitle('波形查看 · AD-HOST');self.setWindowIcon(icon('chart-line'));self.resize(1220,860);self.setMinimumSize(950,680)
        content=QWidget();self.setCentralWidget(content);layout=QVBoxLayout(content);layout.setContentsMargins(16,12,16,12)
        row=QHBoxLayout();layout.addLayout(row);self.path=QLineEdit();self.path.setReadOnly(True);row.addWidget(self.path,1)
        self.choose_button=button('选择 HEX','folder-open','primary');self.cancel_button=button('取消解析','times','danger')
        row.addWidget(self.choose_button);row.addWidget(self.cancel_button)
        self.details=QLabel('每组：电压 2 字节 + 电流 2 字节，大端无符号；电流显示原始计数。');self.details.setWordWrap(True);layout.addWidget(self.details)
        self.progress=QProgressBar();self.progress.setRange(0,1000);self.progress.setValue(0);self.progress.setFormat('%p%');layout.addWidget(self.progress)
        row=QHBoxLayout();layout.addLayout(row);self.tools={}
        for name,text,glyph in [('pan','拖动','hand-paper'),('zoom','框选放大','search-plus'),('measure','双光标','ruler-horizontal'),('home','全貌','expand'),('trigger','触发位置','bolt'),('fit','纵轴适应','arrows-alt-v'),('save','保存图片','image')]:
            b=button(text,glyph);self.tools[name]=b;row.addWidget(b)
            if name in ('pan','zoom','measure'):b.setCheckable(True)
        row.addStretch()
        row=QHBoxLayout();layout.addLayout(row);row.addWidget(QLabel('采样点范围 [起点, 终点)'))
        self.start=spin(0,2_147_483_646,0);self.stop=spin(1,2_147_483_647,1);row.addWidget(self.start);row.addWidget(self.stop)
        self.range_button=button('显示范围','crop-alt');row.addWidget(self.range_button);row.addStretch()
        row.addWidget(QLabel('测量光标'));self.cursor_choice=combo(['A','B']);row.addWidget(self.cursor_choice)
        self.figure=Figure(figsize=(11,5),dpi=100,facecolor=NORD6)
        self.axes=self.figure.subplots(2,1,sharex=True);self.figure.subplots_adjust(left=.09,right=.98,top=.95,bottom=.11,hspace=.18)
        self.lines=[];self.triggers=[];self.hover=[];self.markers={'A':[],'B':[]}
        for ax,color in zip(self.axes,(NORD10,NORD12)):
            ax.set_facecolor('white');ax.grid(True,color=NORD4,linewidth=.6);ax.tick_params(labelsize=9)
            ax.ticklabel_format(axis='x',style='plain',useOffset=False)
            self.lines.append(ax.plot([],[],color=color,linewidth=.9)[0])
            self.triggers.append(ax.axvline(0,color=NORD11,linestyle='--',linewidth=1,visible=False))
            self.hover.append(ax.axvline(0,color='#8491A4',linestyle=':',linewidth=.8,visible=False))
            for name,mc in (('A','#5E81AC'),('B','#A35689')):
                self.markers[name].append(ax.axvline(0,color=mc,linewidth=1.2,visible=False))
        self.axes[0].set_ylabel('Voltage (V)');self.axes[1].set_ylabel('Current (raw)');self.axes[1].set_xlabel('Time (ms)')
        self.canvas=FigureCanvasQTAgg(self.figure);layout.addWidget(self.canvas,1)
        self.navigation=NavigationToolbar2QT(self.canvas,self);self.navigation.hide()
        self.readout=CursorReadout();layout.addWidget(self.readout)
        self.status=QLabel('请选择已保存完成的 HEX 文件。');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.set_record_enabled(False);self.cancel_button.setEnabled(False)

    def choose_path(self):
        return QFileDialog.getOpenFileName(self,'选择 HEX 记录','','HEX 数据 (*.hex *.txt);;所有文件 (*)')[0]

    def save_path(self):
        return QFileDialog.getSaveFileName(self,'保存当前波形','waveform.png','PNG 图片 (*.png)')[0]

    def set_record_enabled(self,enabled):
        for w in list(self.tools.values())+[self.range_button,self.start,self.stop,self.cursor_choice]:w.setEnabled(enabled)

    def display_curve(self,curve,fit=False):
        for line,data in zip(self.lines,(curve.voltage,curve.current)):line.set_data(curve.time_ms,data)
        if fit:
            for ax in self.axes:ax.set_autoscaley_on(True);ax.relim();ax.autoscale_view(scalex=False,scaley=True)
        self.canvas.draw_idle()

    def closeEvent(self,event):
        if self.allow_close:event.accept()
        else:event.ignore();self.close_requested.emit()
