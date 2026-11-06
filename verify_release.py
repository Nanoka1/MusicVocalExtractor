"""Frozen GPU acceptance gate; never publishes or deletes a package."""
import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def package_manifest(package):
    return {p.relative_to(package).as_posix(): sha256(p) for p in sorted(package.rglob("*"))
            if p.is_file() and p.name != "release-validation.json"}


def main():
    import httpx
    from gradio_client import Client, handle_file
    from models import DEFAULT_MODEL, ROFORMER_MODEL, MODELS
    from runtime_paths import MODEL_DIR, OUTPUT_DIR, configure_ffmpeg
    from separate import verify_output, run_tool
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--cpu", action="store_true", help="只验收 CPU；不进行任何 CUDA 探测或运算")
    args = parser.parse_args()
    package = args.package.resolve(strict=True)
    exe = package / "MusicVocalExtractor.exe"
    root = Path(__file__).resolve().parent
    runs = root / "test_artifacts" / "release-validation"
    runs.mkdir(parents=True, exist_ok=True)
    validation = Path(tempfile.mkdtemp(prefix="gpu_", dir=runs))
    env = dict(os.environ, MVE_DATA_DIR=str(validation / "data"), AUDIO_SEPARATOR_MODEL_DIR=str(MODEL_DIR),
               GRADIO_TEMP_DIR=str(validation / "gradio"), NUMBA_CACHE_DIR=str(validation / "numba"),
               OMP_NUM_THREADS="4", MKL_NUM_THREADS="4", MVE_NO_BROWSER="1")
    # Acceptance must exercise the bundle's real default project paths as well.
    env.pop("MVE_DATA_DIR", None)
    env.pop("AUDIO_SEPARATOR_MODEL_DIR", None)
    if args.cpu:
        env["MVE_DEVICE"] = "cpu"
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    with (validation / "cli.log").open("w", encoding="utf-8") as log:
        if args.cpu:
            paths_result = subprocess.check_output([str(exe), "--paths"], cwd=validation, env=env, creationflags=flags, timeout=60)
            paths_info = json.loads(paths_result.decode("utf-8"))
            assert Path(paths_info["output_dir"]) == OUTPUT_DIR
            assert Path(paths_info["model_dir"]) == MODEL_DIR
            audio = validation / ("路径验收 中文 空格 " + time.strftime("%H%M%S") + ".wav")
            run_tool([configure_ffmpeg()["ffmpeg"], "-v", "error", "-n", "-f", "lavfi", "-i", "sine=frequency=330:duration=1", "-ar", "44100", "-ac", "2", str(audio)])
            proofs = []
            OUTPUT_DIR.mkdir(exist_ok=True)
            for name, fmt in ((DEFAULT_MODEL, "MP3"), ("UVR-MDX-NET-Inst_HQ_3.onnx", "WAV"), (ROFORMER_MODEL, "MP3")):
                before = set(OUTPUT_DIR.iterdir())
                subprocess.run([str(exe), str(audio), "--cpu", "--model", name, "--format", fmt, "--performance", "fast"],
                               cwd=validation, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=flags, timeout=300, check=True)
                new = set(OUTPUT_DIR.iterdir()) - before
                assert len(new) == 1
                results = list(new.pop().iterdir())
                assert len(results) == 2
                for result in results:
                    verify_output(result, fmt, configure_ffmpeg())
                proofs.append({"model": name, "passed": True, "device": "cpu"})
            preflight = {"device": "cpu", "gpu_tests": "paused", "paths": paths_info}
        else:
            for command in ("--gpu-check", "--verify-gpu-models"):
                subprocess.run([str(exe), command], cwd=validation, env=env, stdout=log, stderr=subprocess.STDOUT,
                               creationflags=flags, timeout=300, check=True)
            preflight = json.loads((validation / "test_artifacts/gpu-preflight.json").read_text(encoding="utf-8"))
            proofs = json.loads((validation / "test_artifacts/gpu-model-proof/report.json").read_text(encoding="utf-8"))
            assert preflight["tensor_test"] and preflight["cuda_runtime"] and len(proofs) == 3
            assert all(row["passed"] for row in proofs)
            assert next(row for row in proofs if row["model"] == ROFORMER_MODEL)["cuda_forward_calls"] > 0
            assert all(row["cuda_nodes"] > 0 for row in proofs if row["model"] != ROFORMER_MODEL)
            # The same CUDA bundle must also remain usable with an explicit CPU request.
            cpu_audio = validation / "test_artifacts/gpu-model-proof/GPU 中文 验证.wav"
            subprocess.run([str(exe), str(cpu_audio), "--cpu", "--model", DEFAULT_MODEL,
                            "--output-dir", str(validation / "cpu-fallback")], cwd=validation, env=env,
                           stdout=log, stderr=subprocess.STDOUT, creationflags=flags, timeout=300, check=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env["GRADIO_SERVER_PORT"] = str(port)
    address = f"http://127.0.0.1:{port}"
    with (validation / "web.log").open("w", encoding="utf-8") as log:
        child = subprocess.Popen([str(exe)], cwd=validation, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
        try:
            deadline = time.monotonic() + 120
            while True:
                if child.poll() is not None:
                    raise RuntimeError(f"EXE 启动失败，日志：{validation / 'web.log'}")
                try:
                    if httpx.get(address + "/config", timeout=2).status_code == 200:
                        break
                except httpx.RequestError:
                    pass
                if time.monotonic() >= deadline:
                    raise RuntimeError("EXE 启动超时。")
                time.sleep(.5)
            client = Client(address, download_files=str(validation / "downloads"), verbose=False)
            if not args.cpu:
                benchmark_audio = root / "test_artifacts/gpu-benchmark/性能 中文 测试.wav"
                audio = benchmark_audio if benchmark_audio.is_file() else validation / "test_artifacts/gpu-model-proof/GPU 中文 验证.wav"
            config = httpx.get(address + "/config").json()
            assert any(c["props"].get("label") == "当前输出目录" and c["props"].get("value") == str(OUTPUT_DIR) for c in config["components"])
            for mode in (["balanced"] if args.cpu else ["quality", "balanced", "fast"]):
                result = client.predict(handle_file(str(audio)), ROFORMER_MODEL, "MP3", mode, "cpu" if args.cpu else "cuda", api_name="/separate")
                assert "分离完成" in result[2] and ("CPU" if args.cpu else "CUDA") in result[2]
                assert str(OUTPUT_DIR) in result[2]
                for download, preview in zip(result[:2], result[3:]):
                    verify_output(Path(download), "MP3", configure_ffmpeg())
                    assert Path(download).read_bytes() == Path(preview).read_bytes()
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=20)
    settings = json.loads((package / "runtime-config.json").read_text(encoding="utf-8-sig"))
    if "model_dir" in settings:
        assert Path(settings["model_dir"]).resolve() == MODEL_DIR.resolve()
    # audio-separator ships a required 1208-byte mixer.ckpt resource. It is not
    # a downloaded separation model; do not remove it or reject a correct bundle.
    assert not any(list(package.rglob(name)) for name in MODELS)
    assert not any(p.stat().st_size > 1024 * 1024 for pattern in ("*.ckpt", "*.onnx", "*.pth", "*.th") for p in package.rglob(pattern))
    report = {"passed": True, "gpu": not args.cpu, "cpu": args.cpu, "preflight": preflight, "model_proofs": proofs,
              "http_preview_download": True, "models_shared": True,
              "validation_artifacts": str(validation), "manifest": package_manifest(package)}
    (package / "release-validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Frozen {'CPU' if args.cpu else 'GPU'} acceptance PASS: {package}")


if __name__ == "__main__":
    main()
