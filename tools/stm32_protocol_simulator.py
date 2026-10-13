"""Local STM32 protocol simulator for AD-HOST protocol mode.

Implements VER / FST / FINIT / SET <ms>,1 / GET. GET returns the expected
800,000 ASCII HEX bytes per ms and a final CRLF* marker.
"""
import argparse
import socket
import time

ASCII_BYTES_PER_MS = 800_000
PATTERN = b"082A08A5"


def recv_command(conn, buf):
    while b"\r" not in buf:
        data = conn.recv(4096)
        if not data:
            return None, b""
        buf += data
    line, buf = buf.split(b"\r", 1)
    return line.decode("ascii", "replace").strip(), buf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=11235)
    ap.add_argument("--mbps", type=float, default=5.0, help="ASCII payload MB/s; 0=unlimited")
    args = ap.parse_args()
    with socket.socket() as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", args.port)); server.listen(1)
        print("Listening on 127.0.0.1:%d" % args.port, flush=True)
        conn, addr = server.accept()
        with conn:
            print("Connected", addr, flush=True)
            buf = b""; ms = None; record_pending = False
            while True:
                command, buf = recv_command(conn, buf)
                if command is None:
                    break
                print("CMD", command, flush=True)
                if command == "VER":
                    conn.sendall(b"V1.0.10\r\n*")
                elif command == "FST":
                    conn.sendall(b"ID:ADFC,VER:0100,INIT:1,IERR:0,RDY:1\r\n*")
                elif command == "FINIT":
                    conn.sendall(b"\r\n*")
                elif command.startswith("SET "):
                    try:
                        left, enable = command[4:].split(",", 1)
                        ms = int(left.strip()); enable = int(enable.strip())
                        if not (1 <= ms <= 200 and enable in (0, 1)):
                            raise ValueError
                        record_pending = bool(enable)
                        conn.sendall(b"\r\n*")
                    except Exception:
                        conn.sendall(b"\r\n?")
                elif command == "GET" and record_pending and ms:
                    total = ms * ASCII_BYTES_PER_MS
                    sent = 0; started = time.monotonic()
                    block = PATTERN * (256 * 1024 // len(PATTERN))
                    while sent < total:
                        chunk = block[:min(len(block), total - sent)]
                        conn.sendall(chunk); sent += len(chunk)
                        if args.mbps > 0:
                            wait = sent / (args.mbps * 1e6) - (time.monotonic() - started)
                            if wait > 0: time.sleep(wait)
                    conn.sendall(b"\r\n*"); record_pending = False
                    print("GET sent", sent, "bytes", flush=True)
                else:
                    conn.sendall(b"\r\n?")


if __name__ == "__main__":
    main()
