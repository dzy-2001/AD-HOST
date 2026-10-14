import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from src.app import create_application
from src.views.waveform_window import WaveformWindow
from src.controllers.waveform_controller import WaveformController
from src.models.recording import Recording,make_view


class QtInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app,cls.main,cls.controller=create_application();cls.app.setQuitOnLastWindowClosed(False)

    def pump(self):
        for _ in range(5):self.app.processEvents();time.sleep(.01)

    def waveform(self):
        wave=WaveformController(WaveformWindow())
        self.addCleanup(lambda:(wave.close(),wave.worker.thread.join(2)))
        wave.recording=Recording(Path('test.hex'),np.column_stack((np.arange(100),np.arange(100))).astype(np.uint16))
        wave.current_view=make_view(wave.recording);wave._active_range=(0,100);wave._set_limits(wave.full_limits())
        return wave

    def test_restore_overview_discards_pending_zoom_result(self):
        wave=self.waveform()
        with patch.object(wave.worker,'request',return_value=12):
            wave._set_limits((.0002,.0004));wave.refresh_range()
            wave.overview()
            with wave.worker.condition:wave.worker.result=(12,'view',make_view(wave.recording,start=20,stop=41),None)
            wave.poll()
        self.assertEqual(wave.current_view.indices[0],0)
        self.assertEqual(wave.current_view.indices[-1],99)

    def test_fit_y_restores_autoscale_after_explicit_pan_limits(self):
        wave=self.waveform();wave.view.axes[0].set_ylim(10,20)
        wave.view.display_curve(wave.current_view,fit=True)
        low,high=wave.view.axes[0].get_ylim()
        self.assertLess(low,-5.99);self.assertLess(high,0)

    def test_titlebar_close_hides_idle_main_window_on_first_attempt(self):
        self.main.show();self.pump();self.main.close();self.pump()
        self.assertFalse(self.main.isVisible())

    def test_titlebar_close_hides_waveform_on_first_attempt(self):
        wave=self.waveform();wave.view.show();self.pump();wave.view.close();self.pump()
        self.assertFalse(wave.view.isVisible());self.assertTrue(wave.closed)
