import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from mix_export import render_mix, write_mix_wav
from mix_tracks import MIX_CEILING, mix_manifest
from separate import verify_output
from runtime_paths import configure_ffmpeg


class MixExportTests(unittest.TestCase):
    def make_mix(self, root, waveforms, rate):
        name = "音乐 & 测试"
        mix = root / name / "mix"
        mix.mkdir(parents=True)
        frames = len(next(iter(waveforms.values())))
        for label, wave in waveforms.items():
            sf.write(mix / f"{label}.wav", wave, rate, subtype="FLOAT")
        (mix / "timeline.json").write_text(
            json.dumps({"frames": frames, "rate": rate, "tracks": list(waveforms)}), encoding="utf-8"
        )
        return name

    def test_internal_mix_matches_preview_and_publishes_only_mp3(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            rate, frames = 48000, 72001
            t = np.arange(frames) / rate
            lead = .8 * np.cos(2 * np.pi * 307 * t)
            backing = .8 * np.cos(2 * np.pi * 430 * t)
            accompaniment = .8 * np.cos(2 * np.pi * 630 * t)
            name = self.make_mix(root, {
                "LeadVocals": lead, "BackingVocals": backing, "Instrumental": accompaniment,
            }, rate)
            preview = json.loads(mix_manifest(root, name))
            headroom = preview["headroom"]
            self.assertAlmostEqual(headroom, MIX_CEILING / 2.4)
            levels = {"LeadVocals": 100, "BackingVocals": 0, "Instrumental": 50}
            paths = {label: root / name / "mix" / f"{label}.wav" for label in levels}
            internal = root / "test-reference.wav"
            write_mix_wav(internal, paths, {k: v / 100 * .8 * headroom for k, v in levels.items()}, frames, rate, 1)
            output, actual_rate = sf.read(internal)
            self.assertEqual((len(output), actual_rate), (frames, rate))
            np.testing.assert_allclose(output[240:-240], (.8 * headroom * (lead + accompaniment / 2))[240:-240],
                                       atol=2e-7, rtol=0)
            self.assertEqual((output[0], output[-1]), (0, 0))
            first = render_mix(root, name, "MP3", levels, 80)
            second = render_mix(root, name, "MP3", dict.fromkeys(levels, 100), 100)
            self.assertNotEqual(first, second)
            self.assertTrue(first.is_file())
            self.assertLess(np.abs(sf.read(second)[0]).max(), 1)
            self.assertEqual(set(first.parent.iterdir()), {first, second})
            actual, _ = sf.read(first)
            self.assertLess(np.linalg.norm(actual - output) / np.linalg.norm(output), .03)
            with self.assertRaises(ValueError):
                render_mix(root, name, "MP3", {**levels, "LeadVocals": float("nan")}, 100)
            with self.assertRaisesRegex(ValueError, "仅支持 MP3"):
                render_mix(root, name, "WAV", levels, 100)

    def test_mp3_keeps_duration_and_supports_nonstandard_source_rate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            rate = 22050
            samples = .3 * np.sin(2 * np.pi * 300 * np.arange(rate + 3) / rate)
            name = self.make_mix(root, {"Vocals": samples, "Instrumental": samples}, rate)
            result = render_mix(root, name, "MP3", {"Vocals": 0, "Instrumental": 50}, 100)
            self.assertEqual(verify_output(result, "MP3", configure_ffmpeg())["bit_rate"], "320000")
            decoded, decoded_rate = sf.read(result)
            self.assertEqual(decoded_rate, 44100)
            self.assertAlmostEqual(len(decoded) / decoded_rate, len(samples) / rate, delta=1 / decoded_rate)
            self.assertGreater(np.abs(decoded).max(), .12)
            self.assertLess(np.abs(decoded).max(), .17)
