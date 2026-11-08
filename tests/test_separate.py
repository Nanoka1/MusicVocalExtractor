"""普通检查不需要模型；真实分离测试通过 RUN_MODEL_TESTS=1 启用。"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from separate import separate_audio, validate_audio


class InputTests(unittest.TestCase):
    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                validate_audio(Path(folder) / "missing.wav")

    def test_reject_unsupported_format(self):
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "notes.txt"
            audio.write_text("not audio")
            with self.assertRaises(ValueError):
                validate_audio(audio)

    def test_four_extensions_and_unicode_path(self):
        with tempfile.TemporaryDirectory() as folder:
            for extension in (".MP3", ".WAV", ".FLAC", ".M4A"):
                audio = Path(folder) / f"音乐 sample{extension}"
                audio.touch()
                self.assertEqual(validate_audio(audio), audio.resolve())

    def test_cli_error_exit(self):
        script = Path(__file__).resolve().parents[1] / "separate.py"
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run(
                [sys.executable, str(script), str(Path(folder) / "missing.wav")],
                capture_output=True,
            )
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(b"Traceback", result.stderr)


@unittest.skipUnless(os.environ.get("RUN_MODEL_TESTS") == "1", "需要显式启用真实模型测试")
class ModelTests(unittest.TestCase):
    def test_four_formats_with_real_model(self):
        import numpy as np
        import soundfile as sf

        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            # 生成两秒非静音信号，不需要下载或提交歌曲。
            sample_rate = 44100
            time = np.arange(sample_rate * 2) / sample_rate
            signal = 0.2 * np.sin(2 * np.pi * 220 * time)
            stereo = np.column_stack((signal, signal * 0.8))
            source = folder / "source.wav"
            sf.write(source, stereo, sample_rate)
            result_folders = set()
            for extension in ("wav", "mp3", "flac", "m4a"):
                with self.subTest(format=extension):
                    audio = folder / f"音乐 sample.{extension}"
                    subprocess.run(
                        ["ffmpeg", "-v", "error", "-y", "-i", str(source), str(audio)],
                        check=True,
                    )
                    vocals, instrumental = separate_audio(audio, folder / "results", cpu=True, output_format="WAV")
                    self.assertNotIn(vocals.parent, result_folders)
                    result_folders.add(vocals.parent)
                    stems = []
                    for output in (vocals, instrumental):
                        data, rate = sf.read(output)
                        self.assertEqual(rate, sample_rate)
                        self.assertEqual(data.ndim, 2)
                        self.assertEqual(data.shape[1], 2)
                        self.assertAlmostEqual(len(data) / rate, 2.0, delta=0.15)
                        self.assertTrue(np.isfinite(data).all())
                        stems.append(data)
                    self.assertGreater(np.max(np.abs(stems[0])), 0)
                    self.assertGreater(np.max(np.abs(stems[1])), 0)
                    self.assertFalse(np.array_equal(stems[0], stems[1]))


if __name__ == "__main__":
    unittest.main()
