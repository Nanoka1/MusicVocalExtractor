"""End-to-end HTTP verification against a running Python or frozen Gradio app."""
import argparse
import hashlib
import json
import time
from pathlib import Path

import httpx
from gradio_client import Client, handle_file
from models import DEFAULT_MODEL
from runtime_paths import PROJECT_DIR, configure_ffmpeg
from separate import run_tool, verify_output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:7860")
    parser.add_argument("--report", default="test_artifacts/web-test-report.json")
    args = parser.parse_args()
    root = PROJECT_DIR / "test_artifacts"
    root.mkdir(parents=True, exist_ok=True)
    tools = configure_ffmpeg()
    fixtures = [root / "中文 网页 上传 & 测试.mp3", root / "中文 第二个 网页输入.mp3"]
    for fixture, frequency in zip(fixtures, (330, 660)):
        if not fixture.exists():
            run_tool([tools["ffmpeg"], "-v", "error", "-n", "-f", "lavfi", "-i",
                      f"sine=frequency={frequency}:duration=3", "-ar", "44100", "-ac", "2",
                      "-c:a", "libmp3lame", "-b:a", "320k", str(fixture)])
    originals = [hashlib.sha256(fixture.read_bytes()).hexdigest() for fixture in fixtures]
    client = Client(args.url, download_files=str(root / "web-downloads"), verbose=False)
    config = httpx.get(args.url + "/config", timeout=30).json()
    assert config["enable_queue"]
    assert not config.get("share", False)
    jobs = []
    # Submit both before waiting: the queue must isolate the tasks and the selected model/format.
    for fixture, (model, fmt) in zip(fixtures, [(DEFAULT_MODEL, "WAV"), ("UVR-MDX-NET-Voc_FT.onnx", "MP3")]):
        job = client.submit(handle_file(str(fixture)), model, fmt, api_name="/separate")
        jobs.append((model, fmt, job))
    records = []
    for model, fmt, job in jobs:
        stages = []
        responsive = False
        for update in job:
            stages.append(update[2])
            if "正在进行人声分离" in update[2]:
                responsive = httpx.get(args.url + "/config", timeout=10).status_code == 200
        outputs = job.result(timeout=180)
        assert "分离完成" in outputs[2], outputs[2]
        assert model in outputs[2]
        assert responsive, "HTTP did not respond during inference or inference stage was absent"
        assert len(outputs) == 5
        for path, label in zip(outputs[:2], ("Vocals", "Instrumental")):
            assert Path(path).name == f"{label}.{fmt.lower()}"
            verify_output(Path(path), fmt, tools)
            run_tool([tools["ffmpeg"], "-v", "error", "-i", path, "-f", "null", "-"])
        # Preview is served from the same encoded file, avoiding another lossy encode.
        for downloaded, preview in zip(outputs[:2], outputs[3:]):
            assert hashlib.sha256(Path(downloaded).read_bytes()).hexdigest() == hashlib.sha256(Path(preview).read_bytes()).hexdigest()
        records.append({"model": model, "format": fmt, "passed": True,
                        "responsive_during_inference": responsive, "outputs": outputs[:2], "stages": stages})
    assert [hashlib.sha256(fixture.read_bytes()).hexdigest() for fixture in fixtures] == originals
    report = PROJECT_DIR / args.report
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"HTTP upload, queue isolation, inference, preview and download passed: {report}")


if __name__ == "__main__":
    main()
