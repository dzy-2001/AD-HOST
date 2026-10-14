"""Offline ADC records: 8 ASCII HEX characters = big-endian U16 V + U16 I."""
from dataclasses import dataclass
import binascii
import math
import json
import os
from pathlib import Path

import numpy as np
from .calibration import voltage_from_adc,current_from_adc

SAMPLE_RATE_HZ = 100_000_000.0
MAX_SOURCE_BYTES = 1024 * 1024 * 1024
_SPACE = b' \t\r\n\v\f'


class ParseCancelled(Exception):
    """The user cancelled an offline file read."""


@dataclass(frozen=True)
class Recording:
    path: Path
    samples: np.ndarray
    trigger_index: int | None = None
    sample_rate_hz: float = SAMPLE_RATE_HZ
    metadata: dict | None = None


@dataclass(frozen=True)
class CurveView:
    indices: np.ndarray
    time_ms: np.ndarray
    voltage: np.ndarray
    current: np.ndarray


def load_recording(path, *, cancel=None, progress=None, chunk_size=1024 * 1024,
                   max_source_bytes=MAX_SOURCE_BYTES):
    """Read in chunks; never alter the input or silently discard a partial sample.

    A 160 MB ASCII record needs approximately 80 MB of decoded sample storage.
    No full-size floating-point channel arrays are allocated.
    """
    path = Path(path)
    metadata = None
    sidecar = Path(str(path)+'.json')
    if sidecar.exists():
        if sidecar.stat().st_size > 1024*1024:
            raise ValueError('记录元数据超过 1 MiB')
        try:
            metadata = json.loads(sidecar.read_text(encoding='utf-8'))
            if not isinstance(metadata,dict):raise ValueError('元数据必须为对象')
        except (ValueError,UnicodeError) as exc:
            raise ValueError('无法解析记录元数据：'+str(exc)) from exc
        if metadata.get('complete') is False:
            raise ValueError('该记录被标记为未完成，不能作为完整波形打开')
    if '.partial.' in path.name:
        raise ValueError('该文件是未完成的采集记录')
    is_v26 = metadata is not None and metadata.get('protocol') in ('V26','V28')
    if is_v26:
        from .v26_protocol import validate_record,record_rate_hz
        status = metadata.get('status')
        keys = ('SAMPLES','TOTAL','HEX_CHARS','BLOCKS','ACTIVE_PRE','RATE')
        if (metadata.get('complete') is not True or not isinstance(status,dict)
                or any(type(status.get(k)) is not int for k in keys)):
            raise ValueError('采集记录状态或元数据缺失')
        if metadata.get('protocol')=='V28' and 'ACTIVE_RATE_MSPS' not in status:
            raise ValueError('V28 记录缺少实际保存采样率')
        validate_record(status)
        saved_rate=record_rate_hz(status)
        if 'sample_rate_hz' in metadata and metadata['sample_rate_hz']!=saved_rate:
            raise ValueError('记录保存采样率与锁存状态不一致')
        if metadata.get('written_hex_bytes') != status['HEX_CHARS']:
            raise ValueError('采集写入字节数与记录长度不一致')
    if chunk_size < 1:
        raise ValueError('读取块大小必须大于零')
    with path.open('rb') as handle:
        original = os.fstat(handle.fileno())
        size = original.st_size
        if size > max_source_bytes:
            raise ValueError('文件大小超过本版支持的上限（默认 1 GiB ASCII 文件）')
        if cancel is not None and cancel.is_set():
            raise ParseCancelled()
        samples = np.empty((size // 8 + 1, 2), dtype=np.uint16)
        count = 0
        carry = b''
        if handle.read(3) != b'\xef\xbb\xbf':
            handle.seek(0)
        while handle.tell() < size:
            if cancel is not None and cancel.is_set():
                raise ParseCancelled()
            data = handle.read(min(chunk_size, size - handle.tell()))
            if not data:
                raise ValueError('文件在解析期间发生截断，请等待记录完成后再打开')
            text = carry + data.translate(None, _SPACE)
            complete = len(text) // 8 * 8
            carry = text[complete:]
            if complete:
                try:
                    decoded = binascii.unhexlify(text[:complete])
                except (binascii.Error, ValueError) as exc:
                    raise ValueError('文件含非 HEX 字符；请选择仅含 ADC ASCII HEX 的采集文件') from exc
                pairs = np.frombuffer(decoded, dtype='>u2').reshape(-1, 2)
                invalid = pairs[:, 0] > 4095
                if np.any(invalid):
                    index = int(np.flatnonzero(invalid)[0])
                    raise ValueError('第 %d 组电压原始值 %d 超过 12 位范围 0–4095；请检查文件格式和通道顺序'
                                     % (count + index, int(pairs[index, 0])))
                if np.any(pairs[:,1] > 4095):
                    raise ValueError('电流原始值超过 12 位范围 0–4095，无法按探头倍率换算')
                samples[count:count + len(pairs)] = pairs
                count += len(pairs)
            if progress is not None:
                progress(handle.tell(), size)
        if cancel is not None and cancel.is_set():
            raise ParseCancelled()
        final = os.fstat(handle.fileno())
        if final.st_size != size or final.st_mtime_ns != original.st_mtime_ns:
            raise ValueError('文件在解析期间发生变化，请等待记录完成后再打开')
    if carry:
        raise ValueError('HEX 字符总数不是 8 的整数倍：末尾剩余 %d 个字符，不足一组电压/电流' % len(carry))
    if count == 0:
        raise ValueError('文件中没有完整的电压/电流数据')
    samples = samples[:count]
    samples.flags.writeable = False
    if is_v26 and count != status['SAMPLES']:
        raise ValueError('文件实际点数与采集元数据不一致')
    return Recording(path, samples, status['ACTIVE_PRE'] if is_v26 else None,
                     saved_rate if is_v26 else SAMPLE_RATE_HZ, metadata)


def make_view(recording, *, start=0, stop=None, max_points=6000, sample_rate_hz=None):
    """Rebuild a view from original samples, retaining both channels' extrema.

    Full-detail windows contain every sample. Overview windows contain each bin's
    V/I minimum and maximum at their original sample positions, plus endpoints.
    """
    size = len(recording.samples)
    if sample_rate_hz is None:
        sample_rate_hz = recording.sample_rate_hz
    stop = size if stop is None else stop
    if not 0 <= start < stop <= size:
        raise ValueError('显示范围必须满足 0 ≤ 起点 < 终点 ≤ 总点数')
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError('采样率必须是大于零的有限数值')
    if max_points < 6:
        raise ValueError('绘图点数预算至少为 6')
    count = stop - start
    if count <= max_points:
        indices = np.arange(start, stop, dtype=np.int64)
    else:
        bins = max(1, (max_points - 2) // 4)
        edges = np.linspace(start, stop, bins + 1, dtype=np.int64)
        selected = [start, stop - 1]
        for left, right in zip(edges[:-1], edges[1:]):
            block = recording.samples[left:right]
            for channel in (0, 1):
                selected.append(int(left + np.argmin(block[:, channel])))
                selected.append(int(left + np.argmax(block[:, channel])))
        indices = np.unique(selected)
    raw = recording.samples[indices]
    return CurveView(
        indices=indices,
        time_ms=(indices.astype(np.float64) - (recording.trigger_index or 0)) * (1000.0 / sample_rate_hz),
        voltage=voltage_from_adc(raw[:, 0].astype(np.float64)),
        current=current_from_adc(raw[:, 1].astype(np.float64)),
    )
