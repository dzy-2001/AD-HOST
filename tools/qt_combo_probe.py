"""Compare base style and stylesheet scope without changing shared QSS."""
import os
import sys
import json
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM','windows' if sys.platform=='win32' else 'offscreen')
from PyQt6.QtWidgets import QApplication,QWidget,QVBoxLayout,QComboBox,QStyle,QStyleFactory
from PyQt6.QtCore import QT_VERSION_STR
from src.views.widgets.styles import GLOBAL_STYLE


def run():
    app=QApplication([]);default=app.style().objectName()
    output=Path(os.environ.get('AD_HOST_SCREENSHOTS','screenshots'));output.mkdir(exist_ok=True)
    results=[]
    for base in (default,'Fusion'):
        for scope in ('window','application'):
            app.setStyleSheet('');app.setStyle(QStyleFactory.create(base))
            window=QWidget();window.resize(360,150);layout=QVBoxLayout(window)
            combo=QComboBox();combo.addItems(['ETHEL 12kV','ETHEL 10kV','ETHEL 5kV']);combo.setFixedWidth(144)
            layout.addWidget(combo);layout.addStretch()
            (window if scope=='window' else app).setStyleSheet(GLOBAL_STYLE)
            window.show();app.processEvents();combo.showPopup()
            for _ in range(10):app.processEvents();time.sleep(.02)
            key=base.lower()+'-'+scope
            combo.view().window().grab().save(str(output/('combo-'+key+'.png')))
            results.append(dict(base=base,scope=scope,qt=QT_VERSION_STR,default=default,
                                delegate=combo.itemDelegate().metaObject().className(),
                                popup_hint=combo.style().styleHint(QStyle.StyleHint.SH_ComboBox_Popup,None,combo),
                                row_height=combo.view().sizeHintForRow(0)))
            combo.hidePopup();window.close();window.deleteLater();app.processEvents()
    (output/'combo-probe.json').write_text(json.dumps(results,indent=2),'utf-8');print(json.dumps(results))


if __name__=='__main__':run()
