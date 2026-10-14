from pathlib import Path
import tempfile
import time
import unittest
from src.models.core import CaptureConfig
from src.models.v26_protocol import AcquisitionSettings
from src.models.v26_session import V26Session
from tools.v26_simulator import Simulator


FST = ('ID:ADFC,VER:1000,INIT:0,IERR:4,HCLK:168000000,SDCLK:56000000,'
       'STATUS:2061,EVENTS:0000,RDY:1,DONE:0,VALID:0,RR:0,BR:0,LAST:0,'
       'SDONE:0,SETERR:0,STARTOK:0,SET:0,0,GETERR:0,TXSTATE:0,TXERR:0,'
       'PENDING:0,DROP:0,DISC:0,DISCSTATE:0,DISCSENT:0,CONSUMED:0,CMD:0,'
       'CLR:0,START:0,RNEXT:0,ACK:0,REL:0,TOTAL:0,BLOCKS:0,LASTLEN:0,'
       'FAILBR:NONE,FAILSTATE:0,FAILST:0000,FAILEV:0000,TCPRET:0,'
       'FAIL_BLOCK_NO:0,FAIL_BLOCK_LEN:0,FAIL_BLOCK_POS:0,EXPECTED_TOTAL:0,'
       'SENT_BYTES:0,NAGLEOFF:1,SNDBUF:5840,SNDQ:0,ERRMEM:0,MEMSTREAK:0,'
       'MEMMAX:0,SENDOK:0,OUTERR:0')


class DiagnosticBoard(Simulator):
    def __init__(self, response=b'\r\n?'):
        self.tst_response=response
        super().__init__(rate_support=True)

    def _handle(self, conn, cmd):
        if cmd=='FST' or cmd=='TST' and self.tst_response is not None:
            self.commands.append((cmd,time.monotonic()))
            return FST.encode()+b'\r\n*' if cmd=='FST' else self.tst_response
        return super()._handle(conn,cmd)


def wait(session,predicate):
    end=time.monotonic()+3
    while time.monotonic()<end:
        snap=session.snapshot()
        if predicate(snap):return snap
        time.sleep(.005)
    raise AssertionError(session.snapshot())


class DiagnosticConnectionTests(unittest.TestCase):
    def connect(self,response=b'\r\n?'):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        board=DiagnosticBoard(response);self.addCleanup(board.close)
        session=V26Session(CaptureConfig('127.0.0.1',board.port,Path(temp.name)),poll_interval=.01)
        self.addCleanup(lambda:(session.stop(),session.wait(3)))
        session.start()
        wait(session,lambda s:s['state'] in ('connected','failed'))
        return board,session

    def test_rejected_tst_keeps_diagnostics_available_without_auto_reset(self):
        board,s=self.connect();snap=s.snapshot()
        self.assertEqual(snap['state'],'connected')
        self.assertFalse(snap['can_start']);self.assertEqual(snap['status'],{})
        self.assertIn('IERR=4',snap['error']);self.assertIn('1000',snap['error'])
        self.assertIn('版本',snap['error']);self.assertIn('?',snap['diagnostics']['TST'])
        for action in ('start','read','release','force','clear'):
            with self.assertRaises(RuntimeError):s.submit(action,AcquisitionSettings())
        s.submit_command('FST');wait(s,lambda x:not x['busy'])
        self.assertEqual(s.snapshot()['diagnostics']['FST'],FST)
        names=[c for c,t in board.commands]
        self.assertEqual(names.count('TST'),1);self.assertNotIn('FINIT',names)
        board.tst_response=None;s.submit_command('TST')
        snap=wait(s,lambda x:x['can_start'])
        self.assertFalse(snap['error']);self.assertFalse(snap['status_error'])
        s.submit('start',AcquisitionSettings(len_mode=1,length=10,mode=1,rate_msps=5))
        wait(s,lambda x:x['completed']==1)

    def test_lost_status_invalidates_previous_ready_state(self):
        board,s=self.connect(None);self.assertTrue(s.snapshot()['can_start'])
        board.tst_response=b'\r\n?'
        snap=wait(s,lambda x:bool(x.get('status_error')) or x['state']=='failed')
        self.assertEqual(snap['state'],'connected');self.assertFalse(snap['can_start'])
        self.assertEqual(snap['status'],{});self.assertFalse(snap['repeat'])

    def test_malformed_complete_tst_allows_manual_requery(self):
        board,s=self.connect(b'STATUS:2061\r\n*')
        self.assertEqual(s.snapshot()['state'],'connected')
        self.assertIn('缺少字段',s.snapshot()['error'])
        board.tst_response=None;s.submit_command('TST')
        wait(s,lambda x:x['can_start'])


if __name__=='__main__':unittest.main()
