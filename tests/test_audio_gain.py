"""Real FFmpeg gain/limiter checks; no models or personal audio required."""
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf

from audio_gain import audio_peak, finish_gain_report, format_gain_report, validate_gain
from models import DEFAULT_MODEL
from runtime_paths import configure_ffmpeg
from separate import _separate_task, export_stems, run_tool


class GainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tools = configure_ffmpeg()

    def make_stems(self, folder, amplitude=.04, rate=44100, channels=2):
        work = folder / "work"
        work.mkdir()
        t = np.arange(rate) / rate
        stems = {}
        for label, frequency in (("Vocals", 440), ("Instrumental", 220)):
            mono = amplitude * np.sin(2 * np.pi * frequency * t)
            signal = mono if channels == 1 else np.column_stack((mono, mono * .7))
            stems[label] = work / (label + ".wav")
            sf.write(stems[label], signal, rate, subtype="FLOAT")
        return stems

    def test_gain_validation_and_cli_bounds(self):
        for value in (0, 3, 6, 12, "1.5"):
            self.assertEqual(validate_gain(value), float(value))
        for value in (-.1, 12.1, float("nan"), float("inf"), None, "oops"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_gain(value)
        script = Path(__file__).resolve().parents[1] / "separate.py"
        for flag in ("--vocal-gain-db", "--instrumental-gain-db"):
            result = subprocess.run([sys.executable, str(script), "missing.wav", flag, "13"], capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn(b"Traceback", result.stderr)

    def test_exact_zero_bypass_and_independent_gains(self):
        with tempfile.TemporaryDirectory(prefix="中文 增益 ") as temp:
            root = Path(temp)
            stems = self.make_stems(root)
            hashes = {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in stems.items()}
            for fmt in ("WAV", "MP3"):
                baseline = root / fmt
                baseline.mkdir()
                original = export_stems(stems, baseline, fmt, self.tools)
                if fmt == "WAV":
                    for label, path in zip(stems, original):
                        self.assertEqual(path.read_bytes(), stems[label].read_bytes())
                # Each active stem has a fresh work directory, as in real tasks.
                for vocal_db, inst_db in ((3, 0), (6, 0), (12, 0), (0, 3), (0, 6), (0, 12), (6, 12)):
                    with self.subTest(format=fmt, vocals=vocal_db, instrumental=inst_db):
                        case = root / f"{fmt}_{vocal_db}_{inst_db}"
                        case.mkdir()
                        current = self.make_stems(case)
                        # FLOAT WAV headers can contain a creation timestamp. Compare
                        # exports of identical files, not two separately written fixtures.
                        for label in current:
                            current[label].write_bytes(stems[label].read_bytes())
                        report = {}
                        outputs = export_stems(current, case, fmt, self.tools,
                                               vocal_gain_db=vocal_db, instrumental_gain_db=inst_db,
                                               gain_report=report)
                        for index, (label, gain_db) in enumerate((("Vocals", vocal_db), ("Instrumental", inst_db))):
                            if gain_db == 0:
                                self.assertEqual(outputs[index].read_bytes(), original[index].read_bytes())
                            else:
                                data, rate = sf.read(outputs[index], always_2d=True)
                                before, _ = sf.read(original[index], always_2d=True)
                                # Ignore boundary resampler transients and MP3 end padding.
                                measured = np.sqrt(np.mean(data[2000:-2000] ** 2) / np.mean(before[2000:-2000] ** 2))
                                self.assertAlmostEqual(measured, 10 ** (gain_db / 20), delta=.005)
                                self.assertEqual(rate, 44100)
                                self.assertEqual(data.shape, before.shape)
                                self.assertLess(audio_peak(outputs[index])["peak"], 1)
                                self.assertLess(report[label]["peak_shortfall_db"], .05)
                        self.assertEqual(len(list(case.glob("*." + fmt.lower()))), 2)
            self.assertEqual(hashes, {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in stems.items()})

    def test_hot_signal_limited_without_flat_clipping_and_stereo_shift(self):
        for rate, channels in ((44100, 2), (48000, 1)):
            for fmt in ("WAV", "MP3"):
                with self.subTest(rate=rate, channels=channels, format=fmt), tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    stems = self.make_stems(root, amplitude=.8, rate=rate, channels=channels)
                    report = {}
                    outputs = export_stems(stems, root, fmt, self.tools, vocal_gain_db=12,
                                           instrumental_gain_db=12, gain_report=report)
                    for label, path in zip(stems, outputs):
                        data, actual_rate = sf.read(path, always_2d=True)
                        self.assertEqual(actual_rate, rate)
                        self.assertEqual(data.shape, (rate, channels))
                        self.assertTrue(np.isfinite(data).all())
                        self.assertLess(np.max(np.abs(data)), 1)
                        self.assertGreater(np.max(np.abs(data)), .7)
                        self.assertGreater(report[label]["peak_shortfall_db"], 9)
                        self.assertIn("+12.0 dB", format_gain_report(report[label]))
                        # Limiter follows peaks instead of flattening each clipped sample.
                        self.assertLess(np.mean(np.abs(np.diff(data[2000:-2000, 0])) < 1e-7), .01)
                        if channels == 2:
                            np.testing.assert_allclose(data[2000:-2000, 1], data[2000:-2000, 0] * .7, atol=.0003)

    def test_silence_and_invalid_samples(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stems = self.make_stems(root, amplitude=0)
            report = {}
            outputs = export_stems(stems, root, "MP3", self.tools, vocal_gain_db=12, instrumental_gain_db=6,
                                   gain_report=report)
            self.assertEqual(audio_peak(outputs[0])["peak"], 0)
            self.assertIn("静音", format_gain_report(report["Vocals"]))
            bad = root / "nan.wav"
            sf.write(bad, np.array([0, np.nan]), 44100, subtype="FLOAT")
            with self.assertRaisesRegex(RuntimeError, "NaN"):
                audio_peak(bad)
            hot = root / "hot.wav"
            sf.write(hot, np.array([0, 1.01]), 44100, subtype="FLOAT")
            with self.assertRaisesRegex(RuntimeError, "满幅"):
                finish_gain_report({"factor": 1, "input_peak": 1}, hot)

    def test_gain_failure_preserves_originals_and_success_cleans_work(self):
        import torch
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stems = self.make_stems(root)
            source = stems["Vocals"]
            results = root / "results"
            results.mkdir()

            class Engine:
                def __init__(self, output_dir, **kwargs):
                    self.folder = Path(output_dir)

                def separate(self, audio, custom_output_names):
                    for label in custom_output_names:
                        self_path = self.folder / (label + ".wav")
                        self_path.write_bytes(source.read_bytes())
                    return ["Instrumental.wav", "Vocals.wav"]

            for fails in (False, True):
                work = root / str(fails)
                work.mkdir()
                stages = []

                def tool(command):
                    if fails and "-af" in command:
                        raise RuntimeError("limiter failed")
                    return run_tool(command)

                with patch("separate.prepare_model"), patch("separate.validate_loaded_device"), patch("separate.run_tool", side_effect=tool):
                    args = (Engine, source, results, work, DEFAULT_MODEL, "MP3", self.tools, stages.append,
                            "中文 歌曲.wav", True, torch)
                    if fails:
                        with self.assertRaisesRegex(RuntimeError, "limiter failed"):
                            _separate_task(*args, vocal_gain_db=6, instrumental_gain_db=12)
                        self.assertTrue((work / "Vocals.wav").is_file())
                        self.assertTrue((work / "Instrumental.wav").is_file())
                        self.assertNotIn("分离完成", stages)
                    else:
                        outputs = _separate_task(*args, vocal_gain_db=6, instrumental_gain_db=12)
                        self.assertFalse(work.exists())
                        self.assertEqual(set(outputs[0].parent.iterdir()), set(outputs))
