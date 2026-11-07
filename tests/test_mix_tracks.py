"""混音 WAV 保持原曲的帧数、采样率、声道数与起始时间。"""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from mix_tracks import align_track, mix_manifest, save_mix, saved_mixes
from runtime_paths import configure_ffmpeg
from separate import encode_mp3


class MixTrackTests(unittest.TestCase):
    def test_aligned_output_can_be_loaded_again(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
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
            tools = configure_ffmpeg()
            timeline = (4800, 48000, 1)
            stems = {}
            for label, source in {"Vocals": short, "Instrumental": long}.items():
                aligned = align_track(source, root / f"{label}.wav", timeline, tools)
                waveform, rate = sf.read(aligned)
                self.assertEqual((rate, waveform.shape, np.argmax(waveform)), (48000, (4800,), 480))
                stems[label] = result / f"{name}_{label}.mp3"
                encode_mp3(aligned, stems[label], tools)
            save_mix(stems, result, timeline)

            self.assertEqual(saved_mixes(root), [name])
            # 旧乐器分离任务留在磁盘，当前播放器只打开两种人声模式。
            retired = root / "old" / "mix"
            retired.mkdir(parents=True)
            (retired / "timeline.json").write_text(json.dumps({
                "frames": 4800, "rate": 48000,
                "tracks": ["LeadVocals", "BackingVocals", "Drums", "Bass", "Other"],
            }), encoding="utf-8")
            self.assertEqual(saved_mixes(root), [name])
            with self.assertRaises(ValueError):
                mix_manifest(root, "old")
            self.assertTrue((retired / "timeline.json").is_file())
            manifest = json.loads(mix_manifest(root, name))
            self.assertEqual((manifest["title"], manifest["duration"]), (name, 0.1))
            self.assertEqual([track["id"] for track in manifest["tracks"]], ["Vocals", "Instrumental"])
            self.assertIn("%23%20%26%20%2B", manifest["tracks"][0]["url"])
            for track in manifest["tracks"]:
                self.assertTrue(track["url"].endswith(f"_{track['id']}.mp3"))
                waveform, rate = sf.read(stems[track["id"]])
                self.assertEqual((rate, waveform.shape), (48000, (4800,)))
                self.assertAlmostEqual(int(np.argmax(waveform)), 480, delta=2)
            self.assertFalse(list(result.rglob("*.wav")))
            with self.assertRaises(ValueError):
                mix_manifest(root, "../" + name)
            stems["Vocals"].unlink()
            with self.assertRaisesRegex(ValueError, "找不到混音音轨"):
                mix_manifest(root, name)
