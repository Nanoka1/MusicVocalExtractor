"""为混音器保存与原曲采样对齐的 WAV，以及可重新加载的时间轴。"""
import json
import shutil
from pathlib import Path
from urllib.parse import quote

from models import TRACK_LABELS
from separate import run_tool

MIX_TRACK_SETS = (
    frozenset(("Vocals", "Instrumental")),
    frozenset(("LeadVocals", "BackingVocals", "Instrumental")),
)


def song_timeline(audio, work_dir, tools):
    import soundfile as sf

    ffmpeg = [tools["ffmpeg"], "-nostdin", "-v", "error", "-xerror", "-n"]
    # 按解码后的实际采样计数，避免容器时长、MP3 填充影响时间轴。
    reference = work_dir / "timeline.wav"
    run_tool(ffmpeg + ["-i", str(audio), "-map", "0:a:0", "-c:a", "pcm_s16le", str(reference)])
    original = sf.info(str(reference))
    return original.frames, original.samplerate, original.channels


def align_track(source, target, timeline, tools):
    import soundfile as sf

    frames, rate, channels = timeline
    original = sf.info(str(source))
    if source.suffix.lower() == ".wav" and (original.frames, original.samplerate, original.channels) == timeline:
        with target.open("xb") as destination, source.open("rb") as data:
            shutil.copyfileobj(data, destination)
    else:
        # 起点保持在采样 0，只在末尾裁剪或补零。
        run_tool([tools["ffmpeg"], "-nostdin", "-v", "error", "-xerror", "-n",
                  "-i", str(source), "-map", "0:a:0", "-af",
                  f"aresample={rate},apad=whole_len={frames},atrim=end_sample={frames}",
                  "-ac", str(channels), "-c:a", "pcm_s24le", str(target)])
        rendered = sf.info(str(target))
        if (rendered.frames, rendered.samplerate, rendered.channels) != timeline:
            raise RuntimeError(f"混音轨道格式与原曲不一致：{target.name}")
    return target


def save_mix(audio, stems, result_dir, work_dir, tools, timeline=None):
    timeline = timeline or song_timeline(audio, work_dir, tools)
    frames, rate, _ = timeline
    mix = result_dir / "mix"
    mix.mkdir()
    for label, source in stems.items():
        align_track(source, mix / f"{label}.wav", timeline, tools)
    # 轨道全部校验后才写清单，历史下拉列表只显示有完整清单的任务。
    pending = mix / "timeline.tmp"
    pending.write_text(json.dumps({"frames": frames, "rate": rate, "tracks": list(stems)}), encoding="utf-8")
    pending.rename(mix / "timeline.json")


def saved_mixes(output_dir):
    root = Path(output_dir)
    if not root.is_dir():
        return []
    names = []
    for folder in root.iterdir():
        if not folder.is_dir():
            continue
        try:
            read_mix(root, folder.name)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        names.append(folder.name)
    return sorted(names, reverse=True)


def read_mix(output_dir, name):
    root = Path(output_dir).resolve()
    if not isinstance(name, str) or not name or name in {".", ".."} or any(c in name for c in "/\\:"):
        raise ValueError("请选择一个已保存的混音结果。")
    mix = root / name / "mix"
    if mix.resolve() != mix:
        raise ValueError("混音目录必须位于输出目录内。")
    timeline = mix / "timeline.json"
    if not timeline.is_file() or timeline.is_symlink():
        raise ValueError("未找到已完成的混音结果。")
    data = json.loads(timeline.read_text(encoding="utf-8"))
    frames, rate, labels = data["frames"], data["rate"], data["tracks"]
    if (type(frames) is not int or frames <= 0 or type(rate) is not int or rate <= 0
            or not isinstance(labels, list) or not labels
            or any(not isinstance(label, str) or label not in TRACK_LABELS for label in labels)
            or len(set(labels)) != len(labels) or frozenset(labels) not in MIX_TRACK_SETS):
        raise ValueError("混音时间轴或轨道清单无效。")
    tracks = {}
    for label in labels:
        path = mix / f"{label}.wav"
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"找不到混音音轨：{TRACK_LABELS[label]}")
        tracks[label] = path
    return frames, rate, tracks


def file_url(path):
    return "gradio_api/file=" + quote(path.as_posix(), safe="/:")


def mix_manifest(output_dir, name):
    frames, rate, paths = read_mix(output_dir, name)
    tracks = [{"id": label, "label": TRACK_LABELS[label], "url": file_url(path)} for label, path in paths.items()]
    return json.dumps({"title": name, "duration": frames / rate, "tracks": tracks}, ensure_ascii=False)
