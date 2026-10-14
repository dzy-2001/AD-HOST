"""Connect view intents to the existing serial acquisition model."""
import json
import time
import tempfile
from pathlib import Path
from PyQt6.QtCore import QObject,QTimer
from ..models.core import CaptureConfig,RateMeter
from ..models.v26_protocol import AcquisitionSettings,reason_text
from ..models.v26_session import V26Session
from ..models.archives import ArchiveJob
from ..models.calibration import CALIBRATION


class AcquisitionController(QObject):
    def __init__(self,view):
        super().__init__(view);self.view=view;self.session=None;self.waveforms=[];self.closing=False
        self.meter=None;self.last_sample=0;self.last_log='';self.last_error='';self.rate=0
        self.cache=tempfile.TemporaryDirectory(prefix='AD-HOST-');self.records={};self.archive_job=None
        self.cleanup_done=False
        view.connect_requested.connect(self.connect_device);view.disconnect_requested.connect(self.disconnect)
        view.action_requested.connect(self.action);view.command_requested.connect(self.send_command)
        view.plot_requested.connect(self.open_plot);view.close_requested.connect(self.request_close)
        view.save_requested.connect(self.save_record);view.record_list.currentRowChanged.connect(self.update_selected_record)
        view.settings_changed.connect(self.estimate)
        self.timer=QTimer(self);self.timer.timeout.connect(self.refresh);self.timer.start(100);self.estimate()

    def estimate(self):
        try:
            config=AcquisitionSettings(**self.view.values());n=config.samples;p=config.pre_samples
            self.view.estimate.setText(f'<b>{n:,}</b> 点 / 通道 · <b>{n/(config.rate_msps*1000):.6f}</b> ms<br>触发前 {p:,} 点 · 触发后 {n-p:,} 点')
        except ValueError as exc:self.view.estimate.setText(str(exc))

    def connect_device(self):
        if self.closing or self.session and not self.session.wait(0):return
        v=self.view
        try:
            config=CaptureConfig(v.host.text().strip(),v.port.value(),Path(self.cache.name),queue_chunks=int(v.buffer.currentText()))
            self.collect_records()
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
        record=self.selected_record();path=(record['archive'] or record['source']) if latest and record else ''
        if path:active.load_path(path)

    def collect_records(self,snapshot=None):
        if not self.session:return
        snapshot=self.session.snapshot() if snapshot is None else snapshot
        for path in snapshot['records']:
            if path not in self.records:
                self.records[path]=dict(source=path,archive='')
                self.view.record_list.addItem(f'记录 {len(self.records)} · '+Path(path).stem+' · 待保存')
                self.view.record_list.setCurrentRow(self.view.record_list.count()-1)

    def selected_record(self):
        row=self.view.record_list.currentRow()
        return list(self.records.values())[row] if 0<=row<len(self.records) else None

    def update_selected_record(self,*args):
        record=self.selected_record()
        self.view.latest_button.setEnabled(record is not None)
        self.view.save_record_button.setEnabled(record is not None and not record['archive'] and self.archive_job is None)
        self.view.path.setText((record['archive'] or '暂存（尚未存档）：'+Path(record['source']).name) if record else '')

    def save_record(self):
        record=self.selected_record()
        if self.closing or self.archive_job or not record or record['archive']:return
        # Snapshot selection before the modal dialog: new captures may arrive meanwhile.
        source=record['source'];parent=self.view.confirm_archive_directory()
        if not parent or self.closing:return
        if Path(parent).resolve().is_relative_to(Path(self.cache.name).resolve()):
            self.view.show_error('请选择软件临时目录以外的存档位置，避免退出时清理存档。');return
        self.view.output.setText(parent)
        self.archive_job=ArchiveJob(source,parent);self.archive_job.start()
        self.view.notice.setText('正在保存选中的波形记录…');self.update_selected_record()

    def poll_archive(self):
        job=self.archive_job
        if job is None or not job.done.is_set():return
        job.thread.join();self.archive_job=None
        if job.error:self.view.show_error('存档失败，暂存记录仍可重试：'+job.error)
        else:
            record=self.records[str(job.source)];record['archive']=str(job.path)
            row=list(self.records).index(str(job.source))
            self.view.record_list.item(row).setText(f'记录 {row+1} · '+job.path.parent.name+' · 已保存')
            self.view.notice.setText('已存档')
        self.update_selected_record()

    def request_close(self):
        snap=self.session.snapshot() if self.session else {}
        self.collect_records(snap);self.poll_archive()
        pending=sum(not r['archive'] for r in self.records.values())
        active=bool(snap.get('receiving') or snap.get('busy') or snap.get('repeat') or snap.get('status',{}).get('PENDING',0) or snap.get('status',{}).get('STATUS',0)&2)
        if (pending or active) and not self.view.confirm_discard(pending):return
        self.close()

    def refresh(self):
        v=self.view;alive=self.session is not None and not self.session.wait(0)
        self.collect_records();self.poll_archive();self.update_selected_record()
        for waveform in self.waveforms[:]:
            if waveform.closed and waveform.finished:
                self.waveforms.remove(waveform);waveform.view.deleteLater()
        if self.closing:
            if not alive and all(w.finished for w in self.waveforms) and self.archive_job is None:
                if not self.cleanup_done:
                    try:self.cache.cleanup();self.cleanup_done=True
                    except OSError as exc:
                        v.show_error('暂存目录清理失败：'+str(exc));self.timer.stop();v.allow_close=True;QTimer.singleShot(0,v.close);return
                self.timer.stop();v.allow_close=True;QTimer.singleShot(0,v.close)
            return
        v.connect_button.setEnabled(not alive);v.disconnect_button.setEnabled(alive)
        for w in v.connection_widgets:w.setEnabled(not alive)
        if not self.session:
            text=json.dumps(dict(calibration=CALIBRATION,waveform=[w.diagnostics for w in self.waveforms if not w.closed],messages=v.diagnostic_messages),ensure_ascii=False,indent=2)
            if text!=self.last_log:v.log.setPlainText(text);self.last_log=text
            return
        s=self.session.snapshot();v.state.setText(s['phase'])
        if s['state']=='connecting':
            v.rate_status.setText('读取中…')
        elif s.get('status_error'):
            v.rate_status.setText('状态不可用 · 查看诊断')
        elif s['state']!='connected':
            v.rate_status.setText('已断开')
        elif 'CFG_RATE_MSPS' in s['status']:
            v.rate_status.setText(f"设置 {s['status']['CFG_RATE_MSPS']} · 本次 {s['status'].get('ACTIVE_RATE_MSPS','—')} MSPS")
        else:v.rate_status.setText('未返回采样率 · 默认 100 MSPS')
        for action,key in (('configure','can_start'),('start','can_start'),('force','can_force'),('cancel','can_cancel'),('read','can_read'),('release','can_release')):
            v.actions[action].setEnabled(bool(s[key]))
        v.actions['stop_repeat'].setEnabled(s['repeat'])
        for w in v.config_widgets:w.setEnabled(not alive or bool(s['can_start']))
        query=s['state']=='connected' and not s['busy'] and not s['receiving']
        for w in v.query_buttons+[v.send_button]:w.setEnabled(query)
        now=time.monotonic()
        if now-self.last_sample>=1:
            self.rate=self.meter.sample(now,s['rx_bytes'])['instant'] if self.meter else 0;self.last_sample=now
        v.metrics.setText(f'{self.rate/1e6:.2f} MB/s · 已接收 {s["received"]/1e6:.2f} MB · 完成 {s["completed"]} 条')
        v.progress.setValue(int(s['received']/max(1,s['expected'])*1000))
        st=s['status'];v.trigger.setText('触发：'+(reason_text(st['REASON']) if st.get('REASON') else '—'))
        if s['error'] and s['error']!=self.last_error:v.show_error(s['error']);self.last_error=s['error']
        elif not s['error'] and self.last_error:
            self.last_error='';v.notice.setText('设备状态已恢复');v.notice.setProperty('cssClass','')
            v.notice.style().unpolish(v.notice);v.notice.style().polish(v.notice)
        diagnostics=dict(device=s['diagnostics'],status=s['status'],calibration=CALIBRATION,
                         transfer={k:s[k] for k in ('expected','received','written','pending','buffer_bytes','completed')},
                         waveform=[w.diagnostics for w in self.waveforms if not w.closed],messages=v.diagnostic_messages)
        text=json.dumps(diagnostics,ensure_ascii=False,indent=2)+'\n\n'+'\n'.join(e['time']+' '+e['message'] for e in self.session.events()[-40:])
        if text!=self.last_log:v.log.setPlainText(text);self.last_log=text

    def close(self):
        if self.closing:return
        self.closing=True;self.view.centralWidget().setEnabled(False);self.view.notice.setText('正在停止接收并关闭数据文件…')
        self.disconnect()
        for waveform in self.waveforms:waveform.close()
        self.refresh()
