# Specific to the project's audio-separator 0.48 / Gradio 6.31 / torch 2.8 environment.
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata

root = Path(SPECPATH)
if os.environ.get("MVE_BUILD_FLAVOR") == "GPU":
    import torch
    from importlib.metadata import version, PackageNotFoundError
    if torch.version.cuda is None:
        raise RuntimeError("GPU build cannot use CPU-only PyTorch")
    version("onnxruntime-gpu")
    try:
        version("onnxruntime")
    except PackageNotFoundError:
        pass
    else:
        raise RuntimeError("Do not mix CPU and GPU ONNX Runtime")
# Gradio reads UploadedAudio's defining source and the app reads the mixer assets at runtime.
web_assets = [root / name for name in ("app.py", "mixer.html", "mixer.css", "mixer.js")]
for asset in web_assets:
    if not asset.is_file():
        raise RuntimeError(f"Missing web asset: {asset}")
datas = [(str(asset), ".") for asset in web_assets]
for package in ("audio_separator", "gradio", "gradio_client", "huggingface_hub", "librosa", "numba", "safehttpx", "groovy", "hf_gradio"):
    # librosa and numba inspect source files for lazy loading/JIT cache locations.
    datas += collect_data_files(package, include_py_files=package in ("gradio", "gradio_client", "librosa", "numba"))
for distribution in ("audio-separator", "gradio", "gradio-client", "torch", "numpy", "librosa", "soundfile", "onnxruntime", "onnxruntime-gpu", "imageio-ffmpeg"):
    try:
        datas += copy_metadata(distribution)
    except Exception:
        pass  # CPU/GPU ORT are deliberately mutually exclusive.

hiddenimports = [
    "audio_separator.separator.architectures.mdx_separator",
    "audio_separator.separator.architectures.mdxc_separator",
    "audio_separator.separator.architectures.vr_separator",
    # BVE 通过 librosa 延迟加载 samplerate，静态分析无法发现。
    "samplerate",
    "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on",
]
for package in ("audio_separator.separator.uvr_lib_v5", "audio_separator.separator.roformer", "gradio", "gradio_client", "librosa", "onnxruntime", "diffq"):
    hiddenimports += collect_submodules(package)

binaries = collect_dynamic_libs("samplerate", search_patterns=["libsamplerate-64bit.dll"])
if not binaries:
    raise RuntimeError("BVE requires the installed samplerate 64-bit DLL")
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
gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name="MusicVocalExtractor-GUI",
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, gui, a.binaries, a.datas, strip=False, upx=False, name="MusicVocalExtractor")
