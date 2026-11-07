import json
import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import patch

import runtime_paths
from publish_release import validate_candidate
import publish_release
from verify_release import package_manifest


class ReleaseTests(unittest.TestCase):
    def test_named_backup_preserves_previous_release_and_rejects_reuse(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            formal = root / "dist/MusicVocalExtractor"
            candidate = root / "dist/candidate-gpu/MusicVocalExtractor"
            formal.mkdir(parents=True)
            candidate.mkdir(parents=True)
            (formal / "old.txt").write_text("old GPU version")
            (candidate / "new.txt").write_text("new GPU version")
            args = ["publish_release", "--publish", "--backup-name", "formal-before-audio-gain"]
            with patch.object(publish_release, "__file__", str(root / "publish_release.py")), patch.object(sys, "argv", args), patch.object(publish_release, "validate_candidate"), patch.object(publish_release, "assert_not_running"):
                publish_release.main()
                candidate.mkdir()
                (candidate / "next.txt").write_text("next candidate")
                with self.assertRaisesRegex(RuntimeError, "已存在"):
                    publish_release.main()
            self.assertEqual((root / ".reference/formal-before-audio-gain/old.txt").read_text(), "old GPU version")
            self.assertTrue((formal / "new.txt").is_file())
            self.assertTrue((candidate / "next.txt").is_file())

    def test_named_backup_rejects_path_traversal(self):
        for name in ("../escape", "C:\\escape", "a/b", "..", "x" * 65):
            with self.subTest(name=name), patch.object(sys, "argv", ["publish_release", "--backup-name", name]):
                with self.assertRaises(SystemExit) as error:
                    publish_release.main()
                self.assertEqual(error.exception.code, 2)

    def test_gpu_publish_updates_formal_and_keeps_cpu_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            formal = root / "dist/MusicVocalExtractor"
            candidate = root / "dist/candidate-gpu/MusicVocalExtractor"
            formal.mkdir(parents=True); candidate.mkdir(parents=True)
            (formal / "old.txt").write_text("verified CPU fallback")
            (candidate / "new.txt").write_text("synthetic verified GPU candidate")
            older = root / ".reference/formal-exe-rollback"
            older.mkdir(parents=True)
            (older / "keep.txt").write_text("keep older fallback")
            with patch.object(publish_release, "__file__", str(root / "publish_release.py")), patch.object(sys, "argv", ["publish_release", "--publish"]), patch.object(publish_release, "validate_candidate") as validate, patch.object(publish_release, "assert_not_running"):
                publish_release.main()
            validate.assert_called_once_with(candidate.resolve(), require_gpu=True)
            self.assertTrue((formal / "new.txt").is_file())
            self.assertTrue((root / ".reference/formal-before-gpu-rollback/old.txt").is_file())
            self.assertTrue((older / "keep.txt").is_file())

    def test_cpu_verification_cannot_masquerade_as_gpu(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            report = dict(passed=True, gpu=False, cpu=True, http_preview_download=True,
                          models_shared=True, manifest=package_manifest(root),
                          web_revision=runtime_paths.web_revision(), mp3_mix=True)
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
                          manifest=package_manifest(root), web_revision=runtime_paths.web_revision(), mp3_mix=True)
            (root / "release-validation.json").write_text(json.dumps(report))
            self.assertTrue(validate_candidate(root)["passed"])
            app.write_text("modified after verification")
            with self.assertRaisesRegex(RuntimeError, "实测清单不同"):
                validate_candidate(root)

    def test_old_web_version_cannot_be_published(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "release-validation.json").write_text(json.dumps(dict(
                passed=True, gpu=True, http_preview_download=True, models_shared=True,
                web_revision="old", mp3_mix=True, manifest=package_manifest(root),
            )))
            with self.assertRaisesRegex(RuntimeError, "当前网页版本"):
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
