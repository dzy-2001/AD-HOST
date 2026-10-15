"""Exercise real V26 Tk controls and trigger-relative plot on Windows CI."""
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
assert importlib.util.find_spec('ad_host.v26_gui') is not None, 'V26 interface not implemented'
from ad_host.v26_gui import App
from tools.v26_simulator import Simulator

def pump(root,predicate,timeout=15):
    end=time.monotonic()+timeout
    while not predicate():
        assert time.monotonic()<end,'GUI operation timed out'
        root.update();time.sleep(.01)
    root.update()

with tempfile.TemporaryDirectory() as directory:
    board=Simulator(fragment=7)
    root=tk.Tk();app=App(root)
    try:
        app.host.set('127.0.0.1');app.port.set(str(board.port));app.output.set(directory)
        app.len_mode.set('采样点数');app.length.set('10001');app.pre.set('30')
        app.connect_button.invoke();pump(root,lambda:app.session and app.session.snapshot()['can_start'])
        app.begin_capture();pump(root,lambda:app.session.snapshot()['can_force'])
        app.refresh();assert str(app.force_button['state'])=='normal'
        assert not app.session.snapshot()['completed']
        app.force_button.invoke();pump(root,lambda:app.session.snapshot()['can_read'])
        app.refresh();app.read_button.invoke();pump(root,lambda:app.session.snapshot()['completed']==1)
        path=Path(app.session.snapshot()['last_path']);assert path.read_bytes()==b'08000ABC'*10001
        app.open_latest();window=app.plot_window
        pump(root,lambda:not window.busy)
        assert window.recording.trigger_index==3000,window.status.get()
        assert math.isclose(window.current_view.time_ms[0],-.03,abs_tol=1e-12)
        assert window.axes[1].get_xlabel()=='Time relative to trigger (ms)'
        window.axes[0].set_xlim(-.00005,.00005)
        pump(root,lambda:len(window.current_view.indices)<30)
        assert 3000 in window.current_view.indices
        window.figure.savefig(Path(directory)/'waveform.png')
        assert (Path(directory)/'waveform.png').stat().st_size>1000
        window.close();app.open_plot();app.plot_window.close()
        app.session.stop();assert app.session.wait(5)
    finally:
        root.destroy();board.close()
print('PASS: V26 GUI manual acquisition, trigger-relative zoom, export and reopen')
