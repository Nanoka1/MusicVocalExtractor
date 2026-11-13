"""Durable, content-checked recovery records; filenames never imply success."""
import hashlib
import json
import os
import struct
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path


def digest(path):
    path = Path(path)
    before = path.stat()
    with path.open('rb') as source:
        value = hashlib.file_digest(source, 'sha256').hexdigest()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError(f'校验期间文件发生变化：{path}')
    return value


def atomic_json(path, data):
    path = Path(path)
    handle, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    with os.fdopen(handle, 'w', encoding='utf-8') as output:
        json.dump(data, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def wav_record(path, root, expected=None):
    """Check RIFF lengths, every decoded frame, finiteness and SHA-256."""
    import numpy as np
    import soundfile as sf

    path, root = Path(path).resolve(), Path(root).resolve()
    if not path.is_relative_to(root):
        raise ValueError('检查点文件位于任务目录之外。')
    before = path.stat()
    with path.open('rb') as stream:
        header = stream.read(12)
        if header[:4] != b'RIFF' or header[8:] != b'WAVE':
            raise ValueError(f'恢复文件必须是完整 RIFF WAV：{path}')
        if struct.unpack('<I', header[4:8])[0] + 8 != before.st_size:
            raise ValueError(f'WAV 文件长度不完整：{path}')
        while stream.tell() + 8 <= before.st_size:
            name, size = struct.unpack('<4sI', stream.read(8))
            if stream.tell() + size > before.st_size:
                raise ValueError(f'WAV 数据段被截断：{path}')
            stream.seek(size + size % 2, 1)
    with sf.SoundFile(path) as audio:
        spec = [audio.frames, audio.samplerate, audio.channels]
        if audio.frames <= 0 or audio.format not in {'WAV', 'WAVEX'}:
            raise ValueError(f'无效 WAV：{path}')
        if expected is not None and spec != list(expected):
            raise ValueError(f'音轨时间轴不一致：{path}，{spec} != {expected}')
        frames = 0
        for block in audio.blocks(blocksize=65536, dtype='float32', always_2d=True):
            if not np.isfinite(block).all():
                raise ValueError(f'音轨含有 NaN/Inf：{path}')
            frames += len(block)
        if frames != spec[0]:
            raise ValueError(f'音轨未完整解码：{path}')
    value = digest(path)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError(f'音频校验期间文件发生变化：{path}')
    return dict(path=path.relative_to(root).as_posix(), sha256=value, size=after.st_size, spec=spec)


def checked_paths(records, root):
    paths = {}
    for label, record in records.items():
        path = Path(root) / record['path']
        if wav_record(path, root, record['spec']) != record:
            raise ValueError(f'检查点音轨校验失败：{path}')
        paths[label] = path
    return paths


@contextmanager
def phase(stage, message, interval=10):
    """Send the same live stage and elapsed time to console and Gradio."""
    stopped = threading.Event()
    started = time.monotonic()
    stage(message)

    def pulse():
        while not stopped.wait(interval):
            stage(f'{message}（此阶段已用 {time.monotonic() - started:.0f} 秒）')

    thread = threading.Thread(target=pulse, daemon=True, name='separation-status')
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join()


def model_signature(model_dir, names):
    return {name: digest(Path(model_dir) / name) if (Path(model_dir) / name).is_file() else None
            for name in names}


def identity_matches(saved, current, allow_downloaded=()):
    """Only previously absent, explicitly allowed models may gain a fingerprint."""
    if saved == current:
        return True
    previous = dict(saved, models=dict(saved.get('models', {})))
    for name in allow_downloaded:
        if name in previous['models'] and previous['models'][name] is None:
            previous['models'][name] = current.get('models', {}).get(name)
    return previous == current
