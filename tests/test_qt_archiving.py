import os
import sys
os.environ.setdefault('QT_QPA_PLATFORM','windows' if sys.platform=='win32' else 'offscreen')
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from src.app import create_application
from tools.v26_simulator import Simulator


class QtArchivingTests(unittest.TestCase):
    def setUp(self):
        self.app,self.window,self.controller=create_application();self.app.setQuitOnLastWindowClosed(False)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.board=Simulator(rate_support=True);self.addCleanup(self.board.close)
        self.addCleanup(self.shutdown)

    def pump(self,predicate):
        end=time.monotonic()+8
        while not predicate():
            self.assertLess(time.monotonic(),end)
            self.app.processEvents();time.sleep(.005)
        self.controller.refresh();self.app.processEvents()

    def shutdown(self):
        self.controller.close();self.pump(lambda:self.window.allow_close)

    def connect(self):
        w=self.window
        w.host.setText('127.0.0.1');w.port.setValue(self.board.port)
        w.output.setText(str(Path(self.temp.name)/'archives'))
        w.len_mode.setCurrentIndex(1);w.length.setValue(10);w.mode.setCurrentIndex(1);w.gap.setValue(0)
        w.connect_button.click();self.pump(lambda:self.controller.session.snapshot()['can_start'])

    def capture(self,total):
        self.pump(lambda:self.controller.session.snapshot()['can_start'])
        self.window.actions['start'].click()
        self.pump(lambda:self.controller.session.snapshot()['completed']==total)

    def test_manual_mode_hides_thresholds_but_retains_settings(self):
        w=self.window
        self.assertTrue(w.threshold_settings.isHidden())
        w.mode.setCurrentIndex(1);self.assertFalse(w.threshold_settings.isHidden())
        w.vth.setValue(3456);w.enable_i.setChecked(False)
        w.mode.setCurrentIndex(0);self.assertTrue(w.threshold_settings.isHidden())
        w.mode.setCurrentIndex(1)
        self.assertEqual(w.vth.value(),3456);self.assertFalse(w.enable_i.isChecked())
        self.assertNotEqual(Path(w.output.text()).name,'captures')

    def test_save_cancel_reconnect_selection_and_cleanup(self):
        self.connect();self.capture(1);self.capture(2)
        c=self.controller;w=self.window;dest=Path(w.output.text())
        self.assertFalse(dest.exists());self.assertEqual(w.record_list.count(),2)
        sources=list(c.records);self.assertTrue(all(Path(p).exists() for p in sources))
        w.record_list.setCurrentRow(0)
        with patch.object(w,'confirm_archive_directory',return_value=''):
            w.save_record_button.click()
        self.assertFalse(dest.exists());self.assertIsNone(c.archive_job)
        c.disconnect();self.pump(lambda:c.session.wait(0))
        w.connect_button.click();self.pump(lambda:c.session.snapshot()['can_start'])
        self.assertEqual(w.record_list.count(),2)
        with patch.object(w,'confirm_archive_directory',return_value=str(dest)):
            w.save_record_button.click()
        self.pump(lambda:c.archive_job is None)
        saved=Path(c.records[sources[0]]['archive'])
        self.assertRegex(saved.parent.name,r'^\d{8}_\d{4}(?:_\d+)?$')
        self.assertEqual(saved.read_bytes(),b'08000ABC'*10)
        self.assertTrue(Path(str(saved)+'.json').exists())
        self.assertFalse(c.records[sources[1]]['archive'])
        with patch.object(w,'confirm_discard',return_value=False):c.request_close()
        self.assertFalse(c.closing)
        with patch.object(w,'confirm_discard',return_value=True):c.request_close()
        self.pump(lambda:w.allow_close)
        self.assertTrue(saved.exists());self.assertFalse(Path(c.cache.name).exists())

    def test_finishing_capture_during_close_check_still_requires_confirmation(self):
        self.connect();c=self.controller;w=self.window
        first=c.session.snapshot();first.update(records=[],receiving=True)
        second=c.session.snapshot();second.update(records=['newly-completed.hex'],receiving=False)
        with patch.object(c.session,'snapshot',side_effect=[first,second]), \
             patch.object(w,'confirm_discard',return_value=False) as confirm, \
             patch.object(c,'close') as close:
            c.request_close()
            confirm.assert_called_once();close.assert_not_called()

    def test_destination_inside_cache_is_not_treated_as_saved(self):
        self.connect();self.capture(1);c=self.controller;w=self.window
        destination=Path(c.cache.name)/'archive'
        with patch.object(w,'confirm_archive_directory',return_value=str(destination)):
            w.save_record_button.click()
        self.assertIsNone(c.archive_job);self.assertFalse(destination.exists())
        self.assertFalse(c.selected_record()['archive']);self.assertIn('临时目录',w.notice.text())

    def test_archive_failure_can_retry_without_losing_cached_record(self):
        self.connect();self.capture(1);c=self.controller;w=self.window
        dest=Path(self.temp.name)/'not-a-directory';dest.write_text('existing file',encoding='utf-8')
        with patch.object(w,'confirm_archive_directory',return_value=str(dest)):w.save_record_button.click()
        self.pump(lambda:c.archive_job is None)
        self.assertIn('存档失败',w.notice.text());self.assertTrue(w.save_record_button.isEnabled())
        self.assertTrue(Path(c.selected_record()['source']).exists())
        self.assertEqual(dest.read_text('utf-8'),'existing file')


if __name__=='__main__':unittest.main()
