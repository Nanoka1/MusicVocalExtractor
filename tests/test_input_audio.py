import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf

from input_audio import task_input
from task_checkpoint import digest, wav_record
from runtime_paths import configure_ffmpeg


class InputCheckpointTests(unittest.TestCase):
    def test_wav_extensible_pcm32_is_a_valid_complete_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / 'valid-32bit.wav'
            sf.write(audio, np.full((44100, 2), .25), 44100, format='WAVEX', subtype='PCM_32')
            self.assertEqual(sf.info(audio).format, 'WAVEX')
            self.assertEqual(wav_record(audio, root)['spec'], [44100,44100,2])

    def fixture(self, root):
        audio = root / 'source.wav'
        sf.write(audio, np.full((44100, 2), .125, dtype='float32'), 44100, subtype='FLOAT')
        checkpoint = dict(identity=dict(audio_sha256=digest(audio)))
        return audio, checkpoint

    def attempt(self, root, name):
        folder = root / name
        folder.mkdir()
        return folder

    def test_every_attempt_decodes_again_even_with_old_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio, checkpoint = self.fixture(root)
            source, timeline, stems = task_input(audio, root, self.attempt(root, 'attempt_first'),
                                                checkpoint, configure_ffmpeg(), lambda _: None)
            original = source.read_bytes()
            checkpoint['base'] = {'Vocals': {'path': '../missing.wav'}}
            checkpoint['decoded_input']['sha256'] = 'damaged old record'
            with patch('task_checkpoint.checked_paths', side_effect=AssertionError('不应读取旧检查点')):
                fresh, second_timeline, stems = task_input(audio, root, self.attempt(root, 'attempt_next'),
                                                         checkpoint, configure_ffmpeg(), lambda _: None)
            self.assertNotEqual(source, fresh)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(timeline, second_timeline)
            self.assertEqual(sf.info(fresh).subtype, 'FLOAT')
            self.assertIsNone(stems)

    def test_source_decode_failure_never_becomes_input_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio, checkpoint = self.fixture(root)
            with patch('mix_tracks.song_timeline', side_effect=RuntimeError('Header missing')):
                with self.assertRaisesRegex(RuntimeError, '原始音频完整解码失败'):
                    task_input(audio, root, self.attempt(root, 'attempt_bad'),
                        checkpoint, configure_ffmpeg(), lambda _: None)
            self.assertNotIn('decoded_input', checkpoint)
            self.assertNotIn('base', checkpoint)

    def test_real_malformed_mp3_remains_an_error_and_partial_pcm_is_not_adopted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / 'broken.mp3'
            tools = configure_ffmpeg()
            subprocess.run([tools['ffmpeg'], '-nostdin', '-v', 'error', '-n', '-f', 'lavfi',
                '-i', 'sine=frequency=330:duration=4', '-ar', '44100', '-ac', '2',
                '-c:a', 'libmp3lame', '-b:a', '128k', str(audio)], check=True,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            data = bytearray(audio.read_bytes())
            middle = len(data)//2
            data[middle:middle+4096] = bytes(4096)
            audio.write_bytes(data)
            original_hash = digest(audio)
            checkpoint = dict(identity=dict(audio_sha256=original_hash))
            attempt = self.attempt(root, 'attempt_bad')
            with self.assertRaisesRegex(RuntimeError, '原始音频完整解码失败'):
                task_input(audio, root, attempt, checkpoint, tools, lambda _: None)
            self.assertNotIn('decoded_input', checkpoint)
            self.assertTrue((attempt/'timeline.wav').exists())
            self.assertEqual(digest(audio), original_hash)
