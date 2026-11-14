"""Strict decoding and validation of the current new task only."""
from pathlib import Path

from task_checkpoint import atomic_json, phase, wav_record


def task_input(audio, work_dir, attempt, checkpoint, tools, stage):
    """Decode this invocation only; never examine prior task input or stems."""
    from mix_tracks import song_timeline

    work_dir, attempt = Path(work_dir), Path(attempt)
    with phase(stage, '正在严格完整解码本次原曲，创建全新输入 PCM'):
        try:
            timeline = song_timeline(audio, attempt, tools)
        except RuntimeError as error:
            raise RuntimeError(
                f'原始音频完整解码失败：{audio}。请使用完整且可解码的原文件。'
                f'解码器原始错误：{error}') from error
        record = wav_record(attempt / 'timeline.wav', work_dir, timeline)
        _save_input(checkpoint, work_dir, record)
    return attempt / 'timeline.wav', tuple(record['spec']), None


def _save_input(checkpoint, work_dir, record):
    checkpoint.update(decoded_input=record, timeline=record['spec'],
        timeline_source=dict(kind='decoded_input', input_sha256=checkpoint['identity']['audio_sha256']))
    checkpoint['status'] = 'input_complete'
    atomic_json(work_dir / 'task.json', checkpoint)
