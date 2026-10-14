"""Load the shared standard and style only AD-HOST-specific additions.

Common controls are owned by styles.GLOBAL_STYLE. Do not override their
indicators, colors or states here. QtAwesome supplies action icons only.
"""
import qtawesome as qta
from .styles import GLOBAL_STYLE,NORD0,NORD3,NORD4,NORD5,NORD6,NORD8,NORD10,NORD11


def icon(name):
    return qta.icon('fa5s.'+name,color=NORD10,color_disabled=NORD4)


def apply_theme(app):
    app.setStyle('Fusion')
    app.setStyleSheet(GLOBAL_STYLE+f'''
        QDialog, QTabWidget::pane, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {NORD6}; }}
        QTabWidget::pane {{ border: 1px solid {NORD4}; border-radius: 5px; }}
        QTabBar::tab {{ padding: 10px 22px; background: {NORD5}; color: {NORD3}; }}
        QTabBar::tab:selected {{ background: {NORD8}; color: {NORD0}; }}
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
    ''')
