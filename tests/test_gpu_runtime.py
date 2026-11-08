import unittest
from types import SimpleNamespace
from unittest.mock import patch

from gpu_runtime import select_device, validate_loaded_device


class DeviceTests(unittest.TestCase):
    def test_explicit_cuda_never_falls_back(self):
        with patch("torch.cuda.is_available", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "GPU 初始化失败"):
                select_device("cuda")
            self.assertEqual(select_device("cpu"), "cpu")

    def test_initialization_failure_is_visible(self):
        with patch("torch.cuda.is_available", return_value=True), patch("torch.zeros", side_effect=RuntimeError("DLL failure")):
            with self.assertRaisesRegex(RuntimeError, "CUDA 初始化/运算失败"):
                select_device("cuda")

    def test_onnx_fallback_is_rejected(self):
        session = SimpleNamespace(get_providers=lambda: ["CPUExecutionProvider"], run=lambda: None,
                                  disable_fallback=lambda: None)

        def run(_):
            return session.run()

        separator = SimpleNamespace(model_instance=SimpleNamespace(model_run=run))
        with self.assertRaisesRegex(RuntimeError, "拒绝静默回退"):
            validate_loaded_device(separator, "MDX", "cuda")
        self.assertEqual(validate_loaded_device(separator, "MDX", "cpu")["provider"], "CPUExecutionProvider")
