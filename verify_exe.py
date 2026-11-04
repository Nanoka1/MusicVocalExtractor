"""Launch the packaged EXE and exercise HTTP; keep it open for subsequent user work."""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import verify_web


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, default=Path("dist/MusicVocalExtractor/MusicVocalExtractor.exe"))
    parser.add_argument("--close-after-test", action="store_true", help="Close the test EXE afterwards; do not use during interactive work")
    args = parser.parse_args()
    exe = args.exe.resolve(strict=True)
    # Avoid accidentally testing an unrelated already-running server on the same port.
    try:
        httpx.get("http://127.0.0.1:7860/config", timeout=1)
    except httpx.RequestError:
        pass
    else:
        raise RuntimeError("Port 7860 is occupied. Close the existing application before running this EXE check.")
    logs = Path(".tools")
    logs.mkdir(exist_ok=True)
    child_env = dict(os.environ)
    # The verifier imports Python runtime_paths too; do not leak its cache default
    # into the EXE. Exercise the EXE's own normal writable-directory defaults.
    for key in ("NUMBA_CACHE_DIR", "GRADIO_TEMP_DIR", "MVE_DATA_DIR", "AUDIO_SEPARATOR_MODEL_DIR"):
        child_env.pop(key, None)
    with (logs / "exe-runtime.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([str(exe)], cwd=exe.parent, env=child_env, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        try:
            deadline = time.monotonic() + 90
            while True:
                if process.poll() is not None:
                    raise RuntimeError(f"EXE exited with {process.returncode}; see .tools/exe-runtime.log")
                try:
                    response = httpx.get("http://127.0.0.1:7860/config", timeout=2)
                    if response.status_code == 200:
                        break
                except httpx.RequestError:
                    pass
                if time.monotonic() > deadline:
                    raise RuntimeError("EXE did not start its HTTP interface within 90 seconds")
                time.sleep(0.5)
            sys.argv = ["verify_web", "--url", "http://127.0.0.1:7860", "--report", "test_artifacts/exe-web-test-report.json"]
            verify_web.main()
            print(f"Actual frozen EXE startup and inference passed: {exe}")
        finally:
            if process.poll() is None:
                if args.close_after_test:
                    # Only the child created here, when explicitly requested.
                    process.terminate()
                    process.wait(timeout=15)
                else:
                    (logs / "exe-validation.pid").write_text(str(process.pid), encoding="ascii")
                    print(f"EXE kept running for interactive use (PID {process.pid}).")


if __name__ == "__main__":
    main()
