"""Audio Separator wrapper: verified models, named stems and PCM/MP3 export."""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from models import DEFAULT_MODEL, MODELS, ROFORMER_MODEL, check_model
from runtime_paths import DATA_DIR, MODEL_DIR, OUTPUT_DIR, configure_ffmpeg
from gpu_runtime import device_info, preload_onnx_cuda, select_device, validate_loaded_device
from performance import inference_options, infer_with_retry
from audio_gain import validate_gain, render_stem_gain, finish_gain_report, format_gain_report

MODEL_NAME = DEFAULT_MODEL
SUPPORTED_FORMATS = {".mp3", ".wav", ".flac", ".m4a"}


def validate_audio(audio_path):
    audio_path = Path(audio_path).expanduser().resolve()
    if not audio_path.is_file():
        raise ValueError(f"找不到音频文件：{audio_path}")
    if audio_path.suffix.lower() not in SUPPORTED_FORMATS:
        raise ValueError("请使用 MP3、WAV、FLAC 或 M4A 文件。")
    return audio_path


def run_tool(command):
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    if result.returncode:
        raise RuntimeError(f"{Path(command[0]).name} 失败：{result.stderr[-2500:]}")
    return result.stdout


def probe_audio(path, tools=None):
    tools = tools or configure_ffmpeg()
    data = json.loads(run_tool([tools["ffprobe"], "-v", "error", "-select_streams", "a:0",
                               "-show_streams", "-show_format", "-of", "json", str(path)]))
    streams = data.get("streams", [])
    if not streams or float(data.get("format", {}).get("duration", 0)) <= 0:
        raise ValueError(f"文件没有可读取的音轨：{path}")
    return streams[0]


def verify_output(path, output_format, tools):
    if not path.is_file() or path.stat().st_size <= 44:
        raise RuntimeError(f"没有生成有效的结果文件：{path}")
    stream = probe_audio(path, tools)
    codec = stream.get("codec_name", "")
    if output_format == "MP3":
        if codec != "mp3" or int(stream.get("bit_rate", 0)) != 320000:
            raise RuntimeError(f"输出不是 MP3 320 kbps：{path}，探测结果：{stream}")
    elif not codec.startswith("pcm_"):
        raise RuntimeError(f"WAV 输出不是 PCM：{path}，编码：{codec}")
    return stream


def song_title(original_name):
    """Treat upload metadata as a filename, never as a filesystem path."""
    leaf = str(original_name).replace("\\", "/").rsplit("/", 1)[-1]
    title = Path(leaf).stem
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(" .")
    if not title:
        title = "未命名歌曲"
    if re.match(r"^(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)", title, re.I):
        title = "_" + title
    return title


def reserve_result_dir(output_dir, title):
    """Atomic mkdir handles concurrent jobs; budget in Windows UTF-16 units."""
    units = lambda text: len(str(text).encode("utf-16-le")) // 2
    for index in range(1, 100000):
        suffix = "" if index == 1 else f" ({index})"
        # Full longest path: parent / title / title_Instrumental.mp3.
        budget = (240 - units(output_dir) - 2 - units("_Instrumental.mp3")) // 2 - units(suffix)
        if budget < 1:
            raise ValueError("输出根目录路径过长，请选择更短的输出路径。")
        base = title.encode("utf-16-le")[:budget * 2].decode("utf-16-le", errors="ignore").rstrip(" .") or "_"
        if re.match(r"^(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)", base, re.I):
            base = "_" + base[:-1]
        candidate = output_dir / (base + suffix)
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            continue
    raise RuntimeError("同名结果过多，请选择其他输出目录。")


def prepare_model(separator, model, stage, metrics=None):
    """Public APIs, official downloads and SHA-256; preserve existing corrupt files too."""
    from filelock import FileLock, Timeout
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with FileLock(str(MODEL_DIR / ".download.lock"), timeout=1):
            supported = separator.list_supported_model_files()
            arch = check_model(model)
            info = next((item for item in supported.get(arch, {}).values() if item["filename"] == model), None)
            if info is None:
                raise RuntimeError(f"当前 Audio Separator 官方列表未包含 {model}，请检查版本及模型清单。")
            missing = []
            checksums = separator.get_model_checksums()
            for item in info["download_files"]:
                name = item.rsplit("/", 1)[-1]
                path = MODEL_DIR / name
                if name not in checksums:
                    raise RuntimeError(f"官方没有提供 {name} 的完整性校验值，已停止加载。")
                if path.exists():
                    if not separator.verify_model_file_checksum(str(path)):
                        raise RuntimeError(f"模型校验失败，已保留原文件：{path}。请手动移走损坏文件后重试。")
                else:
                    missing.append(name)
            if missing:
                stage("正在下载模型（官方机制及 SHA-256 校验）：" + ", ".join(missing))
            else:
                stage("模型已缓存并通过完整性校验；正在检查模型参数")
            try:
                separator.download_model_and_data(model)
            except Exception as error:
                raise RuntimeError(f"模型下载或参数检查失败：{error}。请检查网络后重试；有效缓存会保留。") from error
            stage("正在加载 AI 模型")
            load_start = time.perf_counter()
            try:
                separator.load_model(model_filename=model)
                if str(getattr(separator, "torch_device", "cpu")).startswith("cuda"):
                    import torch
                    torch.cuda.synchronize()
            except SystemExit as error:
                # MDXC can sys.exit(1) after a failed load; keep the UI worker alive.
                raise RuntimeError(f"模型加载失败：{model}。请检查启动窗口日志；缓存已保留。") from error
            if metrics is not None:
                metrics["load_seconds"] = time.perf_counter() - load_start
    except Timeout as error:
        raise RuntimeError("另一个程序正在检查或下载模型，请稍后重试。") from error


def named_stems(returned, folder, required):
    """Map semantic custom names; never infer identity from return order."""
    stems = {}
    for item in returned:
        path = Path(item)
        path = (path if path.is_absolute() else folder / path).resolve()
        if not path.is_relative_to(folder.resolve()):
            raise RuntimeError(f"引擎返回了本任务目录以外的文件：{path}")
        if path.stem in required:
            if path.stem in stems:
                raise RuntimeError(f"引擎返回重复音轨标签：{path.stem}")
            stems[path.stem] = path
    if set(stems) != set(required):
        raise RuntimeError(f"模型输出标签不完整，期望 {required}，实际 {list(stems)}。已保留中间文件。")
    return stems


def export_stems(stems, result_dir, output_format, tools, title=None, vocal_gain_db=0,
                 instrumental_gain_db=0, gain_report=None):
    """Encode and fully decode both tracks before the caller can publish/clean."""
    gains = {"Vocals": validate_gain(vocal_gain_db), "Instrumental": validate_gain(instrumental_gain_db)}
    gain_report = gain_report if gain_report is not None else {}
    outputs = []
    for label in ("Vocals", "Instrumental"):
        gain_db = gains[label]
        report = {"requested_db": gain_db}
        gain_report[label] = report
        source = stems[label]
        original = verify_output(source, "WAV", tools)
        target = result_dir / f"{title + '_' if title else ''}{label}.{output_format.lower()}"
        if target.exists():
            raise FileExistsError(f"结果已存在，拒绝覆盖：{target}")
        if gain_db > 0:
            # Recovery WAV stays untouched; the extra float WAV is temporary only.
            processed = source.parent / (label + "_gain.wav")
            report.update(render_stem_gain(source, processed, gain_db, tools, run_tool))
            source = processed
        if output_format == "MP3":
            run_tool([tools["ffmpeg"], "-nostdin", "-v", "error", "-n", "-i", str(source),
                      "-map", "0:a:0", "-c:a", "libmp3lame", "-b:a", "320k", str(target)])
        elif gain_db > 0:
            run_tool([tools["ffmpeg"], "-nostdin", "-v", "error", "-n", "-i", str(source),
                      "-map", "0:a:0", "-c:a", "pcm_s24le", str(target)])
        else:
            with target.open("xb") as destination, source.open("rb") as origin:
                shutil.copyfileobj(origin, destination)
        encoded = verify_output(target, output_format, tools)
        if (encoded["sample_rate"], encoded["channels"]) != (original["sample_rate"], original["channels"]):
            raise RuntimeError(f"导出采样率或声道与分离音轨不一致：{target}")
        run_tool([tools["ffmpeg"], "-nostdin", "-v", "error", "-xerror", "-i", str(target), "-f", "null", "-"])
        if gain_db > 0:
            finish_gain_report(report, target)
        outputs.append(target)
    return tuple(outputs)


def separate_audio(audio_path, output_dir=OUTPUT_DIR, cpu=False, model_name=DEFAULT_MODEL,
                   output_format="MP3", progress_callback=None, original_name=None, device="auto",
                   performance_mode="balanced", metrics_callback=None, vocal_gain_db=0,
                   instrumental_gain_db=0):
    total_start = time.perf_counter()
    vocal_gain_db = validate_gain(vocal_gain_db)
    instrumental_gain_db = validate_gain(instrumental_gain_db)
    stage = progress_callback or (lambda message: print(message, flush=True))
    arch = check_model(model_name)
    output_format = output_format.upper()
    if output_format not in {"MP3", "WAV"}:
        raise ValueError("输出格式只能为 MP3 或 WAV。")
    stage("正在检查音频文件")
    audio_path = validate_audio(audio_path)
    tools = configure_ffmpeg()
    probe_audio(audio_path, tools)
    stage("正在检查 AI 模型及运行环境")
    try:
        import torch
        import onnxruntime as ort
        from audio_separator.separator import Separator
    except ImportError as error:
        raise RuntimeError(f"AI 依赖未能导入：{error}。请检查项目虚拟环境。") from error
    selected = select_device(device, cpu)
    info = device_info(selected)
    stats = dict(info, mode=performance_mode, oom_retries=0)
    options = inference_options(model_name, performance_mode, selected, info.get("free_bytes"))
    stats["options"] = options
    if selected == "cuda":
        torch.cuda.reset_peak_memory_stats()
    stage(f"推理设备：{info['name']}（{selected.upper()}）；PyTorch {info['torch']}")
    if selected == "cuda" and arch == "MDX":
        preload_onnx_cuda()
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    work_root = DATA_DIR / "cache" / "separation"
    work_root.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="work_", dir=work_root))
    try:
        outputs = _separate_task(Separator, audio_path, output_dir, work_dir, model_name,
                                 output_format, tools, stage, original_name, selected == "cpu", torch,
                                 options=options, metrics=stats, vocal_gain_db=vocal_gain_db,
                                 instrumental_gain_db=instrumental_gain_db)
        stats["total_seconds"] = time.perf_counter() - total_start
        if selected == "cuda":
            stats["peak_bytes"] = torch.cuda.max_memory_allocated()
        if metrics_callback:
            metrics_callback(stats)
        return outputs
    except (Exception, SystemExit) as error:
        raise RuntimeError(f"分离失败：{error}。恢复材料保留在：{work_dir}") from error


def _separate_task(Separator, audio_path, output_dir, work_dir, model_name,
                   output_format, tools, stage, original_name, cpu, torch, options=None, metrics=None,
                   vocal_gain_db=0, instrumental_gain_db=0):
    metrics = metrics if metrics is not None else {}
    prepare_start = time.perf_counter()
    separator = Separator(model_file_dir=str(MODEL_DIR), output_dir=str(work_dir),
                          output_format="WAV", use_soundfile=False, **(options or {}))
    if cpu:
        # Also works when CUDA was already initialized earlier in this process.
        separator.torch_device = torch.device("cpu")
        separator.onnx_execution_provider = ["CPUExecutionProvider"]
    prepare_model(separator, model_name, stage, metrics=metrics)
    metrics["prepare_seconds"] = time.perf_counter() - prepare_start
    validate_loaded_device(separator, check_model(model_name), "cpu" if cpu else "cuda")
    required = ("Vocals", "Instrumental")
    stage("正在进行人声分离（AI 推理及 WAV 写出；不提供整体百分比）")
    output_names = {name: name for name in required}
    if model_name == ROFORMER_MODEL:
        # Kim's two-source training config calls the complete non-vocal mix 'other'.
        # This alias is specific to this verified two-stem model, never four-stem Other.
        output_names["other"] = "Instrumental"
    inference_start = time.perf_counter()
    returned, stem_dir = infer_with_retry(separator, audio_path, output_names, work_dir, model_name,
                                          "cpu" if cpu else "cuda", metrics, stage)
    if not cpu:
        torch.cuda.synchronize()
    metrics["inference_seconds"] = time.perf_counter() - inference_start
    stems = named_stems(returned, stem_dir, required)
    for path in stems.values():
        verify_output(path, "WAV", tools)
    stage("正在导出音频" + ("：MP3 320 kbps" if output_format == "MP3" else "：WAV PCM"))
    export_start = time.perf_counter()
    result_dir = reserve_result_dir(output_dir, song_title(original_name or audio_path.name))
    staging = work_dir / "export"
    staging.mkdir()
    try:
        gain_report = {}
        encoded = export_stems(stems, staging, output_format, tools, result_dir.name,
                               vocal_gain_db=vocal_gain_db, instrumental_gain_db=instrumental_gain_db,
                               gain_report=gain_report)
        metrics["stem_gains"] = gain_report
        stage(format_gain_report(gain_report["Vocals"], "人声"))
        stage(format_gain_report(gain_report["Instrumental"], "伴奏"))
        outputs = tuple(result_dir / path.name for path in encoded)
        for source, target in zip(encoded, outputs):
            with source.open("rb") as origin, target.open("xb") as destination:
                shutil.copyfileobj(origin, destination)
            verify_output(target, output_format, tools)
    except Exception:
        # Remove only our empty reservation; never touch history or recovery WAVs.
        if not any(result_dir.iterdir()):
            result_dir.rmdir()
        raise
    shutil.rmtree(work_dir)
    metrics["export_seconds"] = time.perf_counter() - export_start
    stage("分离完成")
    return outputs


def main():
    parser = argparse.ArgumentParser(description="将音乐分离为人声和伴奏。")
    parser.add_argument("audio", help="输入音频路径：MP3 / WAV / FLAC / M4A")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    devices = parser.add_mutually_exclusive_group()
    devices.add_argument("--cpu", action="store_true", help="强制使用 CPU")
    devices.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--model", choices=list(MODELS), default=DEFAULT_MODEL)
    parser.add_argument("--format", choices=["MP3", "WAV"], default="MP3")
    parser.add_argument("--performance", choices=["quality", "balanced", "fast"], default="balanced")
    parser.add_argument("--vocal-gain-db", type=validate_gain, default=0,
                        help="分离后人声增益，0～12 dB；正增益启用前瞻峰值保护")
    parser.add_argument("--instrumental-gain-db", type=validate_gain, default=0,
                        help="分离后伴奏增益，0～12 dB；与人声独立控制")
    args = parser.parse_args()
    try:
        from performance import format_metrics
        vocals, instrumental = separate_audio(args.audio, args.output_dir, args.cpu, args.model, args.format,
                                              device=args.device, performance_mode=args.performance,
                                              vocal_gain_db=args.vocal_gain_db,
                                              instrumental_gain_db=args.instrumental_gain_db,
                                              metrics_callback=lambda stats: print(format_metrics(stats) + "\n" +
                                                  format_gain_report(stats["stem_gains"]["Vocals"], "人声") + "\n" +
                                                  format_gain_report(stats["stem_gains"]["Instrumental"], "伴奏")))
    except Exception as error:
        print(f"分离失败：{error}", file=sys.stderr)
        return 1
    print(f"分离完成！人声：{vocals}；伴奏：{instrumental}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
