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


def run(v28=False):
    app,window,controller=create_application();app.setQuitOnLastWindowClosed(False);window.show()
    with tempfile.TemporaryDirectory() as directory:
        board=Simulator(fragment=7,fault='identity_changed',rate_support=v28)
        try:
            window.host.setText('127.0.0.1');window.port.setValue(board.port);window.output.setText(str(Path(directory)/'archives'))
            window.len_mode.setCurrentIndex(1);window.length.setValue(10001);window.pre.setValue(30)
            assert window.length.suffix()==' 点' and '采样点数' in window.length_label.text()
            assert '70%' in window.pre_hint.text()
            assert '+6,621.094 V' in window.vth_hint.text()
            window.vth.setValue(3072);window.ith.setValue(3072)
            assert window.vth_hint.text()=='+15,000.000 V' and window.ith_hint.text()=='+120.000 A'
            assert window.ith_hint.property('cssClass')=='threshold-value'
            window.vth.setValue(2500);window.ith.setValue(1500)
            assert '手动触发' in window.mode_hint.text()
            assert window.threshold_settings.isHidden()
            window.mode.setCurrentIndex(1);assert not window.threshold_settings.isHidden()
            window.mode.setCurrentIndex(0)
            if v28:
                window.len_mode.setCurrentIndex(0);window.length.setValue(2);window.rate.setValue(5)
                assert '10,000' in window.estimate.text() and '2.000000</b> ms' in window.estimate.text()
            window.connect_button.click();original=controller.session;controller.connect_device();assert controller.session is original
            pump(app,lambda:controller.session.snapshot()['can_start']);controller.refresh()
            if v28:
                window.actions['configure'].click()
                pump(app,lambda:not controller.session.snapshot()['busy'] and controller.session.snapshot()['status'].get('CFG_RATE_MSPS')==5)
                assert 'CFG 0,2,30,0,2500,0,1500,4,3,1000,5' in [c for c,t in board.commands]
                assert not any(c.startswith('RATE ') for c,t in board.commands)
                assert 'ARM' not in [c for c,t in board.commands]
                controller.refresh()
            window.actions['start'].click();pump(app,lambda:controller.session.snapshot()['can_force']);controller.refresh()
            assert window.actions['force'].isEnabled();window.actions['force'].click()
            pump(app,lambda:controller.session.snapshot()['completed']==1);controller.refresh()
            assert not (Path(directory)/'archives').exists()
            path=Path(controller.session.snapshot()['last_path']);assert path.read_bytes()==b'08000ABC'*(10000 if v28 else 10001)
            window.latest_button.click();wave=controller.waveforms[-1]
            pump(app,lambda:wave.recording is not None and not wave.busy)
            assert wave.recording.trigger_index==3000
            assert wave.recording.sample_rate_hz==(5000000 if v28 else 100000000)
            assert math.isclose(wave.current_view.time_ms[0],-.6 if v28 else -.03,abs_tol=1e-12)
            before=wave.view.axes[0].get_xlim()
            wave.scroll(SimpleNamespace(inaxes=wave.view.axes[0],xdata=0,button='up'))
            assert wave.view.axes[0].get_xlim()[1]-wave.view.axes[0].get_xlim()[0]<before[1]-before[0]
            wave.view.start.setValue(2990);wave.view.stop.setValue(3011);wave.apply_range()
            pump(app,lambda:len(wave.current_view.indices)<30)
            assert 3000 in wave.current_view.indices
            wave.set_mode('measure');wave.set_cursor('A',0);wave.set_cursor('B',.001 if v28 else .00005)
            assert wave.cursors['A'].index==3000 and wave.cursors['B'].index==3005
            wave.motion(SimpleNamespace(inaxes=wave.view.axes[0],xdata=.0004 if v28 else .00002));assert wave.view.readout.cells['hover']['index'].text()=='3,002'
            assert wave.view.readout.cells['hover']['voltage_raw'].text()=='2048'
            assert wave.view.readout.cells['hover']['current_raw'].text()=='2748'
            assert wave.view.readout.cells['hover']['current'].text()=='82.031'
            assert wave.view.axes[1].get_ylabel()=='Current (A)'
            assert wave.view.readout.cells['A']['voltage_raw'].text()=='2048'
            assert wave.view.readout.cells['B']['voltage_raw'].text()=='2048'
            assert wave.view.readout.cells['delta']['voltage_raw'].text()=='+0'
            assert wave.view.readout.cells['delta']['index'].text()=='+5'
            assert wave.view.readout.cells['delta']['time'].text()==('+0.001000000' if v28 else '+0.000050000')
            wave.save(Path(directory)/'plot.png');assert (Path(directory)/'plot.png').stat().st_size>1000
            screenshots=os.environ.get('AD_HOST_SCREENSHOTS')
            if screenshots:
                output=Path(screenshots);output.mkdir(parents=True,exist_ok=True);app.processEvents();wave.view.canvas.draw()
                window.grab().save(str(output/'main.png'));wave.view.grab().save(str(output/'waveform.png'))
                window.mode.setCurrentIndex(1);app.processEvents()
                window.grab().save(str(output/'main-auto.png'))
                window.mode.setCurrentIndex(0)
                wave.view.resize(950,680);app.processEvents()
                wave.view.grab().save(str(output/'waveform-small.png'))
                window.resize(950,680);app.processEvents()
                start_button=window.actions['start']
                assert window.centralWidget().rect().contains(start_button.mapTo(window.centralWidget(),start_button.rect().center()))
                window.grab().save(str(output/'main-small.png'))
                window.activateWindow();window.len_mode.showPopup();app.processEvents()
                window.len_mode.view().window().grab().save(str(output/'combo-popup.png'))
                window.len_mode.hidePopup()
            wave.overview();pump(app,lambda:len(wave.current_view.indices)>100)
            wave.close();pump(app,lambda:wave.finished);assert wave.recording is None
            controller.open_plot();reopened=controller.waveforms[-1];assert reopened is not wave
            reopened.load_path(path)
            assert all(cell.text()=='—' for row in reopened.view.readout.cells.values() for cell in row.values())
            reopened.close();pump(app,lambda:reopened.finished)
            assert board.interleaved==[]
            controller.close();pump(app,lambda:window.allow_close)
        finally:
            controller.close();board.close();pump(app,lambda:window.allow_close)
    print('PASS: Qt acquisition, relaxed version, icons, zoom, raw cursors, export, close/reopen')


if __name__=='__main__':run('--v28' in sys.argv)
