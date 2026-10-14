# Build on Windows: python -m PyInstaller --noconfirm --clean build_app.spec
# A single dist/AD-HOST.exe, with logo and startup picture embedded.
from pathlib import Path
import os
from PyInstaller.utils.hooks import collect_all

ROOT=Path(SPECPATH)
os.environ['QT_API']='pyqt6'
for filename in ('logo.ico','splash.png'):
    if not (ROOT/'assets'/filename).is_file():
        raise FileNotFoundError(f'Missing asset: {ROOT / "assets" / filename}')
qta_data,qta_binaries,qta_imports=collect_all('qtawesome')
a=Analysis(
    [str(ROOT/'run.py')],pathex=[str(ROOT)],
    binaries=qta_binaries,datas=qta_data+[(str(ROOT/'assets'),'assets')],
    hiddenimports=qta_imports,hookspath=[],runtime_hooks=[],
    excludes=['tkinter','PySide6','PySide2','PyQt5'],noarchive=False,
)
pyz=PYZ(a.pure)
# Bootloader splash appears while a one-file app extracts its dependencies.
# The Qt entry point closes it when the main window is ready. Source execution
# uses QSplashScreen instead, so the same image is also visible under Python.
splash=Splash(str(ROOT/'assets/splash.png'),binaries=a.binaries,datas=a.datas,
              text_pos=None,max_img_size=(800,300),always_on_top=False)
exe=EXE(
    pyz,a.scripts,splash,splash.binaries,a.binaries,a.datas,[],
    name='AD-HOST',debug=False,bootloader_ignore_signals=False,strip=False,
    upx=False,console=False,disable_windowed_traceback=False,
    icon=str(ROOT/'assets/logo.ico'),
)
