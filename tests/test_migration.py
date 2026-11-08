import tempfile
import unittest
from pathlib import Path

from migrate_outputs import copy_verified_tree, migrate, tree_manifest


class MigrationTests(unittest.TestCase):
    def test_conflict_preservation_integrity_and_repeat(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "dist/old/outputs/中文 歌曲"
            source.mkdir(parents=True)
            (source / "中文 歌曲_Vocals.mp3").write_bytes(b"synthetic vocals")
            (source / "中文 歌曲_Instrumental.mp3").write_bytes(b"synthetic backing")
            existing = root / "outputs/中文 歌曲"
            existing.mkdir(parents=True)
            (existing / "preserved.txt").write_text("keep")
            before = tree_manifest(source)
            report = migrate(root, apply=True)
            self.assertEqual(len(report["tasks"]), 1)
            self.assertEqual(tree_manifest(root / "outputs/中文 歌曲 (2)"), before)
            self.assertEqual(tree_manifest(source), before)
            self.assertEqual((existing / "preserved.txt").read_text(), "keep")
            self.assertEqual(len(migrate(root, apply=True)["tasks"]), 1)

    def test_copy_never_overwrites(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            src, dst = root / "src", root / "dst"
            src.mkdir(); dst.mkdir()
            (src / "file").write_bytes(b"source")
            (dst / "file").write_bytes(b"existing")
            with self.assertRaises(FileExistsError):
                copy_verified_tree(src, dst)
            self.assertEqual((dst / "file").read_bytes(), b"existing")
