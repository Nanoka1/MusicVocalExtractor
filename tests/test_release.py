import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import runtime_paths
from publish_release import validate_candidate
from verify_release import package_manifest


class ReleaseTests(unittest.TestCase):
    def test_cpu_verification_cannot_masquerade_as_gpu(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            report = dict(passed=True, gpu=False, cpu=True, http_preview_download=True,
                          models_shared=True, manifest=package_manifest(root))
            (root / "release-validation.json").write_text(json.dumps(report))
            with self.assertRaisesRegex(RuntimeError, "没有通过"):
                validate_candidate(root)
            self.assertTrue(validate_candidate(root, require_gpu=False)["cpu"])

    def test_verified_package_rejects_changed_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            app = root / "example.txt"
            app.write_text("synthetic package fixture")
            report = dict(passed=True, gpu=True, http_preview_download=True, models_shared=True,
                          manifest=package_manifest(root))
            (root / "release-validation.json").write_text(json.dumps(report))
            self.assertTrue(validate_candidate(root)["passed"])
            app.write_text("modified after verification")
            with self.assertRaisesRegex(RuntimeError, "实测清单不同"):
                validate_candidate(root)

    def test_unverified_release_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "release-validation.json").write_text('{"passed": false}')
            with self.assertRaisesRegex(RuntimeError, "没有通过"):
                validate_candidate(root)

    def test_shared_bundle_paths_and_invalid_config(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / "runtime-config.json"
            config.write_text(json.dumps({"data_dir": "../shared", "model_dir": "../shared/models"}))
            with patch.object(runtime_paths, "APP_DIR", root), patch.object(runtime_paths.sys, "frozen", True, create=True):
                settings = runtime_paths.bundle_settings()
                self.assertEqual(settings["model_dir"], (root.parent / "shared/models").resolve())
                config.write_text("not json")
                with self.assertRaisesRegex(RuntimeError, "无法读取运行目录配置"):
                    runtime_paths.bundle_settings()
