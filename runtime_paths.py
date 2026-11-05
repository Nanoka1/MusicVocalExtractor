"""Persistent writable paths and local FFmpeg discovery for Python and onedir."""
import os
import json
import shutil
import sys
import tempfile
from pathlib import Path

SOURCE_DIR = Path(__file__).resolve().parent
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else SOURCE_DIR


def find_project_dir(app_dir, source_dir, frozen):
    """Recognize this project's dist tree by identity and source anchors, never cwd/depth."""
    if not frozen:
        return Path(source_dir).resolve()
    app_dir = Path(app_dir).resolve()
    for candidate in (app_dir, *app_dir.parents):
        marker = candidate / "mve-project.json"
        if not marker.is_file() or not app_dir.is_relative_to(candidate / "dist"):
            continue
        try:
            identity = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise RuntimeError(f"项目目录标识无法读取：{marker}") from error
        if identity.get("application_id") == "MusicVocalExtractor" and all(
                (candidate / name).is_file() for name in ("runtime_paths.py", "separate.py", "app.py")):
            return candidate
    return None


PROJECT_DIR = find_project_dir(APP_DIR, SOURCE_DIR, getattr(sys, "frozen", False))


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
    user_root = Path(os.environ["LOCALAPPDATA"]) if os.environ.get("LOCALAPPDATA") else Path.home() / "AppData" / "Local"
    target = Path(override).expanduser().resolve() if override else PROJECT_DIR or user_root / "MusicVocalExtractor"
    try:
        target.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=target):
            pass
    except OSError as error:
        raise RuntimeError(f"数据目录不可写：{target}。请检查权限或显式设置 MVE_DATA_DIR；没有改存到其他目录。") from error
    return target


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
