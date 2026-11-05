"""Real FFmpeg pipeline tests with deterministic inference, no downloaded music."""
import hashlib
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from models import DEFAULT_MODEL, MODELS
from runtime_paths import configure_ffmpeg
from separate import (_separate_task, probe_audio, reserve_result_dir, run_tool,
                      song_title, verify_output)


class OutputTests(unittest.TestCase):
    def test_model_list_and_default(self):
        self.assertIn(DEFAULT_MODEL, MODELS)
        self.assertIn("UVR-MDX-NET-Voc_FT.onnx", MODELS)
        self.assertIn("UVR-MDX-NET-Inst_HQ_3.onnx", MODELS)
        self.assertNotIn("UVR_MDXNET_KARA_2.onnx", MODELS)
        self.assertNotIn("htdemucs.yaml", MODELS)

    def test_safe_titles_and_concurrent_reservation(self):
        for name, expected in [("周杰伦 - 晴天.mp3", "周杰伦 - 晴天"),
                               ("Taylor Swift - Love Story.flac", "Taylor Swift - Love Story"),
                               (r"C:\fakepath\a & b?.m4a", "a & b_"),
                               ("../../CON.wav", "_CON"), ("...wav", "未命名歌曲")]:
            self.assertEqual(song_title(name), expected)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with ThreadPoolExecutor(max_workers=8) as pool:
                paths = list(pool.map(lambda _: reserve_result_dir(root, "中文 song"), range(16)))
            self.assertEqual(len(set(paths)), 16)
            self.assertTrue((root / "中文 song (2)").is_dir())
            long = reserve_result_dir(root, "音乐😀" * 200)
            self.assertLessEqual(len(str(long / (long.name + "_Instrumental.mp3")).encode("utf-16-le")) // 2, 240)

    def test_real_encoding_matrix_and_failure_recovery(self):
        import torch
        tools = configure_ffmpeg()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "original.wav"
            run_tool([tools["ffmpeg"], "-v", "error", "-n", "-f", "lavfi", "-i",
                      "sine=frequency=330:duration=0.4", "-ar", "44100", "-ac", "2", str(source)])
            original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            results = root / "results"
            results.mkdir()

            class Engine:
                def __init__(self, output_dir, **kwargs):
                    self.folder = Path(output_dir)

                def separate(self, audio, custom_output_names):
                    for label in custom_output_names:
                        run_tool([tools["ffmpeg"], "-v", "error", "-n", "-i", audio,
                                  str(self.folder / (label + ".wav"))])
                    return ["Instrumental.wav", "Vocals.wav"]

            for ext in ("mp3", "wav", "flac", "m4a"):
                audio = root / ("cached." + ext)
                run_tool([tools["ffmpeg"], "-v", "error", "-n", "-i", str(source), str(audio)])
                for fmt in ("MP3", "WAV"):
                    with self.subTest(input=ext, output=fmt):
                        work = root / (ext + fmt)
                        work.mkdir()
                        with patch("separate.prepare_model"):
                            outputs = _separate_task(Engine, audio, results, work, DEFAULT_MODEL, fmt,
                                                     tools, lambda _: None, "周杰伦 - 晴天.mp3", True, torch)
                        self.assertFalse(work.exists())
                        self.assertEqual(set(outputs[0].parent.iterdir()), set(outputs))
                        for path in outputs:
                            self.assertEqual(path.suffix, "." + fmt.lower())
                            self.assertTrue(path.name.startswith(path.parent.name + "_"))
                            stream = verify_output(path, fmt, tools)
                            self.assertEqual((stream["sample_rate"], stream["channels"]), ("44100", 2))

            work = root / "failure"
            work.mkdir()
            stages = []
            from separate import run_tool as real_tool

            def fail_second_encoder(command):
                if "libmp3lame" in command and "Instrumental" in str(command[-1]):
                    raise RuntimeError("second encoder failed")
                return real_tool(command)

            with patch("separate.prepare_model"), patch("separate.run_tool", side_effect=fail_second_encoder):
                with self.assertRaisesRegex(RuntimeError, "second encoder failed"):
                    _separate_task(Engine, source, results, work, DEFAULT_MODEL, "MP3",
                                   tools, stages.append, "failed.wav", True, torch)
            self.assertNotIn("分离完成", stages)
            self.assertFalse((results / "failed").exists())
            self.assertTrue((work / "Vocals.wav").is_file())
            self.assertTrue((work / "Instrumental.wav").is_file())
            self.assertTrue((work / "export" / "failed_Vocals.mp3").is_file())
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), original_hash)


if __name__ == "__main__":
    unittest.main()
