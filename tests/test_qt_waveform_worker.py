import tempfile
import threading
import time
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from src.controllers.waveform_worker import WaveformWorker
from src.models.recording import ParseCancelled,load_recording


class WorkerTests(TestCase):
    def test_latest_load_wins_and_close_releases_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            first=Path(tmp)/'one.hex';second=Path(tmp)/'two.hex';first.write_bytes(b'08000001');second.write_bytes(b'08000002')
            entered=threading.Event();gate=threading.Event()
            def controlled(path,**kwargs):
                if path==first:
                    entered.set();gate.wait(2)
                    if kwargs['cancel'].is_set():raise ParseCancelled()
                return load_recording(path,**kwargs)
            with patch('src.controllers.waveform_worker.load_recording',controlled):
                worker=WaveformWorker()
                try:
                    worker.request('load',first);self.assertTrue(entered.wait(1));token=worker.request('load',second);gate.set()
                    end=time.monotonic()+3;result=None
                    while result is None and time.monotonic()<end:result,_=worker.poll();time.sleep(.01)
                    self.assertEqual(result[0],token);self.assertIsNone(result[3]);self.assertEqual(int(result[2][0].samples[0,1]),2)
                finally:gate.set();worker.close();worker.thread.join(3)
                self.assertFalse(worker.thread.is_alive());self.assertIsNone(worker.result);self.assertIsNone(worker.pending)

    def test_close_during_load_discards_late_result(self):
        entered=threading.Event();gate=threading.Event()
        def blocked(*args,**kwargs):entered.set();gate.wait(2);raise ParseCancelled()
        with patch('src.controllers.waveform_worker.load_recording',blocked):
            worker=WaveformWorker();worker.request('load',Path('unused'));self.assertTrue(entered.wait(1));worker.close();gate.set();worker.thread.join(3)
            self.assertFalse(worker.thread.is_alive());self.assertEqual(worker.poll()[0],None)
