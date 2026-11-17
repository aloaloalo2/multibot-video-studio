import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import store


class DeleteRazgonTest(unittest.TestCase):
    """Deleting a project takes its own Razgon animation along (user, 17 November 2026)."""

    def make(self, root, name, owner):
        folder = root / "razgon" / "projects" / name
        (folder / "story").mkdir(parents=True)
        (folder / "story" / "studio_frames.json").write_text(json.dumps({"project_id": owner}))
        (folder / "build.bin").write_bytes(b"x" * 1000)
        return folder

    def test_own_animation_goes_and_anothers_stays(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid = "a" * 24
            (root / "projects" / pid).mkdir(parents=True)
            (root / "projects" / pid / "project.json").write_text(json.dumps({"id": pid, "name": "x"}))
            own, other = self.make(root, "own", pid), self.make(root, "other", "b" * 24)
            with mock.patch.object(store, "PROJECTS_ROOT", root / "projects"):
                for linked, survives in ((other, True), (own, False)):
                    with mock.patch.object(store, "razgon_link", return_value={"project": str(linked)}):
                        if survives:
                            self.assertIsNone(store.owned_razgon_project({"id": pid}))
                            continue
                        freed = store.delete_project(pid)
            self.assertFalse(own.exists())
            self.assertTrue(other.exists())
            self.assertGreaterEqual(freed, 1000)


if __name__ == "__main__":
    unittest.main()
