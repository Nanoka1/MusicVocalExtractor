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
    from runtime_paths import MODEL_DIR, OUTPUT_DIR, configure_ffmpeg, web_revision
    from separate import verify_output, run_tool
    from audio_gain import audio_peak
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--artifacts-dir", type=Path, help="验收日志及临时音频的保存目录")
    parser.add_argument("--cpu", action="store_true", help="只验收 CPU；不进行任何 CUDA 探测或运算")
    args = parser.parse_args()
    package = args.package.resolve(strict=True)
    exe = package / "MusicVocalExtractor.exe"
    revision = web_revision()
    assert web_revision(package / "_internal") == revision
    build = json.loads((package / "build-info.json").read_text(encoding="utf-8-sig"))
    assert build["web_revision"] == revision
    root = Path(__file__).resolve().parent
    runs = args.artifacts_dir.resolve() if args.artifacts_dir else root / "test_artifacts" / "release-validation"
    runs.mkdir(parents=True, exist_ok=True)
    validation = Path(tempfile.mkdtemp(prefix="gpu_", dir=runs))
    env = dict(os.environ, MVE_DATA_DIR=str(validation / "data"), AUDIO_SEPARATOR_MODEL_DIR=str(MODEL_DIR),
               GRADIO_TEMP_DIR=str(validation / "gradio"), NUMBA_CACHE_DIR=str(validation / "numba"),
               OMP_NUM_THREADS="4", MKL_NUM_THREADS="4", MVE_NO_BROWSER="1")
    # Acceptance must exercise the bundle's real default project paths as well.
    env.pop("MVE_DATA_DIR", None)
    env.pop("AUDIO_SEPARATOR_MODEL_DIR", None)
    env.pop("MVE_DEVICE", None)
    if args.cpu:
        env["MVE_DEVICE"] = "cpu"
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    paths_result = subprocess.check_output([str(exe), "--paths"], cwd=validation, env=env,
                                           creationflags=flags, timeout=60)
    paths_info = json.loads(paths_result.decode("utf-8"))
    assert Path(paths_info["output_dir"]) == OUTPUT_DIR and Path(paths_info["model_dir"]) == MODEL_DIR
    frozen_revision = subprocess.check_output([str(exe), "--web-revision"], cwd=validation, env=env,
                                              creationflags=flags, timeout=60).decode("utf-8").strip()
    assert frozen_revision == revision
    # All inference and web output stays in the acceptance workspace.
    env.update(MVE_DATA_DIR=str(validation / "data"), AUDIO_SEPARATOR_MODEL_DIR=str(MODEL_DIR))
    output_dir = validation / "data" / "outputs"
    with (validation / "cli.log").open("w", encoding="utf-8") as log:
        if args.cpu:
            audio = validation / ("路径验收 中文 空格 " + time.strftime("%H%M%S") + ".wav")
            run_tool([configure_ffmpeg()["ffmpeg"], "-v", "error", "-n", "-f", "lavfi", "-i", "sine=frequency=330:duration=1", "-ar", "44100", "-ac", "2", str(audio)])
            proofs = []
            output_dir.mkdir(parents=True, exist_ok=True)
            for name in MODELS:
                before = set(output_dir.iterdir())
                subprocess.run([str(exe), str(audio), "--cpu", "--model", name, "--performance", "fast"],
                               cwd=validation, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=flags, timeout=300, check=True)
                new = set(output_dir.iterdir()) - before
                assert len(new) == 1
                results = list(new.pop().iterdir())
                assert len(results) == 2
                for result in results:
                    verify_output(result, "MP3", configure_ffmpeg())
                proofs.append({"model": name, "passed": True, "device": "cpu"})
            preflight = {"device": "cpu", "gpu_tests": "paused", "paths": paths_info}
        else:
            for command in ("--gpu-check", "--verify-gpu-models"):
                subprocess.run([str(exe), command], cwd=validation, env=env, stdout=log, stderr=subprocess.STDOUT,
                               creationflags=flags, timeout=300, check=True)
            preflight = json.loads((validation / "test_artifacts/gpu-preflight.json").read_text(encoding="utf-8"))
            proofs = json.loads((validation / "test_artifacts/gpu-model-proof/report.json").read_text(encoding="utf-8"))
            assert preflight["tensor_test"] and preflight["cuda_runtime"] and len(proofs) == len(MODELS)
            assert {row["model"] for row in proofs} == set(MODELS)
            assert all(row["passed"] for row in proofs)
            assert next(row for row in proofs if row["model"] == ROFORMER_MODEL)["cuda_forward_calls"] > 0
            assert all(row["cuda_nodes"] > 0 for row in proofs if row["model"] != ROFORMER_MODEL)
            # The same CUDA bundle must also remain usable with an explicit CPU request.
            cpu_audio = validation / "test_artifacts/gpu-model-proof/GPU 中文 验证.wav"
            subprocess.run([str(exe), str(cpu_audio), "--cpu", "--model", DEFAULT_MODEL,
                            "--vocal-gain-db", "6", "--instrumental-gain-db", "12",
                            "--output-dir", str(validation / "cpu-fallback")], cwd=validation, env=env,
                           stdout=log, stderr=subprocess.STDOUT, creationflags=flags, timeout=300, check=True)
            fallback_files = list((validation / "cpu-fallback").rglob("*.mp3"))
            assert len(fallback_files) == 2
            for path in fallback_files:
                verify_output(path, "MP3", configure_ffmpeg())
                assert audio_peak(path)["peak"] < 1
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
            assert any(c["props"].get("label") == "当前输出目录" and c["props"].get("value") == str(output_dir) for c in config["components"])
            components = [c["props"] for c in config["components"]]
            assert any(c.get("elem_id") == "mve-web-revision" and revision in c["value"] for c in components)
            mixer = next(c for c in config["components"] if "export_mix" in c["props"].get("server_fns", ()))
            for prop, asset in (("html_template", "mixer.html"), ("css_template", "mixer.css"), ("js_on_load", "mixer.js")):
                assert mixer["props"][prop] == (root / asset).read_text(encoding="utf-8")
            modes = next(c["choices"] for c in components if c.get("label") == "分离模式")
            assert {choice[1] for choice in modes} == {"two", "vocals"}
            formats = next(c["choices"] for c in components if c.get("label") == "输出音频格式")
            assert [choice[1] for choice in formats] == ["MP3"]
            for label in ("人声增益（dB）", "伴奏增益（dB）"):
                slider = next(c["props"] for c in config["components"] if c["props"].get("label") == label)
                assert (slider["minimum"], slider["maximum"], slider["value"]) == (0, 12, 0)
            dropdown = next(c['props'] for c in config['components'] if c['props'].get('label') == '选择 AI 分离模型')
            assert dropdown['value'] == DEFAULT_MODEL
            assert {choice[1] for choice in dropdown['choices']} == set(MODELS)
            gain_proofs = []
            for mode in (["balanced"] if args.cpu else ["quality", "balanced", "fast"]):
                vocal_db, inst_db = {"quality": (0, 0), "balanced": (6, 12), "fast": (12, 6)}[mode]
                result = client.predict(handle_file(str(audio)), ROFORMER_MODEL, "MP3", mode, "cpu" if args.cpu else "cuda",
                                        vocal_db, inst_db, api_name="/separate")
                assert "分离完成" in result[2] and ("CPU" if args.cpu else "CUDA") in result[2]
                assert str(output_dir) in result[2]
                assert f"人声增益：+{vocal_db:.1f} dB" in result[2] and f"伴奏增益：+{inst_db:.1f} dB" in result[2]
                for download, preview in zip(result[:2], result[3:]):
                    verify_output(Path(download), "MP3", configure_ffmpeg())
                    assert Path(download).read_bytes() == Path(preview).read_bytes()
                    assert audio_peak(download)["peak"] < 1
                gain_proofs.append(dict(mode=mode, vocal_gain_db=vocal_db, instrumental_gain_db=inst_db,
                                        status=result[2], passed=True))
            mix_job = client.submit(handle_file(str(audio)), DEFAULT_MODEL, "MP3", "balanced",
                                    "cpu" if args.cpu else "cuda", 0, 0, "vocals", api_name="/mix")
            stages = [update[1] for update in mix_job]
            mixed = mix_job.result(timeout=300)
            for stage in ("正在进行人声分离", "正在对齐音轨时间轴", "正在导出音频"):
                assert any(stage in status for status in stages), f"网页缺少实时阶段：{stage}"
            progress_logs = [validation / "web.log", *(validation / "data/cache/logs").glob("mve-*.log")]
            console_log = "\n".join(log.read_text(encoding="utf-8", errors="replace")
                                    for log in progress_logs if log.is_file())
            assert "正在进行人声分离" in console_log and "正在导出音频" in console_log
            assert "100%" in console_log, "缺少模型实际 tqdm 处理进度"
            assert "分离完成" in mixed[1] and ("和声推理设备：CPU" if args.cpu else "和声推理设备：CUDA") in mixed[1]
            mix = json.loads(mixed[2])
            assert [t["id"] for t in mix["tracks"]] == ["LeadVocals", "BackingVocals", "Instrumental"]
            exported = httpx.post(address + "/gradio_api/component_server", json={
                "component_id": mixer["id"], "session_hash": client.session_hash, "fn_name": "export_mix",
                "data": {"name": mix["title"], "format": "MP3",
                         "levels": {"LeadVocals": 100, "BackingVocals": 0, "Instrumental": 50}, "master": 100},
            }, timeout=60)
            exported.raise_for_status()
            reply = exported.json()
            assert reply["name"].endswith(".mp3")
            saved = output_dir / mix["title"]
            assert len(list(saved.glob("*.mp3"))) == 3 and not list(saved.rglob("*.wav"))
            mixed_path = saved / "mix-exports" / reply["name"]
            verify_output(mixed_path, "MP3", configure_ffmpeg())
            response = httpx.get(address + "/" + reply["url"], timeout=30)
            response.raise_for_status()
            assert response.content == mixed_path.read_bytes()
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
              "stem_gain_ui": gain_proofs, "web_revision": revision, "mp3_mix": True,
              "live_stages": stages, "console_progress": True,
              "validation_artifacts": str(validation), "manifest": package_manifest(package)}
    (package / "release-validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Frozen {'CPU' if args.cpu else 'GPU'} acceptance PASS: {package}")


if __name__ == "__main__":
    main()
