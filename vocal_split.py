"""Bounded BVE inference and postprocessing with durable overlapping chunks."""
import tempfile
from pathlib import Path

from separate import named_stems, prepare_model
from gpu_runtime import validate_loaded_device
from task_checkpoint import atomic_json, checked_paths, digest, identity_matches, model_signature, phase, read_json, wav_record
from bounded_vr import CHUNK_SECONDS, VOCAL_LABELS, VR_PARAMS, blend_chunks, chunk_plan, instrument_model

BVE_MODEL = "UVR-BVE-4B_SN-44100-1.pth"


def split_vocals(Separator, audio, work_dir, model_dir, device, stage, *, chunk_seconds=CHUNK_SECONDS):
    import numpy as np
    import soundfile as sf
    import torch
    from filelock import FileLock

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    with FileLock(str(work_dir / 'chunks.lock'), timeout=0):
        info = sf.info(audio)
        if info.samplerate != 44100 or info.channels != 2:
            raise ValueError('BVE 恢复输入必须为 44100 Hz 双声道人声 WAV。')
        plan = chunk_plan(info.frames, info.samplerate, chunk_seconds)
        identity = dict(schema=1, input=digest(audio), spec=[info.frames, info.samplerate, info.channels],
                        models=model_signature(model_dir, [BVE_MODEL, 'vr_model_data.json']),
                        params=VR_PARAMS, chunks=plan, device=device)
        manifest = work_dir / 'chunks.json'
        state = read_json(manifest) if manifest.exists() else dict(identity=identity, completed={})
        allowed = (BVE_MODEL, 'vr_model_data.json') if not state['completed'] else ()
        if not identity_matches(state['identity'], identity, allowed):
            raise ValueError('BVE 检查点的输入、模型或分块参数已变化；原数据已保留。')
        state['identity'] = identity
        atomic_json(manifest, state)
        engine = None
        entries = []
        for index, item in enumerate(plan):
            key = str(index)
            entry = state['completed'].get(key)
            if entry is not None:
                try:
                    if entry['plan'] != item or set(entry['stems']) != set(VOCAL_LABELS):
                        raise ValueError('分块范围或标签已变化。')
                    checked_paths(entry['stems'], work_dir)
                    if any(r['spec'] != [item['b'] - item['a'], 44100, 2] for r in entry['stems'].values()):
                        raise ValueError('分块帧数不一致。')
                except (OSError, ValueError, KeyError, RuntimeError) as error:
                    stage(f'恢复校验：第 {index + 1} 块无效，将保留原文件并重算：{error}')
                    entry = None
            if entry is not None:
                stage(f'第二阶段恢复：已校验并跳过第 {index + 1}/{len(plan)} 块')
                entries.append(entry)
                continue
            stage(f'第二阶段分块：开始第 {index + 1}/{len(plan)} 块；已完成 {len(entries)}/{len(plan)}')
            attempt = Path(tempfile.mkdtemp(prefix=f'chunk_{index:05d}_', dir=work_dir))
            source_path = attempt / 'input.wav'
            with sf.SoundFile(audio) as source:
                source.seek(item['read_start'])
                data = source.read(item['read_end'] - item['read_start'], dtype='float32', always_2d=True)
            data = np.pad(data, ((0, item['read_end'] - item['read_start'] - len(data)), (0, 0)))
            sf.write(source_path, data, 44100, subtype='FLOAT')
            silent = not np.any(data)
            del data
            if not silent:
                if engine is None:
                    engine = Separator(model_file_dir=str(model_dir), output_dir=str(attempt), output_format='WAV',
                                       use_autocast=False, vr_params=dict(VR_PARAMS))
                    if device == 'cpu':
                        engine.torch_device = torch.device('cpu')
                        engine.onnx_execution_provider = ['CPUExecutionProvider']
                    stage(f'正在准备主唱与和声模型：{BVE_MODEL}（{device.upper()}）')
                    prepare_model(engine, BVE_MODEL, stage, arch='VR')
                    model = engine.model_instance
                    if not model.is_bv_model or model.primary_stem_name != 'Vocals' or model.secondary_stem_name != 'Instrumental':
                        raise RuntimeError('BVE 模型元数据与已核实的轨道定义不一致。')
                    if model.model_params.param['band'][4]['hl'] != 480:
                        raise RuntimeError('BVE 频谱网格参数发生变化。')
                    instrument_model(model, stage)
                    state['identity']['models'] = model_signature(model_dir, [BVE_MODEL, 'vr_model_data.json'])
                engine.output_dir = engine.model_instance.output_dir = str(attempt)
                # BVE primary mask predicts backing; complementary mask predicts lead.
                with torch.inference_mode():
                    returned = engine.separate(str(source_path), custom_output_names={
                        'Vocals': 'BackingVocals', 'Instrumental': 'LeadVocals'})
                validate_loaded_device(engine, 'VR', device)
                raw = named_stems(returned, attempt, VOCAL_LABELS)
            records = {}
            for label in VOCAL_LABELS:
                count = item['b'] - item['a']
                if silent:
                    trimmed = np.zeros((count, 2), dtype=np.float32)
                else:
                    with sf.SoundFile(raw[label]) as source:
                        source.seek(item['a'] - item['read_start'])
                        trimmed = source.read(count, dtype='float32', always_2d=True)
                    if len(trimmed) != count:
                        raise RuntimeError('BVE 输出没有覆盖有效音频区域；拒绝补齐丢失音频。')
                target = attempt / f'{label}.checked.wav'
                sf.write(target, trimmed, 44100, subtype='FLOAT')
                records[label] = wav_record(target, work_dir, [count, 44100, 2])
            entry = dict(plan=item, stems=records)
            state['completed'][key] = entry
            atomic_json(manifest, state)
            entries.append(entry)
            stage(f'第二阶段分块：已完成并校验 {len(entries)}/{len(plan)} 块（检查点已保存）')
        merge_dir = Path(tempfile.mkdtemp(prefix='merge_', dir=work_dir))
        with phase(stage, '第二阶段音频后处理：合并交叉淡化音轨及统一峰值保护'):
            stems = blend_chunks(entries, work_dir, merge_dir, identity['spec'], stage)
        state['merged'] = {label: wav_record(path, work_dir, identity['spec']) for label, path in stems.items()}
        atomic_json(manifest, state)
        return stems
