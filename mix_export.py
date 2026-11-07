"""将播放器当前设置渲染为完整音频，复用已对齐的分离结果。"""
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from audio_gain import audio_peak
from mix_tracks import MIX_FADE_SECONDS, mix_playback_format, read_mix
from runtime_paths import configure_ffmpeg
from separate import encode_mp3


def volume_ratio(value):
    if type(value) not in (int, float) or not 0 <= value <= 100:
        raise ValueError("音量必须在 0% 到 100% 之间。")
    return value / 100


def write_mix_wav(target, tracks, gains, frames, rate, channels):
    import numpy as np
    import soundfile as sf

    fade = min(int(rate * MIX_FADE_SECONDS), frames // 2)
    with ExitStack() as stack:
        inputs = {label: stack.enter_context(sf.SoundFile(path)) for label, path in tracks.items()}
        output = stack.enter_context(sf.SoundFile(target, mode="w", samplerate=rate, channels=channels, subtype="PCM_24"))
        # 分块处理，所有轨道始终从同一个采样位置读取。
        for start in range(0, frames, 65536):
            count = min(65536, frames - start)
            block = np.zeros((count, channels), dtype=np.float64)
            for label, audio in inputs.items():
                samples = audio.read(count, dtype="float64", always_2d=True)
                if len(samples) != count:
                    raise ValueError("音轨在导出过程中发生变化。")
                block += samples * gains[label]
            if fade and (start < fade or start + count > frames - fade):
                index = np.arange(start, start + count)
                envelope = np.minimum(1, np.minimum(index, frames - 1 - index) / fade)
                block *= envelope[:, None]
            if not np.isfinite(block).all() or np.max(np.abs(block)) >= 1:
                raise ValueError("混音峰值达到满幅，请降低总音量。")
            output.write(block)


def render_mix(output_dir, name, output_format, levels, master):
    if output_format != "MP3":
        raise ValueError("混音仅支持 MP3（320 kbps）导出。")
    frames, rate, tracks = read_mix(output_dir, name)
    if not isinstance(levels, dict) or levels.keys() != tracks.keys():
        raise ValueError("导出设置与当前音轨不一致，请重新载入混音。")
    ratios = {label: volume_ratio(value) for label, value in levels.items()}
    master = volume_ratio(master)
    channels, headroom = mix_playback_format(frames, rate, tracks)
    gains = {label: level * master * headroom for label, level in ratios.items()}
    folder = Path(output_dir).resolve() / name / "mix-exports"
    if folder.resolve() != folder:
        raise ValueError("混音导出目录必须位于当前歌曲目录内。")
    folder.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = folder / f"混音-{stamp}-{uuid4().hex[:8]}.mp3"
    tools = configure_ffmpeg()
    with TemporaryDirectory(prefix=".render-", dir=folder) as staging:
        wav = Path(staging) / "mix.wav"
        write_mix_wav(wav, tracks, gains, frames, rate, channels)
        candidate = wav.with_suffix(".mp3")
        encode_mp3(wav, candidate, tools)
        if audio_peak(candidate)["peak"] >= 1:
            raise ValueError("编码后的音频达到满幅，请降低总音量再导出。")
        candidate.rename(target)
    return target
