"""Offline load, bounded view reduction, pan/zoom and raw-sample cursors."""
from pathlib import Path
from PyQt6.QtCore import QObject,QTimer
from ..models.waveform import sample_at,visible_range,measurement
from ..models.v26_protocol import reason_text
from .waveform_worker import WaveformWorker


class WaveformController(QObject):
    def __init__(self,view):
        super().__init__(view);self.view=view;self.worker=WaveformWorker();self.recording=None;self.current_view=None
        self.closed=False;self.busy=False;self.token=None;self.mode='pan';self.dragging=None;self.cursors={};self._setting=False
        self._fit_next=False;self._target_range=None;self._active_range=None
        self.timer=QTimer(self);self.timer.timeout.connect(self.poll);self.timer.start(40)
        self.zoom_timer=QTimer(self);self.zoom_timer.setSingleShot(True);self.zoom_timer.timeout.connect(self.refresh_range)
        view.choose_button.clicked.connect(self.choose);view.cancel_button.clicked.connect(self.cancel_load)
        view.close_requested.connect(self.close);view.range_button.clicked.connect(self.apply_range)
        for name in ('pan','zoom','measure'):view.tools[name].clicked.connect(lambda checked=False,n=name:self.set_mode(n))
        view.tools['home'].clicked.connect(self.overview);view.tools['trigger'].clicked.connect(self.return_trigger)
        view.tools['fit'].clicked.connect(self.fit_y);view.tools['save'].clicked.connect(self.save)
        for axis in view.axes:axis.callbacks.connect('xlim_changed',self.range_changed)
        self.connections=[view.canvas.mpl_connect(name,callback) for name,callback in
                          [('motion_notify_event',self.motion),('button_press_event',self.press),('button_release_event',self.release),('scroll_event',self.scroll)]]
        self.set_mode('pan')

    @property
    def finished(self):return not self.worker.thread.is_alive()

    def choose(self):
        path=self.view.choose_path()
        if path:self.load_path(path)

    def clear(self):
        self.recording=None;self.current_view=None;self.cursors.clear();self.dragging=None;self._active_range=None
        self.view.set_record_enabled(False)
        for line in self.view.lines:line.set_data([],[])
        for line in self.view.triggers+self.view.hover+sum(self.view.markers.values(),[]):line.set_visible(False)
        self.view.readout.clear_values();self.view.canvas.draw_idle()

    def load_path(self,path):
        if self.closed:return
        self.zoom_timer.stop();self.clear();self.busy=True;self.view.choose_button.setEnabled(False);self.view.cancel_button.setEnabled(True)
        self.view.path.setText(str(path));self.view.status.setText('正在后台解析 HEX…');self.view.progress.setValue(0)
        self.token=self.worker.request('load',Path(path))

    def cancel_load(self):
        # Supersede the in-flight load with a cancellation generation, without a new job.
        self.worker.invalidate()
        self.token=None;self.busy=False;self.view.choose_button.setEnabled(True);self.view.cancel_button.setEnabled(False)
        self.view.status.setText('解析已取消，可以选择其他文件。')

    def poll(self):
        if self.closed:return
        result,progress=self.worker.poll()
        if self.busy:self.view.progress.setValue(int(progress[0]/max(1,progress[1])*1000))
        if result is None or result[0]!=self.token:return
        _,kind,value,error=result
        if error:
            self.busy=False;self.view.choose_button.setEnabled(True);self.view.cancel_button.setEnabled(False);self.view.status.setText(str(error));return
        if kind=='load':
            self.recording,self.current_view=value;self.busy=False;self.view.choose_button.setEnabled(True);self.view.cancel_button.setEnabled(False)
            self.view.set_record_enabled(True);self.view.tools['trigger'].setEnabled(self.recording.trigger_index is not None)
            count=len(self.recording.samples);self.view.start.setMaximum(count-1);self.view.stop.setMaximum(count)
            self.view.start.setValue(0);self.view.stop.setValue(count);self.view.progress.setValue(1000)
            origin=self.recording.trigger_index
            st=(self.recording.metadata or {}).get('status',{})
            self.view.details.setText(f'{count:,} 组 · {self.recording.sample_rate_hz/1e6:g} MHz / 通道 · '+
                                      ('触发位置未知，时间从记录起点计' if origin is None else f'触发位置 {origin:,} · {reason_text(st.get("REASON",0))}'+(' · 触发样本在记录外' if origin==count else '')))
            self.view.axes[1].set_xlabel('Time relative to trigger (ms)' if origin is not None else 'Time from record start (ms)')
            for line in self.view.triggers:line.set_visible(origin is not None)
            self._active_range=(0,count);self._set_limits(self.full_limits());self.view.display_curve(self.current_view,fit=True)
            self.view.navigation.update();self.view.navigation.push_current()
        else:
            self.current_view=value;self._active_range=self._target_range;self.view.display_curve(value,fit=self._fit_next);self._fit_next=False
        self.view.status.setText(f'当前绘制 {len(self.current_view.indices):,} 个显示点；光标始终读取原始样本。')

    def full_limits(self):
        r=self.recording;origin=r.trigger_index or 0;step=1000/r.sample_rate_hz
        left=-origin*step;right=(len(r.samples)-1-origin)*step
        return (left,right) if left<right else (left-step/2,right+step/2)

    def _set_limits(self,limits):
        self._setting=True
        try:self.view.axes[0].set_xlim(*limits)
        finally:self._setting=False

    def range_changed(self,axis):
        if self.recording is not None and not self.closed and not self._setting:self.zoom_timer.start(80)

    def refresh_range(self):
        if self.recording is None or self.closed:return
        limits=self.view.axes[0].get_xlim();start,stop=visible_range(self.recording,*limits)
        self.view.start.setValue(start);self.view.stop.setValue(stop)
        if self._active_range==(start,stop):
            self.worker.invalidate();self.token=None;self._target_range=None
            if self._fit_next:self.view.display_curve(self.current_view,fit=True);self._fit_next=False
            return
        self._target_range=(start,stop);self.token=self.worker.request('view',self.recording,start,stop)

    def overview(self):
        if self.recording is None:return
        self._set_limits(self.full_limits());self._fit_next=True;self.refresh_range();self.view.canvas.draw_idle()

    def return_trigger(self):
        if self.recording is None or self.recording.trigger_index is None:return
        left,right=self.view.axes[0].get_xlim();width=max(right-left,20*1000/self.recording.sample_rate_hz)
        self._set_limits((-width/2,width/2));self.refresh_range();self.view.canvas.draw_idle()

    def fit_y(self):
        if self.current_view is not None:self._fit_next=True;self.refresh_range()

    def apply_range(self):
        if self.recording is None:return
        start,stop=self.view.start.value(),self.view.stop.value()
        if start>=stop:self.view.status.setText('起点必须小于终点。');return
        origin=self.recording.trigger_index or 0;step=1000/self.recording.sample_rate_hz
        left=(start-origin)*step;right=(stop-1-origin)*step
        if left==right:left-=step/2;right+=step/2
        self._set_limits((left,right));self._fit_next=True;self.refresh_range();self.view.canvas.draw_idle()

    def set_mode(self,mode):
        nav=self.view.navigation
        if nav.mode:
            if 'pan' in str(nav.mode).lower():nav.pan()
            else:nav.zoom()
        self.mode=mode;self.dragging=None
        if mode=='pan':nav.pan()
        elif mode=='zoom':nav.zoom()
        for name in ('pan','zoom','measure'):self.view.tools[name].setChecked(name==mode)

    def scroll(self,event):
        if self.recording is None or event.inaxes not in self.view.axes or event.xdata is None:return
        left,right=self.view.axes[0].get_xlim();step=1000/self.recording.sample_rate_hz
        factor=.8 if event.button=='up' else 1.25
        width=max(step,min((right-left)*factor,max(step,len(self.recording.samples)*step*4)))
        fraction=max(0,min(1,(event.xdata-left)/(right-left)))
        self.view.axes[0].set_xlim(event.xdata-width*fraction,event.xdata+width*(1-fraction));self.view.canvas.draw_idle()

    def press(self,event):
        if self.mode!='measure' or self.recording is None or event.inaxes not in self.view.axes or event.xdata is None or event.button!=1:return
        selected=self.view.cursor_choice.currentText()
        if self.cursors and event.x is not None:
            nearest=min(self.cursors,key=lambda n:abs(event.inaxes.transData.transform((self.cursors[n].time_ms,0))[0]-event.x))
            if abs(event.inaxes.transData.transform((self.cursors[nearest].time_ms,0))[0]-event.x)<10:selected=nearest
        self.dragging=selected;self.view.cursor_choice.setCurrentText(selected);self.set_cursor(selected,event.xdata)

    def release(self,event):self.dragging=None

    def motion(self,event):
        if self.recording is None or event.inaxes not in self.view.axes or event.xdata is None:return
        if self.dragging:self.set_cursor(self.dragging,event.xdata)
        point=sample_at(self.recording,event.xdata)
        for line in self.view.hover:line.set_xdata([point.time_ms]*2);line.set_visible(True)
        self.view.readout.set_point('hover',point)
        self.view.canvas.draw_idle()

    def set_cursor(self,name,time_ms):
        if self.recording is None:return
        point=sample_at(self.recording,time_ms);self.cursors[name]=point
        for line in self.view.markers[name]:line.set_xdata([point.time_ms]*2);line.set_visible(True)
        self.view.readout.set_point(name,point)
        if len(self.cursors)==2:
            self.view.readout.set_difference(measurement(self.cursors['A'],self.cursors['B']))
        self.view.canvas.draw_idle()

    def save(self,path=None):
        if self.recording is None:return
        if not isinstance(path,(str,Path)):path=self.view.save_path()
        if path:
            try:self.view.figure.savefig(str(path),dpi=160);self.view.status.setText('已保存当前视图：'+str(path))
            except (OSError,ValueError) as exc:self.view.status.setText('图片保存失败：'+str(exc))

    def close(self):
        if self.closed:return
        self.closed=True;self.timer.stop();self.zoom_timer.stop();self.worker.close();self.clear()
        for connection in self.connections:self.view.canvas.mpl_disconnect(connection)
        self.view.allow_close=True;QTimer.singleShot(0,self.view.close)
