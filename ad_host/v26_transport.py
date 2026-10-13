"""Serial TCP framing and bounded, failure-aware record writer."""
import os
import queue
import socket
import threading
import time


class CommandRejected(RuntimeError):
    pass


class Stopped(RuntimeError):
    pass


class Transport:
    def __init__(self,sock,halt,on_rx,on_tx,command_timeout=5):
        self.sock=sock;self.halt=halt;self.on_rx=on_rx;self.on_tx=on_tx
        self.command_timeout=command_timeout;self.buffer=bytearray()

    def recv(self,deadline,timeout_message,check=lambda:None):
        while True:
            check()
            if self.halt.is_set():raise Stopped('连接已关闭；当前操作未完成')
            if time.monotonic()>=deadline:raise TimeoutError(timeout_message)
            try:data=self.sock.recv(1024*1024)
            except socket.timeout:continue
            if not data:raise ConnectionError('设备断开连接')
            self.on_rx(len(data));return data

    def send(self,payload):
        if self.halt.is_set():raise Stopped('连接已关闭')
        if self.buffer:raise ValueError('上一条回复后仍有未归属字节，需重连确认状态')
        self.sock.sendall(payload);self.on_tx(len(payload))

    def request(self,payload):
        self.send(payload);deadline=time.monotonic()+self.command_timeout
        while True:
            found=[(self.buffer.find(marker),marker) for marker in (b'\r\n*',b'\r\n?')]
            found=[item for item in found if item[0]>=0]
            if found:
                end,marker=min(found)
                body=bytes(self.buffer[:end]);del self.buffer[:end+3]
                if marker==b'\r\n?':raise CommandRejected(payload.decode('ascii').strip()+' 被设备拒绝；需核对状态')
                return body.decode('ascii').strip()
            if len(self.buffer)>65536:raise ValueError('文本回复超过 64 KiB')
            self.buffer.extend(self.recv(deadline,'命令回复超时；结果未知，请重连核对，勿重复启动'))


class RecordWriter:
    def __init__(self,path,max_chunks,halt,on_written,timeout=30):
        self.path=path;self.halt=halt;self.on_written=on_written;self.timeout=timeout
        self.queue=queue.Queue(maxsize=max_chunks);self.error=None;self.written=0
        self.done=threading.Event();self.ready=threading.Event();self.last_progress=time.monotonic()
        self.thread=threading.Thread(target=self._run,name='v26-record-writer',daemon=True)
        self.thread.start();self.ready.wait(timeout);self.check()
        if not self.ready.is_set():raise TimeoutError('创建采集文件超时')

    def check(self):
        if self.error:raise OSError('写盘失败：'+str(self.error)) from self.error

    def put(self,data,*,finishing=False):
        while True:
            self.check()
            if not finishing and self.halt.is_set():raise Stopped('接收已停止')
            try:self.queue.put(data,timeout=.05);return
            except queue.Full:
                if time.monotonic()-self.last_progress>self.timeout:raise TimeoutError('写盘长时间无进度')

    def finish(self):
        # A socket may time out before any payload arrives. Finishing has its
        # own deadline so an idle writer still receives the close sentinel.
        self.last_progress=time.monotonic()
        if not self.done.is_set():self.put(None,finishing=True)
        while not self.done.wait(.05):
            self.check()
            if time.monotonic()-self.last_progress>self.timeout:raise TimeoutError('等待写盘完成超时')
        self.check()

    def _run(self):
        try:
            with self.path.open('xb',buffering=0) as f:
                self.ready.set()
                while True:
                    data=self.queue.get()
                    if data is None:break
                    view=memoryview(data)
                    while view:
                        count=f.write(view)
                        if not count:raise OSError('文件写入返回零字节')
                        view=view[count:];self.written+=count;self.last_progress=time.monotonic()
                        self.on_written(count)
                f.flush();os.fsync(f.fileno())
        except Exception as exc:self.error=exc
        finally:self.ready.set();self.done.set()
