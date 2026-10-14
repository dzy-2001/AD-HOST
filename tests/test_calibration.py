from pathlib import Path
import unittest
import numpy as np
from src.models.recording import Recording,make_view
from src.models.waveform import sample_at,measurement


class CalibrationTests(unittest.TestCase):
    def setUp(self):
        self.record=Recording(Path('probe.hex'),np.array([[0,0],[2048,2048],[3072,3072],[4095,4095]],dtype=np.uint16))

    def test_probe_ranges_zero_and_120_amp_example(self):
        view=make_view(self.record)
        np.testing.assert_allclose(view.voltage,[-30000,0,15000,29985.3515625])
        np.testing.assert_allclose(view.current,[-240,0,120,239.8828125])

    def test_cursor_uses_physical_units_and_retains_both_raw_counts(self):
        point=sample_at(self.record,.00002)
        self.assertEqual(point.voltage,15000);self.assertEqual(point.current,120)
        self.assertEqual(point.voltage_raw,3072);self.assertEqual(point.current_raw,3072)

    def test_difference_uses_physical_units_without_unsigned_wrap(self):
        a=sample_at(self.record,0);b=sample_at(self.record,.00002)
        delta=measurement(b,a)
        self.assertEqual(delta['voltage'],-45000);self.assertEqual(delta['current'],-360)
        self.assertEqual(delta['voltage_raw'],-3072);self.assertEqual(delta['current_raw'],-3072)


if __name__=='__main__':unittest.main()
