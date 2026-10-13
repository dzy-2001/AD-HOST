import json
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from ad_host.core import ASCII_BYTES_PER_MS, CaptureConfig, CaptureSession, RateMeter


class Server:
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


def recv_line(conn):
    data = bytearray()
    while not data.endswith(b"\r"):
        chunk = conn.recv(1024)
        if not chunk:
            raise AssertionError("client closed")
        data.extend(chunk)
    return bytes(data)


def wait_for(session, predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snap = session.snapshot()
        if predicate(snap):
            return snap
        if snap["state"] == "failed":
            raise AssertionError(snap)
        time.sleep(.01)
    raise AssertionError(session.snapshot())


class ProtocolCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def session(self, server, **kwargs):
        s = CaptureSession(CaptureConfig("127.0.0.1", server.port, Path(self.temp.name), **kwargs))
        self.addCleanup(lambda: (s.stop(), s.wait(10)))
        s.start()
        wait_for(s, lambda x: x["state"] == "receiving")
        return s

    def test_auto_set_get_saves_only_adc_hex(self):
        payload = b"082A08A5" * (ASCII_BYTES_PER_MS // 8)

        def peer(conn):
            self.assertEqual(recv_line(conn), b"SET 1,1\r")
            conn.sendall(b"\r")
            conn.sendall(b"\n*")
            self.assertEqual(recv_line(conn), b"GET\r")
            for off in range(0, len(payload), 13711):
                conn.sendall(payload[off:off + 13711])
            conn.sendall(b"\r\n*")
            while conn.recv(1024):
                pass

        server = Server(peer)
        s = self.session(server, chunk_bytes=32768, queue_chunks=8)
        s.start_capture(1)
        snap = wait_for(s, lambda x: x["capture_complete"] and x["capture_written_bytes"] == len(payload), timeout=15)
        path = Path(snap["capture_path"])
        self.assertTrue(path.exists())
        self.assertEqual(path.read_bytes(), payload)
        meta = json.loads(Path(str(path) + ".json").read_text("utf-8"))
        self.assertTrue(meta["complete"])
        self.assertEqual(meta["expected_hex_bytes"], ASCII_BYTES_PER_MS)
        self.assertEqual(meta["received_hex_bytes"], ASCII_BYTES_PER_MS)
        self.assertEqual(meta["written_hex_bytes"], ASCII_BYTES_PER_MS)
        self.assertNotIn(b"\r\n*", path.read_bytes())
        s.stop(); self.assertTrue(s.wait(10)); server.finish()

    def test_set_reject_does_not_create_capture_file(self):
        def peer(conn):
            self.assertEqual(recv_line(conn), b"SET 10,1\r")
            conn.sendall(b"\r\n?")
            while conn.recv(1024):
                pass
        server = Server(peer)
        s = self.session(server)
        s.start_capture(10)
        snap = wait_for(s, lambda x: x["protocol_state"] == "idle" and "SET" in x["capture_error"])
        self.assertFalse(snap["capture_path"])
        self.assertEqual(snap["capture_received_bytes"], 0)
        s.stop(); self.assertTrue(s.wait(10)); server.finish()

    def test_non_hex_payload_marks_capture_incomplete(self):
        def peer(conn):
            self.assertEqual(recv_line(conn), b"SET 1,1\r")
            conn.sendall(b"\r\n*")
            self.assertEqual(recv_line(conn), b"GET\r")
            conn.sendall(b"082A08A5XYZ")
            while conn.recv(1024):
                pass
        server = Server(peer)
        s = self.session(server)
        s.start_capture(1)
        snap = wait_for(s, lambda x: x["protocol_state"] == "idle" and "非 HEX" in x["capture_error"])
        self.assertFalse(snap["capture_complete"])
        s.stop(); self.assertTrue(s.wait(10)); server.finish()

    def test_manual_command_blocked_while_capture_active(self):
        gate = threading.Event()
        def peer(conn):
            self.assertEqual(recv_line(conn), b"SET 1,1\r")
            gate.wait(3)
            conn.sendall(b"\r\n?")
            while conn.recv(1024):
                pass
        server = Server(peer)
        s = self.session(server)
        s.start_capture(1)
        with self.assertRaises(RuntimeError):
            s.send_text("FST")
        gate.set()
        wait_for(s, lambda x: x["protocol_state"] == "idle")
        s.stop(); self.assertTrue(s.wait(10)); server.finish()

    def test_expected_size_formula(self):
        server = Server(lambda conn: time.sleep(.5))
        s = self.session(server)
        # Do not need the server to answer SET; snapshot must expose expected length immediately.
        s.start_capture(10)
        self.assertEqual(s.snapshot()["capture_expected_bytes"], 8_000_000)
        s.stop(); self.assertTrue(s.wait(10)); server.finish()


class RateTests(unittest.TestCase):
    def test_rates(self):
        meter = RateMeter(0.0)
        self.assertEqual(meter.sample(1.0, 1_000_000)["instant"], 1_000_000)
        r = meter.sample(3.0, 5_000_000)
        self.assertEqual(r["instant"], 2_000_000)
        self.assertAlmostEqual(r["average"], 5_000_000 / 3)


if __name__ == "__main__":
    unittest.main()
