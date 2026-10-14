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
                self.assertIn('状态不可用',window.rate_status.text())
                self.assertIn('TST 被设备拒绝',window.notice.text())
                self.assertIn('IERR=4',window.log.toPlainText())
                window.command.setText('TST');window.send_button.click()
                pump(lambda:not controller.session.snapshot()['busy'])
                self.assertIn('TST 被设备拒绝',window.notice.text())
                self.assertIn('IERR=4',window.log.toPlainText())
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


class QtDiagnosticLogTests(unittest.TestCase):
    def setUp(self):
        self.app,self.window,self.controller=create_application();self.app.setQuitOnLastWindowClosed(False)
        self.window.show();self.window.tabs.setCurrentIndex(2);self.controller.timer.stop();self.app.processEvents()

    def tearDown(self):
        self.controller.close();self.pump(lambda:self.window.allow_close)

    def pump(self,predicate):
        end=time.monotonic()+5
        while not predicate():
            self.assertLess(time.monotonic(),end)
            self.controller.refresh();self.app.processEvents();time.sleep(.005)
        self.controller.refresh();self.app.processEvents()

    def test_valid_query_clears_stale_local_error_and_shows_response(self):
        from tools.v26_simulator import Simulator
        board=Simulator(rate_support=True)
        try:
            w=self.window;c=self.controller
            w.host.setText('127.0.0.1');w.port.setValue(board.port);w.connect_button.click()
            self.pump(lambda:c.session.snapshot()['can_start'])
            c.send_command('VERX');self.assertEqual(w.notice.property('cssClass'),'error')
            w.command.setText('VER');w.send_button.click();self.pump(lambda:not c.session.snapshot()['busy'])
            self.assertNotEqual(w.notice.property('cssClass'),'error')
            self.assertNotIn('不受支持',w.notice.text())
            self.assertIn('接收 VER',w.log.toPlainText());self.assertIn('V1.0.15 (V28)',w.log.toPlainText())
        finally:
            c.disconnect();self.pump(lambda:c.session.wait(0));board.close()

    def test_refresh_follows_bottom_but_preserves_scrolled_position_and_selection(self):
        from PyQt6.QtGui import QTextCursor
        w=self.window;c=self.controller
        w.diagnostic_messages=[f'entry {i:03d}' for i in range(90)]
        c.refresh();self.app.processEvents();bar=w.log.verticalScrollBar()
        self.assertGreater(bar.maximum(),0)
        bar.setValue(bar.maximum());w.diagnostic_messages.append('new bottom')
        c.refresh();self.app.processEvents();self.assertEqual(bar.value(),bar.maximum())
        cursor=w.log.document().find('entry 020');w.log.setTextCursor(cursor)
        bar.setValue(bar.maximum()//3);before=bar.value();selection=w.log.textCursor().selectedText()
        w.diagnostic_messages.insert(0,'earlier content expanded ' * 20)
        w.diagnostic_messages.append('new entry while reading')
        c.refresh();self.app.processEvents()
        self.assertEqual(bar.value(),before);self.assertEqual(w.log.textCursor().selectedText(),selection)
        # A queued GUI refresh with unchanged text must also preserve the viewport.
        c.refresh();self.app.processEvents();self.assertEqual(bar.value(),before)
        self.assertNotIn('earlier content expanded',w.log.toPlainText())
        cursor=w.log.textCursor();cursor.clearSelection();w.log.setTextCursor(cursor)
        c.refresh();self.app.processEvents();self.assertEqual(bar.value(),before)
        bar.setValue(bar.maximum());c.refresh();self.app.processEvents()
        self.assertIn('earlier content expanded',w.log.toPlainText())
        self.assertIn('new entry while reading',w.log.toPlainText())
        self.assertEqual(bar.value(),bar.maximum())


if __name__=='__main__':unittest.main()
