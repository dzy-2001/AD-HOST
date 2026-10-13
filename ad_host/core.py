"""STM32/FPGA protocol-aware TCP capture.

The receiver thread only performs socket recv + protocol demultiplexing. ADC payload
is queued to a dedicated disk writer, so GUI work and file I/O do not run in the
socket receive loop.
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

ASCII_BYTES_PER_MS = 800_000
END_OK = b"\r\n*"
END_ERR = b"\r\n?"
_HEX_BYTES = frozenset(b"0123456789ABCDEF")


@dataclass(frozen=True)
class CaptureConfig:
    host: str
    port: int
    output_dir: Path
    chunk_bytes: int = 1024 * 1024
    queue_chunks: int = 512
    rcvbuf_bytes: int = 32 * 1024 * 1024

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
        if not 64 * 1024 <= self.rcvbuf_bytes <= 64 * 1024 * 1024:
            raise ValueError("Socket 接收缓冲必须在 64 KiB–64 MiB 之间")


class RateMeter:
    """Monotonic, actual-interval rates."""
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
    """One TCP connection with protocol-aware SET/GET capture."""
    def __init__(self, config):
        self.config = config
        self.directory = Path(config.output_dir).expanduser().resolve() / (
            datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
        )
        self.started_clock = time.monotonic()
        self._ended_clock = None
        self._started_utc = None
        self._ended_utc = None
        self._lock = threading.RLock()
        self._halt = threading.Event()
        self._done = threading.Event()
        self._commands = queue.Queue(maxsize=32)
        self._capture_q = queue.Queue(maxsize=config.queue_chunks)
        self._capture_writer_stop = object()
        self._events = deque(maxlen=300)
        self._sock = None
        self._worker = None
        self._capture_writer = None
        self._state = "new"
        self._reason = None
        self._error = ""
        self._rx = 0
        self._tx = 0
        self._preview = b""
        self._last_reply = ""
        self._reply_buf = bytearray()

        self._proto_state = "idle"  # idle / await_set / capture / await_end
        self._capture_ms = 0
        self._capture_expected = 0
        self._capture_received = 0
        self._capture_written = 0
        self._capture_pending = 0
        self._capture_peak_pending = 0
        self._capture_started_clock = 0.0
        self._capture_ended_clock = 0.0
        self._capture_complete = False
        self._capture_error = ""
        self._capture_path = ""
        self._capture_meta_path = ""
        self._capture_index = 0
        self._capture_file = None
        self._capture_meta = None
        self._capture_writer_done = threading.Event()
        self._capture_writer_done.set()

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
            expected = self._capture_expected
            received = self._capture_received
            progress = (received / expected) if expected else 0.0
            capture_elapsed = 0.0
            if self._capture_started_clock:
                capture_end = self._capture_ended_clock or end
                capture_elapsed = max(0.0, capture_end - self._capture_started_clock)
            return dict(
                state=self._state, error=self._error, end_reason=self._reason,
                rx_bytes=self._rx, tx_bytes=self._tx, clock=end,
                elapsed=max(0, end - self.started_clock), preview=self._preview,
                directory=str(self.directory), last_reply=self._last_reply,
                protocol_state=self._proto_state,
                capture_ms=self._capture_ms,
                capture_expected_bytes=expected,
                capture_received_bytes=received,
                capture_written_bytes=self._capture_written,
                capture_pending_bytes=self._capture_pending,
                capture_peak_pending_bytes=self._capture_peak_pending,
                capture_buffer_bytes=self.config.chunk_bytes * self.config.queue_chunks,
                capture_progress=progress,
                capture_elapsed=capture_elapsed,
                capture_complete=self._capture_complete,
                capture_error=self._capture_error,
                capture_path=self._capture_path,
            )

    def start(self):
        with self._lock:
            if self._state != "new":
                raise RuntimeError("每个连接会话只能启动一次")
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
        """Manual command. Disabled while an automatic SET/GET capture is active."""
        if not isinstance(payload, bytes) or not 1 <= len(payload) <= MAX_COMMAND_BYTES:
            raise ValueError("指令必须是 1–4096 字节的 bytes")
        with self._lock:
            if self._state != "receiving" or self._halt.is_set():
                raise RuntimeError("当前没有可发送指令的连接")
            if self._proto_state != "idle":
                raise RuntimeError("自动采集进行中，请等待本次 GET 完成")
        self._queue_command(payload, "手动指令")

    def send_text(self, command):
        if not command:
            raise ValueError("指令不能为空")
        self.send(command.encode("ascii") + b"\r")

    def start_capture(self, milliseconds):
        """Send SET <ms>,1; after '*' automatically send GET and save ADC HEX only."""
        try:
            milliseconds = int(milliseconds)
        except (TypeError, ValueError) as exc:
            raise ValueError("采集时间必须是 1–200 ms 的整数") from exc
        if not 1 <= milliseconds <= 200:
            raise ValueError("采集时间必须在 1–200 ms")
        with self._lock:
            if self._state != "receiving" or self._halt.is_set():
                raise RuntimeError("请先连接 STM32")
            if self._proto_state != "idle":
                raise RuntimeError("上一条采集尚未结束")
            if not self._capture_writer_done.is_set():
                raise RuntimeError("上一条采集文件仍在完成写入，请稍候")
            self._capture_index += 1
            self._capture_ms = milliseconds
            self._capture_expected = milliseconds * ASCII_BYTES_PER_MS
            self._capture_received = 0
            self._capture_written = 0
            self._capture_pending = 0
            self._capture_peak_pending = 0
            self._capture_started_clock = 0.0
            self._capture_ended_clock = 0.0
            self._capture_complete = False
            self._capture_error = ""
            self._capture_path = ""
            self._capture_meta_path = ""
            self._reply_buf.clear()
            self._proto_state = "await_set"
        self._queue_command(("SET %d,1\r" % milliseconds).encode("ascii"), "SET %d,1" % milliseconds)
        self._event("自动采集：等待 SET 成功回复，然后自动发送 GET")

    def _queue_command(self, payload, label):
        try:
            self._commands.put_nowait((payload, label))
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

    def _send_loop(self, sock):
        while not self._halt.is_set():
            try:
                payload, label = self._commands.get(timeout=.1)
            except queue.Empty:
                continue
            if self._halt.is_set():
                self._event("连接正在结束，1 条已排队指令未发送")
                break
            try:
                sock.sendall(payload)
                with self._lock:
                    self._tx += len(payload)
                self._event("已发送：%s" % label)
            except OSError as exc:
                if not self._halt.is_set():
                    self._fail("发送失败：" + str(exc))
                break

    def _open_capture_file(self):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = "capture_%03d_%dms_%s.hex" % (self._capture_index, self._capture_ms, stamp)
        path = self.directory / name
        meta_path = self.directory / (name + ".json")
        handle = path.open("xb", buffering=1024 * 1024)
        with self._lock:
            self._capture_file = handle
            self._capture_path = str(path)
            self._capture_meta_path = str(meta_path)
            self._capture_writer_done.clear()
            self._capture_started_clock = time.monotonic()
            self._capture_meta = {
                "format_version": 1,
                "application": "AD-HOST STM32/FPGA 0.2.0",
                "capture_ms": self._capture_ms,
                "payload_format": "uppercase ASCII HEX, big-endian uint16 voltage + uint16 current, 8 chars per pair",
                "expected_hex_bytes": self._capture_expected,
                "started_utc": datetime.now(timezone.utc).isoformat(),
                "complete": False,
            }
        self._event("GET 数据文件：%s，期望 %d 字节" % (name, self._capture_expected))

    def _finish_capture_file(self, complete, error=""):
        with self._lock:
            if error and not self._capture_error:
                self._capture_error = error
            self._capture_complete = bool(complete)
            self._capture_ended_clock = time.monotonic()
        # The writer closes/flushed file after sentinel. The metadata is written there.
        self._capture_q.put(self._capture_writer_stop)

    def _capture_write_loop(self):
        while not self._halt.is_set() or not self._capture_q.empty():
            try:
                item = self._capture_q.get(timeout=.1)
            except queue.Empty:
                continue
            if item is self._capture_writer_stop:
                handle = None
                meta = None
                meta_path = ""
                with self._lock:
                    handle, self._capture_file = self._capture_file, None
                    if self._capture_meta is not None:
                        meta = dict(self._capture_meta)
                        meta.update({
                            "ended_utc": datetime.now(timezone.utc).isoformat(),
                            "received_hex_bytes": self._capture_received,
                            "written_hex_bytes": self._capture_written,
                            "complete": self._capture_complete,
                            "error": self._capture_error,
                            "elapsed_seconds": self._capture_ended_clock - self._capture_started_clock
                                if self._capture_started_clock and self._capture_ended_clock else 0.0,
                        })
                        meta_path = self._capture_meta_path
                if handle is not None:
                    try:
                        handle.flush()
                        os.fsync(handle.fileno())
                    finally:
                        handle.close()
                if meta and meta_path:
                    with open(meta_path, "w", encoding="utf-8") as f:
                        json.dump(meta, f, ensure_ascii=False, indent=2)
                        f.flush(); os.fsync(f.fileno())
                self._capture_writer_done.set()
                continue
            handle = None
            with self._lock:
                handle = self._capture_file
            if handle is None:
                self._fail("内部错误：采集数据到达但文件未打开")
                return
            try:
                view = memoryview(item)
                while view:
                    n = handle.write(view)
                    if not n:
                        raise OSError("文件写入返回 0")
                    with self._lock:
                        self._capture_written += n
                        self._capture_pending -= n
                    view = view[n:]
            except Exception as exc:
                self._fail("采集文件写入失败：" + str(exc))
                return

    def _queue_capture_bytes(self, data):
        if not data:
            return
        # Validate before writing so a command/error reply can never silently contaminate ADC data.
        if any(b not in _HEX_BYTES for b in data):
            bad = next(b for b in data if b not in _HEX_BYTES)
            self._protocol_abort("GET 数据出现非 HEX 字节 0x%02X" % bad)
            return
        with self._lock:
            self._capture_received += len(data)
            self._capture_pending += len(data)
            self._capture_peak_pending = max(self._capture_peak_pending, self._capture_pending)
        while not self._halt.is_set():
            try:
                self._capture_q.put(data, timeout=.1)
                return
            except queue.Full:
                continue

    def _protocol_abort(self, message):
        with self._lock:
            active = self._proto_state != "idle"
            self._capture_error = message
            self._proto_state = "idle"
            self._last_reply = message
        self._event("本次采集失败：" + message)
        if active and self._capture_file is not None:
            self._finish_capture_file(False, message)

    def _record_reply(self, raw):
        text = raw.decode("ascii", "replace").strip()
        with self._lock:
            self._last_reply = text or repr(raw)
        self._event("设备回复：" + (text or repr(raw)))

    def _consume_idle(self, data):
        self._reply_buf.extend(data)
        if len(self._reply_buf) > 64 * 1024:
            del self._reply_buf[:-4096]
            self._event("空闲回复缓存超过 64 KiB，仅保留末尾")
        while True:
            ok = self._reply_buf.find(END_OK)
            er = self._reply_buf.find(END_ERR)
            candidates = [x for x in (ok, er) if x >= 0]
            if not candidates:
                break
            pos = min(candidates)
            end = pos + 3
            raw = bytes(self._reply_buf[:end])
            del self._reply_buf[:end]
            self._record_reply(raw)

    def _consume_set_reply(self, data):
        self._reply_buf.extend(data)
        ok = self._reply_buf.find(END_OK)
        er = self._reply_buf.find(END_ERR)
        if ok < 0 and er < 0:
            if len(self._reply_buf) > 4096:
                self._protocol_abort("SET 回复超过 4096 字节且未找到结束标记")
            return b""
        positions = [(ok, True) if ok >= 0 else None, (er, False) if er >= 0 else None]
        pos, success = min((x for x in positions if x is not None), key=lambda x: x[0])
        end = pos + 3
        reply = bytes(self._reply_buf[:end])
        leftover = bytes(self._reply_buf[end:])
        self._reply_buf.clear()
        self._record_reply(reply)
        if not success:
            self._protocol_abort("SET 被设备拒绝（?）")
            return leftover
        try:
            self._open_capture_file()
        except Exception as exc:
            self._protocol_abort("无法创建采集文件：" + str(exc))
            return leftover
        with self._lock:
            self._proto_state = "capture"
        self._queue_command(b"GET\r", "GET")
        return leftover

    def _consume_capture(self, data):
        with self._lock:
            remaining = self._capture_expected - self._capture_received
        if remaining <= 0:
            with self._lock:
                self._proto_state = "await_end"
            return data
        take = min(remaining, len(data))
        self._queue_capture_bytes(data[:take])
        with self._lock:
            reached = self._capture_received >= self._capture_expected
        if reached:
            with self._lock:
                self._proto_state = "await_end"
            return data[take:]
        return b""

    def _consume_end(self, data):
        self._reply_buf.extend(data)
        if len(self._reply_buf) < 3:
            return b""
        prefix = bytes(self._reply_buf[:3])
        if prefix == END_OK:
            leftover = bytes(self._reply_buf[3:])
            self._reply_buf.clear()
            with self._lock:
                self._proto_state = "idle"
                self._last_reply = "GET 完成 *"
            self._finish_capture_file(True)
            self._event("GET 完整：%d / %d HEX 字节，结束标记 * 正常" %
                        (self._capture_received, self._capture_expected))
            return leftover
        if prefix == END_ERR:
            leftover = bytes(self._reply_buf[3:])
            self._reply_buf.clear()
            self._protocol_abort("GET 返回 ?")
            return leftover
        self._protocol_abort("已收满期望数据，但后续不是 \\r\\n*；实际前3字节=%s" % prefix.hex(" ").upper())
        self._reply_buf.clear()
        return b""

    def _consume_protocol(self, data):
        pending = data
        for _ in range(8):
            if not pending:
                return
            with self._lock:
                state = self._proto_state
            if state == "idle":
                self._consume_idle(pending)
                return
            if state == "await_set":
                pending = self._consume_set_reply(pending)
            elif state == "capture":
                pending = self._consume_capture(pending)
            elif state == "await_end":
                pending = self._consume_end(pending)
            else:
                self._protocol_abort("未知协议状态：" + state)
                return

    def _session_manifest(self):
        snap = self.snapshot()
        return {
            "format_version": 2,
            "application": "AD-HOST STM32/FPGA 0.2.0",
            "started_utc": self._started_utc,
            "ended_utc": self._ended_utc,
            "remote_ip": self.config.host,
            "remote_port": self.config.port,
            "received_tcp_bytes": snap["rx_bytes"],
            "sent_tcp_bytes": snap["tx_bytes"],
            "state": snap["state"],
            "end_reason": snap["end_reason"],
            "error": snap["error"],
            "events": self.events(),
        }

    def _save_session_manifest(self):
        tmp = self.directory / "session.json.tmp"
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(self._session_manifest(), f, ensure_ascii=False, indent=2)
            f.flush(); os.fsync(f.fileno())
        tmp.replace(self.directory / "session.json")

    def _mark_active_capture_incomplete(self, reason):
        with self._lock:
            active = self._proto_state in ("capture", "await_end") and self._capture_file is not None
            waiting_set = self._proto_state == "await_set"
            if active or waiting_set:
                self._capture_error = reason
                self._proto_state = "idle"
        if active:
            self._finish_capture_file(False, reason)
            self._event("连接结束，本次 GET 不完整：%d / %d" %
                        (self._capture_received, self._capture_expected))
        elif waiting_set:
            self._event("连接结束，SET 尚未完成")

    def _run(self):
        sock = None
        sender = None
        try:
            self.directory.mkdir(parents=True, exist_ok=False)
            family = socket.AF_INET6 if ipaddress.ip_address(self.config.host).version == 6 else socket.AF_INET
            sock = socket.socket(family, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.config.rcvbuf_bytes)
            sock.settimeout(3.0)
            sock.connect((self.config.host, self.config.port))
            sock.settimeout(.5)
            with self._lock:
                self._sock = sock
                self._state = "receiving"
            self._capture_writer = threading.Thread(target=self._capture_write_loop, name="capture-writer", daemon=True)
            sender = threading.Thread(target=self._send_loop, args=(sock,), name="command-sender", daemon=True)
            self._capture_writer.start()
            sender.start()
            self._event("连接成功。自动采集只保存 GET 的 ADC HEX，不把 SET/VER/FST 回复混入数据文件。")
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
                    self._preview = data[-256:]
                self._consume_protocol(data)
        except Exception as exc:
            if not (self._halt.is_set() and isinstance(exc, OSError)):
                self._fail("连接/接收失败：" + str(exc))
        finally:
            self._mark_active_capture_incomplete("TCP 连接结束")
            self._halt.set()
            with self._lock:
                self._state = "finishing"
                self._sock = None
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    sock.close()
                except OSError:
                    pass
            if sender is not None:
                sender.join(timeout=2)
            # Make sure a capture file is flushed even if connection ended outside protocol.
            if self._capture_file is not None and self._capture_writer_done.is_set() is False:
                try:
                    self._capture_q.put_nowait(self._capture_writer_stop)
                except queue.Full:
                    self._capture_q.put(self._capture_writer_stop)
            if self._capture_writer is not None:
                self._capture_writer.join(timeout=10)
            with self._lock:
                self._ended_clock = time.monotonic()
                self._ended_utc = datetime.now(timezone.utc).isoformat()
                self._state = "failed" if self._error else "finished"
                if self._reason is None:
                    self._reason = "local_stop"
            self._event("连接已结束")
            try:
                self._save_session_manifest()
            except Exception as exc:
                with self._lock:
                    if not self._error:
                        self._error = "会话记录保存失败：" + str(exc)
                    self._state = "failed"
            self._done.set()
