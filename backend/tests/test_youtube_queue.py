"""«Опублікувати»: the episodes wait in one queue and only one publishing session is opened for them."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import published
import store


class QueueTest(unittest.TestCase):
    def test_three_episodes_open_one_session_and_wait_in_turn(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projects = {pid: {"id": pid, "channel_id": "c" + pid} for pid in ("a", "b", "c")}
            with patch.object(store, "DATA_ROOT", root), patch.object(store, "PROJECTS_ROOT", root / "projects"), \
                 patch.object(store, "project_dir", side_effect=lambda pid: root / "projects" / pid), \
                 patch.object(store, "load_project", side_effect=lambda pid: projects[pid]):
                answers = [published.enqueue(pid) for pid in ("a", "b", "c")]
                self.assertEqual([a["open_session"] for a in answers], [True, False, False])
                self.assertEqual([row["project"] for row in published.queue()], ["a", "b", "c"])
                self.assertEqual(published.active_channels(), {"ca", "cb", "cc"})
                self.assertEqual(published.publishing({"id": "b"}), "queued")


if __name__ == "__main__":
    unittest.main()
