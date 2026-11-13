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

    def test_decoded_input_is_checkpointed_and_reused_before_models(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio, checkpoint = self.fixture(root)
            source, timeline, stems = task_input(audio, root, self.attempt(root, 'attempt_first'),
                                                checkpoint, configure_ffmpeg(), lambda _: None)
            self.assertEqual(timeline, (44100, 44100, 2))
            self.assertIsNone(stems)
            self.assertEqual(sf.info(source).subtype, 'FLOAT')
            self.assertEqual(checkpoint['status'], 'input_complete')
            with patch('mix_tracks.song_timeline', side_effect=AssertionError('重复解码')):
                recovered, recovered_timeline, _ = task_input(audio, root, self.attempt(root, 'attempt_next'),
                    checkpoint, configure_ffmpeg(), lambda _: None)
            self.assertEqual(recovered, source)
            self.assertEqual(recovered_timeline, timeline)

    def test_completed_base_uses_saved_timeline_even_if_decoded_copy_is_damaged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio, checkpoint = self.fixture(root)
            source, timeline, _ = task_input(audio, root, self.attempt(root, 'attempt_first'),
                                            checkpoint, configure_ffmpeg(), lambda _: None)
            checkpoint['base'] = {}
            for label in ('Vocals', 'Instrumental'):
                target = root / (label + '.wav')
                shutil.copy2(source, target)
                checkpoint['base'][label] = wav_record(target, root)
            source.write_bytes(b'partial retained')
            with patch('mix_tracks.song_timeline', side_effect=AssertionError('不应重复解码原曲')):
                recovered, actual, stems = task_input(audio, root, self.attempt(root, 'attempt_resume'),
                    checkpoint, configure_ffmpeg(), lambda _: None)
            self.assertIsNone(recovered)
            self.assertEqual(actual, timeline)
            self.assertEqual(set(stems), {'Vocals', 'Instrumental'})
            self.assertEqual(source.read_bytes(), b'partial retained')

    def test_792_checkpoint_can_reuse_its_complete_reference_but_not_a_partial_one(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio, checkpoint = self.fixture(root)
            checkpoint['base'] = {}
            for label in ('Vocals', 'Instrumental'):
                target = root / (label + '.wav')
                shutil.copy2(audio, target)
                checkpoint['base'][label] = wav_record(target, root)
            partial = self.attempt(root, 'attempt_failed') / 'timeline.wav'
            partial.write_bytes(b'RIFF incomplete')
            reference = self.attempt(root, 'attempt_ok') / 'timeline.wav'
            shutil.copy2(audio, reference)
            with patch('mix_tracks.song_timeline', side_effect=AssertionError('不应再次解码')):
                _, timeline, stems = task_input(audio, root, self.attempt(root, 'attempt_resume'),
                    checkpoint, configure_ffmpeg(), lambda _: None)
            self.assertEqual(timeline, (44100,44100,2))
            self.assertEqual(checkpoint['decoded_input']['path'], 'attempt_ok/timeline.wav')
            self.assertEqual(partial.read_bytes(), b'RIFF incomplete')

    def test_bad_pcm_is_redecoded_without_overwriting_the_failed_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio, checkpoint = self.fixture(root)
            source, _, _ = task_input(audio, root, self.attempt(root, 'attempt_first'),
                                      checkpoint, configure_ffmpeg(), lambda _: None)
            source.write_bytes(source.read_bytes()[:-20])
            broken = source.read_bytes()
            recovered, _, _ = task_input(audio, root, self.attempt(root, 'attempt_repair'),
                checkpoint, configure_ffmpeg(), lambda _: None)
            self.assertNotEqual(source, recovered)
            self.assertEqual(source.read_bytes(), broken)

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

    def test_confirmed_legacy_timeline_must_bind_current_input_and_both_stem_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio, checkpoint = self.fixture(root)
            checkpoint['base'] = {}
            for label in ('Vocals', 'Instrumental'):
                target = root / (label + '.wav')
                shutil.copy2(audio, target)
                checkpoint['base'][label] = wav_record(target, root)
            checkpoint['timeline'] = [44100,44100,2]
            checkpoint['timeline_source'] = dict(kind='confirmed_existing_stems',
                input_sha256=checkpoint['identity']['audio_sha256'],
                base_sha256={k:v['sha256'] for k,v in checkpoint['base'].items()})
            with patch('mix_tracks.song_timeline', side_effect=AssertionError('不应解码坏原曲')):
                _, timeline, stems = task_input(audio, root, self.attempt(root, 'attempt_ok'),
                    checkpoint, configure_ffmpeg(), lambda _: None)
                self.assertEqual(timeline, (44100,44100,2))
                self.assertEqual(set(stems), {'Vocals','Instrumental'})
                checkpoint['timeline_source']['base_sha256']['Vocals'] = 'wrong'
                with self.assertRaisesRegex(ValueError, '时间轴与音轨文件不匹配'):
                    task_input(audio, root, self.attempt(root, 'attempt_wrong'),
                        checkpoint, configure_ffmpeg(), lambda _: None)
