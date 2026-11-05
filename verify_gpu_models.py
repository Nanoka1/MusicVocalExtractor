"""Opt-in real CUDA proof, including ONNX node profiling and RoFormer hooks."""
import json
from pathlib import Path
from unittest.mock import patch


def main():
    import torch
    import onnxruntime as ort
    import separate
    from models import MODELS, ROFORMER_MODEL
    from gpu_runtime import onnx_session
    from runtime_paths import configure_ffmpeg
    root = Path("test_artifacts/gpu-model-proof").resolve()
    root.mkdir(parents=True, exist_ok=True)
    audio = root / "GPU 中文 验证.wav"
    if not audio.exists():
        separate.run_tool([configure_ffmpeg()["ffmpeg"], "-v", "error", "-n", "-f", "lavfi", "-i",
                           "sine=frequency=330:duration=3", "-ar", "44100", "-ac", "2", str(audio)])
    reports = []
    prepare = separate.prepare_model
    session_factory = ort.InferenceSession
    for name in MODELS:
        proof = {"model": name, "cuda_forward_calls": 0}
        handles = []
        sessions = []

        def profiled_session(*args, **kwargs):
            options = kwargs.get("sess_options") or ort.SessionOptions()
            options.enable_profiling = True
            options.profile_file_prefix = str(root / (name + ".profile"))
            kwargs["sess_options"] = options
            session = session_factory(*args, **kwargs)
            sessions.append(session)
            return session

        def prepared(separator, model, stage, **kwargs):
            prepare(separator, model, stage, **kwargs)
            if model == ROFORMER_MODEL:
                network = separator.model_instance.model_run

                def before(module, args):
                    assert next(module.parameters()).is_cuda
                    assert args[0].is_cuda

                def after(module, args, output):
                    assert output.is_cuda and torch.isfinite(output).all().item()
                    proof["cuda_forward_calls"] += 1

                handles.extend([network.register_forward_pre_hook(before), network.register_forward_hook(after)])
        torch.cuda.reset_peak_memory_stats()
        try:
            with patch.object(separate, "prepare_model", prepared), patch.object(ort, "InferenceSession", profiled_session):
                outputs = separate.separate_audio(audio, root / "results", model_name=name, device="cuda")
            torch.cuda.synchronize()
            proof["peak_bytes"] = torch.cuda.max_memory_allocated()
            proof["outputs"] = list(map(str, outputs))
            if name == ROFORMER_MODEL:
                assert proof["cuda_forward_calls"] > 0 and proof["peak_bytes"] > 0
            else:
                nodes = []
                for session in sessions:
                    profile = json.loads(Path(session.end_profiling()).read_text())
                    nodes.extend(x for x in profile if x.get("args", {}).get("provider") == "CUDAExecutionProvider")
                assert nodes, "ONNX did not execute any CUDA nodes"
                proof["cuda_nodes"] = len(nodes)
                proof["cuda_ops"] = sorted({x["args"].get("op_name") for x in nodes})
            proof["passed"] = True
            reports.append(proof)
        finally:
            for handle in handles:
                handle.remove()
        print(json.dumps(proof, ensure_ascii=False), flush=True)
    (root / "report.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
