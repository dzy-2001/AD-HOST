import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from ad_host.recording import load_recording,make_view


class TriggerRecordingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'capture.hex';self.path.write_bytes(b'08000ABC'*10)
        self.meta={'protocol':'V26','complete':True,'status':{'SAMPLES':10,'TOTAL':40,'HEX_CHARS':80,
                   'BLOCKS':1,'ACTIVE_PRE':3,'RATE':100000000,'REASON':1},'written_hex_bytes':80}

    def save_meta(self):Path(str(self.path)+'.json').write_text(json.dumps(self.meta),encoding='utf-8')

    def test_trigger_relative_time_uses_active_pre(self):
        self.save_meta();r=load_recording(self.path);view=make_view(r)
        np.testing.assert_allclose(view.time_ms[[0,3,9]],[-.00003,0,.00006],atol=1e-14)

    def test_pre100_has_only_negative_sample_times(self):
        self.meta['status']['ACTIVE_PRE']=10;self.save_meta()
        self.assertLess(make_view(load_recording(self.path)).time_ms[-1],0)

    def test_invalid_metadata_or_partial_record_is_not_silently_plotted(self):
        for key,value in [('complete',False),('written_hex_bytes',79)]:
            old=self.meta[key];self.meta[key]=value;self.save_meta()
            with self.subTest(key=key),self.assertRaises(ValueError):load_recording(self.path)
            self.meta[key]=old
        self.meta['status']['SAMPLES']=11;self.save_meta()
        with self.assertRaises(ValueError):load_recording(self.path)

    def test_current_above_twelve_bits_is_rejected_with_or_without_metadata(self):
        self.path.write_bytes(b'0800FFFF'*10);self.save_meta()
        with self.assertRaises(ValueError):load_recording(self.path)
        Path(str(self.path)+'.json').unlink()
        with self.assertRaises(ValueError):load_recording(self.path)

if __name__=='__main__':unittest.main()
