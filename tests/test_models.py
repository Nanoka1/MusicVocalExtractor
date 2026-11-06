"""Download/cache failure tests use synthetic bytes, not fake production weights."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from models import ROFORMER_MODEL, DEFAULT_MODEL, MODELS, REMOVED_MODELS, check_model
from separate import prepare_model, separate_audio


class ModelCacheTests(unittest.TestCase):
    def test_retired_models_never_reach_download_engine(self):
        from unittest.mock import Mock
        self.assertEqual(DEFAULT_MODEL, ROFORMER_MODEL)
        self.assertEqual(set(MODELS), {ROFORMER_MODEL})
        for model in REMOVED_MODELS:
            engine = Mock()
            with self.assertRaisesRegex(ValueError, "已停用"):
                prepare_model(engine, model, lambda _: None)
            engine.list_supported_model_files.assert_not_called()
            engine.download_model_and_data.assert_not_called()

    def test_legacy_configuration_without_local_default_does_not_download(self):
        with tempfile.TemporaryDirectory() as folder, patch("separate.MODEL_DIR", Path(folder)):
            for model in REMOVED_MODELS:
                with self.assertRaisesRegex(ValueError, "未执行下载"):
                    separate_audio("unused.wav", model_name=model)

    def test_legacy_configuration_selects_existing_default_with_notice(self):
        import separate
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            # A registration fixture; mocked task never loads these synthetic bytes.
            (root / DEFAULT_MODEL).write_bytes(b"registration fixture only")
            audio = root / "input.wav"
            audio.touch()
            stages, stats = [], {}
            with patch.object(separate, "MODEL_DIR", root), patch.object(separate, "DATA_DIR", root), patch.object(separate, "probe_audio"), patch.object(separate, "_separate_task", return_value=(root / "v.mp3", root / "i.mp3")) as task:
                retired = next(iter(REMOVED_MODELS))
                separate_audio(audio, root / "results", model_name=retired, device="cpu",
                               progress_callback=stages.append, metrics_callback=stats.update)
            self.assertEqual(task.call_args.args[4], DEFAULT_MODEL)
            self.assertEqual(stats["requested_model"], retired)
            self.assertEqual(stats["model"], DEFAULT_MODEL)
            self.assertTrue(any("不会下载旧模型" in stage for stage in stages))

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
