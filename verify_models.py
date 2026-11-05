"""Explicit real inference test; creates only its own test_artifacts, no personal audio."""
import hashlib
import json
import time
from pathlib import Path

from models import DEFAULT_MODEL
from runtime_paths import PROJECT_DIR, configure_ffmpeg
from separate import probe_audio, run_tool, separate_audio, verify_output


def main():
    import numpy as np
    import soundfile as sf
    folder = PROJECT_DIR / "test_artifacts" / "中文 测试 & 音频"
    folder.mkdir(parents=True, exist_ok=True)
    tools = configure_ffmpeg()
    wav = folder / "输入 歌曲.wav"
    mp3 = folder / "输入 歌曲.mp3"
    if not wav.exists():
        rate = 44100
        t = np.arange(rate * 3) / rate
        melody = 0.15 * np.sin(2 * np.pi * (220 * t + 45 * np.sin(t * 3)))
        backing = 0.12 * np.sin(2 * np.pi * 110 * t)
        sf.write(wav, np.column_stack((melody + backing, melody * 0.8 + backing)), rate)
    if not mp3.exists():
        run_tool([tools["ffmpeg"], "-v", "error", "-n", "-i", str(wav), "-c:a", "libmp3lame", "-b:a", "320k", str(mp3)])
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (wav, mp3)}
    cases = [(DEFAULT_MODEL, wav, "WAV"), (DEFAULT_MODEL, mp3, "MP3"),
             ("UVR-MDX-NET-Voc_FT.onnx", mp3, "MP3"),
             ("UVR-MDX-NET-Inst_HQ_3.onnx", wav, "WAV")]
    report = []
    for model, source, fmt in cases:
        start = time.perf_counter()
        stages = []
        case = {"model": model, "input": str(source), "format": fmt}
        try:
            outputs = separate_audio(source, folder / "results", cpu=True, model_name=model, output_format=fmt,
                                     progress_callback=lambda stage: (print(stage, flush=True), stages.append(stage)))
            for output in outputs:
                verify_output(output, fmt, tools)
                run_tool([tools["ffmpeg"], "-v", "error", "-i", str(output), "-f", "null", "-"])
                data, rate = sf.read(output)
                assert np.isfinite(data).all()
                assert abs(len(data) / rate - 3) < 0.15
            a, _ = sf.read(outputs[0])
            b, _ = sf.read(outputs[1])
            assert not np.array_equal(a, b), "stems are identical"
            case.update(passed=True, outputs=list(map(str, outputs)), probe=[probe_audio(p, tools) for p in outputs])
        except Exception as error:
            import traceback
            traceback.print_exc()
            case.update(passed=False, error=str(error))
        case.update(seconds=round(time.perf_counter()-start, 2), stages=stages)
        report.append(case)
        (folder / "model-test-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in case.items() if k != "probe"}, ensure_ascii=False), flush=True)
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (wav, mp3)}
    assert before == after, "input changed"
    parents = [Path(c["outputs"][0]).parent for c in report if c["passed"]]
    assert len(set(parents)) == len(parents), "result directory reused"
    return 0 if all(c["passed"] for c in report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
