"""界面输入检查，以及可选的 HTTP 上传、分离和下载测试。"""

import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(importlib.util.find_spec("gradio"), "未安装可选界面依赖")
class InterfaceTests(unittest.TestCase):
    def test_upload_metadata_survives_cached_filename(self):
        from app import UploadedAudio, create_app
        from gradio.data_classes import FileData
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "random_cache.mp3"
            path.touch()
            upload = UploadedAudio(type="filepath")
            value = upload.preprocess(FileData(path=str(path), orig_name="原始 中文 & 歌曲.mp3"))
            self.assertEqual(str(value), str(path))
            self.assertEqual(value.original_name, "原始 中文 & 歌曲.mp3")
        self.assertIsNotNone(create_app().get_config_file())

    def test_no_file_clears_results(self):
        from app import extract_vocals
        updates = list(extract_vocals(None))
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0][:2], (None, None))
        self.assertIn("请先选择", updates[0][2])

    def test_error_clears_previous_results(self):
        from app import extract_vocals
        with tempfile.TemporaryDirectory() as folder:
            wrong_file = Path(folder) / "notes.txt"
            wrong_file.write_text("not audio")
            updates = list(extract_vocals(str(wrong_file)))
        self.assertEqual(updates[0][:2], (None, None))
        self.assertEqual(updates[-1][:2], (None, None))
        self.assertIn("分离失败", updates[-1][2])


@unittest.skipUnless(os.environ.get("RUN_UI_TESTS") == "1", "需要显式启用真实界面测试")
class InterfaceIntegrationTests(unittest.TestCase):
    def test_upload_separate_download(self):
        import numpy as np
        import soundfile as sf
        from gradio_client import Client, handle_file
        from app import OUTPUT_DIR, create_app

        OUTPUT_DIR.mkdir(exist_ok=True)
        demo = create_app().queue()
        try:
            _, address, _ = demo.launch(
                server_name="127.0.0.1", server_port=None,
                prevent_thread_lock=True, inbrowser=False, share=False,
                allowed_paths=[str(OUTPUT_DIR)],
            )
            with tempfile.TemporaryDirectory() as folder:
                audio = Path(folder) / "sample.mp3"
                subprocess.run([
                    "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=2", "-ar", "44100", "-ac", "2", str(audio),
                ], check=True)
                client = Client(address, download_files=folder, verbose=False)
                empty = client.predict(None, api_name="/separate")
                self.assertEqual(empty[:2], (None, None))
                vocals, instrumental, status, vocals_preview, instrumental_preview = client.predict(
                    handle_file(str(audio)), output_format="WAV", api_name="/separate")
                self.assertIn("分离完成", status)
                for path in (vocals, instrumental):
                    self.assertTrue(Path(path).is_file())
                    data, rate = sf.read(path)
                    self.assertEqual(rate, 44100)
                    self.assertAlmostEqual(len(data) / rate, 2.0, delta=0.15)
                    self.assertTrue(np.isfinite(data).all())
                    self.assertGreater(np.max(np.abs(data)), 0)
        finally:
            demo.close()


if __name__ == "__main__":
    unittest.main()
