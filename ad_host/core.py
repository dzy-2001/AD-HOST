"""Bounded TCP capture, independent disk writer and command sender.

Only received application bytes are counted; recv boundaries are not frames.
"""
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import queue
import socket
import threading
import time
import uuid

from .commands import MAX_COMMAND_BYTES


@dataclass(frozen=True)
class CaptureConfig:
    host: str
    port: int
    output_dir: Path
    chunk_bytes: int = 256 * 1024
    queue_chunks: int = 256
    roll_bytes: int = 1024 * 1024 * 1024

    def __post_init__(self):
        try:
            ipaddress.ip_address(self.host)
        except ValueError as exc:
            raise ValueError("请输入有效的 STM32 IPv4 或 IPv6 地址") from exc
        if not 1 <= self.port <= 65535:
            raise ValueError("端口必须在 1–65535 之间")
        if not 1 <= self.chunk_bytes <= 1024 * 1024:
            raise ValueError("接收块大小必须在 1 B–1 MiB 之间")
        if not 1 <= self.queue_chunks <= 4096:
            raise ValueError("缓冲块数必须在 1–4096 之间")
        if self.roll_bytes <= 0:
            raise ValueError("分卷大小必须大于零")


class RateMeter:
    """Monotonic, actual-interval rates. Call approximately once a second."""
    def __init__(self, started):
        self.started = started
        self.points = deque([(started, 0)])
        self.last_time = started
        self.last_bytes = 0
        self.result = dict(instant=0.0, recent=0.0, average=0.0, peak=0.0)

    def sample(self, now, total):
        if now <= self.last_time:
            return dict(self.result)
        instant = max(0, total - self.last_bytes) / (now - self.last_time)
        self.points.append((now, total))
        while len(self.points) > 2 and self.points[1][0] <= now - 10:
            self.points.popleft()
        first_time, first_bytes = self.points[0]
        self.result = dict(
            instant=instant,
            recent=max(0, total - first_bytes) / max(now - first_time, 1e-9),
            average=total / max(now - self.started, 1e-9),
            peak=max(self.result["peak"], instant),
        )
        self.last_time, self.last_bytes = now, total
        return dict(self.result)


class CaptureSession:
    """One connection, one directory. Reconnection always creates a new session."""
    def __init__(self, config):
        self.config = config
        self.directory = Path(config.output_dir).expanduser().resolve() / (
            datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
        )
        self.started_clock = time.monotonic()
        self._ended_clock = None
        self._started_utc = None
        self._ended_utc = None
        self._lock = threading.Lock()
        self._halt = threading.Event()
        self._rx_done = threading.Event()
        self._writer_failed = threading.Event()
        self._done = threading.Event()
        self._data = queue.Queue(maxsize=config.queue_chunks)
        self._commands = queue.Queue(maxsize=32)
        self._events = deque(maxlen=200)
        self._sock = None
        self._worker = None
        self._file = None
        self._part_size = 0
        self._parts = []
        self._durable = False
        self._state = "new"
        self._reason = None
        self._error = ""
        self._rx = self._written = self._tx = self._pending = self._peak_pending = 0
        self._preview = b""

    def _event(self, message):
        with self._lock:
            self._events.append({"time": datetime.now().isoformat(timespec="seconds"),
                                 "message": message})

    def events(self):
        with self._lock:
            return list(self._events)

    def snapshot(self):
        with self._lock:
            end = self._ended_clock if self._ended_clock is not None else time.monotonic()
            return dict(
                state=self._state, error=self._error, end_reason=self._reason,
                rx_bytes=self._rx, written_bytes=self._written, tx_bytes=self._tx,
                pending_bytes=self._pending, peak_pending_bytes=self._peak_pending,
                buffer_bytes=self.config.chunk_bytes * self.config.queue_chunks,
                elapsed=max(0, end - self.started_clock),
                clock=end, preview=self._preview, directory=str(self.directory),
            )

    def start(self):
        with self._lock:
            if self._state != "new":
                raise RuntimeError("每个采集会话只能启动一次")
            self._state = "connecting"
            self.started_clock = time.monotonic()
            self._started_utc = datetime.now(timezone.utc).isoformat()
        self._worker = threading.Thread(target=self._run, name="capture", daemon=True)
        self._worker.start()

    def stop(self):
        with self._lock:
            if self._state in ("new", "finished", "failed"):
                return
            if self._reason is None:
                self._reason = "local_stop"
            self._state = "stopping"
            self._halt.set()
            sock = self._sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def wait(self, timeout=None):
        return self._done.wait(timeout)

    def send(self, payload):
        if not isinstance(payload, bytes) or not 1 <= len(payload) <= MAX_COMMAND_BYTES:
            raise ValueError("指令必须是 1–4096 字节的 bytes")
        with self._lock:
            if self._state != "receiving" or self._halt.is_set():
                raise RuntimeError("当前没有可发送指令的连接")
            try:
                self._commands.put_nowait(payload)
            except queue.Full as exc:
                raise RuntimeError("发送队列已满，请等待后重试") from exc

    def _fail(self, message):
        with self._lock:
            if not self._error:
                self._error = str(message)
            self._reason = "error"
            self._halt.set()
            sock = self._sock
        self._event(str(message))
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def _open_part(self):
        path = self.directory / ("part_%05d.bin" % (len(self._parts) + 1))
        self._file = path.open("xb", buffering=1024 * 1024)
        self._part_size = 0
        self._parts.append({"name": path.name, "bytes": 0})

    def _close_part(self):
        if self._file is not None:
            handle, self._file = self._file, None
            try:
                handle.flush()
                os.fsync(handle.fileno())
            finally:
                handle.close()

    def _write_chunk(self, data):
        view = memoryview(data)
        while view:
            if self._part_size == self.config.roll_bytes:
                self._close_part()
                self._open_part()
            count = min(len(view), self.config.roll_bytes - self._part_size)
            actual = self._file.write(view[:count])
            if actual != count:
                raise OSError("文件写入不完整")
            self._part_size += count
            self._parts[-1]["bytes"] += count
            with self._lock:
                self._written += count
                self._pending -= count
            view = view[count:]

    def _write_loop(self):
        try:
            while True:
                try:
                    data = self._data.get(timeout=.1)
                except queue.Empty:
                    if self._rx_done.is_set():
                        break
                    continue
                self._write_chunk(data)
            self._close_part()
            self._durable = True
        except Exception as exc:
            self._writer_failed.set()
            self._fail("保存失败：" + str(exc))
        finally:
            try:
                self._close_part()
            except Exception as exc:
                self._writer_failed.set()
                self._durable = False
                self._fail("文件关闭失败：" + str(exc))

    def _send_loop(self, sock):
        while not self._halt.is_set():
            try:
                payload = self._commands.get(timeout=.1)
            except queue.Empty:
                continue
            if self._halt.is_set():
                self._event("连接正在结束，1 条已排队指令未发送")
                break
            try:
                sock.sendall(payload)
                with self._lock:
                    self._tx += len(payload)
                self._event("已提交 TCP 发送：%d 字节（不代表设备已执行）" % len(payload))
            except OSError as exc:
                self._event("指令发送未完成，可能已发送部分字节；不会自动重发")
                if not self._halt.is_set():
                    self._fail("发送失败：" + str(exc))
                break

    def _manifest(self, final=False):
        snap = self.snapshot()
        return dict(
            format_version=1, application="AD-HOST 0.1.0",
            started_utc=self._started_utc, ended_utc=self._ended_utc,
            remote_ip=self.config.host, remote_port=self.config.port,
            transport="TCP", payload_format="raw bytes, recv boundaries are not frames",
            chunk_bytes=self.config.chunk_bytes, queue_chunks=self.config.queue_chunks,
            roll_bytes=self.config.roll_bytes, parts=list(self._parts),
            state=snap["state"], end_reason=snap["end_reason"], error=snap["error"],
            elapsed_seconds=snap["elapsed"], received_bytes=snap["rx_bytes"],
            written_bytes=snap["written_bytes"], sent_bytes=snap["tx_bytes"],
            peak_pending_bytes=snap["peak_pending_bytes"],
            storage_complete=bool(final and self._durable and not self._writer_failed.is_set()
                                  and snap["rx_bytes"] == snap["written_bytes"]),
            source_completeness="not_verified", events=self.events(),
        )

    def _save_manifest(self, final=False):
        temporary = self.directory / "session.json.tmp"
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(self._manifest(final), handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(self.directory / "session.json")

    def _run(self):
        sock = None
        writer = sender = None
        try:
            self.directory.mkdir(parents=True, exist_ok=False)
            self._save_manifest()
            self._open_part()
            if self._halt.is_set():
                return
            family = socket.AF_INET6 if ipaddress.ip_address(self.config.host).version == 6 else socket.AF_INET
            sock = socket.socket(family, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
            sock.settimeout(3.0)
            sock.connect((self.config.host, self.config.port))
            sock.settimeout(.5)
            with self._lock:
                self._sock = sock
            if self._halt.is_set():
                return
            writer = threading.Thread(target=self._write_loop, name="disk-writer", daemon=True)
            sender = threading.Thread(target=self._send_loop, args=(sock,), name="command-sender", daemon=True)
            writer.start()
            sender.start()
            with self._lock:
                if not self._halt.is_set():
                    self._state = "receiving"
            self._event("连接成功，开始保存原始字节")
            while not self._halt.is_set():
                try:
                    data = sock.recv(self.config.chunk_bytes)
                except socket.timeout:
                    continue
                if not data:
                    with self._lock:
                        if self._reason is None:
                            self._reason = "peer_closed"
                    break
                with self._lock:
                    self._rx += len(data)
                    self._pending += len(data)
                    self._peak_pending = max(self._peak_pending, self._pending)
                    self._preview = data[-256:]
                # Preserve an already-received block even when the user stops.
                # A full queue applies TCP backpressure; it never discards blocks.
                while not self._writer_failed.is_set():
                    try:
                        self._data.put(data, timeout=.1)
                        break
                    except queue.Full:
                        continue
        except Exception as exc:
            if not (self._halt.is_set() and isinstance(exc, OSError)):
                self._fail("采集失败：" + str(exc))
        finally:
            self._halt.set()
            with self._lock:
                self._state = "finishing"
                self._sock = None
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                sock.close()
            self._rx_done.set()
            if sender is not None:
                sender.join()
            if writer is not None:
                writer.join()
            else:
                try:
                    self._close_part()
                except Exception as exc:
                    self._writer_failed.set()
                    self._fail("文件关闭失败：" + str(exc))
            unsent = self._commands.qsize()
            if unsent:
                self._event("%d 条已排队指令未发送" % unsent)
            # Release data after a disk error; pending counters remain as evidence.
            while True:
                try:
                    self._data.get_nowait()
                except queue.Empty:
                    break
            with self._lock:
                self._ended_clock = time.monotonic()
                self._ended_utc = datetime.now(timezone.utc).isoformat()
                self._state = "failed" if self._error else "finished"
                if self._reason is None:
                    self._reason = "local_stop"
            self._event("采集已结束；请核对接收量、保存量及设备端计数")
            try:
                if self.directory.is_dir():
                    self._save_manifest(final=True)
            except Exception as exc:
                self._fail("会话记录保存失败：" + str(exc))
                with self._lock:
                    self._state = "failed"
            self._done.set()
