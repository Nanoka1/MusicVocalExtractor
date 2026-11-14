import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import soundfile as sf

from vocal_split import BVE_MODEL, VOCAL_LABELS, split_vocals
from task_checkpoint import read_json, wav_record


class Engine:
    calls = []
    fail_at = None

    def __init__(self, output_dir, **kwargs):
        self.output_dir = output_dir
        self.model_instance = SimpleNamespace(is_bv_model=True, primary_stem_name='Vocals',
            secondary_stem_name='Instrumental', model_params=SimpleNamespace(param={'band': {4: {'hl': 480}}}),
            inference_vr=lambda x: x, spec_to_wav=lambda x: x, output_dir=output_dir)

    def separate(self, audio, custom_output_names):
        self.calls.append(audio)
        if len(self.calls) == self.fail_at:
            raise SystemExit('模拟进程中断')
        data, rate = sf.read(audio, dtype='float32', always_2d=True)
        for generic, value in [('Vocals', data * .25), ('Instrumental', data * .75)]:
            self.model_instance.final_process(custom_output_names[generic] + '.wav', value, generic)
        return ['BackingVocals.wav', 'LeadVocals.wav']


class VocalSplitTests(unittest.TestCase):
    def test_bve_output_labels_follow_metadata_even_when_order_is_reversed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / "vocals.wav"
            sf.write(audio, np.full((44100 * 4, 2), .2), 44100, subtype='FLOAT')
            Engine.calls, Engine.fail_at = [], None
            with patch("vocal_split.prepare_model") as prepare, patch("vocal_split.validate_loaded_device") as validate:
                stems = split_vocals(Engine, audio, root / "bve", root / "models",
                                    "cpu", lambda _: None)
            prepare.assert_called_once()
            self.assertEqual(prepare.call_args.args[1], BVE_MODEL)
            self.assertEqual(prepare.call_args.kwargs, {"arch": "VR"})
            self.assertEqual(len(Engine.calls), 1)
            validate.assert_called_once()
            self.assertEqual(stems["LeadVocals"].name, "LeadVocals.wav")
            self.assertEqual(stems["BackingVocals"].name, "BackingVocals.wav")
            for label, value in [('LeadVocals', .15), ('BackingVocals', .05)]:
                actual, _ = sf.read(stems[label])
                self.assertEqual(actual.shape, (44100 * 4, 2))
                np.testing.assert_allclose(actual, value, atol=2e-7)

    def test_failure_and_repeated_calls_always_process_every_chunk(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio, work = root / 'vocals.wav', root / 'bve'
            t = np.arange(44100 * 14) / 44100
            data = np.column_stack((np.sin(t * 2200), np.cos(t * 1700))).astype('float32') * .2
            # Impulses at both crossfade boundaries catch missing/duplicated samples.
            data[44100 * 6] = .6
            data[44100 * 12] = -.6
            sf.write(audio, data, 44100, subtype='FLOAT')
            Engine.calls, Engine.fail_at = [], 2
            def run(stages, seconds=6):
                with patch('vocal_split.prepare_model'), patch('vocal_split.validate_loaded_device'):
                    return split_vocals(Engine, audio, work, root / 'models', 'cpu', stages.append,
                                        chunk_seconds=seconds)
            with self.assertRaises(SystemExit):
                run([])
            first_run = next(work.glob('run_*'))
            state = read_json(first_run / 'chunks.json')
            self.assertEqual(list(state['completed']), ['0'])
            saved = first_run / state['completed']['0']['stems']['LeadVocals']['path']
            original = saved.read_bytes()
            Engine.calls, Engine.fail_at = [], None
            stages = []
            stems = run(stages)
            self.assertEqual(len(Engine.calls), 3)
            self.assertFalse(any('跳过' in s or '恢复校验' in s for s in stages))
            self.assertEqual(saved.read_bytes(), original)
            for label, multiplier in [('LeadVocals', .75), ('BackingVocals', .25)]:
                actual, _ = sf.read(stems[label], dtype='float32')
                np.testing.assert_allclose(actual, data * multiplier, atol=3e-7)
                wav_record(stems[label], work, [len(data), 44100, 2])
            saved.write_bytes(original[:-100])
            Engine.calls = []
            run([])
            self.assertEqual(len(Engine.calls), 3)
            self.assertEqual(saved.read_bytes(), original[:-100])
            Engine.calls = []
            run([], seconds=7)
            self.assertEqual(len(Engine.calls), 2)
            self.assertEqual(len(list(work.glob('run_*'))), 4)

    def test_truncated_and_nonfinite_wav_are_not_checkpoints(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'bad.wav'
            sf.write(path, np.full((100, 2), np.nan), 44100, subtype='FLOAT')
            with self.assertRaisesRegex(ValueError, 'NaN'):
                wav_record(path, root)
            sf.write(path, np.zeros((100, 2)), 44100, subtype='PCM_16')
            path.write_bytes(path.read_bytes()[:-16])
            with self.assertRaisesRegex(ValueError, '不完整'):
                wav_record(path, root)
