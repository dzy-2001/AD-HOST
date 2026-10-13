"""Exercise the real offline popup, worker, calibration, zoom and PNG export."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
assert importlib.util.find_spec('ad_host.plot_window') is not None, 'Offline plotting popup is not implemented'
from ad_host.gui import App


def pump(root, predicate, timeout=15):
    end = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < end, 'GUI worker did not finish'
        root.update()
        time.sleep(.01)
    root.update()


with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / 'known.hex'
    # 10001 samples: overview must be reduced; zoom must restore full detail.
    path.write_bytes(b'08000001' * 5000 + b'0FFFABCD' + b'08000002' * 5000)
    root = tk.Tk()
    root.withdraw()
    app = App(root)
    app.open_plot()
    window = app.plot_window
    window.withdraw()
    window.load_path(path)
    pump(root, lambda: not window.busy)
    assert window.recording is not None, window.status.get()
    assert len(window.recording.samples) == 10001
    assert window.current_view.voltage.max() == 5.9970703125
    assert window.current_view.current.max() == 43981
    assert len(window.current_view.indices) < 10001
    # A toolbar-equivalent x-axis change must regenerate from original samples.
    window.axes[0].set_xlim(0.04995, 0.05005)
    pump(root, lambda: len(window.current_view.indices) < 30)
    assert 5000 in window.current_view.indices
    assert window.current_view.voltage.max() == 5.9970703125
    assert window.axes[0].get_ylabel() == 'Voltage (V)'
    assert window.axes[1].get_ylabel() == 'Current (raw counts)'
    image = Path(directory) / 'view.png'
    window.figure.savefig(image)
    assert image.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
    window.close()
    app.open_plot()
    assert app.plot_window.winfo_exists()
    app.plot_window.close()
    root.destroy()
print('PASS: offline popup, HEX parsing, exact voltage/time, raw current, zoom and PNG export')
