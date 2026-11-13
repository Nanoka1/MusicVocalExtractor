"""Verified decoded input and timeline recovery, independent of model execution."""
from pathlib import Path

from task_checkpoint import atomic_json, checked_paths, phase, wav_record


def _timeline(value):
    if (not isinstance(value, (list, tuple)) or len(value) != 3
            or any(type(item) is not int or item <= 0 for item in value)):
        raise ValueError('任务时间轴必须包含有效的帧数、采样率和声道数。')
    return tuple(value)


def task_input(audio, work_dir, attempt, checkpoint, tools, stage):
    """Reuse complete model results before attempting to decode the source again."""
    from mix_tracks import song_timeline
    from separation_recovery import base_records

    work_dir = Path(work_dir)
    source_hash = checkpoint['identity']['audio_sha256']
    stems = None
    if checkpoint.get('base'):
        with phase(stage, '恢复校验：完整读取第一阶段人声及伴奏 WAV'):
            stems = checked_paths(checkpoint['base'], work_dir)
            if set(stems) != {'Vocals', 'Instrumental'}:
                raise ValueError('第一阶段恢复必须同时包含完整人声和伴奏。')
            if checkpoint.get('timeline') is not None:
                timeline = _timeline(checkpoint['timeline'])
                basis = checkpoint.get('timeline_source', {})
                if basis.get('input_sha256') != source_hash:
                    raise ValueError('保存的时间轴未关联当前原曲内容，拒绝复用。')
                kind = basis.get('kind')
                if kind == 'confirmed_existing_stems':
                    hashes = {label: item['sha256'] for label, item in checkpoint['base'].items()}
                    if basis.get('base_sha256') != hashes:
                        raise ValueError('确认恢复的旧时间轴与音轨文件不匹配。')
                elif kind != 'decoded_input':
                    raise ValueError('不支持此时间轴来源，恢复材料已保留。')
                base_records(stems, work_dir, timeline)
                stage('第一阶段恢复：音轨及已保存时间轴校验通过，跳过基础模型及原曲重复解码')
                return None, timeline, stems

            # 792aa61 recorded successful base stems but omitted their timeline.
            # A full matching reference in that same task can be adopted; partial
            # failed attempts and ambiguous references must never become success.
            candidates = {}
            for reference in work_dir.glob('attempt_*/timeline.wav'):
                try:
                    record = wav_record(reference, work_dir)
                    base_records(stems, work_dir, record['spec'])
                    candidates[record['sha256']] = record
                except (OSError, ValueError, RuntimeError):
                    continue
            if len(candidates) > 1:
                raise ValueError('旧任务存在不同内容的时间轴参考，无法安全自动选择；所有文件均保留。')
            if candidates:
                record = next(iter(candidates.values()))
                _save_input(checkpoint, work_dir, record)
                stage('已从旧任务完整参考 WAV 恢复时间轴，跳过基础模型及原曲重复解码')
                return None, tuple(record['spec']), stems

    if not stems and checkpoint.get('decoded_input'):
        try:
            with phase(stage, '恢复校验：完整读取已解码输入 WAV'):
                source = checked_paths({'Input': checkpoint['decoded_input']}, work_dir)['Input']
                timeline = _timeline(checkpoint['decoded_input']['spec'])
                basis = checkpoint.get('timeline_source', {})
                if basis != dict(kind='decoded_input', input_sha256=source_hash):
                    raise ValueError('已解码输入的原曲关联无效。')
            stage('输入恢复：已校验完整 PCM，跳过原曲重复解码')
            return source, timeline, None
        except (OSError, ValueError, KeyError, RuntimeError) as error:
            stage(f'已解码输入检查点无效，仅重新解码输入，原文件保留：{error}')

    with phase(stage, '正在严格完整解码原曲，保存输入及时间轴检查点'):
        try:
            timeline = song_timeline(audio, attempt, tools)
        except RuntimeError as error:
            raise RuntimeError(
                f'原始音频完整解码失败：{audio}。未将部分 timeline.wav 视为成功输入；'
                '已有模型音轨及分块检查点均保留。请使用完整原文件，或先关联确认已有的完整分离音轨。'
                f'解码器原始错误：{error}') from error
        record = wav_record(attempt / 'timeline.wav', work_dir, timeline)
        if stems:
            base_records(stems, work_dir, timeline)
        _save_input(checkpoint, work_dir, record)
    return (attempt / 'timeline.wav' if not stems else None), tuple(record['spec']), stems


def _save_input(checkpoint, work_dir, record):
    checkpoint.update(decoded_input=record, timeline=record['spec'],
        timeline_source=dict(kind='decoded_input', input_sha256=checkpoint['identity']['audio_sha256']))
    if not checkpoint.get('base'):
        checkpoint['status'] = 'input_complete'
    atomic_json(work_dir / 'task.json', checkpoint)
