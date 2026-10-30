import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import director  # noqa: E402
import space  # noqa: E402
import store  # noqa: E402

PID = "e" * 24


class SpaceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.folder, self.razgon = base / "project", base / "razgon" / "05-test"
        media = self.folder / "media"
        media.mkdir(parents=True)
        self.build = self.razgon / "build"
        (self.build / "studio").mkdir(parents=True)
        (self.build / "studio" / "frame_001.mp4").write_bytes(b"x" * 1000)
        (self.build / "music.wav").write_bytes(b"x" * 500)
        (self.build / "live.log").write_text("live")
        (self.build / "kept.wav").write_bytes(b"x" * 300)                  # the studio still points at this one
        (media / "frame_001.mp4").write_bytes(b"y" * 200)                   # on the timeline
        (media / "frame_001-aaaaaaaa.mp4").write_bytes(b"y" * 100)          # replaced, only undo shows it
        self.project = {"id": PID, "episode_path": str(base / "05 Test"),
                        "assets": [{"id": "now", "path": str(media / "frame_001.mp4")},
                                   {"id": "old", "path": str(media / "frame_001-aaaaaaaa.mp4")},
                                   {"id": "bed", "path": str(self.build / "kept.wav")}],
                        "tracks": [{"clips": [{"asset_id": "now"}, {"asset_id": "bed"}]}]}
        history = self.folder / "history" / "past"
        history.mkdir(parents=True)
        for index, asset in enumerate(["old", "old", "now"]):
            (history / f"{index}.json").write_text(json.dumps({"tracks": [{"clips": [{"asset_id": asset}]}]}))
        for item in (patch.object(store, "project_dir", return_value=self.folder),
                     patch.object(store, "load_project", side_effect=lambda pid: json.loads(json.dumps(self.project))),
                     patch.object(store, "save_project", side_effect=lambda project: self.project.update(project)),
                     patch.object(space.frame_progress, "razgon_project", return_value=self.razgon)):
            item.start()
            self.addCleanup(item.stop)

    def test_it_says_how_much_goes_and_frees_exactly_that(self):
        self.assertEqual(space.usage(PID), {"build": 1500, "old_renders": 100, "old_count": 1, "total": 1600, "busy": None})
        self.assertEqual(space.free(PID), {"freed": 1600})
        self.assertEqual(sorted(path.name for path in self.build.iterdir()), ["kept.wav", "live.log"])
        self.assertFalse((self.folder / "media" / "frame_001-aaaaaaaa.mp4").exists())
        self.assertTrue((self.folder / "media" / "frame_001.mp4").exists())             # the frame on the timeline stays
        self.assertEqual([asset["id"] for asset in self.project["assets"]], ["now", "bed"])
        # the undo steps that showed the old frame go, the newer one stays
        self.assertEqual([path.name for path in store.history_entries(PID, "past")], ["2.json"])
        self.assertEqual(space.usage(PID)["total"], 0)

    def test_nothing_goes_while_an_agent_works_on_the_episode(self):
        director.ACTIVE.add(PID)
        self.addCleanup(director.ACTIVE.discard, PID)
        self.assertEqual(space.usage(PID)["busy"], "Зараз іде режисура")
        with self.assertRaises(store.StudioError) as caught:
            space.free(PID)
        self.assertEqual(caught.exception.status, 409)
        self.assertTrue((self.build / "music.wav").exists())


if __name__ == "__main__":
    unittest.main()
