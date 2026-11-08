"""Independent post-separation stem gain and lookahead peak protection."""
import math


def validate_gain(value):
    try:
        gain = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("音轨增益必须为 0～+12 dB 的有限数值。") from error
    if not math.isfinite(gain) or not 0 <= gain <= 12:
        raise ValueError("音轨增益必须为 0～+12 dB 的有限数值。")
    return gain


def audio_peak(path):
    """Bounded memory, including decoded floating-point MP3 overshoots."""
    import numpy as np
    import soundfile as sf
    peak = 0.0
    with sf.SoundFile(str(path)) as audio:
        frames, rate, channels = len(audio), audio.samplerate, audio.channels
        for block in audio.blocks(blocksize=65536, dtype="float64", always_2d=True):
            if not np.isfinite(block).all():
                raise RuntimeError(f"音频包含 NaN/Inf：{path}")
            peak = max(peak, float(np.max(np.abs(block))))
    if not frames:
        raise RuntimeError(f"音频没有采样：{path}")
    return dict(peak=peak, frames=frames, rate=rate, channels=channels)


def peak_db(peak):
    return 20 * math.log10(peak) if peak else None


def render_stem_gain(source, target, gain_db, tools, run_tool, ceiling_db=-1.0):
    """Float processing avoids intermediate clipping; 4x limits intersample peaks.

    alimiter links channels, compensates lookahead latency, and has no automatic
    makeup gain. The caller encodes and checks the final decoded file separately.
    """
    gain_db = validate_gain(gain_db)
    before = audio_peak(source)
    factor = 10 ** (gain_db / 20)
    rate = before["rate"]
    ceiling = 10 ** (ceiling_db / 20)
    filters = (f"volume={factor:.15g}:precision=double,aresample={rate * 4},"
               f"alimiter=limit={ceiling:.15g}:attack=5:release=50:level=false:latency=true,"
               f"aresample={rate}")
    run_tool([tools["ffmpeg"], "-nostdin", "-v", "error", "-n", "-i", str(source),
              "-map", "0:a:0", "-af", filters, "-c:a", "pcm_f32le", str(target)])
    after = audio_peak(target)
    if after["peak"] >= 1:
        raise RuntimeError("限幅后浮点峰值仍达到满幅，已停止编码，避免整数 PCM 削波；恢复材料已保留。")
    if any(before[key] != after[key] for key in ("frames", "rate", "channels")):
        raise RuntimeError("增益处理改变了长度、采样率或声道；已停止导出。")
    return dict(requested_db=gain_db, factor=factor, input_peak=before["peak"], ceiling_db=ceiling_db)


def finish_gain_report(report, target):
    decoded = audio_peak(target)
    if decoded["peak"] >= 1.0:
        raise RuntimeError("增益后音频解码峰值达到满幅，已停止发布；请降低增益重试，恢复材料已保留。")
    expected = report["input_peak"] * report["factor"]
    report.update(output_peak_dbfs=peak_db(decoded["peak"]),
                  peak_shortfall_db=max(0.0, 20 * math.log10(expected / decoded["peak"]))
                  if expected and decoded["peak"] else 0.0)


def format_gain_report(report, label="人声"):
    gain = report.get("requested_db", 0)
    if gain == 0:
        return f"{label}增益：+0.0 dB（原导出路径，未启用增益或限幅）"
    peak = report.get("output_peak_dbfs")
    level = f"{peak:.2f} dBFS" if peak is not None else "静音"
    return (f"{label}增益：+{gain:.1f} dB（系数 {report['factor']:.4f}）\n"
            f"导出{label}采样峰值：{level}；限幅器上限 {report['ceiling_db']:.1f} dBFS\n"
            f"峰值相对未限幅理论值降低：{report['peak_shortfall_db']:.2f} dB（含限幅及编码影响，非整体响度）")
