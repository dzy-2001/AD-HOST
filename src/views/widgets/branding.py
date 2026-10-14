"""Application identity and startup picture, separate from action icons."""
import sys
from PyQt6.QtCore import QSize,Qt
from PyQt6.QtGui import QIcon,QPixmap
from PyQt6.QtWidgets import QSplashScreen
from ...resources import resource_path


def application_icon():
    return QIcon(str(resource_path('assets/logo.ico')))


class StartupSplash:
    def __init__(self,app):
        self.window=None;self.bootloader=None
        if getattr(sys,'frozen',False):
            try:
                import pyi_splash
                if pyi_splash.is_alive():self.bootloader=pyi_splash
            except ImportError:pass
        if self.bootloader is None:
            pixmap=QPixmap(str(resource_path('assets/splash.png')))
            if pixmap.isNull():return
            screen=app.primaryScreen()
            width,height=800,300
            if screen:
                available=screen.availableGeometry()
                width=min(width,int(available.width()*.8));height=min(height,int(available.height()*.8))
            pixmap=pixmap.scaled(QSize(width,height),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
            self.window=QSplashScreen(pixmap);self.window.setWindowIcon(application_icon())
            self.window.show();app.processEvents()

    def finish(self,window):
        if self.window:self.window.finish(window)
        self.close()

    def close(self):
        if self.window:self.window.close()
        if self.bootloader:
            self.bootloader.close();self.bootloader=None
