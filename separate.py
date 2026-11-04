"""最基础的人声分离：读取一个音频，保存人声和伴奏两个 WAV 文件。"""

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
MODEL_NAME = "UVR_MDXNET_KARA_2.onnx"
SUPPORTED_FORMATS = {".mp3", ".wav", ".flac", ".m4a"}


def validate_audio(audio_path):
    """先检查输入，避免输错路径后才下载模型。"""
    audio_path = Path(audio_path).expanduser().resolve()
    if not audio_path.is_file():
        raise ValueError(f"找不到音频文件：{audio_path}")
    if audio_path.suffix.lower() not in SUPPORTED_FORMATS:
        raise ValueError("请使用 MP3、WAV、FLAC 或 M4A 文件。")
    return audio_path


def separate_audio(audio_path, output_dir, cpu=False):
    """使用预训练模型分离，不需要训练；返回两个结果文件的路径。"""
    audio_path = validate_audio(audio_path)
    for command in ("ffmpeg", "ffprobe"):
        if shutil.which(command) is None:
            raise RuntimeError(f"未找到 {command}，请安装 FFmpeg 并将其加入 PATH。")

    # 在导入 AI 依赖之前设置，供命令行 --cpu 使用。
    if cpu:
        os.environ["CUDA_VISIBLE_DEVICES"] = "-1"

    try:
        import torch
        import onnxruntime as ort
        from audio_separator.separator import Separator
    except ImportError as error:
        raise RuntimeError(f"AI 依赖未能导入：{error}。请按 README 在虚拟环境中安装依赖。") from error

    # 优先使用 NVIDIA；ONNX 模型还需要 ONNX Runtime 的 CUDA 支持。
    if torch.cuda.is_available():
        if hasattr(ort, "preload_dlls"):
            ort.preload_dlls()
        if "CUDAExecutionProvider" not in ort.get_available_providers():
            raise RuntimeError("ONNX Runtime 缺少 CUDA 支持，请按 GPU 安装说明配置，或使用 --cpu。")
        print("检测到 NVIDIA CUDA，将尝试 GPU 分离；实际设备请查看引擎日志。", flush=True)
    else:
        print("使用 CPU 分离，速度可能较慢。", flush=True)

    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    # 每次建立独立文件夹，避免同名歌曲或重复运行覆盖已有结果。
    result_dir = Path(tempfile.mkdtemp(prefix="separation_", dir=output_dir))
    model_dir = PROJECT_DIR / "models"
    model_dir.mkdir(exist_ok=True)
    print(f"结果文件夹：{result_dir}", flush=True)
    print("首次运行会联网下载预训练模型，之后使用本地缓存。", flush=True)

    separator = Separator(
        model_file_dir=str(model_dir),
        output_dir=str(result_dir),
        output_format="WAV",
        # 使用默认 FFmpeg 导出路径，避免 MP3 的编码类型被误用于 WAV。
        use_soundfile=False,
    )
    separator.load_model(model_filename=MODEL_NAME)
    separator.separate(
        str(audio_path),
        custom_output_names={"Vocals": "Vocals", "Instrumental": "Instrumental"},
    )

    vocals = result_dir / "Vocals.wav"
    instrumental = result_dir / "Instrumental.wav"
    for result in (vocals, instrumental):
        if not result.is_file() or result.stat().st_size <= 44:
            raise RuntimeError(f"没有生成有效的结果文件：{result}")
    return vocals, instrumental


def main():
    parser = argparse.ArgumentParser(description="将音乐分离为人声和伴奏，保存为 WAV。")
    parser.add_argument("audio", help="输入音频路径：MP3 / WAV / FLAC / M4A")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_DIR / "outputs", help="结果保存位置")
    parser.add_argument("--cpu", action="store_true", help="强制使用 CPU，适合没有 NVIDIA 或 GPU 配置失败时")
    args = parser.parse_args()

    try:
        vocals, instrumental = separate_audio(args.audio, args.output_dir, args.cpu)
    except Exception as error:
        print(f"分离失败：{error}", file=sys.stderr)
        print("请检查音频、依赖、FFmpeg、网络或显存；失败的结果文件夹可能包含不完整文件。", file=sys.stderr)
        return 1

    print(f"\n分离完成！\n人声：{vocals}\n伴奏：{instrumental}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
