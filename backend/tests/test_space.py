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
        listed = patch.object(store, "listed_project", side_effect=lambda path: json.loads(json.dumps(self.project)))
        listed.start(); self.addCleanup(listed.stop)
        space._FREEABLE.clear()
        self.assertFalse(space.freeable(PID))                    # 1.6 KB is not worth a button (100 MB at least)
        with patch.object(space, "FREEABLE_MIN", 1000):
            space._FREEABLE.clear()
            self.assertTrue(space.freeable(PID))                 # the card offers «Звільнити місце»
        self.assertEqual(space.usage(PID), {"build": 1500, "old_renders": 100, "old_count": 1, "cache": 0, "total": 1600, "busy": None})
        self.assertEqual(space.free(PID), {"freed": 1600})
        with patch.object(space, "FREEABLE_MIN", 1000):
            self.assertFalse(space.freeable(PID))                # and stops offering it once nothing is left
        self.assertEqual(sorted(path.name for path in self.build.iterdir()), ["kept.wav", "live.log"])
        self.assertFalse((self.folder / "media" / "frame_001-aaaaaaaa.mp4").exists())
        self.assertTrue((self.folder / "media" / "frame_001.mp4").exists())             # the frame on the timeline stays
        self.assertEqual([asset["id"] for asset in self.project["assets"]], ["now", "bed"])
        # the undo steps that showed the old frame go, the newer one stays
        self.assertEqual([path.name for path in store.history_entries(PID, "past")], ["2.json"])
        self.assertEqual(space.usage(PID)["total"], 0)

    def test_the_studio_cache_of_the_episode_goes_too(self):
        stills = self.folder / "stills"; stills.mkdir()
        (stills / "still-a.png").write_bytes(b"x" * 300)
        self.assertEqual(space.usage(PID)["cache"], 300)
        space.free(PID)
        self.assertFalse(stills.exists())
        self.assertTrue((self.folder / "media" / "frame_001.mp4").exists())   # the frame on the timeline stays

    def test_nothing_goes_while_an_agent_works_on_the_episode(self):
        director.ACTIVE.add(PID)
        self.addCleanup(director.ACTIVE.discard, PID)
        self.assertEqual(space.usage(PID)["busy"], "Зараз іде режисура")
        with self.assertRaises(store.StudioError) as caught:
            space.free(PID)
        self.assertEqual(caught.exception.status, 409)
        self.assertTrue((self.build / "music.wav").exists())


class AllSpaceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ids = ['a' * 24, 'b' * 24, 'c' * 24]
        for index, pid in enumerate(self.ids):
            folder = self.root / pid
            (folder / 'stills').mkdir(parents=True)
            (folder / 'stills' / 'cached.png').write_bytes(b'x' * (index + 1) * 100)
            (folder / 'voice.mp3').write_bytes(b'keep')
            (folder / 'project.json').write_text(json.dumps({
                'id': pid, 'schema_version': 2, 'layer_mode': 'item', 'tracks': [], 'assets': [],
                'deleted_at': 1 if index == 2 else None}))
        for item in (patch.object(store, 'PROJECTS_ROOT', self.root),
                     patch.object(space.frame_progress, 'razgon_project', return_value=None),
                     patch.object(store, 'load_project', side_effect=lambda pid: store.read_json(store.project_path(pid)))):
            item.start(); self.addCleanup(item.stop)

    def test_totals_all_projects_without_the_card_minimum_and_skips_busy_and_deleted(self):
        self.assertEqual(space.all_usage(), {'total': 300, 'projects': 2, 'busy': 0, 'unavailable': 0})
        blocked = lambda pid: 'export' if pid == self.ids[1] else None
        self.assertEqual(space.all_usage(blocked), {'total': 100, 'projects': 1, 'busy': 1, 'unavailable': 0})
        result = space.free_all(blocked)
        self.assertEqual(result, {'freed': 100, 'projects': 1, 'busy': 1, 'unavailable': 0})
        self.assertFalse((self.root / self.ids[0] / 'stills').exists())
        for pid in self.ids:
            self.assertEqual((self.root / pid / 'voice.mp3').read_bytes(), b'keep')
            self.assertTrue((self.root / pid / 'project.json').exists())
        for pid in self.ids[1:]:
            self.assertTrue((self.root / pid / 'stills').exists())

    def test_execution_rechecks_activity_after_the_quote(self):
        self.assertEqual(space.all_usage()['total'], 300)
        result = space.free_all(lambda pid: 'started' if pid in self.ids[:2] else None)
        self.assertEqual(result['freed'], 0)
        self.assertEqual(result['busy'], 2)
        self.assertEqual(space.all_usage()['total'], 300)

    def test_broken_project_does_not_abort_other_projects(self):
        (self.root / self.ids[1] / 'project.json').write_text('{broken')
        self.assertEqual(space.all_usage(), {'total': 100, 'projects': 1, 'busy': 0, 'unavailable': 1})
        result = space.free_all()
        self.assertEqual(result['freed'], 100)
        self.assertEqual(result['unavailable'], 1)
        self.assertEqual(space.all_usage()['total'], 0)

    def test_parallel_cleanup_is_rejected(self):
        with space._SWEEP_LOCK:
            with self.assertRaises(store.StudioError) as error:
                space.free_all()
        self.assertEqual(error.exception.status, 409)


if __name__ == "__main__":
    unittest.main()
