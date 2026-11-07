import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

from instrument_split import CHUNK, SCNET_MODEL, cached_weights, demix


class InstrumentSplitTests(unittest.TestCase):
    def test_download_is_cached_only_after_verification(self):
        fixture = b"small checkpoint fixture"
        response = MagicMock()
        response.__enter__.return_value.iter_content.return_value = [fixture]
        checksum = hashlib.sha256(fixture).hexdigest()
        with (
            tempfile.TemporaryDirectory() as folder,
            patch("instrument_split.SCNET_BYTES", len(fixture)),
            patch("instrument_split.SCNET_SHA256", checksum),
            patch("requests.get", return_value=response) as download,
        ):
            model_dir = Path(folder)
            target = cached_weights(model_dir, lambda _: None)
            self.assertEqual(target.read_bytes(), fixture)
            self.assertEqual(cached_weights(model_dir, lambda _: None), target)
            target.write_bytes(b"corrupt existing cache")
            with self.assertRaisesRegex(RuntimeError, "权重校验失败"):
                cached_weights(model_dir, lambda _: None)
            download.assert_called_once()
            self.assertEqual(target.read_bytes(), b"corrupt existing cache")

    def test_bad_download_leaves_no_weight_or_partial_file(self):
        response = MagicMock()
        response.__enter__.return_value.iter_content.return_value = [b"invalid checkpoint"]
        with tempfile.TemporaryDirectory() as folder, patch("requests.get", return_value=response):
            model_dir = Path(folder)
            with self.assertRaisesRegex(RuntimeError, "权重校验失败"):
                cached_weights(model_dir, lambda _: None)
            self.assertFalse((model_dir / SCNET_MODEL).exists())
            self.assertFalse(list(model_dir.glob("*.partial")))

    def test_overlap_add_keeps_the_original_sample_grid(self):
        # 用恒等推理代替模型，验证两个声道在跨分段边界时都保持原样。
        frames = CHUNK * 2 + 137
        waveform = np.zeros((2, frames), dtype=np.float32)
        waveform[0, CHUNK - 1:CHUNK + 1] = (0.2, -0.2)
        waveform[1, -2:] = (0.1, -0.1)
        with patch("instrument_split.infer_chunk", side_effect=lambda _session, part, _window: np.stack([part] * 4)):
            actual = demix(None, waveform, "cpu", "balanced", lambda _: None)
        self.assertEqual(actual.shape, (4, 2, frames))
        np.testing.assert_allclose(actual[0], waveform, atol=1e-7)
