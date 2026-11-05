"""Real CUDA tensor smoke test; no installation or system changes."""
import json
from pathlib import Path


def main():
    import importlib.metadata as metadata
    import torch
    import onnxruntime as ort
    from gpu_runtime import device_info, preload_onnx_cuda, select_device
    select_device("cuda")
    preload_onnx_cuda()
    torch.cuda.reset_peak_memory_stats()
    x = torch.randn(2048, 2048, device="cuda")
    y = x @ x
    torch.cuda.synchronize()
    assert y.is_cuda and torch.isfinite(y).all().item()
    report = device_info("cuda")
    report.update(onnxruntime=ort.__version__, providers=ort.get_available_providers(),
                  cudnn=torch.backends.cudnn.version(), separator=metadata.version("audio-separator"),
                  peak_bytes=torch.cuda.max_memory_allocated(), tensor_test=True)
    try:
        metadata.version("onnxruntime")
    except metadata.PackageNotFoundError:
        pass
    else:
        raise RuntimeError("检测到 CPU ONNX Runtime 分发包，GPU 环境不应混装。")
    target = Path("test_artifacts/gpu-preflight.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
