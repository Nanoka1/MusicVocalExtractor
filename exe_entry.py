"""Frozen entry point; also accepts the existing CLI for repeatable EXE inference QA."""
import multiprocessing
import sys


if __name__ == "__main__":
    multiprocessing.freeze_support()
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
