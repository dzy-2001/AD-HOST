import json
from pathlib import Path
import tempfile
import time
import unittest
from src.models.core import CaptureConfig
from src.models.v26_protocol import AcquisitionSettings
from src.models.v26_session import V26Session
from tools.v26_simulator import Simulator


def wait(session, predicate, timeout=3):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        snap=session.snapshot()
        if predicate(snap):return snap
        time.sleep(.005)
    raise AssertionError(session.snapshot())


class DeferredReadTests(unittest.TestCase):
    def connect(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        board=Simulator(rate_support=True);self.addCleanup(board.close)
        session=V26Session(CaptureConfig('127.0.0.1',board.port,Path(temp.name)),poll_interval=.01,progress_timeout=3)
        self.addCleanup(lambda:(session.stop(),session.wait(3)))
        session.start();wait(session,lambda x:x['can_start'])
        return board,session

    def complete(self,session,mode=0,repeat=False):
        session.submit('start',AcquisitionSettings(len_mode=1,length=11,pre=30,mode=mode,rate_msps=5,gap_ms=50),repeat=repeat)
        if mode==0:
            wait(session,lambda x:x['can_force']);session.submit('force')
        return wait(session,lambda x:x['can_read'])

    def test_force_keeps_record_until_explicit_get(self):
        board,s=self.connect();snap=self.complete(s)
        s.progress_timeout=.1
        time.sleep(.2)  # Longer than the GET timeout: waiting is not receiving.
        self.assertEqual(s.snapshot()['completed'],0)
        self.assertEqual(s.snapshot()['state'],'connected')
        self.assertNotIn('GET',[c for c,t in board.commands])
        self.assertNotIn('RELEASE',[c for c,t in board.commands])
        self.assertEqual(list(s.directory.glob('*.hex')),[])
        self.assertFalse(snap['can_start']);self.assertTrue(snap['can_release'])
        with self.assertRaises(RuntimeError):s.submit('start',AcquisitionSettings())
        s.progress_timeout=3  # File creation on Windows CI needs a realistic timeout.
        s.submit_command('GET');snap=wait(s,lambda x:x['completed']==1 and x['can_start'])
        self.assertEqual(Path(snap['last_path']).read_bytes(),b'08000ABC'*11)
        meta=json.loads(Path(snap['last_path']+'.json').read_text('utf-8'))
        self.assertEqual(meta['sample_rate_hz'],5_000_000)
        self.assertEqual(meta['active_settings']['mode'],0)
        self.assertEqual(meta['status']['ACTIVE_PRE'],3)
        self.assertEqual([c for c,t in board.commands].count('GET'),1)

    def test_repeat_waits_for_manual_read_and_stop_preserves_pending_record(self):
        board,s=self.connect();self.complete(s,mode=1,repeat=True)
        time.sleep(.15)
        self.assertEqual(board.arm_count,1);self.assertTrue(s.snapshot()['repeat'])
        self.assertNotIn('GET',[c for c,t in board.commands])
        s.submit('read');wait(s,lambda x:x['completed']==1 and x['can_read'])
        self.assertEqual(board.arm_count,2)
        s.submit('stop_repeat');time.sleep(.15)
        self.assertFalse(s.snapshot()['repeat']);self.assertTrue(s.snapshot()['can_read'])
        self.assertNotIn('ABORT',[c for c,t in board.commands])
        self.assertNotIn('RELEASE',[c for c,t in board.commands])
        s.submit('read');wait(s,lambda x:x['completed']==2 and x['can_start'])
        time.sleep(.1);self.assertEqual(board.arm_count,2)

    def test_explicit_release_discards_without_get(self):
        board,s=self.connect();self.complete(s)
        s.submit('release');wait(s,lambda x:x['can_start'])
        self.assertIn('RELEASE',[c for c,t in board.commands])
        self.assertNotIn('GET',[c for c,t in board.commands])
        self.assertEqual(s.snapshot()['completed'],0)

    def test_pending_record_survives_host_disconnect_and_reconnect(self):
        board,s=self.connect();self.complete(s);s.stop();self.assertTrue(s.wait(3))
        new=V26Session(s.config,poll_interval=.01)
        self.addCleanup(lambda:(new.stop(),new.wait(3)));new.start()
        wait(new,lambda x:x['can_read']);time.sleep(.1)
        self.assertNotIn('GET',[c for c,t in board.commands])
        new.submit('read');snap=wait(new,lambda x:x['completed']==1)
        self.assertEqual(Path(snap['last_path']).read_bytes(),b'08000ABC'*11)
