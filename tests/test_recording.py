import importlib
import importlib.util
from pathlib import Path
import tempfile
import threading
import unittest

import numpy as np


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('ad_host.recording'),
                             'The offline HEX parser has not been implemented')
        self.api = importlib.import_module('ad_host.recording')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'capture.hex'

    def load(self, content, **kwargs):
        self.path.write_bytes(content)
        return self.api.load_recording(self.path, **kwargs)

    def test_ascii_decoding_big_endian_and_channel_order(self):
        # 0000/0001, 0800/0ABC, 0FFF/FFFF; catches byte swap or channel swap.
        recording = self.load(b'0000000108000ABC0FFFFFFF')
        np.testing.assert_array_equal(recording.samples, [[0, 1], [2048, 2748], [4095, 65535]])
        self.assertEqual(recording.samples.dtype, np.dtype('uint16'))
        self.assertFalse(recording.samples.flags.writeable)

    def test_voltage_formula_and_100mhz_time_axis(self):
        recording = self.load(b'0000000108000ABC0FFFFFFF')
        view = self.api.make_view(recording)
        np.testing.assert_allclose(view.voltage, [-6, 0, 5.9970703125])
        np.testing.assert_array_equal(view.current, [1, 2748, 65535])
        np.testing.assert_allclose(view.time_ms, [0, 0.00001, 0.00002], rtol=1e-12)

    def test_whitespace_lowercase_bom_and_chunk_boundary(self):
        recording = self.load(b'\xef\xbb\xbf00 00\t00 01\r\n08 00 0a bc\n', chunk_size=7)
        np.testing.assert_array_equal(recording.samples, [[0, 1], [2048, 2748]])

    def test_rejects_incomplete_pairs_and_non_hex_without_modifying_input(self):
        for content in (b'0', b'0000', b'000000', b'00000001\r\n*', b'0000GG00', b'\xff0000000', b'  \r\n'):
            with self.subTest(content=content):
                self.path.write_bytes(content)
                with self.assertRaises(ValueError):
                    self.api.load_recording(self.path, chunk_size=7)
                self.assertEqual(self.path.read_bytes(), content)

    def test_voltage_above_12bit_range_is_reported_not_masked(self):
        with self.assertRaisesRegex(ValueError, '4095'):
            self.load(b'10000001')

    def test_cancel_and_progress(self):
        cancellation = threading.Event()
        progress = []
        def update(done, total):
            progress.append((done, total))
            cancellation.set()
        with self.assertRaises(self.api.ParseCancelled):
            self.load(b'08000001' * 100, chunk_size=16, cancel=cancellation, progress=update)
        self.assertTrue(progress)
        self.assertLess(progress[0][0], progress[0][1])

    def test_file_size_limit_is_checked_before_parsing(self):
        with self.assertRaisesRegex(ValueError, '大小'):
            self.load(b'08000001' * 10, max_source_bytes=32)

    def test_overview_keeps_single_sample_peaks_in_both_channels(self):
        samples = np.full((10000, 2), 2048, dtype=np.uint16)
        samples[1234, 0] = 4095
        samples[5678, 1] = 65535
        samples[3011, 0] = 0
        recording = self.api.Recording(self.path, samples)
        view = self.api.make_view(recording, max_points=100)
        self.assertLessEqual(len(view.indices), 100)
        self.assertTrue({0, 1234, 3011, 5678, 9999}.issubset(set(view.indices)))
        self.assertTrue(np.all(np.diff(view.indices) > 0))
        self.assertEqual(view.voltage.max(), 5.9970703125)
        self.assertEqual(view.current.max(), 65535)

    def test_zoom_uses_original_samples_and_absolute_time(self):
        samples = np.column_stack((np.arange(100, dtype=np.uint16), np.arange(100, dtype=np.uint16) + 100))
        recording = self.api.Recording(self.path, samples)
        view = self.api.make_view(recording, start=50, stop=60, max_points=100)
        np.testing.assert_array_equal(view.indices, np.arange(50, 60))
        np.testing.assert_array_equal(view.current, np.arange(150, 160))
        np.testing.assert_allclose(view.time_ms[[0, -1]], [.0005, .00059])

    def test_invalid_view_range_and_sample_rate_are_rejected(self):
        recording = self.load(b'08000001' * 10)
        for kwargs in ({'start': -1}, {'start': 5, 'stop': 5}, {'stop': 11},
                       {'sample_rate_hz': 0}, {'sample_rate_hz': float('nan')}, {'max_points': 5}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.api.make_view(recording, **kwargs)


if __name__ == '__main__':
    unittest.main()
