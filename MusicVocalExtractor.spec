# Specific to the project's audio-separator 0.48 / Gradio 6.31 / torch 2.8 environment.
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH)
datas = []
for package in ("audio_separator", "gradio", "gradio_client", "huggingface_hub", "librosa", "numba", "safehttpx", "groovy", "hf_gradio"):
    # librosa and numba inspect source files for lazy loading/JIT cache locations.
    datas += collect_data_files(package, include_py_files=package in ("gradio", "gradio_client", "librosa", "numba"))
for distribution in ("audio-separator", "gradio", "gradio-client", "torch", "onnxruntime", "onnxruntime-gpu", "imageio-ffmpeg"):
    try:
        datas += copy_metadata(distribution)
    except Exception:
        pass  # CPU/GPU ORT are deliberately mutually exclusive.

hiddenimports = [
    "audio_separator.separator.architectures.mdx_separator",
    "audio_separator.separator.architectures.demucs_separator",
    "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on",
]
for package in ("audio_separator.separator.uvr_lib_v5", "gradio", "gradio_client", "librosa", "onnxruntime", "diffq"):
    hiddenimports += collect_submodules(package)

binaries = []
ffmpeg_dir = os.environ.get("MVE_FFMPEG_DIR")
if ffmpeg_dir:
    ffmpeg_dir = Path(ffmpeg_dir).resolve()
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        executable = ffmpeg_dir / name
        if not executable.is_file():
            raise RuntimeError(f"Missing {executable}")
        binaries.append((str(executable), "ffmpeg"))

a = Analysis([str(root / "exe_entry.py")], pathex=[str(root)], binaries=binaries,
             datas=datas, hiddenimports=hiddenimports,
             # Numba needs real source paths for cache locators; PYZ co_filename is relative.
             module_collection_mode={"librosa": "py", "numba": "py"},
             excludes=["tkinter", "matplotlib", "IPython", "pytest", "tensorboard"],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="MusicVocalExtractor",
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="MusicVocalExtractor")
