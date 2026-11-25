"""The project store reads and edits a long film without repeating work: cached transition leads, one anchor per
edit, compact project.json, undo steps written from text."""
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import joins
import store

PID = "a" * 24


def film(video: Path) -> dict:
    clips_a = [{"id": "v1", "kind": "video", "asset_id": "vid", "start": 0, "duration": 2, "trim_start": 0}]
    clips_b = [{"id": "i1", "kind": "image", "asset_id": "img", "start": 2, "duration": 2}]
    clips_c = [{"id": "i2", "kind": "image", "asset_id": "img", "start": 4, "duration": 2}]
    return {"id": PID, "name": "Тест", "schema_version": 2, "layer_mode": "item", "revision": 3, "fps": 25,
            "duration": 6, "created_at": 1_700_000_000_000, "scenes": [],
            "assets": [{"id": "vid", "kind": "video", "path": str(video)}, {"id": "img", "kind": "image", "path": str(video)}],
            "tracks": [{"id": "l1", "type": "universal", "clips": clips_a}, {"id": "l2", "type": "universal", "clips": clips_b},
                       {"id": "l3", "type": "universal", "clips": clips_c}],
            "scene_groups": [{"id": "a", "role": "scene", "clip_ids": ["v1"]}, {"id": "b", "role": "scene", "clip_ids": ["i1"]},
                             {"id": "c", "role": "scene", "clip_ids": ["i2"]}],
            "join_transitions": [{"id": "j1", "from_ref": "group:a", "to_ref": "group:b", "type": "crossfade", "duration": .5, "seam": 2},
                                 {"id": "j2", "from_ref": "group:b", "to_ref": "group:c", "type": "crossfade", "duration": .5, "seam": 4}]}


class StoreEditsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.video = root / "clip.mp4"
        self.video.write_bytes(b"x" * 10)
        self.lengths = {}
        patches = [mock.patch.object(store, "DATA_ROOT", root), mock.patch.object(store, "PROJECTS_ROOT", root / "projects"),
                   mock.patch.object(store, "media_duration", lambda path: self.lengths.get(Path(path).stat().st_size)),
                   mock.patch.dict(store._ANCHORS, clear=True)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        (root / "projects" / PID).mkdir(parents=True)
        (root / "projects" / PID / "project.json").write_text(json.dumps(film(self.video)))
        self.lengths[10] = 2.0   # the video ends with its clip: the transition out of it ends on the seam

    def tearDown(self):
        self.tmp.cleanup()

    def fresh(self) -> dict:
        project = store.upgrade_legacy_project(store.read_json(store.project_path(PID)))
        project["created_at"] = store.project_created_at(project, store.project_dir(PID))
        return joins.anchor(project)

    def test_a_second_read_reuses_the_leads_and_gives_the_same_project(self):
        first = store.load_project(PID)
        with mock.patch.object(joins, "anchor", side_effect=AssertionError("anchored again")):
            second = store.load_project(PID)
        self.assertEqual(first, second)
        self.assertEqual(second, self.fresh())
        self.assertAlmostEqual(second["join_transitions"][0]["lead"], .48)

    def test_a_video_of_another_length_anchors_again(self):
        store.load_project(PID)
        self.video.write_bytes(b"x" * 20)
        self.lengths[20] = 9.0
        project = store.load_project(PID)
        self.assertEqual(project, self.fresh())
        self.assertAlmostEqual(project["join_transitions"][0]["lead"], .24)

    def test_a_batch_anchors_once_and_matches_one_action_at_a_time(self):
        moves = [{"type": "update_clip", "payload": {"clip_id": "i2", "patch": {"opacity": .5 + i / 100}}} for i in range(20)]
        calls = []
        real = joins.anchor
        with mock.patch.object(joins, "anchor", side_effect=lambda p: calls.append(1) or real(p)):
            store.load_project(PID)
            calls.clear()
            result = store.apply_action(PID, "batch", {"actions": moves}, 3)
        self.assertEqual(len(calls), 1)
        expected = film(self.video)
        for move in moves:
            store.apply_universal_action(expected, move["type"], move["payload"])   # outside an edit: reconcile as before
        self.assertEqual(result["join_transitions"], expected["join_transitions"])
        self.assertEqual(result["revision"], 4)
        # the leads remembered from the edit are what a fresh read gives
        with mock.patch.object(joins, "anchor", side_effect=AssertionError("anchored again")):
            again = store.load_project(PID)
        self.assertEqual(again, self.fresh())

    def test_a_seam_broken_inside_a_batch_loses_its_transition_as_before(self):
        result = store.apply_action(PID, "batch", {"actions": [
            {"type": "move_clip", "payload": {"clip_id": "i2", "start": 4.5}},
            {"type": "move_clip", "payload": {"clip_id": "i2", "start": 4}}]}, 3)
        self.assertEqual([join["id"] for join in result["join_transitions"]], ["j1"])

    def test_undo_brings_back_the_step_before_and_the_file_is_compact_json(self):
        before = store.load_project(PID)
        store.apply_action(PID, "update_clip", {"clip_id": "i1", "patch": {"opacity": .3}}, 3)
        text = store.project_path(PID).read_text()
        self.assertNotIn("\n  ", text)
        self.assertEqual(json.loads(text)["created_at"], 1_700_000_000_000)
        undone = store.apply_action(PID, "undo", {})
        clip = lambda project: next(c for t in project["tracks"] for c in t["clips"] if c["id"] == "i1")
        self.assertEqual(clip(undone), clip(before))
        self.assertEqual(store.load_project(PID)["revision"], 5)
        redone = store.apply_action(PID, "redo", {})
        self.assertEqual(clip(redone)["opacity"], .3)

    def test_a_failed_batch_saves_nothing_and_leaves_no_edit_state(self):
        mtime = os.stat(store.project_path(PID)).st_mtime_ns
        with self.assertRaises(store.StudioError):
            store.apply_action(PID, "batch", {"actions": [{"type": "update_clip", "payload": {"clip_id": "i1", "patch": {"opacity": .2}}},
                                                          {"type": "no_such_action", "payload": {}}]}, 3)
        self.assertEqual(os.stat(store.project_path(PID)).st_mtime_ns, mtime)
        self.assertIsNone(getattr(store._EDIT, "joins", None))
        self.assertFalse(store.history_state(PID)["can_undo"])

    def test_old_scene_actions_are_refused_with_a_clear_message(self):
        with self.assertRaisesRegex(store.StudioError, "старому формату"):
            store.apply_action(PID, "add_scene", {"duration": 2})
        with self.assertRaisesRegex(store.StudioError, "не підтримано"):
            store.apply_action(PID, "no_such_action", {})


if __name__ == "__main__":
    unittest.main()
