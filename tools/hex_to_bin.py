"""Convert an AD-HOST capture_*.hex file to packed binary bytes."""
import argparse
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("output", nargs="?")
    args = ap.parse_args()
    src = Path(args.input)
    dst = Path(args.output) if args.output else src.with_suffix(".bin")
    carry = b""
    with src.open("rb") as fi, dst.open("wb") as fo:
        while True:
            chunk = fi.read(1024 * 1024)
            if not chunk:
                break
            chunk = carry + chunk
            if len(chunk) & 1:
                carry = chunk[-1:]
                chunk = chunk[:-1]
            else:
                carry = b""
            fo.write(bytes.fromhex(chunk.decode("ascii")))
        if carry:
            raise SystemExit("input HEX length is odd")
    print("%s -> %s (%d bytes)" % (src, dst, dst.stat().st_size))


if __name__ == "__main__":
    main()
