"""Project-owned VR adapter, overlap planning and bounded streaming reconstruction."""
from pathlib import Path
from types import MethodType

from task_checkpoint import phase

VOCAL_LABELS = ('LeadVocals', 'BackingVocals')
CHUNK_SECONDS = 60
CONTEXT_SECONDS = 3
FADE_SECONDS = 1
VR_PARAMS = dict(batch_size=1, window_size=512, aggression=5, enable_tta=False,
                 enable_post_process=False, high_end_process=False)


def chunk_plan(frames, rate, seconds=CHUNK_SECONDS, context=CONTEXT_SECONDS, fade=FADE_SECONDS):
    core, pad, overlap = round(seconds * rate), round(context * rate), round(fade * rate)
    if core <= 2 * overlap or pad < 1 or overlap < 1:
        raise ValueError('分块长度必须大于两倍淡化长度，且上下文与淡化必须为正。')
    result = []
    for start in range(0, frames, core):
        end = min(frames, start + core)
        a, b = max(0, start - overlap), min(frames, end + overlap)
        # BVE 4band_v3_sn: align all bands to the original 480-sample grid.
        read_start = max(0, a - pad) // 480 * 480
        result.append(dict(start=start, end=end, a=a, b=b, read_start=read_start, read_end=b + pad))
    return result


def blend_chunks(entries, folder, output_dir, spec, stage):
    """Streaming overlap-add with complementary raised-cosine weights."""
    import numpy as np
    import soundfile as sf

    frames, rate, channels = spec
    raw = {label: output_dir / f'{label}.raw.wav' for label in VOCAL_LABELS}
    peaks = []
    for label in VOCAL_LABELS:
        stage(f'第二阶段音频后处理：交叉淡化合并 {label}')
        peak = 0.0
        with sf.SoundFile(raw[label], 'x', samplerate=rate, channels=channels, subtype='FLOAT') as output:
            for start in range(0, frames, 65536):
                end = min(frames, start + 65536)
                mixed = np.zeros((end - start, channels), dtype=np.float32)
                weights = np.zeros(end - start, dtype=np.float32)
                for index, entry in enumerate(entries):
                    plan = entry['plan']
                    a, b = max(start, plan['a']), min(end, plan['b'])
                    if b <= a:
                        continue
                    positions = np.arange(a, b)
                    weight = np.ones(b - a, dtype=np.float32)
                    if index:
                        left, right = plan['a'], entries[index - 1]['plan']['b']
                        x = np.clip((positions - left) / (right - left), 0, 1)
                        weight *= (0.5 - 0.5 * np.cos(np.pi * x)).astype(np.float32)
                    if index + 1 < len(entries):
                        left, right = entries[index + 1]['plan']['a'], plan['b']
                        x = np.clip((positions - left) / (right - left), 0, 1)
                        weight *= (0.5 + 0.5 * np.cos(np.pi * x)).astype(np.float32)
                    with sf.SoundFile(folder / entry['stems'][label]['path']) as source:
                        source.seek(a - plan['a'])
                        data = source.read(b - a, dtype='float32', always_2d=True)
                    if len(data) != b - a:
                        raise ValueError('分块音轨不完整。')
                    mixed[a - start:b - start] += data * weight[:, None]
                    weights[a - start:b - start] += weight
                if np.any(weights <= 0):
                    raise ValueError('分块时间轴存在空洞。')
                mixed /= weights[:, None]
                if not np.isfinite(mixed).all():
                    raise ValueError('合并音轨存在 NaN/Inf。')
                peak = max(peak, float(np.max(np.abs(mixed))))
                output.write(mixed)
        peaks.append(peak)
    # One constant for both full tracks, avoiding independent chunk normalization.
    gain = min(1.0, 0.9 / max(peaks)) if max(peaks) else 1.0
    stems = {}
    for label in VOCAL_LABELS:
        target = output_dir / f'{label}.wav'
        with sf.SoundFile(raw[label]) as source, sf.SoundFile(
                target, 'x', samplerate=rate, channels=channels, subtype='PCM_24') as output:
            for data in source.blocks(blocksize=65536, dtype='float32', always_2d=True):
                output.write(data * gain)
        stems[label] = target
    return stems


def instrument_model(model, stage):
    """Instance-local adapter; no dependency files or global classes are modified."""
    original_inference, original_wave = model.inference_vr, model.spec_to_wav

    def inference(self, *args, **kwargs):
        with phase(stage, '第二阶段：当前块推理及频谱掩膜后处理'):
            return original_inference(*args, **kwargs)

    def waveform(self, *args, **kwargs):
        with phase(stage, '第二阶段音频后处理：当前块逆 STFT / 重采样'):
            return original_wave(*args, **kwargs)

    def write_float(self, stem_path, source, stem_name):
        import numpy as np
        import soundfile as sf
        if not np.isfinite(source).all():
            raise ValueError('BVE 输出含有 NaN/Inf。')
        stage(f'第二阶段音频后处理：保存当前块 {stem_name}')
        # Preserve raw floating point: normalize once after stitching the full tracks.
        with sf.SoundFile(Path(self.output_dir) / stem_path, 'x', samplerate=44100,
                          channels=source.shape[1], subtype='FLOAT') as output:
            output.write(source)

    model.inference_vr = MethodType(inference, model)
    model.spec_to_wav = MethodType(waveform, model)
    model.final_process = MethodType(write_float, model)
