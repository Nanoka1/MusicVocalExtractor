"""Progress must remain live while inference is still running."""
import io
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import exe_entry


@unittest.skipUnless(sys.platform == "win32", "Windows 控制台测试")
class ConsoleProgressTests(unittest.TestCase):
    def test_frozen_gui_opens_once_and_mirrors_tqdm_to_log(self):
        console, log = io.StringIO(), io.StringIO()
        kernel = Mock()
        kernel.GetConsoleWindow.side_effect = [0, 123]
        with patch.object(exe_entry.sys, "platform", "win32"), \
                patch.object(exe_entry.sys, "frozen", True, create=True), \
                patch.object(exe_entry.sys, "stdout", log), patch.object(exe_entry.sys, "stderr", log), \
                patch("ctypes.WinDLL", return_value=kernel), patch("builtins.open", return_value=console):
            exe_entry.show_progress_console()
            from tqdm import tqdm

            for _ in tqdm(range(2), file=exe_entry.sys.stderr, mininterval=0):
                pass
            print("正在导出音频：MP3 320 kbps", flush=True)
            exe_entry.show_progress_console()
        kernel.AllocConsole.assert_called_once()
        self.assertIn("100%", console.getvalue())
        self.assertIn("正在导出音频", console.getvalue())
        self.assertEqual(console.getvalue(), log.getvalue())

    def test_console_allocation_failure_keeps_existing_streams(self):
        kernel = Mock()
        kernel.GetConsoleWindow.return_value = 0
        kernel.AllocConsole.return_value = 0
        stream = io.StringIO()
        with patch.object(exe_entry.sys, "platform", "win32"), \
                patch.object(exe_entry.sys, "frozen", True, create=True), \
                patch.object(exe_entry.sys, "stdout", stream), \
                patch("ctypes.WinDLL", return_value=kernel), self.assertLogs(level="WARNING"):
            exe_entry.show_progress_console()
            self.assertIs(exe_entry.sys.stdout, stream)

    def test_source_run_does_not_allocate_console(self):
        with patch.object(exe_entry.sys, "frozen", False, create=True), patch("ctypes.WinDLL") as loader:
            exe_entry.show_progress_console()
        loader.assert_not_called()


class StageProgressTests(unittest.TestCase):
    def test_real_callback_reports_validation_stage(self):
        from separate import separate_audio

        stages = []
        with self.assertRaises(ValueError):
            separate_audio(Path(__file__).with_name("missing-progress-fixture.wav"), progress_callback=stages.append)
        self.assertEqual(stages, ["正在检查音频文件"])

    def test_worker_delivers_stage_before_finishing_and_reports_error(self):
        from app import separation_updates

        release, worker_finished = threading.Event(), threading.Event()
        progress, console = Mock(), Mock()
        caller = threading.get_ident()
        worker_threads = []

        def separate(*args, progress_callback, **kwargs):
            worker_threads.append(threading.get_ident())
            progress_callback("正在进行人声分离")
            try:
                if not release.wait(5):
                    raise TimeoutError("测试未释放推理线程")
                raise RuntimeError("测试错误")
            finally:
                worker_finished.set()

        with patch("app.separate_audio", separate), patch("exe_entry.show_progress_console", console), \
                patch("builtins.print") as printed:
            updates = separation_updates("fixture.wav", "test-model", "MP3", "balanced", "cuda", 0, 0, progress)
            try:
                self.assertIn("正在检查", next(updates)[1])
                self.assertIn("正在进行人声分离", next(updates)[1])
                self.assertFalse(worker_finished.is_set())
                self.assertNotEqual(worker_threads, [caller])
                console.assert_called_once()
                progress.assert_called_once_with(None, desc="正在进行人声分离")
                printed.assert_any_call("正在进行人声分离", flush=True)
            finally:
                release.set()
            with self.assertLogs(level="ERROR"):
                self.assertIn("分离失败：测试错误", next(updates)[1])
            self.assertEqual(list(updates), [])
            self.assertTrue(worker_finished.is_set())


if __name__ == "__main__":
    unittest.main()
