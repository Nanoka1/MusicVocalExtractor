import tempfile
import unittest
from pathlib import Path

from audit_builds import verify_preserved
from migrate_outputs import digest


class CleanupSafetyTests(unittest.TestCase):
    def test_new_unmigrated_song_or_changed_copy_blocks_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old = root / "dist/old"
            original = old / "outputs/song/Vocals.mp3"
            copy = root / "outputs/song/Vocals.mp3"
            original.parent.mkdir(parents=True)
            copy.parent.mkdir(parents=True)
            original.write_bytes(b"synthetic audio")
            copy.write_bytes(original.read_bytes())
            rows = [{"source": str(original.relative_to(root)), "destination": str(copy.relative_to(root)), "sha256": digest(original)}]
            self.assertTrue(verify_preserved(root, old, rows))
            new = original.parent / "new.wav"
            new.write_bytes(b"must preserve")
            with self.assertRaisesRegex(RuntimeError, "尚未保护"):
                verify_preserved(root, old, rows)
            new.unlink()  # Only this test's synthetic file.
            copy.write_bytes(b"changed")
            with self.assertRaisesRegex(RuntimeError, "不完整"):
                verify_preserved(root, old, rows)
