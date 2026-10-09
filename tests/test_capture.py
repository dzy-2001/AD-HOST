import json
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from ad_host.core import CaptureConfig, CaptureSession, RateMeter


class Server:
    """One local TCP peer; propagates server-thread exceptions to the test."""
    def __init__(self, handler):
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.listener.settimeout(8)
        self.port = self.listener.getsockname()[1]
        self.handler = handler
        self.error = None
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        try:
            with self.listener:
                conn, _ = self.listener.accept()
                with conn:
                    conn.settimeout(8)
                    self.handler(conn)
        except Exception as exc:
            self.error = exc

    def finish(self):
        self.thread.join(10)
        if self.thread.is_alive():
            raise AssertionError("server did not finish")
        if self.error:
            raise self.error


def await_state(session, state, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snap = session.snapshot()
        if snap["state"] == state:
            return snap
        if snap["state"] in ("failed", "finished"):
            raise AssertionError(snap)
        time.sleep(0.01)
    raise AssertionError(session.snapshot())


def saved_bytes(session):
    return b"".join(p.read_bytes() for p in sorted(session.directory.glob("part_*.bin")))


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def session(self, server, **kwargs):
        session = CaptureSession(CaptureConfig("127.0.0.1", server.port, Path(self.temp.name), **kwargs))
        self.addCleanup(lambda: (session.stop(), session.wait(10)))
        session.start()
        return session

    def test_fragmented_stream_rollover_and_command_on_same_connection(self):
        payload = bytes(range(256)) * 8192 + b"tail"
        command = b"\xaa\x55\x00\xff\r\n"
        received = bytearray()

        def peer(conn):
            # Data flows before and after the command.
            conn.sendall(payload[:777])
            while len(received) < len(command):
                data = conn.recv(len(command) - len(received))
                if not data:
                    raise AssertionError("client closed before command")
                received.extend(data)
            for offset in range(777, len(payload), 13001):
                conn.sendall(payload[offset:offset + 13001])
            conn.shutdown(socket.SHUT_WR)

        server = Server(peer)
        session = self.session(server, chunk_bytes=16384, queue_chunks=4, roll_bytes=100003)
        await_state(session, "receiving")
        session.send(command)
        self.assertTrue(session.wait(12), session.snapshot())
        server.finish()
        snap = session.snapshot()
        self.assertEqual(snap["state"], "finished", snap)
        self.assertEqual(saved_bytes(session), payload)
        self.assertEqual(bytes(received), command)
        self.assertEqual(snap["rx_bytes"], len(payload))
        self.assertEqual(snap["written_bytes"], len(payload))
        self.assertEqual(snap["pending_bytes"], 0)
        self.assertEqual(snap["tx_bytes"], len(command))
        manifest = json.loads((session.directory / "session.json").read_text("utf-8"))
        self.assertTrue(manifest["storage_complete"])
        self.assertEqual(manifest["end_reason"], "peer_closed")
        self.assertEqual(manifest["source_completeness"], "not_verified")
        parts = sorted(session.directory.glob("part_*.bin"))
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(p.stat().st_size <= 100003 for p in parts))

    def test_local_stop_flushes_already_received_data(self):
        payload = b"received-before-stop" * 20000
        def peer(conn):
            conn.sendall(payload)
            while conn.recv(1024):
                pass
        server = Server(peer)
        session = self.session(server, queue_chunks=2, chunk_bytes=8192)
        deadline = time.monotonic() + 8
        while session.snapshot()["rx_bytes"] < len(payload) and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertEqual(session.snapshot()["rx_bytes"], len(payload))
        session.stop()
        self.assertTrue(session.wait(10))
        server.finish()
        self.assertEqual(saved_bytes(session), payload)
        manifest = json.loads((session.directory / "session.json").read_text("utf-8"))
        self.assertEqual(manifest["end_reason"], "local_stop")
        self.assertTrue(manifest["storage_complete"])

    def test_backpressure_is_bounded_and_preserves_bytes(self):
        payload = bytes(range(251)) * 10000
        original = CaptureSession._write_chunk
        def slow_write(session, chunk):
            time.sleep(.002)
            return original(session, chunk)
        server = Server(lambda conn: conn.sendall(payload))
        with patch.object(CaptureSession, "_write_chunk", slow_write):
            session = self.session(server, chunk_bytes=8192, queue_chunks=2, roll_bytes=100000)
            self.assertTrue(session.wait(15), session.snapshot())
        server.finish()
        snap = session.snapshot()
        self.assertEqual(saved_bytes(session), payload)
        # Queue, one writer-owned block and one receiver-owned block.
        self.assertLessEqual(snap["peak_pending_bytes"], 4 * 8192)
        self.assertEqual(snap["state"], "finished", snap)

    def test_write_failure_is_explicit_and_never_claims_complete(self):
        server = Server(lambda conn: conn.sendall(b"x" * 65536))
        with patch.object(CaptureSession, "_write_chunk", side_effect=OSError("disk full")):
            session = self.session(server)
            self.assertTrue(session.wait(10))
        server.finish()
        snap = session.snapshot()
        self.assertEqual(snap["state"], "failed")
        self.assertIn("disk full", snap["error"])
        manifest = json.loads((session.directory / "session.json").read_text("utf-8"))
        self.assertFalse(manifest["storage_complete"])

    def test_output_failure_does_not_connect(self):
        bad = Path(self.temp.name) / "file"
        bad.write_text("not a directory")
        session = CaptureSession(CaptureConfig("127.0.0.1", 1, bad))
        session.start()
        self.assertTrue(session.wait(5))
        self.assertEqual(session.snapshot()["state"], "failed")

    def test_refused_connection_and_repeated_stop(self):
        with socket.socket() as unused:
            unused.bind(("127.0.0.1", 0))
            port = unused.getsockname()[1]
        session = CaptureSession(CaptureConfig("127.0.0.1", port, Path(self.temp.name)))
        session.start()
        self.assertTrue(session.wait(8))
        session.stop()
        session.stop()
        self.assertEqual(session.snapshot()["state"], "failed")
        with self.assertRaises(RuntimeError):
            session.send(b"test")
        with self.assertRaises(RuntimeError):
            session.start()

    def test_invalid_config(self):
        for kwargs in ({"port": 0}, {"host": "not an IP"}, {"queue_chunks": 0},
                       {"chunk_bytes": 0}, {"roll_bytes": 0}):
            args = dict(host="127.0.0.1", port=5000, output_dir=Path(self.temp.name))
            args.update(kwargs)
            with self.assertRaises(ValueError):
                CaptureConfig(**args)


class RateTests(unittest.TestCase):
    def test_rates_include_idle_time_and_do_not_depend_on_timer_precision(self):
        meter = RateMeter(0.0)
        self.assertEqual(meter.sample(1.0, 1000000)["instant"], 1000000)
        result = meter.sample(3.0, 5000000)
        self.assertEqual(result["instant"], 2000000)
        self.assertAlmostEqual(result["average"], 5000000 / 3)
        self.assertEqual(result["peak"], 2000000)
        result = meter.sample(13.0, 5000000)
        self.assertEqual(result["instant"], 0)
        self.assertEqual(result["recent"], 0)
        self.assertEqual(result["peak"], 2000000)
        self.assertEqual(meter.sample(13.0, 5000000), result)
