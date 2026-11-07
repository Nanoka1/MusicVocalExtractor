"""混音 WAV 保持原曲的帧数、采样率、声道数与起始时间。"""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from mix_tracks import mix_manifest, save_mix, saved_mixes
from runtime_paths import configure_ffmpeg


class MixTrackTests(unittest.TestCase):
    def test_aligned_output_can_be_loaded_again(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / "original.wav"
            sf.write(audio, np.zeros(4800), 48000)
            short = root / "short.wav"
            long = root / "long.wav"
            # 同一个脉冲位于 10 ms，两轨的尾部长度不同。
            for path, frames in [(short, 2000), (long, 5000)]:
                samples = np.zeros((frames, 2))
                samples[441] = 0.25
                sf.write(path, samples, 44100)
            name = "混音 # & +"
            result = root / name
            result.mkdir()
            save_mix(audio, {"Vocals": short, "Instrumental": long}, result, root, configure_ffmpeg())

            self.assertEqual(saved_mixes(root), [name])
            manifest = json.loads(mix_manifest(root, name))
            self.assertEqual((manifest["title"], manifest["duration"]), (name, 0.1))
            self.assertEqual([track["id"] for track in manifest["tracks"]], ["Vocals", "Instrumental"])
            self.assertIn("%23%20%26%20%2B", manifest["tracks"][0]["url"])
            for track in manifest["tracks"]:
                waveform, rate = sf.read(result / "mix" / f"{track['id']}.wav")
                self.assertEqual((rate, waveform.shape, np.argmax(waveform)), (48000, (4800,), 480))
            with self.assertRaises(ValueError):
                mix_manifest(root, "../" + name)
            (result / "mix" / "Vocals.wav").unlink()
            with self.assertRaisesRegex(ValueError, "找不到混音音轨"):
                mix_manifest(root, name)
