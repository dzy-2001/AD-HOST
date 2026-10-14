"""Aligned, selectable raw-sample readouts; no sampling or delta calculations."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame,QGridLayout,QLabel


class CursorReadout(QFrame):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName('cursorReadout')
        grid=QGridLayout(self);grid.setContentsMargins(6,6,6,6)
        grid.setHorizontalSpacing(0);grid.setVerticalSpacing(1)
        self.cells={}
        headings=('读数','采样点','时间（ms）','电压（V）','电压 ADC','电流（A）','电流 ADC')
        for col,text in enumerate(headings):
            label=QLabel(text);label.setProperty('cssClass','readout-heading')
            label.setAlignment((Qt.AlignmentFlag.AlignLeft if col==0 else Qt.AlignmentFlag.AlignRight)|Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(label,0,col);grid.setColumnStretch(col,1 if col else 0)
        for row,(name,title) in enumerate((('hover','鼠标位置'),('A','光标 A'),('B','光标 B'),('delta','差值 B − A')),1):
            label=QLabel(title);label.setProperty('cssClass','readout-name');label.setProperty('readoutRow',name)
            grid.addWidget(label,row,0);self.cells[name]={}
            for col,key in enumerate(('index','time','voltage','voltage_raw','current','current_raw'),1):
                cell=QLabel('—');cell.setProperty('cssClass','readout-value');cell.setProperty('readoutRow',name)
                cell.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
                cell.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                cell.setAccessibleName(title+' '+headings[col]);grid.addWidget(cell,row,col);self.cells[name][key]=cell
        self.setToolTip('读数来自原始采样点。双光标模式下选择 A/B 后点击波形，或拖动已有标记。差值按 B−A 计算。')

    def clear_values(self):
        for row in self.cells.values():
            for cell in row.values():cell.setText('—')

    def set_point(self,name,point):
        self._set_values(name,(f'{point.index:,}',f'{point.time_ms:.9f}',f'{point.voltage:.3f}',str(point.voltage_raw),f'{point.current:.3f}',str(point.current_raw)))

    def set_difference(self,delta):
        self._set_values('delta',(f"{delta['samples']:+,}",f"{delta['time_ms']:+.9f}",
                                  f"{delta['voltage']:+.3f}",f"{delta['voltage_raw']:+d}",f"{delta['current']:+.3f}",f"{delta['current_raw']:+d}"))

    def _set_values(self,name,values):
        for cell,value in zip(self.cells[name].values(),values):cell.setText(value)
