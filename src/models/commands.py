"""Strict command encoding. No framing or checksum is invented."""
import re

MAX_COMMAND_BYTES = 4096


def encode_command(text, mode="HEX", ending="NONE"):
    if mode == "HEX":
        compact = re.sub(r"\s+", "", text)
        if not compact or len(compact) % 2 or not re.fullmatch(r"[0-9a-fA-F]+", compact):
            raise ValueError("HEX 必须是完整字节，例如 AA 55 01 FF；不支持 0x 前缀")
        payload = bytes.fromhex(compact)
    elif mode == "UTF-8":
        if not text:
            raise ValueError("指令不能为空")
        payload = text.encode("utf-8")
    else:
        raise ValueError("未知指令格式")
    suffix = {"NONE": b"", "LF": b"\n", "CR": b"\r", "CRLF": b"\r\n"}
    if ending not in suffix:
        raise ValueError("未知结束符")
    payload += suffix[ending]
    if len(payload) > MAX_COMMAND_BYTES:
        raise ValueError("单条指令不能超过 4096 字节")
    return payload
