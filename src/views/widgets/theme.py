"""Application additions to the shared stylesheet; keep styles.py reusable."""
from pathlib import Path
from PyQt6.QtCore import QTemporaryDir
import qtawesome as qta
from .styles import GLOBAL_STYLE,NORD0,NORD3,NORD4,NORD5,NORD6,NORD8,NORD10,NORD11


def icon(name):
    return qta.icon('fa5s.'+name,color=NORD10,color_disabled=NORD4)


def apply_theme(app):
    app.setStyle('Fusion')
    app._theme_assets=QTemporaryDir()
    root=Path(app._theme_assets.path())
    for name in ('chevron-up','chevron-down','check'):
        if not icon(name).pixmap(16,16).save(str(root/(name+'.png'))):
            raise RuntimeError('无法创建界面图标资源')
    up=(root/'chevron-up.png').as_posix();down=(root/'chevron-down.png').as_posix();check=(root/'check.png').as_posix()
    app.setStyleSheet(GLOBAL_STYLE+f'''
        QDialog, QTabWidget::pane, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {NORD6}; }}
        QTabWidget::pane {{ border: 1px solid {NORD4}; border-radius: 5px; }}
        QTabBar::tab {{ padding: 10px 22px; background: {NORD5}; color: {NORD3}; }}
        QTabBar::tab:selected {{ background: {NORD8}; color: {NORD0}; }}
        QComboBox QAbstractItemView {{ selection-color: {NORD0}; }}
        QComboBox::down-arrow {{ image: url("{down}"); width: 12px; height: 12px; }}
        QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url("{up}"); width: 10px; height: 10px; }}
        QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url("{down}"); width: 10px; height: 10px; }}
        QCheckBox::indicator:checked {{ image: url("{check}"); }}
        QPushButton:disabled {{ background: {NORD5}; color: #8491A4; border: 1px solid {NORD4}; }}
        QPushButton:checked {{ border: 2px solid {NORD10}; background: {NORD8}; }}
        QProgressBar {{ border: 1px solid {NORD4}; border-radius: 4px; text-align: center; min-height: 18px; background: white; }}
        QProgressBar::chunk {{ background: {NORD10}; border-radius: 3px; }}
        QLabel[cssClass="error"] {{ color: {NORD11}; }}
        QLabel[cssClass="field-label"] {{ font-weight: bold; color: {NORD3}; }}
        QLabel[cssClass="field-hint"] {{ color: {NORD3}; }}
        QLabel[cssClass="summary"] {{ background: {NORD6}; border-radius: 4px; padding: 7px 10px; }}
        QFrame#cursorReadout {{ background: white; border: 1px solid {NORD4}; border-radius: 5px; }}
        QLabel[cssClass="readout-heading"] {{ color: {NORD3}; font-size: 9pt; padding: 3px 8px; background: {NORD5}; }}
        QLabel[cssClass="readout-name"] {{ font-weight: bold; padding: 3px 8px; }}
        QLabel[cssClass="readout-value"] {{ font-family: "Consolas", "DejaVu Sans Mono", monospace; padding: 3px 8px; }}
        QLabel[readoutRow="A"] {{ color: {NORD10}; background: #F2F6FA; }}
        QLabel[readoutRow="B"] {{ color: #A35689; background: #FAF5F8; }}
        QLabel[readoutRow="delta"] {{ background: {NORD5}; font-weight: bold; }}
        QToolTip {{ color: {NORD0}; background: white; border: 1px solid {NORD4}; padding: 5px; }}
    ''')
