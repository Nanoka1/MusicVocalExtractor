"""Frozen entry point; also accepts the existing CLI for repeatable EXE inference QA."""
import multiprocessing
import sys


class _ConsoleMirror:
    """Keep the GUI log while sending live tqdm output to its console."""

    def __init__(self, console, log):
        self.console, self.log = console, log

    def write(self, text):
        self.log.write(text)
        return self.console.write(text)

    def flush(self):
        self.log.flush()
        self.console.flush()

    def __getattr__(self, name):
        return getattr(self.console, name)


def show_progress_console():
    """Restore the GUI build's console on demand, before inference imports tqdm."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    import ctypes
    import logging

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    if kernel32.GetConsoleWindow():
        return
    if not kernel32.AllocConsole():
        logging.warning("无法打开分离进度窗口，错误码 %s；请查看网页处理状态。", ctypes.get_last_error())
        return
    kernel32.SetConsoleTitleW("MusicVocalExtractor · 实时分离进度（关闭窗口将退出程序）")
    try:
        console = open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)
    except OSError:
        logging.exception("无法连接进度控制台；请查看网页处理状态。")
        return
    sys.stdout = _ConsoleMirror(console, sys.stdout)
    sys.stderr = _ConsoleMirror(console, sys.stderr)


def run_windowed():
    import logging
    import os
    import tempfile
    import traceback
    from datetime import datetime
    from pathlib import Path

    name = f"mve-{datetime.now():%Y%m%d-%H%M%S}-{os.getpid()}.log"
    try:
        from runtime_paths import DATA_DIR

        logs = DATA_DIR / "cache" / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        log_path = logs / name
        log = log_path.open("a", encoding="utf-8", errors="replace", buffering=1)
    except Exception:
        # A malformed config or unwritable data directory can fail before logging is available.
        log_path = Path(tempfile.gettempdir()) / name
        log_path.write_text(traceback.format_exc(), encoding="utf-8", errors="replace")
        raise RuntimeError(f"启动失败，请查看日志：{log_path}") from None

    # PyInstaller's windowed bootloader does not provide standard streams.
    sys.stdout = sys.stderr = log
    logging.basicConfig(stream=log, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.info("开始启动 MusicVocalExtractor")
    try:
        from app import main

        main()
    except Exception:
        logging.exception("MusicVocalExtractor 启动或运行失败")
        raise RuntimeError(f"启动或运行失败，请查看日志：{log_path}") from None


if __name__ == "__main__":
    multiprocessing.freeze_support()
    if sys.stdout is None and sys.stderr is None:
        run_windowed()
        raise SystemExit(0)
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if sys.argv[1:] == ["--paths"]:
        import json
        from runtime_paths import PROJECT_DIR, DATA_DIR, MODEL_DIR, OUTPUT_DIR
        print(json.dumps({"project_dir": str(PROJECT_DIR) if PROJECT_DIR else None,
                          "data_dir": str(DATA_DIR), "model_dir": str(MODEL_DIR),
                          "output_dir": str(OUTPUT_DIR)}, ensure_ascii=False))
        raise SystemExit(0)
    if sys.argv[1:] == ["--web-revision"]:
        from runtime_paths import web_revision
        print(web_revision())
        raise SystemExit(0)
    if sys.argv[1:] == ["--gpu-check"]:
        from verify_gpu import main
        raise SystemExit(main())
    if sys.argv[1:] == ["--verify-gpu-models"]:
        from verify_gpu_models import main
        raise SystemExit(main())
    if len(sys.argv) > 1:
        from separate import main
        raise SystemExit(main())
    from app import main
    main()
