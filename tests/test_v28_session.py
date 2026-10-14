import json
from pathlib import Path
import tempfile
import time
import unittest
from ad_host.core import CaptureConfig
from src.models.v26_protocol import AcquisitionSettings
from src.models.v26_session import V26Session
from tools.v26_simulator import Simulator


def wait(session,predicate,timeout=5):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        snap=session.snapshot()
        if predicate(snap):return snap
        time.sleep(.005)
    raise AssertionError(session.snapshot())


class V28SessionTests(unittest.TestCase):
    def connect(self,**kwargs):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        board=Simulator(**kwargs);self.addCleanup(board.close)
        session=V26Session(CaptureConfig('127.0.0.1',board.port,Path(temp.name)),poll_interval=.01)
        self.addCleanup(lambda:(session.stop(),session.wait(3)))
        session.start();wait(session,lambda s:s['state']=='connected')
        return board,session

    def test_time_mode_low_rate_saves_actual_rate_and_raw_timing(self):
        board,s=self.connect(rate_support=True)
        s.submit('start',AcquisitionSettings(length=2,mode=1,rate_msps=5))
        snap=wait(s,lambda x:x['completed']==1)
        path=Path(snap['last_path']);self.assertEqual(path.stat().st_size,80000)
        meta=json.loads(Path(str(path)+'.json').read_text('utf-8'))
        self.assertEqual(meta['protocol'],'V28');self.assertEqual(meta['sample_rate_hz'],5000000)
        self.assertEqual(meta['status']['ACTIVE_PRE'],3000)
        self.assertEqual(meta['status']['CFG_SAMPLES'],1) # time mode does not depend on this register
        self.assertEqual(meta['adc_clock_hz'],100000000)
        self.assertEqual(meta['status']['TRIGGER_DELAY_TICKS'],17);self.assertEqual(meta['status']['TRIGGER_PHASE'],3)
        self.assertIn('CFG 0,2,30,1,2048,0,2048,4,3,1000,5',[c for c,t in board.commands])
        self.assertEqual(board.interleaved,[])

    def test_rate_button_command_does_not_arm_and_rejected_write_invalidates_config(self):
        board,s=self.connect(rate_support=True)
        s.submit_command('RATE 5');wait(s,lambda x:not x['busy'] and x['status'].get('CFG_RATE_MSPS')==5)
        self.assertNotIn('ARM',[c for c,t in board.commands])
        s.submit('configure',AcquisitionSettings(length=2,rate_msps=5));wait(s,lambda x:not x['busy'] and x['configured'] is not None)
        board.fault='reject_rate';s.submit('rate',20)
        snap=wait(s,lambda x:not x['busy'] and bool(x['error']))
        self.assertIsNone(snap['configured']);self.assertEqual(snap['status']['CFG_RATE_MSPS'],20)
        self.assertNotIn('ARM',[c for c,t in board.commands])

    def test_rate_change_is_blocked_while_waiting_for_trigger(self):
        board,s=self.connect(rate_support=True)
        s.submit('start',AcquisitionSettings(len_mode=1,length=100,rate_msps=5));wait(s,lambda x:x['can_force'])
        self.assertFalse(s.snapshot()['can_set_rate'])
        with self.assertRaises(RuntimeError):s.submit('rate',20)
        self.assertNotIn('RATE 20',[c for c,t in board.commands])

    def test_ten_argument_command_explicitly_resets_v28_rate_to_100(self):
        board,s=self.connect(rate_support=True)
        s.submit('rate',5);wait(s,lambda x:not x['busy'] and x['status'].get('CFG_RATE_MSPS')==5)
        s.submit_command('CFG 1,100,30,0,2500,0,1500,4,3,1000')
        wait(s,lambda x:not x['busy'] and x['configured'] is not None)
        self.assertEqual(s.snapshot()['configured']['rate_msps'],100)
        self.assertIn('CFG 1,100,30,0,2500,0,1500,4,3,1000,100',[c for c,t in board.commands])

    def test_wrong_active_or_configured_rate_never_gets_record(self):
        for fault in ('active_rate_mismatch','cfg_rate_mismatch'):
            with self.subTest(fault=fault):
                board,s=self.connect(rate_support=True,fault=fault)
                s.submit('start',AcquisitionSettings(len_mode=1,length=100,mode=1,rate_msps=5))
                wait(s,lambda x:bool(x['error']) and not x['busy'])
                self.assertNotIn('GET',[c for c,t in board.commands]);self.assertEqual(s.snapshot()['completed'],0)

    def test_legacy_device_connects_and_rejects_low_rate_before_cfg(self):
        board,s=self.connect()
        self.assertTrue(s.snapshot()['can_start']);self.assertFalse(s.snapshot()['can_set_rate'])
        s.submit('start',AcquisitionSettings(rate_msps=5));wait(s,lambda x:bool(x['error']) and not x['busy'])
        self.assertFalse(any(c.startswith('CFG') or c=='ARM' for c,t in board.commands))

    def test_reconnected_record_uses_active_rate_not_next_configured_rate(self):
        board,s=self.connect(rate_support=True);s.stop();self.assertTrue(s.wait(3))
        board.active=[1,100,30,0,2500,0,1500,4,3,0,5]
        board.config=[1,200,30,0,2500,0,1500,4,3,0,20];board.samples_register=200;board.phase='done'
        new=V26Session(s.config,poll_interval=.01);self.addCleanup(lambda:(new.stop(),new.wait(3)))
        new.start();wait(new,lambda x:x['can_read']);new.submit('read')
        snap=wait(new,lambda x:x['completed']==1)
        meta=json.loads(Path(snap['last_path']+'.json').read_text('utf-8'))
        self.assertEqual(meta['sample_rate_hz'],5000000);self.assertIsNone(meta['active_settings'])
        self.assertEqual(meta['status']['CFG_RATE_MSPS'],20)


if __name__=='__main__':unittest.main()
