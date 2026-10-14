from pathlib import Path
import tempfile
import time
import unittest
from src.models.core import CaptureConfig
from src.models.v26_session import V26Session
from tools.v26_simulator import Simulator


class DiagnosticCommandsTests(unittest.TestCase):
    def connect(self,**kwargs):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        board=Simulator(rate_support=True,**kwargs);self.addCleanup(board.close)
        session=V26Session(CaptureConfig('127.0.0.1',board.port,Path(temp.name)))
        self.addCleanup(lambda:(session.stop(),session.wait(3)))
        session.start();self.wait(session,lambda s:s['state']=='connected')
        return board,session

    def wait(self,session,predicate):
        end=time.monotonic()+3
        while time.monotonic()<end:
            snap=session.snapshot()
            if predicate(snap):return snap
            time.sleep(.005)
        self.fail(str(session.snapshot()))

    def test_manual_queries_log_their_received_payloads(self):
        board,s=self.connect(fragment=3)
        for command,expected in [('VER','V1.0.15 (V28)'),('FST','ID:ADFC'),('FREG','ID:ADFC'),('TST','STATUS:2061')]:
            before=len(s.events());s.submit_command(command);self.wait(s,lambda x:not x['busy'])
            events=[e['message'] for e in s.events()[before:]]
            self.assertTrue(any('接收 '+command in e and expected in e for e in events),events)
            self.assertIn(expected,s.snapshot()['diagnostics'][command])
        before=len(s.events());time.sleep(.25)
        self.assertFalse(any('接收 TST' in e['message'] for e in s.events()[before:]),'Automatic polling must not flood the log')

    def test_command_entry_normalizes_case_and_surrounding_spaces(self):
        board,s=self.connect()
        for text,expected in [('  ver  ','VER'),('\tfst\t','FST'),('tSt','TST'),(' freg ','FREG'),('rate\t5','RATE 5')]:
            before=len(board.commands)
            try:s.submit_command(text)
            except (ValueError,RuntimeError) as exc:self.fail(f'{text!r} rejected locally: {exc}')
            self.wait(s,lambda x:not x['busy'])
            self.assertIn(expected,[c for c,t in board.commands[before:]])

    def test_device_rejection_is_reported_as_received_not_local_validation(self):
        board,s=self.connect(fault='identity_rejected')
        before=len(s.events());s.submit_command('VER');self.wait(s,lambda x:not x['busy'])
        self.assertIn('被设备拒绝',s.snapshot()['error'])
        self.assertTrue(any('接收 VER' in e['message'] and '?' in e['message'] for e in s.events()[before:]))

    def test_normalization_still_rejects_multiple_or_nonascii_commands(self):
        board,s=self.connect()
        for text in ('VER\rFST','VER\n','VER\0','ＶＥＲ','   ','VER extra'):
            with self.subTest(text=text),self.assertRaises(ValueError):s.submit_command(text)
        self.assertFalse(s.snapshot()['busy'])
