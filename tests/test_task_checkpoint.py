import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf
from filelock import FileLock

from separate import separate_audio
from separation_recovery import choose_work
from task_checkpoint import read_json


class FreshTaskTests(unittest.TestCase):
    def test_identical_input_never_discovers_or_locks_old_work(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / 'work_failed'
            old.mkdir()
            broken = old / 'task.json'
            broken.write_bytes(b'not valid json')
            with FileLock(str(root / 'work_failed.lock'), timeout=0), \
                    patch.object(Path, 'glob', side_effect=AssertionError('历史目录被扫描')), \
                    patch('task_checkpoint.read_json', side_effect=AssertionError('旧清单被读取')):
                first, state = choose_work(root, {'same': True}, old, lambda _: None)
                second, other = choose_work(root, {'same': True}, None, lambda _: None)
            self.assertNotEqual(first, second)
            self.assertRegex(first.name, r'^work_[0-9a-f]{32}$')
            self.assertEqual(state['task_id'], first.name)
            self.assertEqual(other['restart_policy'], 'always_new')
            self.assertEqual(broken.read_bytes(), b'not valid json')

    def run_fixture(self, cleanup_error=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / 'source.wav'
            models = root / 'models'
            models.mkdir()
            sf.write(audio, np.full((44100 * 2, 2), .1), 44100)
            calls, stages, stats = [], [], []

            def base(Separator, source, work, *args):
                calls.append(work)
                result = {}
                for label in ('Vocals', 'Instrumental'):
                    result[label] = work / f'{label}.wav'
                    shutil.copy2(source, result[label])
                return result

            def bve(Separator, source, work, model_dir, device, stage):
                work.mkdir(exist_ok=True)
                return {label: Path(shutil.copy2(source, work / (label + '.wav')))
                        for label in ('LeadVocals', 'BackingVocals')}

            common = dict(device='cpu', split_backing=True, progress_callback=stages.append,
                          metrics_callback=lambda value: stats.append(dict(value)))
            with patch('separate.DATA_DIR', root), patch('separate.MODEL_DIR', models), \
                    patch('separate._base_stems', base):
                with patch('vocal_split.split_vocals', side_effect=RuntimeError('模拟 CUDA 推理失败')):
                    with self.assertRaisesRegex(RuntimeError, '模拟 CUDA 推理失败'):
                        separate_audio(audio, root / 'results', **common)
                old = next((root / 'cache/separation').glob('work_*'))
                self.assertEqual(read_json(old / 'task.json')['status'], 'failed')
                (old / 'task.json').write_bytes(b'corrupt old task')
                saved = next(old.glob('base_*/Vocals.wav'))
                saved.write_bytes(b'truncated historical audio')
                with patch('vocal_split.split_vocals', bve):
                    if cleanup_error:
                        with patch('separate.shutil.rmtree', side_effect=PermissionError('测试文件占用')):
                            outputs = separate_audio(audio, root / 'results', **common)
                        work = calls[-1].parent
                        self.assertEqual(read_json(work / 'task.json')['status'], 'complete')
                        self.assertTrue(all(p.exists() for p in outputs))
                        self.assertTrue(any('暂未清理' in s for s in stages))
                    else:
                        first = separate_audio(audio, root / 'results', resume_work=old,
                                               legacy_work=old, legacy_log=root/'missing.log', **common)
                        second = separate_audio(audio, root / 'results', **common)
                        self.assertNotEqual(first[0].parent, second[0].parent)
                        self.assertTrue(all(sf.info(p).frames == 88200 for p in (*first, *second)))
                        self.assertEqual(len(calls), 3)
                        self.assertEqual(len({w.parent for w in calls}), 3)
                        self.assertEqual(len({s['task_id'] for s in stats}), 2)
                        self.assertTrue(all(not s['resumed_base'] for s in stats))
                        self.assertEqual(list((root/'cache/separation').glob('work_*')), [old])
                self.assertEqual((old/'task.json').read_bytes(), b'corrupt old task')
                self.assertEqual(saved.read_bytes(), b'truncated historical audio')
                self.assertFalse(list((root/'cache/separation').glob('*.lock')))

    def test_failure_retry_and_repeated_song_each_recompute_and_cleanup(self):
        self.run_fixture()

    def test_cleanup_failure_preserves_successful_outputs_and_reports_reason(self):
        self.run_fixture(cleanup_error=True)


if __name__ == '__main__':
    unittest.main()
