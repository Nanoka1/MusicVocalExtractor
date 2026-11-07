"""Regression tests for semantic mapping, safe export and model cache protection."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from models import DEFAULT_MODEL, check_model
from runtime_paths import configure_ffmpeg
from separate import export_stems, named_stems, prepare_model, run_tool, verify_output


class UpgradeTests(unittest.TestCase):
    def test_unknown_model_rejected(self):
        with self.assertRaises(ValueError):
            check_model("unknown.onnx")

    def test_semantic_mapping_independent_of_order(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            stems = named_stems(["Instrumental.wav", "Vocals.wav"], folder, ("Vocals", "Instrumental"))
            self.assertEqual(stems["Vocals"], folder.resolve() / "Vocals.wav")
            self.assertEqual(stems["Instrumental"], folder.resolve() / "Instrumental.wav")
            with self.assertRaises(RuntimeError):
                named_stems(["Drums.wav", "Vocals.wav"], folder, ("Vocals", "Instrumental"))
            with self.assertRaises(RuntimeError):
                named_stems(["../Vocals.wav", "Instrumental.wav"], folder, ("Vocals", "Instrumental"))

    def test_corrupt_model_is_never_overwritten_or_deleted(self):
        class FakeSeparator:
            downloaded = False
            def list_supported_model_files(self):
                return {check_model(DEFAULT_MODEL): {"Default": {"filename": DEFAULT_MODEL, "download_files": [DEFAULT_MODEL]}}}
            def get_model_checksums(self):
                return {DEFAULT_MODEL: "published checksum"}
            def verify_model_file_checksum(self, path):
                return False
            def download_model_and_data(self, model):
                self.downloaded = True
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            model = folder / DEFAULT_MODEL
            model.write_bytes(b"preserve me")
            separator = FakeSeparator()
            with patch("separate.MODEL_DIR", folder), self.assertRaises(RuntimeError):
                prepare_model(separator, DEFAULT_MODEL, lambda stage: None)
            self.assertEqual(model.read_bytes(), b"preserve me")
            self.assertFalse(separator.downloaded)

    def test_mp3_unicode_spaces_special_chars(self):
        tools = configure_ffmpeg()
        with tempfile.TemporaryDirectory(prefix="中文 空格 & 音频 ") as temp:
            folder = Path(temp)
            work = folder / "intermediate"
            work.mkdir()
            stems = {}
            for name, frequency in (("Vocals", 440), ("Instrumental", 220)):
                path = work / f"{name}.wav"
                run_tool([tools["ffmpeg"], "-v", "error", "-n", "-f", "lavfi", "-i",
                          f"sine=frequency={frequency}:duration=1", "-ar", "44100", "-ac", "2", str(path)])
                stems[name] = path
            original_hashes = {k: hashlib.sha256(v.read_bytes()).hexdigest() for k, v in stems.items()}
            result = folder / "MP3"
            result.mkdir()
            outputs = export_stems(stems, result, "MP3", tools)
            for output in outputs:
                stream = verify_output(output, "MP3", tools)
                self.assertEqual(stream["channels"], 2)
                # Decode the whole result: a file header alone does not prove playability.
                run_tool([tools["ffmpeg"], "-v", "error", "-i", str(output), "-f", "null", "-"])
            with self.assertRaises((RuntimeError, FileExistsError)):
                export_stems(stems, result, "MP3", tools)
            with self.assertRaisesRegex(ValueError, "仅支持 MP3"):
                export_stems(stems, result, "WAV", tools)
            self.assertEqual(original_hashes, {k: hashlib.sha256(v.read_bytes()).hexdigest() for k, v in stems.items()})

    def test_failed_mp3_keeps_wav(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            wave = folder / "source.wav"
            wave.write_bytes(b"this task's original PCM")
            with patch("separate.verify_output"), patch("separate.encode_mp3", side_effect=RuntimeError("encoder failed")):
                with self.assertRaises(RuntimeError):
                    export_stems({"Vocals": wave, "Instrumental": wave}, folder, "MP3", {"ffmpeg": "ffmpeg"})
            self.assertEqual(wave.read_bytes(), b"this task's original PCM")
