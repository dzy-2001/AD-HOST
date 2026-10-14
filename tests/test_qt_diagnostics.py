import os
import sys
os.environ.setdefault('QT_QPA_PLATFORM','windows' if sys.platform=='win32' else 'offscreen')
from pathlib import Path
import tempfile
import time
import unittest
from src.app import create_application
from test_diagnostic_connection import DiagnosticBoard


class QtDiagnosticsTests(unittest.TestCase):
    def test_diagnostic_connection_remains_queryable_and_recovers(self):
        app,window,controller=create_application();app.setQuitOnLastWindowClosed(False)
        def pump(predicate):
            end=time.monotonic()+5
            while not predicate():
                self.assertLess(time.monotonic(),end)
                app.processEvents();time.sleep(.005)
            controller.refresh();app.processEvents()
        with tempfile.TemporaryDirectory() as directory:
            board=DiagnosticBoard()
            try:
                window.host.setText('127.0.0.1');window.port.setValue(board.port);window.output.setText(directory)
                window.connect_button.click()
                pump(lambda:controller.session.snapshot()['state'] in ('connected','failed'))
                self.assertTrue(window.send_button.isEnabled())
                self.assertFalse(window.actions['start'].isEnabled())
                self.assertIn('未知',window.rate_status.text())
                self.assertIn('IERR=4',window.notice.text())
                window.command.setText('TST');window.send_button.click()
                pump(lambda:not controller.session.snapshot()['busy'])
                self.assertIn('IERR=4',window.notice.text())
                board.tst_response=None;window.send_button.click()
                pump(lambda:controller.session.snapshot()['can_start'])
                self.assertTrue(window.actions['start'].isEnabled())
                self.assertIn('100 MSPS',window.rate_status.text())
                self.assertNotIn('IERR=4',window.notice.text())
                screenshots=os.environ.get('AD_HOST_SCREENSHOTS')
                if screenshots:
                    Path(screenshots).mkdir(parents=True,exist_ok=True)
                    window.grab().save(str(Path(screenshots)/'diagnostic-recovered.png'))
            finally:
                controller.close();pump(lambda:window.allow_close);board.close()


if __name__=='__main__':unittest.main()
