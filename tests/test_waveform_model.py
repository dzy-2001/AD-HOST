import unittest
from pathlib import Path
import numpy as np


class WaveformModelTests(unittest.TestCase):
    def setUp(self):
        from src.models.recording import Recording
        self.recording=Recording(Path('test.hex'),np.array([[0,10],[2048,20],[4095,30]],dtype=np.uint16),1)

    def test_cursor_snap_and_values_use_original_samples(self):
        from src.models.waveform import sample_at
        point=sample_at(self.recording,.000009)
        self.assertEqual(point.index,2)
        self.assertAlmostEqual(point.time_ms,.00001)
        self.assertAlmostEqual(point.voltage,4095*12/4096-6)
        self.assertEqual(point.current,30)
        self.assertEqual(point.voltage_raw,4095)

    def test_cursor_clamps_and_range_covers_endpoints(self):
        from src.models.waveform import sample_at,visible_range
        self.assertEqual(sample_at(self.recording,-100).index,0)
        self.assertEqual(sample_at(self.recording,100).index,2)
        self.assertEqual(visible_range(self.recording,-100,100),(0,3))
        self.assertEqual(visible_range(self.recording,0,.00001),(1,3))

    def test_delta_and_pre100_coordinates(self):
        from src.models.waveform import sample_at,measurement
        from src.models.recording import Recording
        record=Recording(self.recording.path,self.recording.samples,3)
        a=sample_at(record,-.00003);b=sample_at(record,-.00001)
        delta=measurement(a,b)
        self.assertAlmostEqual(delta['time_ms'],.00002)
        self.assertEqual(delta['samples'],2)
        self.assertEqual(delta['current'],20)
        self.assertEqual(delta['voltage_raw'],4095)
        self.assertEqual(measurement(b,a)['voltage_raw'],-4095)

    def test_nonfinite_coordinates_rejected(self):
        from src.models.waveform import sample_at,visible_range
        for value in (float('nan'),float('inf')):
            with self.assertRaises(ValueError):sample_at(self.recording,value)
            with self.assertRaises(ValueError):visible_range(self.recording,0,value)
