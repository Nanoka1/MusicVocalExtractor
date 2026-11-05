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
    from models import ROFORMER_MODEL
    from runtime_paths import MODEL_DIR, configure_ffmpeg
    from separate import verify_output
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
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
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    with (validation / "cli.log").open("w", encoding="utf-8") as log:
        for command in ("--gpu-check", "--verify-gpu-models"):
            subprocess.run([str(exe), command], cwd=validation, env=env, stdout=log, stderr=subprocess.STDOUT,
                           creationflags=flags, timeout=300, check=True)
    preflight = json.loads((validation / "test_artifacts/gpu-preflight.json").read_text(encoding="utf-8"))
    proofs = json.loads((validation / "test_artifacts/gpu-model-proof/report.json").read_text(encoding="utf-8"))
    assert preflight["tensor_test"] and preflight["cuda_runtime"] and len(proofs) == 3
    assert all(row["passed"] for row in proofs)
    assert next(row for row in proofs if row["model"] == ROFORMER_MODEL)["cuda_forward_calls"] > 0
    assert all(row["cuda_nodes"] > 0 for row in proofs if row["model"] != ROFORMER_MODEL)
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
            audio = validation / "test_artifacts/gpu-model-proof/GPU 中文 验证.wav"
            result = client.predict(handle_file(str(audio)), ROFORMER_MODEL, "MP3", "balanced", "cuda", api_name="/separate")
            assert "分离完成" in result[2] and "CUDA" in result[2]
            for download, preview in zip(result[:2], result[3:]):
                verify_output(Path(download), "MP3", configure_ffmpeg())
                assert Path(download).read_bytes() == Path(preview).read_bytes()
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=20)
    settings = json.loads((package / "runtime-config.json").read_text(encoding="utf-8-sig"))
    assert Path(settings["model_dir"]).resolve() == MODEL_DIR.resolve()
    assert not any(package.rglob("*.ckpt")) and not any(package.rglob("*.onnx"))
    report = {"passed": True, "gpu": True, "preflight": preflight, "model_proofs": proofs,
              "http_preview_download": True, "models_shared": True,
              "validation_artifacts": str(validation), "manifest": package_manifest(package)}
    (package / "release-validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Frozen GPU acceptance PASS: {package}")


if __name__ == "__main__":
    main()
