import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import runtime_paths as paths


class RuntimePathTests(unittest.TestCase):
    def make_project(self, root):
        (root / "mve-project.json").write_text('{"application_id":"MusicVocalExtractor"}')
        for name in ("app.py", "separate.py", "runtime_paths.py"):
            (root / name).touch()

    def test_source_and_dist_depths_do_not_depend_on_cwd(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.make_project(root)
            for rel in ("dist/MusicVocalExtractor", "dist/build-old/MusicVocalExtractor", "dist/candidate-cpu/MusicVocalExtractor"):
                exe_dir = root / rel
                exe_dir.mkdir(parents=True)
                self.assertEqual(paths.find_project_dir(exe_dir, exe_dir / "_internal", True), root.resolve())
            self.assertEqual(paths.find_project_dir(root / "unrelated", root, False), root.resolve())
            self.assertIsNone(paths.find_project_dir(root / "portable", root / "portable/_internal", True))

    def test_standalone_uses_explicit_user_data_not_exe_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(paths, "PROJECT_DIR", None), patch.object(paths, "BUNDLE_SETTINGS", {}), patch.dict(os.environ, {"LOCALAPPDATA": str(root)}, clear=True):
                self.assertEqual(paths.data_dir(), root / "MusicVocalExtractor")

    def test_overrides_are_retained_and_unwritable_target_is_not_silently_changed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.dict(os.environ, {"MVE_DATA_DIR": str(root / "custom")}), patch.object(paths, "BUNDLE_SETTINGS", {}):
                self.assertEqual(paths.data_dir(), (root / "custom").resolve())
                with patch("runtime_paths.tempfile.TemporaryFile", side_effect=PermissionError("test")):
                    with self.assertRaisesRegex(RuntimeError, "没有改存到其他目录"):
                        paths.data_dir()
            with patch.dict(os.environ, {"MVE_DATA_DIR": ""}), patch.object(paths, "BUNDLE_SETTINGS", {"data_dir": root / "configured"}):
                self.assertEqual(paths.data_dir(), root / "configured")
