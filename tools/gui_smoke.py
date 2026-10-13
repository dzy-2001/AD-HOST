"""Windows CI smoke test: real Tk + automatic SET/GET + exact capture file."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import socket
import tempfile
import threading
import time
import tkinter as tk

from ad_host.core import ASCII_BYTES_PER_MS
from ad_host.gui import App

listener = socket.socket(); listener.bind(("127.0.0.1", 0)); listener.listen(1); listener.settimeout(10)
port = listener.getsockname()[1]
payload = b"082A08A5" * (ASCII_BYTES_PER_MS // 8)
errors = []

def recv_line(conn):
    b = bytearray()
    while not b.endswith(b"\r"):
        d = conn.recv(1024)
        if not d: raise AssertionError("client closed")
        b.extend(d)
    return bytes(b)

def peer():
    try:
        with listener:
            conn, _ = listener.accept()
            with conn:
                conn.settimeout(10)
                assert recv_line(conn) == b"SET 1,1\r"
                conn.sendall(b"\r\n*")
                assert recv_line(conn) == b"GET\r"
                conn.sendall(payload)
                conn.sendall(b"\r\n*")
                while conn.recv(1024): pass
    except Exception as exc:
        errors.append(exc)

thread = threading.Thread(target=peer, daemon=True); thread.start()
with tempfile.TemporaryDirectory() as directory:
    root = tk.Tk(); app = App(root)
    app.host.set("127.0.0.1"); app.port.set(str(port)); app.output.set(directory); app.capture_ms.set("1")
    app.connect_button.invoke()
    deadline = time.monotonic() + 20; started = False
    while time.monotonic() < deadline:
        root.update()
        if app.session and app.session.snapshot()["state"] == "receiving" and not started:
            app.auto_capture(); started = True
        if started:
            snap = app.session.snapshot()
            if snap["capture_complete"] and snap["capture_written_bytes"] == len(payload): break
        time.sleep(.01)
    assert started
    snap = app.session.snapshot(); assert snap["capture_complete"], snap
    app.stop()
    assert app.session.wait(10)
    thread.join(5); assert not errors, errors
    assert Path(snap["capture_path"]).read_bytes() == payload
    app.on_close()
print("PASS: Tk UI auto SET/GET saves exact ADC HEX payload")
