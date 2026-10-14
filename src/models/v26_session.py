"""V26 single-flight acquisition scheduler. Only this worker touches the socket."""
from collections import deque
from dataclasses import asdict,replace
from datetime import datetime,timezone
import json
from pathlib import Path
import queue
import socket
import threading
import time
import uuid

from .v26_protocol import (AcquisitionSettings,ERROR_MASK,can_arm,can_get,can_force,
                           can_release,parse_fst,parse_tst,validate_record,record_rate_hz)
from .v26_transport import Transport,RecordWriter,CommandRejected,Stopped


class StatusUnavailable(ValueError):
    """A complete TST reply was rejected or cannot describe acquisition state."""


class V26Session:
    def __init__(self,config,*,command_timeout=5,progress_timeout=30,poll_interval=.1):
        self.config=config;self.command_timeout=command_timeout;self.progress_timeout=progress_timeout
        self.poll_interval=poll_interval
        self.directory=Path(config.output_dir).resolve()/(datetime.now().strftime('%Y%m%d_%H%M%S_')+uuid.uuid4().hex[:8])
        self._lock=threading.RLock();self._halt=threading.Event();self._done=threading.Event()
        self._actions=queue.Queue(maxsize=1);self._pending=False;self._events=deque(maxlen=300)
        self._sock=None;self.transport=None;self._worker=None
        self.state='new';self.phase='未连接';self.error='';self.status={};self.diagnostics={};self.status_error=''
        self.configured=None;self.active=None;self.managed=False;self.repeating=False;self._repeat_stopped=False
        self.receiving=False;self.completed=0;self.last_path='';self.rx=0;self.tx=0
        self.expected=0;self.received=0;self.written=0;self.index=0;self.capture_started=0
        self._bad_metadata=0;self._next_poll=0

    def _event(self,text):
        with self._lock:self._events.append({'time':datetime.now().isoformat(timespec='seconds'),'message':str(text)})

    def events(self):
        with self._lock:return list(self._events)

    def snapshot(self):
        with self._lock:
            available=self.state=='connected' and not self._pending and not self.receiving and not self.status_error
            s=dict(self.status)
            return dict(state=self.state,phase=self.phase,error=self.error,status=s,diagnostics=dict(self.diagnostics),
                        status_error=self.status_error,active_settings=asdict(self.active) if self.active else None,
                        configured=asdict(self.configured) if self.configured else None,
                        repeat=self.repeating,receiving=self.receiving,busy=self._pending,
                        can_start=available and not self.managed and not self.repeating and can_arm(s),
                        can_set_rate=available and not self.managed and not self.repeating and can_arm(s) and 'CFG_RATE_MSPS' in s,
                        can_force=bool(available and can_force(s,self.active)),
                        can_read=available and not self.managed and can_get(s),
                        can_release=available and not self.managed and can_release(s),
                        can_cancel=available and bool(s.get('STATUS',0)&(2|4)) or self.receiving,
                        completed=self.completed,last_path=self.last_path,rx_bytes=self.rx,tx_bytes=self.tx,
                        expected=self.expected,received=self.received,written=self.written,
                        pending=max(0,self.received-self.written),buffer_bytes=self.config.chunk_bytes*self.config.queue_chunks,
                        elapsed=time.monotonic()-self.capture_started if self.capture_started else 0,
                        directory=str(self.directory))

    def start(self):
        if self._worker is not None:raise RuntimeError('会话只能启动一次')
        self.state='connecting';self._worker=threading.Thread(target=self._run,name='v26-protocol',daemon=True);self._worker.start()

    def stop(self):
        self._halt.set()
        if self._sock:
            try:self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:pass

    def wait(self,timeout=None):return self._done.wait(timeout)

    def submit(self,action,settings=None,repeat=False,command=None):
        if action not in ('configure','start','arm','force','cancel','read','release','stop_repeat','query','finit','clear','rate'):
            raise ValueError('不支持的操作')
        with self._lock:
            if self.state!='connected':raise RuntimeError('请先连接设备并读取采集状态')
            if self.status_error and action not in ('query','finit','stop_repeat'):
                raise RuntimeError('采集状态不可用，请先在设备诊断中查询 TST；'+self.status_error)
            if action=='stop_repeat':self._repeat_stopped=True;self.repeating=False;self._event('已停止后续记录，当前记录继续完成');return
            if action=='cancel' and self.receiving:
                self.repeating=False;self.stop();return
            if self.receiving or self._pending:raise RuntimeError('上一条操作尚未完成；GET 中禁止发送控制命令')
            if action in ('configure','start','arm','rate'):
                if self.managed or self.repeating or not can_arm(self.status):raise RuntimeError('设备尚未就绪、有未处理记录或仍在重复采集')
                if action in ('configure','start') and not isinstance(settings,AcquisitionSettings):raise ValueError('缺少完整采集配置')
                if action=='rate':
                    if type(settings) is not int or not 1<=settings<=100:raise ValueError('保存采样率必须为 1–100 MSPS 的整数')
                    if 'CFG_RATE_MSPS' not in self.status:raise ValueError('设备未提供可调保存速率')
            if repeat and (settings is None or settings.mode!=1 or 'GAP_LEFT_MS' not in self.status):
                raise ValueError('重复采集需要自动模式和设备 GAP_LEFT_MS 字段')
            if action=='force' and not can_force(self.status,self.active):raise RuntimeError('本次不是已确认的手动采集，或历史尚未就绪')
            if action=='query' and command not in ('VER','FST','TST','FREG'):raise ValueError('查询指令不受支持')
            if action in ('finit','clear') and (self.managed or self.status.get('STATUS',0)&(2|4)):
                raise RuntimeError('请先处理当前采集/记录')
            if action=='start':self._repeat_stopped=False
            self._pending=True;self._actions.put_nowait((action,settings,repeat,command))

    def submit_command(self,text):
        try:raw=text.encode('ascii')
        except UnicodeEncodeError as exc:raise ValueError('指令必须为 ASCII') from exc
        if not 1<=len(raw)<=127 or any(c in raw for c in (10,13,0)):
            raise ValueError('只允许一条指令，正文 1–127 字节，无内嵌换行')
        name,sep,arg=text.partition(' ')
        if name in ('CFG','ACQ'):
            fields=arg.split(',')
            if len(fields) not in (10,11) or any(not x.strip().isascii() or not x.strip().isdigit() for x in fields):
                raise ValueError('CFG/ACQ 需要十个或十一个无符号十进制整数')
            settings=AcquisitionSettings(*map(lambda x:int(x.strip()),fields))
            # ACQ semantics use verified CFG + ARM to keep the same host state gates.
            return self.submit('configure' if name=='CFG' else 'start',settings)
        if name=='RATE' and sep:
            if not arg.isascii() or not arg.isdigit():raise ValueError('RATE 需要 1–100 的无符号十进制整数')
            return self.submit('rate',int(arg))
        if sep:raise ValueError('参数配置请使用完整 CFG/ACQ 或 RATE')
        actions={'ARM':'arm','FORCE':'force','ABORT':'cancel','RELEASE':'release','GET':'read','FINIT':'finit','CLEAR_EVENTS':'clear'}
        if name in actions:return self.submit(actions[name])
        return self.submit('query',command=name)

    def _add(self,name,count):
        with self._lock:setattr(self,name,getattr(self,name)+count)

    def _request(self,command):
        payload=command if isinstance(command,bytes) else command.encode('ascii')+b'\r'
        label=payload.decode('ascii').strip()
        if label!='TST':self._event('发送 '+label)
        try:result=self.transport.request(payload)
        except CommandRejected:
            with self._lock:self.diagnostics[label.split(' ')[0]]='? (设备拒绝)'
            raise
        except UnicodeDecodeError:
            with self._lock:self.diagnostics[label.split(' ')[0]]='完整回复包含非 ASCII 字节'
            raise
        with self._lock:self.diagnostics[label.split(' ')[0]]=result or '*'
        return result

    def _status(self):
        try:
            reply=self._request('TST')
        except (CommandRejected,UnicodeDecodeError) as exc:
            return self._status_unavailable(str(exc))
        try:status=parse_tst(reply)
        except ValueError as exc:return self._status_unavailable(str(exc))
        with self._lock:
            if self.error==self.status_error:self.error=''
            self.status=status;self.status_error=''
        return status

    def _status_unavailable(self,reason):
        if self.transport.buffer:
            raise ConnectionError('TST 回复后有未归属字节，已断开；请重连核对设备状态')
        # FST is diagnostic context, never a substitute for TST record metadata.
        try:fst=parse_fst(self.diagnostics.get('FST',''))
        except ValueError:fst={}
        detail=''
        if fst.get('INIT')=='0':
            ierr=fst.get('IERR','未知');version=fst.get('VER','未知')
            detail=f'；设备报告 FPGA 初始化未成功（INIT=0，IERR={ierr}，FPGA VER={version}）'
            if ierr=='4':detail+='；初始化错误码指向 FPGA 版本不匹配，请核对配套 FPGA 程序及 FMC 版本寄存器回读'
        message=reason+detail+'；TCP 连接保留，仅可诊断，取得有效 TST 后恢复采集'
        with self._lock:
            self.status={};self.status_error=message;self.error=message
            self.configured=None;self.active=None;self.managed=False;self.repeating=False
        self._event(message)
        raise StatusUnavailable(message)

    def _run(self):
        try:
            self.directory.mkdir(parents=True)
            sock=socket.create_connection((self.config.host,self.config.port),timeout=self.command_timeout)
            self._sock=sock;sock.settimeout(.1);sock.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,self.config.rcvbuf_bytes)
            self.transport=Transport(sock,self._halt,lambda n:self._add('rx',n),lambda n:self._add('tx',n),self.command_timeout)
            # Identity replies are diagnostic only; firmware labels do not gate connection.
            for command in ('VER','FST'):
                try:self._request(command)
                except CommandRejected:
                    with self._lock:self.diagnostics[command]='? (设备未提供此诊断)'
                    self._event(command+' 查询未被接受，继续读取采集状态')
            try:self._status()
            except StatusUnavailable:pass
            self.state='connected';self._event('TCP 已连接；'+('仅诊断，采集状态不可用' if self.status_error else '已读取采集状态；版本严格检查已停用'))
            while not self._halt.is_set():
                try:item=self._actions.get(timeout=.05 if self.status_error else max(.001,min(.05,self._next_poll-time.monotonic())))
                except queue.Empty:item=None
                if item is not None:
                    try:self._perform(*item)
                    except (CommandRejected,ValueError,RuntimeError) as exc:
                        if isinstance(exc,Stopped):raise
                        self.error=str(exc);self.managed=False;self.repeating=False;self._event(exc)
                        if not self.status_error:
                            try:self._status()
                            except StatusUnavailable:pass
                    finally:
                        with self._lock:self._pending=False
                elif not self.status_error and time.monotonic()>=self._next_poll:
                    try:self._status()
                    except StatusUnavailable:pass
                    else:
                        try:self._advance()
                        except (CommandRejected,ValueError) as exc:
                            self.error=str(exc);self.managed=False;self.repeating=False;self._event(exc)
                    self._next_poll=time.monotonic()+self.poll_interval
                self._describe()
        except Stopped as exc:
            if self.receiving:self.error=str(exc)
        except Exception as exc:
            self.error=str(exc);self.state='failed';self._event(exc)
        finally:
            self._halt.set();self.repeating=False;self.receiving=False
            if self._sock:self._sock.close()
            if self.state!='failed':self.state='finished'
            self.phase='连接结束，重连后先核对设备状态'
            self._done.set()

    def _perform(self,action,settings,repeat,command):
        # A status poll may have failed after this action was queued.
        if self.status_error and action not in ('query','finit','stop_repeat'):
            raise RuntimeError('采集状态已失效，已取消排队操作；请先手动查询 TST')
        self.error=self.status_error
        if action in ('configure','start'):
            self.phase='写入并核对配置';s=self._status()
            if not can_arm(s):raise ValueError('设备有活动或未释放记录')
            self.configured=None
            self._request(settings.command(include_rate='CFG_RATE_MSPS' in s));s=self._status()
            if not settings.matches(s):raise ValueError('配置回读不一致，请核对诊断')
            self.configured=settings
            if action=='start':self._arm(repeat)
        elif action=='rate':
            s=self._status()
            if not can_arm(s) or 'CFG_RATE_MSPS' not in s:raise ValueError('设备未就绪或未提供可调保存速率')
            self.configured=None
            self._request(f'RATE {settings}');s=self._status()
            if s.get('CFG_RATE_MSPS')!=settings:raise ValueError('保存采样率回读不一致，请核对设备配置')
            self._event(f'已设置下一组保存采样率 {settings} MSPS；准备采集时将提交全部配置')
        elif action=='arm':self._arm(False)
        elif action=='force':
            if not can_force(self._status(),self.active):raise ValueError('手动触发条件已变化，请查看状态')
            self._request('FORCE')
        elif action=='cancel':self._cancel_capture()
        elif action=='release':
            self.repeating=False;self.managed=False
            if not can_release(self._status()):raise ValueError('读端忙或记录未完成，不能 RELEASE')
            self._request('RELEASE');self._verify_released();self.active=None
        elif action=='read':
            if not can_get(self._status()):raise ValueError('记录尚不可读取')
            self._read_record()
        elif action=='query':self._status() if command=='TST' else self._request(command)
        elif action=='finit':
            self._request('FINIT');self.configured=None;self.active=None;self._status()
        elif action=='clear':self._request('CLEAR_EVENTS');self._status()

    def _arm(self,repeat):
        if self.configured is None:raise ValueError('请先明确应用完整配置')
        s=self._status()
        if not can_arm(s):raise ValueError('设备未就绪')
        if not self.configured.matches(s):raise ValueError('设备配置已变化，请重新应用配置')
        if self.configured.mode==1 and s.get('GAP_LEFT_MS',0)>0:raise ValueError('设备自动组间隔尚未结束')
        # A stop request may arrive while configuration/status replies are pending.
        if repeat and self._repeat_stopped:return
        # A rejected ARM can still have executed on FPGA; never reuse prior settings.
        self.active=None
        self._request('ARM')
        self.active=self.configured;self.managed=True;self._bad_metadata=0
        with self._lock:self.repeating=repeat and not self._repeat_stopped
        self.phase='已准备，等待触发';self._next_poll=0

    def _verify_released(self):
        s=self._status()
        if not s['STATUS']&1 or s['STATUS']&(2|8) or s['PENDING']!=0:
            raise ValueError('取消/释放后的状态未恢复就绪，请核对设备')

    def _cancel_capture(self):
        self.repeating=False;self.managed=False;s=self._status()
        if s['STATUS']&2 and not s['STATUS']&4:
            try:self._request('ABORT')
            except CommandRejected:
                s=self._status()
                if not can_release(s):raise
                self._request('RELEASE')
        elif can_release(s):self._request('RELEASE')
        else:raise ValueError('当前不能取消/释放，请查看设备状态')
        self._verify_released();self.active=None

    def _advance(self):
        s=self.status
        if self.managed and s['STATUS']&ERROR_MASK:
            raise ValueError('设备错误位有效；停止自动操作，请查看诊断并处理记录')
        if self.managed and can_get(s):
            try:validate_record(s,self.active)
            except ValueError:
                self._bad_metadata+=1
                if self._bad_metadata>=3:raise
                return
            self._read_record();self.managed=False
        elif self.managed and can_arm(s):
            raise ValueError('采集未产生有效记录已回到就绪，请检查是否被取消')
        elif self.repeating and not self.managed and can_arm(s):
            if 'GAP_LEFT_MS' not in s:raise ValueError('缺少 GAP_LEFT_MS，已停止重复采集')
            if s['GAP_LEFT_MS']==0:self._arm(True)

    def _describe(self):
        if self.receiving:return
        if self.status_error:
            self.phase='已连接（仅诊断，采集状态不可用）';return
        s=self.status;status=s.get('STATUS',0)
        if status&ERROR_MASK:self.phase='设备异常，请处理已有记录/查看诊断'
        elif status&4:self.phase='记录完成，可读取或丢弃'
        elif status&2:
            if s.get('TRIGGERED'):self.phase='已触发，正在完成记录'
            elif not s.get('HISTORY_READY'):self.phase='正在建立前触发历史'
            elif self.active is None:self.phase='设备有等待中的记录，本次锁存配置未知'
            else:self.phase='等待手动触发' if self.active.mode==0 else '等待阈值条件触发'
        elif self.repeating:self.phase=f"等待组间隔：{s.get('GAP_LEFT_MS','未知')} ms"
        elif can_arm(s):self.phase='就绪'
        else:self.phase='设备未就绪，请查看诊断'

    def _read_record(self):
        s=dict(self.status);validate_record(s,self.active)
        self.index+=1;self.expected=s['HEX_CHARS'];self.received=0;self.written=0;self.capture_started=time.monotonic()
        self.receiving=True;self.phase='读取波形，已暂停状态查询'
        base=f'capture_{self.index:04d}_{s["SAMPLES"]}pairs_{uuid.uuid4().hex[:6]}'
        partial=self.directory/(base+'.partial.hex');final=self.directory/(base+'.hex')
        meta=dict(format_version=4,application='AD-HOST Qt6 0.6.1',protocol='V28' if 'ACTIVE_RATE_MSPS' in s else 'V26',
                  sample_rate_hz=record_rate_hz(s),adc_clock_hz=s['RATE'],complete=False,
                  status=s,active_settings=asdict(self.active) if self.active else None,
                  active_configuration_known=self.active is not None,diagnostics=dict(self.diagnostics),
                  expected_hex_bytes=self.expected,started_utc=datetime.now(timezone.utc).isoformat())
        writer=None;success=False;failure='';carry=b''
        try:
            writer=RecordWriter(partial,self.config.queue_chunks,self._halt,lambda n:self._add('written',n),self.progress_timeout)
            self.transport.send(b'GET\r');deadline=time.monotonic()+self.progress_timeout
            while self.received<self.expected:
                writer.check()
                if self.transport.buffer:
                    data=bytes(self.transport.buffer);self.transport.buffer.clear()
                else:data=self.transport.recv(deadline,'GET 接收进度超时',writer.check)
                deadline=time.monotonic()+self.progress_timeout
                take=min(len(data),self.expected-self.received);body=data[:take]
                self.transport.buffer.extend(data[take:])
                if body.translate(None,b'0123456789ABCDEF'):raise ValueError('GET 正文含错误标志或非 HEX 字符')
                decoded=carry+body;end=len(decoded)//8*8
                if decoded[:end:4].strip(b'0'):raise ValueError('V26 电压/电流高 4 位非零，超出 12 位范围')
                carry=decoded[end:]
                for offset in range(0,len(body),self.config.chunk_bytes):
                    piece=body[offset:offset+self.config.chunk_bytes];writer.put(piece);self._add('received',len(piece))
            while len(self.transport.buffer)<3:
                self.transport.buffer.extend(self.transport.recv(deadline,'GET 结束标志接收进度超时',writer.check))
                deadline=time.monotonic()+self.progress_timeout
            marker=bytes(self.transport.buffer[:3]);del self.transport.buffer[:3]
            if marker!=b'\r\n*' or carry:raise ValueError('GET 长度或结束标志不正确')
            if self.transport.buffer:raise ValueError('GET 结束后有多余数据')
            self.phase='完成写盘';writer.finish()
            if writer.written!=self.expected:raise OSError('写入长度与记录不一致')
            success=True
        except Exception as exc:
            failure=str(exc)
            if writer:
                try:writer.finish()
                except Exception as disk_exc:failure+='；'+str(disk_exc)
            # Framing failure leaves wire ownership ambiguous; do not resume polling.
            raise ConnectionError(failure) from exc
        finally:
            meta.update(complete=success,error=failure,received_hex_bytes=self.received,written_hex_bytes=self.written,
                        elapsed_seconds=time.monotonic()-self.capture_started)
            path=final if success else partial
            temporary=Path(str(path)+'.json.tmp')
            with temporary.open('w',encoding='utf-8') as f:
                json.dump(meta,f,ensure_ascii=False,indent=2);f.flush()
                import os
                os.fsync(f.fileno())
            temporary.replace(Path(str(path)+'.json'))
            # Publish the usable HEX only after its durable metadata exists.
            # Any earlier failure leaves the data visibly marked partial.
            if success:partial.replace(final)
            self.receiving=False
        self.last_path=str(final);self.completed+=1;self._event(f'已完整保存 {self.expected:,} HEX 字节：{final.name}')
        self._status()
