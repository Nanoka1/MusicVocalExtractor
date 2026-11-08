"""Download/cache failure tests use synthetic bytes, not fake production weights."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from models import ROFORMER_MODEL, check_model
from separate import prepare_model


class ModelCacheTests(unittest.TestCase):
    def test_roformer_official_registration_and_checksums(self):
        import json
        from importlib.resources import files
        package = files("audio_separator")
        models = json.loads(package.joinpath("models.json").read_text())
        self.assertEqual(check_model(ROFORMER_MODEL), "MDXC")
        self.assertIn({ROFORMER_MODEL: "vocals_mel_band_roformer.yaml"}, models["roformer_download_list"].values())
        hashes = json.loads(package.joinpath("model-checksums.json").read_text())["sha256"]
        for name in (ROFORMER_MODEL, "vocals_mel_band_roformer.yaml"):
            self.assertRegex(hashes[name], r"^[a-f0-9]{64}$")

    def test_first_download_cache_reuse_and_failures(self):
        names = (ROFORMER_MODEL, "vocals_mel_band_roformer.yaml")
        payload = b"unit test fixture, never loaded as a model"

        class Engine:
            downloaded = 0
            loaded = 0
            fail_download = False
            fail_load = False

            def list_supported_model_files(self):
                return {"MDXC": {"Kim": {"filename": ROFORMER_MODEL, "download_files": names}}}

            def get_model_checksums(self):
                return {name: hashlib.sha256(payload).hexdigest() for name in names}

            def verify_model_file_checksum(self, path):
                return hashlib.sha256(Path(path).read_bytes()).hexdigest() == hashlib.sha256(payload).hexdigest()

            def download_model_and_data(self, model):
                if self.fail_download:
                    raise OSError("network unavailable")
                for name in names:
                    if not (root / name).exists():
                        (root / name).write_bytes(payload)
                        self.downloaded += 1

            def load_model(self, model_filename):
                if self.fail_load:
                    raise SystemExit(1)
                self.loaded += 1

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            engine = Engine()
            stages = []
            with patch("separate.MODEL_DIR", root):
                prepare_model(engine, ROFORMER_MODEL, stages.append)
                prepare_model(engine, ROFORMER_MODEL, stages.append)
                self.assertEqual((engine.downloaded, engine.loaded), (2, 2))
                self.assertTrue(any("已缓存" in stage for stage in stages))
                engine.fail_load = True
                with self.assertRaisesRegex(RuntimeError, "模型加载失败"):
                    prepare_model(engine, ROFORMER_MODEL, stages.append)
                (root / names[1]).write_bytes(b"keep corrupt config")
                with self.assertRaisesRegex(RuntimeError, "模型校验失败"):
                    prepare_model(engine, ROFORMER_MODEL, stages.append)
                self.assertEqual((root / names[1]).read_bytes(), b"keep corrupt config")
                (root / names[1]).unlink()  # Only this test's own synthetic config.
                engine.fail_download = True
                with self.assertRaisesRegex(RuntimeError, "模型下载或参数检查失败"):
                    prepare_model(engine, ROFORMER_MODEL, stages.append)
                self.assertEqual((root / names[0]).read_bytes(), payload)
                with patch.object(engine, "get_model_checksums", return_value={}):
                    with self.assertRaisesRegex(RuntimeError, "没有提供"):
                        prepare_model(engine, ROFORMER_MODEL, stages.append)
