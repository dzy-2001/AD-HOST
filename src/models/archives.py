"""Explicit waveform archives; acquisition cache remains owned by the controller."""
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import threading


def reserve_directory(parent,now=None):
    """Atomically claim a minute-based name without overwriting existing data."""
    parent=Path(parent);parent.mkdir(parents=True,exist_ok=True)
    stem=(now or datetime.now()).strftime('%Y%m%d_%H%M')
    suffix=0
    while True:
        path=parent/(stem if suffix==0 else f'{stem}_{suffix}')
        try:path.mkdir();return path
        except FileExistsError:suffix+=1


def save_archive(source,parent,*,now=None):
    source=Path(source)
    meta=json.loads(Path(str(source)+'.json').read_text('utf-8'))
    expected=meta.get('expected_hex_bytes')
    if meta.get('complete') is not True or type(expected) is not int or expected<=0 or source.stat().st_size!=expected:
        raise ValueError('只有已完整接收且长度正确的波形可以存档')
    directory=reserve_directory(parent,now)
    target=directory/(directory.name+'.hex')
    partial=directory/(directory.name+'.partial.hex')
    metadata=Path(str(target)+'.json')
    try:
        with source.open('rb') as src,partial.open('xb') as dst:
            shutil.copyfileobj(src,dst,1024*1024);dst.flush();os.fsync(dst.fileno())
        if partial.stat().st_size!=expected:raise OSError('存档长度与原记录不一致')
        with metadata.open('x',encoding='utf-8') as dst:
            json.dump(meta,dst,ensure_ascii=False,indent=2);dst.flush();os.fsync(dst.fileno())
        partial.replace(target)
        return target
    except Exception:
        # Only remove files created by this operation in its exclusively claimed directory.
        for path in (partial,metadata):
            try:path.unlink(missing_ok=True)
            except OSError:pass
        try:directory.rmdir()
        except OSError:pass
        raise


class ArchiveJob:
    def __init__(self,source,parent):
        self.source=Path(source);self.parent=Path(parent)
        self.done=threading.Event();self.path=None;self.error=''
        self.thread=threading.Thread(target=self._run,name='waveform-archive',daemon=True)

    def start(self):self.thread.start()

    def _run(self):
        try:self.path=save_archive(self.source,self.parent)
        except Exception as exc:self.error=str(exc)
        finally:self.done.set()
