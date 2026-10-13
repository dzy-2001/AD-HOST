"""Verify the maximum V26 record over real TCP at a representative 6 MB/s."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ad_host.core import CaptureConfig
from ad_host.v26_protocol import AcquisitionSettings
from ad_host.v26_session import V26Session
from tools.v26_simulator import Simulator

with tempfile.TemporaryDirectory() as directory:
    board=Simulator(mbps=6)
    session=V26Session(CaptureConfig('127.0.0.1',board.port,Path(directory),queue_chunks=16))
    start=time.monotonic();peak=0;armed=False;session.start()
    try:
        while time.monotonic()-start<90:
            s=session.snapshot();peak=max(peak,s['pending'])
            if s['state']=='failed':raise AssertionError(s)
            if s['can_start'] and not armed:
                session.submit('start',AcquisitionSettings(length=200,pre=30,mode=1));armed=True
            if s['completed']==1:break
            time.sleep(.01)
        else:raise AssertionError(session.snapshot())
        path=Path(s['last_path']);assert path.stat().st_size==160000000
        digest=hashlib.sha256()
        with path.open('rb') as f:
            while data:=f.read(1000000):digest.update(data)
        expected=hashlib.sha256()
        for _ in range(160):expected.update(b'08000ABC'*125000)
        assert digest.digest()==expected.digest()
        meta=json.loads(Path(str(path)+'.json').read_text('utf-8'))
        assert meta['complete'] and meta['status']['ACTIVE_PRE']==6000000
        assert meta['written_hex_bytes']==160000000 and not board.interleaved
        assert peak<=17*1048576
        print(f'PASS: 160 MB / 20 million pairs, SHA256 exact, elapsed={time.monotonic()-start:.2f}s, peak pending={peak/1048576:.2f}MiB')
    finally:
        session.stop();assert session.wait(10);board.close()
