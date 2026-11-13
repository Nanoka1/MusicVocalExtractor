import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf

from models import DEFAULT_MODEL
from separate import separate_audio
from task_checkpoint import identity_matches, read_json


class TaskRecoveryTests(unittest.TestCase):
    def test_first_bve_download_does_not_invalidate_finished_base_stage(self):
        from separation_recovery import choose_work
        from task_checkpoint import atomic_json
        from vocal_split import BVE_MODEL
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            work = root / 'work_download'
            work.mkdir()
            before = dict(models={BVE_MODEL: None, DEFAULT_MODEL: 'verified-base'}, settings={})
            current = dict(models={BVE_MODEL: 'downloaded-bve', DEFAULT_MODEL: 'verified-base'}, settings={})
            atomic_json(work / 'task.json', dict(identity=before, base={'Vocals': 'record'}))
            found, _ = choose_work(root, current, None, lambda _: None)
            self.assertEqual(found, work)
            self.assertFalse(identity_matches(before, current))
            changed = dict(current, models={BVE_MODEL: 'downloaded-bve', DEFAULT_MODEL: 'changed-base'})
            with self.assertRaisesRegex(ValueError, '不匹配'):
                choose_work(root, changed, work, lambda _: None)

    def test_stage_one_survives_failure_auto_resume_and_input_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / 'source.wav'
            models = root / 'models'
            models.mkdir()
            sf.write(audio, np.full((44100 * 4, 2), .1), 44100)
            calls = []

            def base(Separator, source, work, *args):
                calls.append(source)
                result = {}
                for label in ('Vocals', 'Instrumental'):
                    result[label] = work / f'{label}.wav'
                    shutil.copy2(source, result[label])
                return result

            def bve(Separator, source, work, model_dir, device, stage):
                work.mkdir(exist_ok=True)
                result = {}
                for label in ('LeadVocals', 'BackingVocals'):
                    result[label] = work / f'{label}.wav'
                    shutil.copy2(source, result[label])
                return result

            with patch('separate.DATA_DIR', root), patch('separate.MODEL_DIR', models), \
                    patch('separate._base_stems', base), patch('vocal_split.split_vocals', side_effect=RuntimeError('中断')):
                with self.assertRaisesRegex(RuntimeError, '中断'):
                    separate_audio(audio, root / 'results', device='cpu', split_backing=True)
            work = next((root / 'cache/separation').glob('work_*'))
            state = read_json(work / 'task.json')
            self.assertEqual(set(state['base']), {'Vocals', 'Instrumental'})
            self.assertEqual(state['status'], 'failed')
            stages = []
            with patch('separate.DATA_DIR', root), patch('separate.MODEL_DIR', models), \
                    patch('separate._base_stems', base), patch('vocal_split.split_vocals', bve):
                # Explicit resume rejects changed input before model execution.
                other = root / 'different.wav'
                sf.write(other, np.full((44100 * 4, 2), .2), 44100)
                with self.assertRaisesRegex(ValueError, '不匹配'):
                    separate_audio(other, root / 'results', device='cpu', split_backing=True, resume_work=work)
                result = separate_audio(audio, root / 'results', device='cpu', split_backing=True,
                                        progress_callback=stages.append)
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(result), 3)
            self.assertTrue(any('跳过基础模型' in s for s in stages))
            self.assertTrue(all(sf.info(path).frames == 44100 * 4 for path in result))
            self.assertFalse(work.exists())


if __name__ == '__main__':
    unittest.main()
