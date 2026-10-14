from PyQt6.QtWidgets import QFrame,QVBoxLayout,QLabel,QPushButton,QSpinBox,QComboBox
from .theme import icon


def button(text,glyph,css=None,tip=None):
    widget=QPushButton(icon(glyph),text)
    if css:widget.setProperty('cssClass',css)
    widget.setToolTip(tip or text)
    widget.setAccessibleName(text)
    return widget


def card(title):
    widget=QFrame();widget.setProperty('cssClass','card')
    layout=QVBoxLayout(widget);layout.setContentsMargins(14,12,14,12)
    label=QLabel(title);label.setProperty('cssClass','card-title');layout.addWidget(label)
    return widget,layout


def spin(low,high,value,suffix=''):
    widget=QSpinBox();widget.setRange(low,high);widget.setValue(value);widget.setSuffix(suffix)
    widget.setKeyboardTracking(False)
    return widget


def combo(items):
    widget=QComboBox();widget.addItems(items);return widget
