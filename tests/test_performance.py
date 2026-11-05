import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from models import ROFORMER_MODEL
from performance import inference_options, infer_with_retry, observe_forward


class PerformanceTests(unittest.TestCase):
    def test_modes_and_model_specific_options(self):
        settings = [inference_options(ROFORMER_MODEL, m, "cuda", 8 * 1024**3) for m in ("quality", "balanced", "fast")]
        self.assertEqual([s["mdxc_params"]["overlap"] for s in settings], [4, 2, 1])
        self.assertEqual([s["use_autocast"] for s in settings], [False, True, True])
        low = inference_options(ROFORMER_MODEL, "balanced", "cuda", 2 * 1024**3)
        self.assertLess(low["mdxc_params"]["segment_size"], settings[1]["mdxc_params"]["segment_size"])
        self.assertFalse(inference_options(ROFORMER_MODEL, "fast", "cpu")["use_autocast"])
        self.assertNotIn("mdxc_params", inference_options("UVR-MDX-NET-Voc_FT.onnx", "balanced", "cuda"))
        with self.assertRaises(ValueError):
            inference_options(ROFORMER_MODEL, "unknown", "cuda")

    def test_oom_retries_once_in_isolated_folder(self):
        import torch
        class Engine:
            calls = 0
            fail_always = False
            model_instance = None

            def __init__(self):
                self.model_instance = SimpleNamespace(segment_size=801)

            def separate(self, *args, **kwargs):
                self.calls += 1
                if self.calls == 1 or self.fail_always:
                    raise torch.cuda.OutOfMemoryError("simulated CUDA OOM")
                return ["Vocals.wav", "Instrumental.wav"]

        for always in (False, True):
            with self.subTest(always=always), tempfile.TemporaryDirectory() as folder:
                engine = Engine()
                engine.fail_always = always
                metrics = {}
                with patch("performance.observe_forward", return_value=[]), patch("torch.cuda.empty_cache"), patch("gpu_runtime.validate_loaded_device"):
                    call = lambda: infer_with_retry(engine, Path("input.wav"), {}, Path(folder), ROFORMER_MODEL,
                                                    "cuda", metrics, lambda _: None)
                    if always:
                        with self.assertRaisesRegex(RuntimeError, "CUDA 显存不足"):
                            call()
                    else:
                        _, active = call()
                        self.assertEqual(active, Path(folder) / "oom_retry")
                self.assertEqual(engine.calls, 2)
                self.assertEqual(engine.model_instance.segment_size, 400)
                self.assertEqual(metrics["oom_retries"], 1)

    def test_nonfinite_forward_is_rejected(self):
        import torch
        class BadNetwork(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.weight = torch.nn.Parameter(torch.ones(1))
            def forward(self, value):
                return value * float("nan")
        network = BadNetwork()
        separator = SimpleNamespace(model_instance=SimpleNamespace(model_run=network))
        handles = observe_forward(separator, "cpu", {})
        try:
            with self.assertRaises(FloatingPointError):
                network(torch.ones(1))
        finally:
            for handle in handles:
                handle.remove()
