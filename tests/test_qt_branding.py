import os
import sys
os.environ.setdefault('QT_QPA_PLATFORM','windows' if sys.platform=='win32' else 'offscreen')
from pathlib import Path
import time
import unittest
from unittest.mock import patch
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication,QSplashScreen
from src.app import create_application


class BrandingTests(unittest.TestCase):
    def close_app(self,app,window,controller):
        if getattr(window,'startup_splash',None):window.startup_splash.close()
        controller.close();end=time.monotonic()+3
        while not window.allow_close and time.monotonic()<end:
            app.processEvents();time.sleep(.005)
        app.processEvents()
        self.assertTrue(window.allow_close)

    def test_application_and_both_windows_use_asset_icon(self):
        from src.views.waveform_window import WaveformWindow
        app,window,controller=create_application();app.setQuitOnLastWindowClosed(False)
        self.addCleanup(self.close_app,app,window,controller)
        wave=WaveformWindow();self.addCleanup(wave.deleteLater)
        expected=QIcon(str(Path(__file__).resolve().parents[1]/'assets/logo.ico')).pixmap(32,32).toImage()
        self.assertFalse(expected.isNull())
        for icon in (app.windowIcon(),window.windowIcon(),wave.windowIcon()):
            self.assertEqual(icon.pixmap(32,32).toImage(),expected)

    def test_splash_visible_until_main_window_is_ready(self):
        app,window,controller=create_application(show_splash=True);app.setQuitOnLastWindowClosed(False)
        self.addCleanup(self.close_app,app,window,controller)
        splash=next(w for w in QApplication.topLevelWidgets() if isinstance(w,QSplashScreen) and w.isVisible())
        self.assertFalse(splash.pixmap().isNull());self.assertFalse(window.isVisible())
        self.assertLessEqual(splash.width(),800)
        screenshots=os.environ.get('AD_HOST_SCREENSHOTS')
        if screenshots:
            output=Path(screenshots);output.mkdir(parents=True,exist_ok=True);splash.grab().save(str(output/'startup-splash.png'))
        window.show();app.processEvents();window.startup_splash.finish(window);app.processEvents()
        self.assertFalse(splash.isVisible());self.assertTrue(window.isVisible())

    def test_initialization_failure_closes_splash(self):
        with patch('src.views.main_window.MainWindow',side_effect=RuntimeError('initialization failed')):
            with self.assertRaisesRegex(RuntimeError,'initialization failed'):create_application(show_splash=True)
        QApplication.processEvents()
        self.assertFalse(any(isinstance(w,QSplashScreen) and w.isVisible() for w in QApplication.topLevelWidgets()))
