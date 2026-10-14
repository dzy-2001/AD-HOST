import json
from pathlib import Path
import tempfile
import unittest
from src.models.recording import load_recording,make_view
from src.models.waveform import sample_at,measurement


class V28RecordingTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/'record.hex';self.path.write_bytes(b'08000ABC'*10000)
        self.meta=dict(protocol='V28',complete=True,written_hex_bytes=80000,sample_rate_hz=5000000,
                       status=dict(SAMPLES=10000,TOTAL=40000,HEX_CHARS=80000,BLOCKS=5,ACTIVE_PRE=3000,
                                   RATE=100000000,CFG_RATE_MSPS=20,ACTIVE_RATE_MSPS=5))

    def load(self):
        Path(str(self.path)+'.json').write_text(json.dumps(self.meta),'utf-8')
        return load_recording(self.path)

    def test_saved_rate_drives_plot_and_cursor_time_after_reopen(self):
        record=self.load();self.assertEqual(record.sample_rate_hz,5000000)
        curve=make_view(record);self.assertAlmostEqual(curve.time_ms[0],-.6)
        self.assertAlmostEqual(curve.time_ms[-1],1.3998)
        a=sample_at(record,0);b=sample_at(record,.001)
        self.assertEqual(a.index,3000);self.assertEqual(b.index,3005)
        self.assertAlmostEqual(measurement(a,b)['time_ms'],.001)

    def test_missing_or_conflicting_rate_metadata_rejected(self):
        self.meta['status'].pop('ACTIVE_RATE_MSPS')
        with self.assertRaises(ValueError):self.load()
        self.meta['status']['ACTIVE_RATE_MSPS']=5;self.meta['sample_rate_hz']=100000000
        with self.assertRaises(ValueError):self.load()

    def test_legacy_v26_and_plain_hex_keep_100_msps(self):
        self.meta['protocol']='V26';self.meta.pop('sample_rate_hz')
        self.meta['status'].pop('CFG_RATE_MSPS');self.meta['status'].pop('ACTIVE_RATE_MSPS')
        self.assertEqual(self.load().sample_rate_hz,100000000)
        Path(str(self.path)+'.json').unlink()
        self.assertEqual(load_recording(self.path).sample_rate_hz,100000000)


if __name__=='__main__':unittest.main()
