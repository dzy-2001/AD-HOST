"""Local-only test peer; does not connect to real equipment."""
import argparse
import socket
import threading
import time


def main():
    parser = argparse.ArgumentParser(description="AD-HOST local TCP simulator")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--mib", type=int, default=64, help="payload size in MiB")
    parser.add_argument("--mbps", type=float, default=10, help="payload MB/s; 0 = unthrottled")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or args.mib <= 0 or args.mbps < 0:
        parser.error("invalid port, size or rate")
    with socket.socket() as server:
        server.bind(("127.0.0.1", args.port))
        server.listen(1)
        print("Listening on 127.0.0.1:%d; connect AD-HOST to this address." % args.port, flush=True)
        conn, address = server.accept()
        with conn:
            conn.settimeout(.5)
            stop = threading.Event()
            def commands():
                while not stop.is_set():
                    try:
                        data = conn.recv(4096)
                        if not data:
                            break
                        print("RX command stream chunk (not a frame):", data.hex(" "), flush=True)
                    except socket.timeout:
                        continue
                    except OSError:
                        break
            receiver = threading.Thread(target=commands, daemon=True)
            receiver.start()
            block = bytes(range(256)) * 1024
            total = args.mib * 1024 * 1024
            sent = 0
            started = time.monotonic()
            try:
                while sent < total:
                    chunk = block[:min(len(block), total - sent)]
                    conn.sendall(chunk)
                    sent += len(chunk)
                    if args.mbps:
                        delay = sent / (args.mbps * 1e6) - (time.monotonic() - started)
                        if delay > 0:
                            time.sleep(delay)
                print("Sent %d bytes; compare with AD-HOST received/written totals." % sent, flush=True)
                conn.shutdown(socket.SHUT_WR)
            except OSError as exc:
                print("Connection ended:", exc, "completed sendall bytes:", sent)
            finally:
                stop.set()
                receiver.join(2)


if __name__ == "__main__":
    main()
