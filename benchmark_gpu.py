"""Same-input CPU/CUDA benchmark; synthetic audio is not an audio quality test."""
import argparse
import gc
import json
import subprocess
import threading
import time
from pathlib import Path
from unittest.mock import patch


def main():
    import numpy as np
    import soundfile as sf
    import torch
    import separate
    from models import ROFORMER_MODEL
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path)
    args = parser.parse_args()
    root = Path("test_artifacts/gpu-benchmark").resolve()
    root.mkdir(parents=True, exist_ok=True)
    audio = args.audio or root / "性能 中文 测试.wav"
    if not args.audio and not audio.exists():
        rate = 44100
        t = np.arange(rate * 16) / rate
        lead = .16 * np.sin(2 * np.pi * (220 * t + 18 * np.sin(2.2 * t)))
        backing = .1 * np.sin(2 * np.pi * 110 * t) + .05 * np.sin(2 * np.pi * 660 * t)
        sf.write(audio, np.column_stack((lead + backing, lead * .85 + backing)), rate)
    torch.set_num_threads(4)
    cases = [("cpu_fp32", "cpu", "fast", "fp32"),
             ("gpu_before_fp32", "cuda", "fast", "fp32"),
             ("gpu_quality", "cuda", "quality", "fp32"),
             ("gpu_balanced", "cuda", "balanced", "autocast"),
             ("gpu_fast", "cuda", "fast", "autocast"),
             ("gpu_native_fp16_evaluation", "cuda", "fast", "native_fp16")]
    base_options = separate.inference_options
    records = []
    baseline_audio = None
    for label, device, mode, precision in cases:
        gc.collect()
        torch.cuda.empty_cache()
        samples = []
        stop = threading.Event()

        def monitor():
            while not stop.is_set():
                try:
                    result = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used", "--format=csv,noheader,nounits"],
                                            capture_output=True, text=True, timeout=5,
                                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    if result.returncode == 0:
                        samples.append([int(x.strip()) for x in result.stdout.strip().split(",")])
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    pass
                stop.wait(.2)

        def options(*params, **kwargs):
            values = base_options(*params, **kwargs)
            values["use_autocast"] = precision == "autocast"
            values["use_native_fp16"] = precision == "native_fp16"
            return values

        thread = threading.Thread(target=monitor, daemon=True)
        if device == "cuda":
            thread.start()
        stats = {"case": label, "precision": precision, "cpu_threads": 4}
        try:
            with patch.object(separate, "inference_options", options):
                paths = separate.separate_audio(audio, root / "results", model_name=ROFORMER_MODEL,
                                                device=device, performance_mode=mode, output_format="WAV",
                                                metrics_callback=stats.update)
            arrays = [sf.read(path)[0] for path in paths]
            assert all(np.isfinite(x).all() and np.max(np.abs(x)) > 0 for x in arrays)
            assert set(paths[0].parent.iterdir()) == set(paths)
            if label == "gpu_before_fp32":
                baseline_audio = arrays
            if baseline_audio is not None:
                stats["relative_l2_vs_gpu_fp32_fast"] = [float(np.linalg.norm(x - ref) / max(np.linalg.norm(ref), 1e-12))
                                                          for x, ref in zip(arrays, baseline_audio)]
            stats["passed"] = True
        except Exception as error:
            stats.update(passed=False, error=str(error))
            if precision != "native_fp16":
                raise
        finally:
            stop.set()
            if device == "cuda":
                thread.join(timeout=6)
        stats["nvidia_gpu_utilization_peak_percent"] = max((x[0] for x in samples), default=None)
        stats["nvidia_process_device_memory_peak_mib"] = max((x[1] for x in samples), default=None)
        records.append(stats)
        (root / "report.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(stats, ensure_ascii=False), flush=True)
    cpu_seconds = records[0]["inference_seconds"]
    for row in records:
        if row.get("passed"):
            row["inference_speedup_vs_cpu"] = cpu_seconds / row["inference_seconds"]
    (root / "report.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
