"""Audio Separator wrapper: verified models, named stems and PCM/MP3 export."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from models import DEFAULT_MODEL, MODELS, check_model
from runtime_paths import MODEL_DIR, OUTPUT_DIR, PROJECT_DIR, configure_ffmpeg

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


def prepare_model(separator, model, stage):
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
            separator.load_model(model_filename=model)
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


def export_stems(stems, result_dir, output_format, tools):
    """Keep task WAVs on success and failure; encode MP3 exactly once."""
    outputs = []
    for label in ("Vocals", "Instrumental"):
        source = stems[label]
        verify_output(source, "WAV", tools)
        target = result_dir / f"{label}.{output_format.lower()}"
        if target.exists():
            raise FileExistsError(f"结果已存在，拒绝覆盖：{target}")
        if output_format == "MP3":
            run_tool([tools["ffmpeg"], "-nostdin", "-v", "error", "-n", "-i", str(source),
                      "-map", "0:a:0", "-c:a", "libmp3lame", "-b:a", "320k", str(target)])
        else:
            import shutil
            with target.open("xb") as destination, source.open("rb") as origin:
                shutil.copyfileobj(origin, destination)
        verify_output(target, output_format, tools)
        outputs.append(target)
    return tuple(outputs)


def separate_audio(audio_path, output_dir=OUTPUT_DIR, cpu=False, model_name=DEFAULT_MODEL,
                   output_format="MP3", progress_callback=None):
    stage = progress_callback or (lambda message: print(message, flush=True))
    arch = check_model(model_name)
    output_format = output_format.upper()
    if output_format not in {"MP3", "WAV"}:
        raise ValueError("输出格式只能为 MP3 或 WAV。")
    stage("正在检查音频文件")
    audio_path = validate_audio(audio_path)
    tools = configure_ffmpeg()
    probe_audio(audio_path, tools)
    if cpu:
        os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    stage("正在检查 AI 模型及运行环境")
    try:
        import torch
        import onnxruntime as ort
        from audio_separator.separator import Separator
    except ImportError as error:
        raise RuntimeError(f"AI 依赖未能导入：{error}。请检查项目虚拟环境。") from error
    if torch.cuda.is_available() and arch == "MDX":
        if hasattr(ort, "preload_dlls"):
            ort.preload_dlls()
        if "CUDAExecutionProvider" not in ort.get_available_providers():
            raise RuntimeError("ONNX Runtime 缺少 CUDA 支持，请按原 GPU 说明配置，或使用 --cpu。")
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    result_dir = Path(tempfile.mkdtemp(prefix="separation_", dir=output_dir))
    work_dir = result_dir / "intermediate_wav"
    work_dir.mkdir()
    stage(f"本次结果目录：{result_dir}；正在检查 AI 模型")
    separator = Separator(model_file_dir=str(MODEL_DIR), output_dir=str(work_dir),
                          output_format="WAV", use_soundfile=False)
    prepare_model(separator, model_name, stage)
    required = ("Vocals", "Drums", "Bass", "Other") if arch == "Demucs" else ("Vocals", "Instrumental")
    stage("正在进行人声分离（AI 推理及 WAV 写出；不提供整体百分比）")
    returned = separator.separate(str(audio_path), custom_output_names={name: name for name in required})
    stems = named_stems(returned, work_dir, required)
    for path in stems.values():
        verify_output(path, "WAV", tools)
    stage("正在导出音频" + ("：MP3 320 kbps" if output_format == "MP3" else "：WAV PCM"))
    if arch == "Demucs":
        instrumental = work_dir / "Instrumental.wav"
        command = [tools["ffmpeg"], "-nostdin", "-v", "error", "-n"]
        for name in ("Drums", "Bass", "Other"):
            command.extend(["-i", str(stems[name])])
        command.extend(["-filter_complex", "[0:a][1:a][2:a]amix=inputs=3:normalize=0:dropout_transition=0[out]",
                        "-map", "[out]", "-c:a", "pcm_s24le", str(instrumental)])
        run_tool(command)
        stems["Instrumental"] = instrumental
    try:
        outputs = export_stems(stems, result_dir, output_format, tools)
    except Exception as error:
        raise RuntimeError(f"音频导出失败：{error}。本次 WAV 已保留在 {work_dir}。") from error
    stage("分离完成")
    return outputs


def main():
    parser = argparse.ArgumentParser(description="将音乐分离为人声和伴奏。")
    parser.add_argument("audio", help="输入音频路径：MP3 / WAV / FLAC / M4A")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--cpu", action="store_true", help="强制使用 CPU")
    parser.add_argument("--model", choices=list(MODELS), default=DEFAULT_MODEL)
    parser.add_argument("--format", choices=["MP3", "WAV"], default="MP3")
    args = parser.parse_args()
    try:
        vocals, instrumental = separate_audio(args.audio, args.output_dir, args.cpu, args.model, args.format)
    except Exception as error:
        print(f"分离失败：{error}", file=sys.stderr)
        return 1
    print(f"分离完成！人声：{vocals}；伴奏：{instrumental}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
