"""Task identity, checkpoint discovery and explicit adoption of logged legacy WAVs."""
import importlib.metadata
import shutil
import tempfile
from pathlib import Path

from task_checkpoint import atomic_json, digest, identity_matches, model_signature, read_json, wav_record


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
    from vocal_split import BVE_MODEL
    def matches(state):
        # The base checkpoint predates a first-ever BVE download. It did not use
        # those missing files; completed BVE blocks validate their own fingerprints.
        allowed = (BVE_MODEL, 'vr_model_data.json') if state.get('base') else ()
        return identity_matches(state['identity'], expected, allowed)

    if resume_work:
        folder = Path(resume_work).resolve()
        if folder.parent != root.resolve() or not folder.name.startswith('work_'):
            raise ValueError('恢复路径必须是 cache/separation 下的 work_* 任务目录。')
        state = read_json(folder / 'task.json')
        if not matches(state):
            raise ValueError('任务输入、模型、参数或运行版本不匹配，拒绝复用。')
        stage(f'恢复任务：{folder}；正在逐文件重新校验')
        return folder, state
    for folder in sorted(root.glob('work_*'), key=lambda p: p.stat().st_mtime_ns, reverse=True):
        try:
            state = read_json(folder / 'task.json')
            if matches(state) and state.get('status') != 'complete':
                stage(f'发现可恢复任务：{folder}；正在逐文件重新校验')
                return folder, state
        except (OSError, ValueError, KeyError, TypeError):
            continue
    folder = Path(tempfile.mkdtemp(prefix='work_', dir=root))
    state = dict(identity=expected, status='created')
    atomic_json(folder / 'task.json', state)
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


def adopt_legacy(legacy, log_path, audio, folder, model, timeline, stage):
    """No saved calculation state exists: import only fully checked WAV artifacts."""
    legacy, log_path, audio = Path(legacy).resolve(), Path(log_path).resolve(), Path(audio).resolve()
    if not legacy.is_dir() or not log_path.is_file():
        raise ValueError('旧任务目录或来源日志不存在。')
    log = log_path.read_text(encoding='utf-8', errors='replace')
    source_event = 'Processing file: ' + str(audio)
    bve_event = 'Processing file: ' + str(legacy / 'Vocals.wav')
    if source_event not in log or bve_event not in log or model not in log:
        raise ValueError('日志没有证明原始音频、第一阶段模型与旧人声缓存的关联，拒绝自动采用。')
    if log.index(source_event) >= log.index(bve_event):
        raise ValueError('旧日志的处理阶段顺序不一致。')
    original = {label: legacy / f'{label}.wav' for label in ('Vocals', 'Instrumental')}
    base_records(original, legacy, timeline)
    destination = Path(tempfile.mkdtemp(prefix='legacy_import_', dir=folder))
    stems = {}
    for label, path in original.items():
        stems[label] = destination / path.name
        shutil.copy2(path, stems[label])
        if digest(stems[label]) != digest(path):
            raise ValueError('旧任务 WAV 复制校验失败；原文件仍保留。')
    stage('已采用日志关联且全量校验通过的第一阶段 WAV；旧任务未保存 BVE 计算状态，第二阶段从第 1 块开始。')
    return stems, dict(directory=str(legacy), log=str(log_path), log_sha256=digest(log_path),
                       limitation='旧版未保存参数快照；只核实日志模型名称、输入关联和实际 WAV，不声称恢复旧计算状态。')
