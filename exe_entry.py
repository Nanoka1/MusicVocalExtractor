"""Frozen entry point; also accepts the existing CLI for repeatable EXE inference QA."""
import multiprocessing
import sys


if __name__ == "__main__":
    multiprocessing.freeze_support()
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) > 1:
        from separate import main
        raise SystemExit(main())
    from app import main
    main()
