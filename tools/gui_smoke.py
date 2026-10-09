"""Windows CI smoke test: real Tk window + command + capture + clean exit."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import socket
import tempfile
import threading
import time
import tkinter as tk

from ad_host.gui import App

listener = socket.socket()
listener.bind(("127.0.0.1", 0))
listener.listen(1)
listener.settimeout(10)
port = listener.getsockname()[1]
payload = bytes(range(256)) * 100
errors = []

def peer():
    try:
        with listener:
            conn, _ = listener.accept()
            with conn:
                conn.settimeout(10)
                received = bytearray()
                while len(received) < 2:
                    chunk = conn.recv(2 - len(received))
                    if not chunk:
                        raise AssertionError("missing command")
                    received.extend(chunk)
                assert received == b"\xaa\x55", received
                conn.sendall(payload)
    except Exception as exc:
        errors.append(exc)

thread = threading.Thread(target=peer, daemon=True)
thread.start()
with tempfile.TemporaryDirectory() as directory:
    root = tk.Tk()
    app = App(root)
    app.host.set("127.0.0.1")
    app.port.set(str(port))
    app.output.set(directory)
    app.command_text.insert("1.0", "AA 55")
    app.connect_button.invoke()
    deadline = time.monotonic() + 15
    sent = False
    while time.monotonic() < deadline:
        root.update()
        if app.session.snapshot()["state"] == "receiving" and not sent:
            app.send()
            sent = True
        if app.session.wait(0):
            break
        time.sleep(.01)
    assert sent
    assert app.session.wait(0), app.session.snapshot()
    thread.join(5)
    assert not thread.is_alive()
    assert not errors, errors
    assert app.session.snapshot()["state"] == "finished", app.session.snapshot()
    assert b"".join(p.read_bytes() for p in sorted(app.session.directory.glob("part_*.bin"))) == payload
    app.refresh()
    app.on_close()
print("PASS: Tk UI connects, sends exact HEX bytes, saves received data and exits")
