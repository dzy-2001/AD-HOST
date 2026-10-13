import gc
from pathlib import Path
import queue
import threading
from types import SimpleNamespace
import unittest
import weakref

import numpy as np

from ad_host.plot_window import PlotWindow
from ad_host.recording import Recording


class PlotLifecycleTests(unittest.TestCase):
    def test_close_releases_unpolled_result_and_late_worker_result(self):
        # A completed worker can publish just before the user closes the popup.
        # App keeps the closed popup object until it is opened again.
        samples = np.zeros((1000, 2), dtype=np.uint16)
        reference = weakref.ref(samples)
        messages = queue.SimpleQueue()
        messages.put(('loaded', Recording(Path('example.hex'), samples)))
        del samples
        window = SimpleNamespace(closed=False, _cancel=threading.Event(),
                                 _poll_id=None, _zoom_id=None, _messages=messages,
                                 recording=None, current_view=None,
                                 destroy=lambda: None)
        PlotWindow.close(window)
        self.assertTrue(window._cancel.is_set())
        # Simulate an already-running worker publishing after close, then exiting.
        messages.put(('loaded', messages.get_nowait()[1]))
        del messages
        gc.collect()
        self.assertIsNone(reference(), 'Closed popup retained parsed samples')


if __name__ == '__main__':
    unittest.main()
