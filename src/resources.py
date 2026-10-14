"""Read bundled assets independently of the shell's working directory."""
from pathlib import Path
import sys


def resource_path(relative):
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
    return root/relative


def set_windows_app_id():
    if sys.platform=='win32':
        import ctypes
        from ctypes import wintypes
        function=ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        function.argtypes=[wintypes.LPCWSTR];function.restype=ctypes.c_long
        function('AD-HOST.Desktop')
