"""Current-task provenance and creation; historical work is never discovered."""
import importlib.metadata
import uuid
from datetime import datetime, timezone
from pathlib import Path

from task_checkpoint import atomic_json, digest, model_signature, wav_record


def identity(audio, model, model_dir, settings):
    from vocal_split import BVE_MODEL, CHUNK_SECONDS, VR_PARAMS

    names = [model, Path(model).with_suffix('.yaml').name, 'mdx_model_data.json']
    if settings['split_backing']:
        names += [BVE_MODEL, 'vr_model_data.json']
    return dict(schema=1, audio_sha256=digest(audio), audio_size=Path(audio).stat().st_size,
                models=model_signature(model_dir, names), settings=settings,
                engine=importlib.metadata.version('audio-separator'),
                runtime={name: importlib.metadata.version(name) for name in
                         ('torch', 'numpy', 'librosa', 'soundfile')},
                algorithm=dict(version=1, chunk_seconds=CHUNK_SECONDS, context_seconds=3,
                               fade_seconds=1, vr_params=VR_PARAMS))


def choose_work(root, expected, resume_work, stage):
    """Always reserve a new UUID directory, including for legacy callers."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if resume_work is not None:
        stage('旧任务恢复已停用；忽略恢复路径，本次从零开始。')
    task_id = 'work_' + uuid.uuid4().hex
    folder = root / task_id
    folder.mkdir()  # Atomic reservation; never open or overwrite another task.
    state = dict(task_id=task_id, identity=expected, status='created',
                 created_at=datetime.now(timezone.utc).isoformat(), restart_policy='always_new')
    atomic_json(folder / 'task.json', state)
    stage(f'新任务：{task_id}；独立工作目录：{folder}；从零开始分离')
    return folder, state


def base_records(stems, folder, timeline):
    records = {label: wav_record(path, folder) for label, path in stems.items()}
    if set(records) != {'Vocals', 'Instrumental'}:
        raise ValueError('第一阶段必须包含完整人声及伴奏。')
    specs = [r['spec'] for r in records.values()]
    frames, rate, channels = timeline
    expected_frames = round(frames * specs[0][1] / rate)
    # Engine inverse STFT may remove less than one hop; alignment happens at export.
    if (specs[0] != specs[1] or specs[0][2] not in ({1, 2} if channels == 1 else {channels})
            or abs(specs[0][0] - expected_frames) > 2048):
        raise ValueError('第一阶段音轨长度、采样率或声道与原曲不一致。')
    return records
