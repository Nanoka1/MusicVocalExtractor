"""Explicit device selection and evidence from the engine's actual runtime."""
from pathlib import Path
import logging
import os
import time

_dll_handles = []


def select_device(requested="auto", cpu=False, *, allow_cpu_fallback=False):
    import torch
    if requested == "auto":
        requested = os.environ.get("MVE_DEVICE", "auto")
    if requested not in {"auto", "cpu", "cuda"}:
        raise ValueError("推理设备只能为 auto、cpu 或 cuda。")
    if cpu:
        requested = "cpu"
    available = torch.cuda.is_available() if requested != "cpu" else False
    if requested == "cuda" and not available:
        raise RuntimeError(f"GPU 初始化失败：PyTorch {torch.__version__} / CUDA {torch.version.cuda}。请主动选择 CPU，或使用已验证的 GPU 环境。")
    if available:
        try:
            torch.zeros(1, device="cuda").add_(1)
            torch.cuda.synchronize()
            return "cuda"
        except Exception as error:
            if requested == "auto" and allow_cpu_fallback:
                return "cpu"
            raise RuntimeError(f"CUDA 初始化/运算失败，请主动选择 CPU：{error}") from error
    if requested == "auto" and torch.version.cuda is not None and not allow_cpu_fallback:
        # A CUDA build with no available device must not conceal initialization errors.
        import subprocess
        try:
            detected = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                                      capture_output=True, timeout=5,
                                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.TimeoutExpired):
            detected = None
        if detected is not None and detected.returncode == 0 and detected.stdout.strip():
            raise RuntimeError("已检测到 NVIDIA 显卡，但 CUDA 初始化不可用；请检查驱动/DLL，或主动选择 CPU。")
    return "cpu"


def preload_onnx_cuda():
    import os
    import torch
    import onnxruntime as ort
    folder = Path(torch.__file__).resolve().parent / "lib"
    if os.name == "nt" and folder.is_dir() and not _dll_handles:
        _dll_handles.append(os.add_dll_directory(str(folder)))
    if hasattr(ort, "preload_dlls"):
        ort.preload_dlls(directory=str(folder))
    if "CUDAExecutionProvider" not in ort.get_available_providers():
        raise RuntimeError("ONNX Runtime 没有 CUDAExecutionProvider；请使用 GPU 环境，或主动选择 CPU。")


def device_info(device):
    import torch
    info = {"device": device, "torch": torch.__version__, "cuda_runtime": torch.version.cuda}
    if device == "cuda":
        free, total = torch.cuda.mem_get_info()
        info.update(name=torch.cuda.get_device_name(0), capability=list(torch.cuda.get_device_capability(0)),
                    free_bytes=free, total_bytes=total, architectures=torch.cuda.get_arch_list())
    else:
        info["name"] = "CPU"
    return info


def hardware_status():
    started = time.perf_counter()
    try:
        selected = select_device()
        info = device_info(selected)
        if selected == "cuda":
            return f"显卡：{info['name']}\n可用设备：CUDA GPU\n显存：{info['total_bytes'] / 1024**3:.2f} GiB（空闲 {info['free_bytes'] / 1024**3:.2f} GiB）"
        return f"当前未启用 GPU 加速\n正在使用 CPU 模式（PyTorch {info['torch']}）"
    except Exception as error:
        logging.exception("GPU 检查失败")
        return f"GPU 检查失败：{error}"
    finally:
        logging.getLogger(__name__).info("GPU 状态检测耗时 %.2f 秒", time.perf_counter() - started)


def onnx_session(separator):
    """0.48.0 stores its InferenceSession in model_run's closure."""
    model = getattr(separator, "model_instance", None)
    run = getattr(model, "model_run", None)
    for cell in getattr(run, "__closure__", None) or ():
        value = cell.cell_contents
        if hasattr(value, "get_providers") and hasattr(value, "run"):
            return value
    return None


def validate_loaded_device(separator, arch, device):
    if arch == "MDX":
        session = onnx_session(separator)
        expected = "CUDAExecutionProvider" if device == "cuda" else "CPUExecutionProvider"
        if session is None or session.get_providers()[0] != expected:
            raise RuntimeError(f"ONNX 实际会话未使用 {expected}，拒绝静默回退。")
        session.disable_fallback()
        return {"provider": expected}
    model = separator.model_instance.model_run
    actual = next(model.parameters()).device.type
    if actual != device:
        raise RuntimeError(f"模型实际设备为 {actual}，期望 {device}，拒绝静默回退。")
    return {"model_device": actual}
