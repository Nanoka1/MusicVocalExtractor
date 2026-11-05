"""Persistent writable paths and local FFmpeg discovery for Python and onedir."""
import os
import json
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else PROJECT_DIR


def bundle_settings():
    config = APP_DIR / "runtime-config.json"
    if not getattr(sys, "frozen", False) or not config.is_file():
        return {}
    try:
        data = json.loads(config.read_text(encoding="utf-8-sig"))
        return {key: (APP_DIR / data[key]).resolve() for key in ("data_dir", "model_dir") if key in data}
    except (OSError, ValueError, TypeError) as error:
        raise RuntimeError(f"无法读取运行目录配置：{config}；请检查路径。") from error


BUNDLE_SETTINGS = bundle_settings()


def data_dir():
    override = os.environ.get("MVE_DATA_DIR") or BUNDLE_SETTINGS.get("data_dir")
    if override:
        return Path(override).expanduser().resolve()
    candidates = [APP_DIR]
    if getattr(sys, "frozen", False):
        candidates.append(Path(os.environ.get("LOCALAPPDATA", Path.home())) / "MusicVocalExtractor")
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=candidate):
                pass
            return candidate
        except OSError:
            continue
    raise RuntimeError("程序目录不可写。请移动到可写目录，或设置 MVE_DATA_DIR。")


DATA_DIR = data_dir()
MODEL_DIR = Path(os.environ.get("AUDIO_SEPARATOR_MODEL_DIR") or BUNDLE_SETTINGS.get("model_dir") or DATA_DIR / "models").expanduser().resolve()
OUTPUT_DIR = DATA_DIR / "outputs"
# Numba JIT caches must also stay writable and outside frozen package resources.
os.environ.setdefault("NUMBA_CACHE_DIR", str(DATA_DIR / "cache" / "numba"))


def configure_ffmpeg():
    """Change only the current process PATH, never Windows settings."""
    bundle = Path(getattr(sys, "_MEIPASS", APP_DIR))
    for folder in (APP_DIR / "ffmpeg", bundle / "ffmpeg"):
        if all((folder / (name + ".exe")).is_file() for name in ("ffmpeg", "ffprobe")):
            if str(folder) not in os.environ.get("PATH", "").split(os.pathsep):
                os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")
            break
    paths = {name: shutil.which(name) for name in ("ffmpeg", "ffprobe")}
    if not all(paths.values()):
        raise RuntimeError("缺少 FFmpeg/FFprobe。请把两个 EXE 放在程序的 ffmpeg 文件夹中，或使用本机已安装版本。")
    return paths
