"""Connect view intents to the existing serial acquisition model."""
import json
import time
from pathlib import Path
from PyQt6.QtCore import QObject,QTimer
from ..models.core import CaptureConfig,RateMeter
from ..models.v26_protocol import AcquisitionSettings,reason_text
from ..models.v26_session import V26Session


class AcquisitionController(QObject):
    def __init__(self,view):
        super().__init__(view);self.view=view;self.session=None;self.waveforms=[];self.closing=False
        self.meter=None;self.last_sample=0;self.last_log='';self.last_error='';self.rate=0
        view.connect_requested.connect(self.connect_device);view.disconnect_requested.connect(self.disconnect)
        view.action_requested.connect(self.action);view.command_requested.connect(self.send_command)
        view.plot_requested.connect(self.open_plot);view.close_requested.connect(self.close)
        view.settings_changed.connect(self.estimate)
        self.timer=QTimer(self);self.timer.timeout.connect(self.refresh);self.timer.start(100);self.estimate()

    def estimate(self):
        try:
            config=AcquisitionSettings(**self.view.values());n=config.samples;p=config.pre_samples
            self.view.estimate.setText(f'每通道：<b>{n:,} 点</b>　|　时长：<b>{n/(config.rate_msps*1000):.6f} ms</b>　|　HEX 大小：<b>{n*8/1e6:.3f} MB</b><br>触发前：<b>{p:,} 点（{config.pre}%）</b>　　触发后：<b>{n-p:,} 点（{100-config.pre}%）</b>'+('　· 不包含触发样本' if config.pre==100 else ''))
        except ValueError as exc:self.view.estimate.setText(str(exc))

    def connect_device(self):
        if self.closing or self.session and not self.session.wait(0):return
        v=self.view
        try:
            config=CaptureConfig(v.host.text().strip(),v.port.value(),Path(v.output.text()),queue_chunks=int(v.buffer.currentText()))
            self.session=V26Session(config,progress_timeout=v.timeout.value());self.session.start()
            self.meter=RateMeter(time.monotonic());self.last_sample=0;self.rate=0;self.last_error='';self.refresh()
        except (ValueError,OSError) as exc:v.show_error(exc)

    def disconnect(self):
        if self.session:self.session.stop()

    def action(self,name):
        try:
            if self.session is None or self.closing:raise ValueError('请先连接设备')
            config=AcquisitionSettings(**self.view.values()) if name in ('configure','start') else None
            self.session.submit(name,config,repeat=self.view.repeat.isChecked() if name=='start' else False)
            self.refresh()
        except (ValueError,RuntimeError) as exc:self.view.show_error(exc)

    def send_command(self,text):
        try:
            if self.session is None or self.closing:raise ValueError('请先连接设备')
            self.session.submit_command(text);self.refresh()
        except (ValueError,RuntimeError) as exc:self.view.show_error(exc)

    def open_plot(self,latest=False):
        if self.closing:return
        from ..views.waveform_window import WaveformWindow
        from .waveform_controller import WaveformController
        active=next((w for w in self.waveforms if not w.closed),None)
        if active is None:
            active=WaveformController(WaveformWindow(self.view));self.waveforms.append(active)
        active.view.show();active.view.raise_();active.view.activateWindow()
        path=self.session.snapshot()['last_path'] if latest and self.session else ''
        if path:active.load_path(path)

    def refresh(self):
        v=self.view;alive=self.session is not None and not self.session.wait(0)
        for waveform in self.waveforms[:]:
            if waveform.closed and waveform.finished:
                self.waveforms.remove(waveform);waveform.view.deleteLater()
        if self.closing:
            if not alive and all(w.finished for w in self.waveforms):
                self.timer.stop();v.allow_close=True;QTimer.singleShot(0,v.close)
            return
        v.connect_button.setEnabled(not alive);v.disconnect_button.setEnabled(alive)
        for w in v.connection_widgets:w.setEnabled(not alive)
        if not self.session:return
        s=self.session.snapshot();v.state.setText(s['phase'])
        if s['state']=='connecting':
            v.rate_status.setText('正在读取设备状态，尚未确认保存采样率')
        elif s.get('status_error'):
            v.rate_status.setText('采集状态读取失败，保存采样率未知；请查看设备诊断')
        elif s['state']!='connected':
            v.rate_status.setText('已断开；保存采样率尚未确认')
        elif 'CFG_RATE_MSPS' in s['status']:
            v.rate_status.setText(f"设备配置 {s['status']['CFG_RATE_MSPS']} MSPS · 当前锁存 {s['status'].get('ACTIVE_RATE_MSPS','—')} MSPS · ADC 100 MHz")
        else:v.rate_status.setText('设备状态未返回采样率信息；按旧协议默认 100 MSPS（非测量值）')
        for action,key in (('configure','can_start'),('start','can_start'),('force','can_force'),('cancel','can_cancel'),('read','can_read'),('release','can_release')):
            v.actions[action].setEnabled(bool(s[key]))
        v.actions['stop_repeat'].setEnabled(s['repeat'])
        for w in v.config_widgets:w.setEnabled(not alive or bool(s['can_start']))
        query=s['state']=='connected' and not s['busy'] and not s['receiving']
        for w in v.query_buttons+[v.send_button]:w.setEnabled(query)
        now=time.monotonic()
        if now-self.last_sample>=1:
            self.rate=self.meter.sample(now,s['rx_bytes'])['instant'] if self.meter else 0;self.last_sample=now
        v.metrics.setText(f"TCP {self.rate/1e6:.2f} MB/s · 已接收 {s['received']:,} / {s['expected']:,} B · 已写入 {s['written']:,} B\n待写 {s['pending']/1048576:.1f} / {s['buffer_bytes']/1048576:.0f} MiB · 完成 {s['completed']} 条")
        v.progress.setValue(int(s['received']/max(1,s['expected'])*1000))
        st=s['status'];v.trigger.setText(f"触发原因：{reason_text(st.get('REASON',0))} · 前触发位置 {st.get('ACTIVE_PRE','—')} · 间隔剩余 {st.get('GAP_LEFT_MS','未知')} ms")
        if s['last_path']:v.path.setText(s['last_path']);v.latest_button.setEnabled(True)
        if s['error'] and s['error']!=self.last_error:v.show_error(s['error']);self.last_error=s['error']
        elif not s['error'] and self.last_error:
            self.last_error='';v.notice.setText('设备状态已恢复，可按当前状态操作。');v.notice.setProperty('cssClass','')
            v.notice.style().unpolish(v.notice);v.notice.style().polish(v.notice)
        text=json.dumps(s['diagnostics'],ensure_ascii=False,indent=2)+'\n\n'+'\n'.join(e['time']+' '+e['message'] for e in self.session.events()[-40:])
        if text!=self.last_log:v.log.setPlainText(text);self.last_log=text

    def close(self):
        if self.closing:return
        self.closing=True;self.view.centralWidget().setEnabled(False);self.view.notice.setText('正在停止接收并关闭数据文件…')
        self.disconnect()
        for waveform in self.waveforms:waveform.close()
        self.refresh()
