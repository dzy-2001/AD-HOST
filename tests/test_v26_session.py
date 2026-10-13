import importlib
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import threading
import unittest
from unittest.mock import patch

from ad_host.core import CaptureConfig
from ad_host.v26_protocol import AcquisitionSettings
from tools.v26_simulator import Simulator


def wait(session,predicate,timeout=5):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        snap=session.snapshot()
        if predicate(snap):return snap
        time.sleep(.005)
    raise AssertionError(session.snapshot())


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('ad_host.v26_session'),'V26 scheduler not implemented')
        self.api=importlib.import_module('ad_host.v26_session')
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)

    def connect(self,**kwargs):
        server=Simulator(**kwargs);self.addCleanup(server.close)
        session=self.api.V26Session(CaptureConfig('127.0.0.1',server.port,Path(self.temp.name),queue_chunks=2),
                                    command_timeout=.5,progress_timeout=.3,poll_interval=.01)
        self.addCleanup(lambda:(session.stop(),session.wait(3)))
        session.start();wait(session,lambda s:s['state']=='connected')
        return server,session

    def test_manual_history_force_fragmented_get_and_complete_metadata(self):
        board,s=self.connect(fragment=7)
        s.submit('start',AcquisitionSettings(len_mode=1,length=11,pre=30))
        wait(s,lambda x:x['can_force'])
        self.assertNotIn('GET',[c for c,t in board.commands])
        s.submit('force');snap=wait(s,lambda x:x['completed']==1)
        path=Path(snap['last_path']);self.assertEqual(path.read_bytes(),b'08000ABC'*11)
        meta=json.loads(Path(str(path)+'.json').read_text('utf-8'))
        self.assertTrue(meta['complete']);self.assertEqual(meta['status']['ACTIVE_PRE'],3)
        self.assertEqual(meta['written_hex_bytes'],88);self.assertEqual(meta['active_settings']['mode'],0)
        self.assertEqual(board.interleaved,[])

    def test_auto_repeat_honors_device_gap_and_never_force(self):
        board,s=self.connect()
        s.submit('start',AcquisitionSettings(len_mode=1,length=100,mode=1,gap_ms=120),repeat=True)
        wait(s,lambda x:x['completed']>=2);s.submit('stop_repeat')
        commands=[c for c,t in board.commands];self.assertNotIn('FORCE',commands)
        arms=[t for c,t in board.commands if c=='ARM']
        self.assertGreaterEqual(arms[1]-arms[0],.12)
        self.assertEqual(board.interleaved,[])

    def test_cancel_racing_done_releases_without_get(self):
        board,s=self.connect(fault='abort_race')
        s.submit('start',AcquisitionSettings(len_mode=1,length=10))
        wait(s,lambda x:x['can_force']);s.submit('cancel')
        wait(s,lambda x:x['can_start'])
        names=[c for c,t in board.commands]
        self.assertIn('ABORT',names);self.assertIn('RELEASE',names);self.assertNotIn('GET',names)

    def test_arm_timeout_disconnects_without_retry(self):
        board,s=self.connect(fault='drop_arm');s.submit('start',AcquisitionSettings(len_mode=1,length=10))
        wait(s,lambda x:x['state']=='failed')
        self.assertEqual([c for c,t in board.commands].count('ARM'),1)
        self.assertEqual(board.commands[-1][0],'ARM')

    def test_get_error_and_bad_adc_never_complete(self):
        for fault in ('error_get','invalid_adc'):
            with self.subTest(fault=fault):
                board,s=self.connect(fault=fault)
                s.submit('start',AcquisitionSettings(len_mode=1,length=10,mode=1))
                snap=wait(s,lambda x:x['state']=='failed')
                self.assertEqual(snap['completed'],0)
                s.wait(3)
                partial=list(s.directory.glob('*.partial.hex.json'))
                self.assertTrue(partial);self.assertFalse(json.loads(partial[0].read_text('utf-8'))['complete'])

    def test_get_no_progress_timeout_is_separate_from_trigger_wait(self):
        board,s=self.connect(fault='stall_get')
        s.submit('start',AcquisitionSettings(len_mode=1,length=10))
        wait(s,lambda x:x['can_force']);time.sleep(.4)
        self.assertEqual(s.snapshot()['state'],'connected')
        s.submit('force');snap=wait(s,lambda x:x['state']=='failed')
        self.assertIn('进度',snap['error']);self.assertEqual(board.interleaved,[])

    def test_missing_gap_disables_repeat_instead_of_guessing_zero(self):
        board,s=self.connect(fault='missing_gap')
        with self.assertRaises(ValueError):s.submit('start',AcquisitionSettings(mode=1),repeat=True)

    def test_get_cancel_closes_socket_without_abort_or_queries(self):
        board,s=self.connect(fault='stall_get')
        s.submit('start',AcquisitionSettings(len_mode=1,length=100,mode=1))
        wait(s,lambda x:x['receiving']);self.assertTrue(board.get_active.wait(1))
        s.submit('cancel');self.assertTrue(s.wait(3))
        self.assertEqual(s.snapshot()['completed'],0)
        self.assertEqual(board.commands[-1][0],'GET');self.assertEqual(board.interleaved,[])

    def test_failed_configuration_is_read_back_and_never_armed(self):
        board,s=self.connect(fault='reject_cfg')
        s.submit('start',AcquisitionSettings(len_mode=1,length=13))
        wait(s,lambda x:bool(x['error']) and not x['busy'])
        self.assertNotIn('ARM',[c for c,t in board.commands])
        self.assertEqual(s.snapshot()['status']['CFG_SAMPLES'],13)

    def test_reconnected_completed_record_does_not_invent_active_settings(self):
        board,s=self.connect();s.stop();self.assertTrue(s.wait(3))
        board.active=[1,11,30,0,2500,0,1500,4,3,0];board.phase='done'
        new=self.api.V26Session(CaptureConfig('127.0.0.1',board.port,Path(self.temp.name)),poll_interval=.01)
        self.addCleanup(lambda:(new.stop(),new.wait(3)));new.start();wait(new,lambda x:x['can_read'])
        self.assertIsNone(new.snapshot()['active_settings']);self.assertFalse(new.snapshot()['can_force'])
        new.submit('read');snap=wait(new,lambda x:x['completed']==1)
        meta=json.loads(Path(snap['last_path']+'.json').read_text('utf-8'))
        self.assertIsNone(meta['active_settings']);self.assertFalse(meta['active_configuration_known'])

    def test_disk_failure_closes_writer_and_never_reports_success(self):
        board,s=self.connect();original=Path.open;opened=[]
        class DiskFull:
            def __init__(self,wrapped):self.wrapped=wrapped
            def __enter__(self):return self
            def __exit__(self,*args):self.wrapped.close()
            def write(self,data):raise OSError('simulated disk full')
        def disk_open(path,*args,**kwargs):
            f=original(path,*args,**kwargs)
            if args and args[0]=='xb':opened.append(f);return DiskFull(f)
            return f
        with patch.object(Path,'open',disk_open):
            s.submit('start',AcquisitionSettings(len_mode=1,length=100,mode=1))
            wait(s,lambda x:x['state']=='failed');self.assertTrue(s.wait(3))
        self.assertEqual(s.snapshot()['completed'],0);self.assertTrue(all(f.closed for f in opened))
        meta=list(s.directory.glob('*.partial.hex.json'))
        self.assertFalse(json.loads(meta[0].read_text('utf-8'))['complete'])

    def test_metadata_failure_keeps_partial_name(self):
        board,s=self.connect();original=Path.open
        def disk_open(path,*args,**kwargs):
            if str(path).endswith('.json.tmp'):raise OSError('metadata storage failed')
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',disk_open):
            s.submit('start',AcquisitionSettings(len_mode=1,length=11,mode=1))
            wait(s,lambda x:x['state']=='failed');self.assertTrue(s.wait(3))
        self.assertEqual(s.snapshot()['completed'],0)
        self.assertTrue(list(s.directory.glob('*.partial.hex')))
        self.assertFalse([p for p in s.directory.glob('*.hex') if '.partial.' not in p.name])

    def test_repeat_gap_freezes_configuration_until_stop_repeat(self):
        board,s=self.connect()
        s.submit('start',AcquisitionSettings(len_mode=1,length=10,mode=1,gap_ms=1000),repeat=True)
        wait(s,lambda x:x['completed']==1 and x['status'].get('GAP_LEFT_MS',0)>0)
        self.assertFalse(s.snapshot()['can_start'])
        with self.assertRaises(RuntimeError):s.submit('configure',AcquisitionSettings())
        s.submit('stop_repeat');wait(s,lambda x:x['can_start'])

    def test_stop_repeat_during_second_arm_acknowledgment_is_not_lost(self):
        board,s=self.connect();board.arm_gate=threading.Event()
        s.submit('start',AcquisitionSettings(len_mode=1,length=10,mode=1,gap_ms=0),repeat=True)
        end=time.monotonic()+3
        while board.arm_count<2 and time.monotonic()<end:time.sleep(.005)
        self.assertEqual(board.arm_count,2)
        s.submit('stop_repeat');board.arm_gate.set()
        wait(s,lambda x:x['completed']>=2)
        self.assertFalse(s.snapshot()['repeat'])
        time.sleep(.1);self.assertEqual(board.arm_count,2)

    def test_rejected_executed_arm_does_not_reuse_previous_configuration(self):
        board,s=self.connect()
        s.submit('start',AcquisitionSettings(len_mode=1,length=10,mode=1,gap_ms=0))
        wait(s,lambda x:x['completed']==1 and x['can_start'])
        board.fault='reject_executed_arm'
        s.submit('start',AcquisitionSettings(len_mode=1,length=20,mode=0))
        snap=wait(s,lambda x:bool(x['error']) and not x['busy'])
        self.assertIsNone(snap['active_settings'])
        self.assertFalse(snap['can_force'])
        board.phase='done'
        wait(s,lambda x:x['can_read']);s.submit('read')
        snap=wait(s,lambda x:x['completed']==2)
        meta=json.loads(Path(snap['last_path']+'.json').read_text('utf-8'))
        self.assertIsNone(meta['active_settings'])
        self.assertEqual(meta['status']['SAMPLES'],20)

if __name__=='__main__':unittest.main()
