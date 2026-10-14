"""Real Qt workflow and waveform interactions; offscreen is supported."""
import os
import sys
os.environ.setdefault('QT_QPA_PLATFORM','windows' if sys.platform=='win32' else 'offscreen')
import math
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.app import create_application
from tools.v26_simulator import Simulator


def pump(app,predicate,timeout=15):
    end=time.monotonic()+timeout
    while not predicate():
        assert time.monotonic()<end,'Qt operation timed out'
        app.processEvents();time.sleep(.01)
    app.processEvents()


def run():
    app,window,controller=create_application();app.setQuitOnLastWindowClosed(False);window.show()
    with tempfile.TemporaryDirectory() as directory:
        board=Simulator(fragment=7,fault='identity_changed')
        try:
            window.host.setText('127.0.0.1');window.port.setValue(board.port);window.output.setText(directory)
            window.len_mode.setCurrentIndex(1);window.length.setValue(10001);window.pre.setValue(30)
            window.connect_button.click();original=controller.session;controller.connect_device();assert controller.session is original
            pump(app,lambda:controller.session.snapshot()['can_start']);controller.refresh()
            window.actions['start'].click();pump(app,lambda:controller.session.snapshot()['can_force']);controller.refresh()
            assert window.actions['force'].isEnabled();window.actions['force'].click()
            pump(app,lambda:controller.session.snapshot()['completed']==1);controller.refresh()
            path=Path(controller.session.snapshot()['last_path']);assert path.read_bytes()==b'08000ABC'*10001
            window.latest_button.click();wave=controller.waveforms[-1]
            pump(app,lambda:wave.recording is not None and not wave.busy)
            assert wave.recording.trigger_index==3000
            assert math.isclose(wave.current_view.time_ms[0],-.03,abs_tol=1e-12)
            before=wave.view.axes[0].get_xlim()
            wave.scroll(SimpleNamespace(inaxes=wave.view.axes[0],xdata=0,button='up'))
            assert wave.view.axes[0].get_xlim()[1]-wave.view.axes[0].get_xlim()[0]<before[1]-before[0]
            wave.view.start.setValue(2990);wave.view.stop.setValue(3011);wave.apply_range()
            pump(app,lambda:len(wave.current_view.indices)<30)
            assert 3000 in wave.current_view.indices
            wave.set_mode('measure');wave.set_cursor('A',0);wave.set_cursor('B',.00005)
            assert wave.cursors['A'].index==3000 and wave.cursors['B'].index==3005
            wave.motion(SimpleNamespace(inaxes=wave.view.axes[0],xdata=.00002));assert '3,002' in wave.view.readout.text()
            wave.save(Path(directory)/'plot.png');assert (Path(directory)/'plot.png').stat().st_size>1000
            screenshots=os.environ.get('AD_HOST_SCREENSHOTS')
            if screenshots:
                output=Path(screenshots);output.mkdir(parents=True,exist_ok=True);app.processEvents();wave.view.canvas.draw()
                window.grab().save(str(output/'main.png'));wave.view.grab().save(str(output/'waveform.png'))
            wave.overview();pump(app,lambda:len(wave.current_view.indices)>100)
            wave.close();pump(app,lambda:wave.finished);assert wave.recording is None
            controller.open_plot();reopened=controller.waveforms[-1];assert reopened is not wave
            reopened.load_path(path);reopened.close();pump(app,lambda:reopened.finished)
            assert board.interleaved==[]
            controller.close();pump(app,lambda:window.allow_close)
        finally:
            controller.close();board.close();pump(app,lambda:window.allow_close)
    print('PASS: Qt acquisition, relaxed version, icons, zoom, raw cursors, export, close/reopen')


if __name__=='__main__':run()
