import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import store


class FollowChannelKindTest(unittest.TestCase):
    """An episode not planned yet follows its channel's new kind; a planned or produced one keeps its own."""

    def test_only_unplanned_episodes_follow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def make(pid, **extra):
                (root / pid).mkdir()
                (root / pid / "project.json").write_text(json.dumps({"id": pid, "channel_id": "c", "project_kind": "regular", **extra}))
            make("fresh"); make("produced", production_request={"id": "r"}); make("planned"); make("other", channel_id="x")
            plans = {"planned": {"frames": [{"number": 1}]}}
            with mock.patch.object(store, "PROJECTS_ROOT", root), \
                 mock.patch.object(store, "project_plan_file", side_effect=lambda p: p["id"] if p["id"] in plans else None), \
                 mock.patch.object(store, "cached_plan", side_effect=lambda path: (plans[path], None)):
                moved = store.follow_channel_kind("c", "animated")
            self.assertEqual(moved, ["fresh"])
            self.assertEqual(json.loads((root / "fresh" / "project.json").read_text())["project_kind"], "animated")


if __name__ == "__main__":
    unittest.main()
