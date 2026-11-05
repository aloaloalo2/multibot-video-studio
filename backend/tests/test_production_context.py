import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import production
import production_context as context
import store


class ContextTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.rz = self.root / "rz"
        (self.rz / "scenes").mkdir(parents=True)
        (self.rz / "story").mkdir()
        self.project = {"id": "test", "episode_path": str(self.root), "name": "Test", "channel_id": "test"}
        self.request = {"id": "job", "frames": 3, "total_frames": 3, "start": 0, "end": 9}
        self.plan = {"script_sha256": "voice", "frames": [
            {"number": n, "start": (n - 1) * 3, "end": n * 3, "format": "razgon_2d", "sentences": [f"Line {n}"]}
            for n in range(1, 4)]}
        (self.rz / "story/shots.json").write_text(json.dumps({"shots": [
            {"id": f"s{n}", "start": (n - 1) * 3, "end": n * 3} for n in range(1, 4)]}))
        (self.rz / "story/studio_frames.json").write_text(json.dumps(self.plan))
        (self.rz / "scenes/a.js").write_text("take('s1', {}); take('s2', {});")
        for p in (patch.object(store, "load_project_plan", return_value=self.plan),
                  patch.object(store, "made_frames", return_value=[1, 2]),
                  patch.object(store, "project_dir", return_value=self.root),
                  patch.object(context.frame_progress, "razgon_project", return_value=self.rz)):
            p.start(); self.addCleanup(p.stop)

    def test_handoff_uses_existing_frames_and_scene_ownership(self):
        packet = context.build(self.project, self.request)
        self.assertEqual(packet["pending_frames"], [3])
        self.assertEqual(packet["issues"], [])
        self.assertEqual(packet["frames"][1]["takes"], ["s2"])
        self.assertEqual(packet["frames"][1]["scene_files"], ["scenes/a.js"])
        self.assertEqual(packet["frames"][2]["scene_files"], [])
        self.assertEqual(packet["frames"][1]["missing_takes"], [])
        self.assertEqual(packet["frames"][2]["missing_takes"], ['s3'])
        before = json.dumps(self.plan)
        path, _ = context.write(self.project, self.request, repair=True)
        self.assertEqual(json.loads(path.read_text())["mode"], "repair")
        self.assertEqual(json.dumps(self.plan), before)

    def test_batches_only_include_unfinished_frames_in_groups_of_five(self):
        self.request['frames'] = 13
        self.plan['frames'] = [dict(self.plan['frames'][0], number=n) for n in range(1, 14)]
        packet = context.build(self.project, self.request)
        self.assertEqual(packet['batch_size'], 5)
        self.assertEqual(packet['frame_batches'], [[3,4,5,6,7], [8,9,10,11,12], [13]])
        self.assertIn('Пакет 1: 3, 4, 5, 6, 7', context.text(packet))

    def test_mismatched_plan_refuses_handoff_before_model(self):
        linked = json.loads((self.rz / "story/studio_frames.json").read_text())
        linked["frames"][1]["start"] = 2.5
        (self.rz / "story/studio_frames.json").write_text(json.dumps(linked))
        with self.assertRaisesRegex(store.StudioError, "розходяться"):
            context.write(self.project, self.request)

    def test_missing_scene_import_is_named_for_repair_and_clears_when_restored(self):
        (self.rz / "scenes/a.js").write_text("import './missing.js'; take('s1', {});")
        packet = context.build(self.project, self.request)
        self.assertEqual(packet["scene_issues"], [{"file": "scenes/a.js", "missing": "./missing.js"}])
        self.assertIn("missing.js", context.text(packet))
        (self.rz / "scenes/missing.js").write_text("export const fixed = true;")
        self.assertEqual(context.build(self.project, self.request)["scene_issues"], [])

    def test_pause_continuation_uses_handoff_preserving_author_wishes(self):
        self.project["production_request"] = {**self.request, "status": "done", "session_id": "large-old-session"}
        with patch.object(store, "load_project", return_value=self.project), \
             patch.object(store, "save_project"), patch.object(production, "start"):
            production.fix("test", "Fix frame 2")
            self.assertFalse(self.project["production_request"]["continue_session"])
            self.project["production_request"].update(status="failed", paused=True)
            production.resume("test")
            self.assertFalse(self.project["production_request"]["continue_session"])
            self.assertEqual(self.project["production_request"]["continuation_mode"], "handoff")
            self.assertEqual(self.project["production_request"]["task_notes"], "Fix frame 2")
            self.assertEqual(self.project["production_request"]["session_id"], "large-old-session")

    def test_each_repair_has_its_own_cost_log(self):
        first = production.run_log("test", self.request)
        second = production.run_log("test", {**self.request, "fixes": 1})
        third = production.run_log("test", {**self.request, "fixes": 2})
        self.assertEqual(len({first, second, third}), 3)

    def test_continuation_handoff_preserves_summary_wishes_and_remaining_frames(self):
        request = {**self.request, "continuation_mode": "handoff", "task_notes": "Fix the chair in frame 3",
                   "summary": "Frames 1 and 2 are ready."}
        packet = context.build(self.project, request, repair=True)
        self.assertEqual(packet["mode"], "continue")
        self.assertEqual(packet["pending_frames"], [3])
        text = context.text(packet)
        self.assertIn("Fix the chair in frame 3", text)
        self.assertIn("Frames 1 and 2 are ready.", text)
        self.assertIn("001 0.00-3.00 готовий", text)
        self.assertIn("003 6.00-9.00 зробити", text)

    def test_worker_never_resends_old_history_even_for_a_legacy_continue_flag(self):
        for continuation in (False, True):
            self.project["production_request"] = {**self.request, "status": "requested", "session_id": "old-session",
                                                  "continue_session": continuation}
            with patch.object(store, "load_project", return_value=self.project), \
                 patch.object(store, "save_project"), patch.object(store, "project_animated", return_value=True), \
                 patch.object(production, "drawn", return_value=True), patch.object(production.logo_layer, "place"), \
                 patch.object(production.razgon_sound, "start"), \
                 patch.object(production.director, "claude", return_value=(0, {"result": "Ready", "session_id": "new"})) as model:
                production.run("test", Path("claude"), "Fix frame 2")
            self.assertIsNone(model.call_args.kwargs["resume"])

    def test_mismatched_source_never_spends_a_model_request(self):
        (self.rz / "story/studio_frames.json").write_text('{"script_sha256":"other","frames":[]}')
        self.project["production_request"] = {**self.request, "status": "requested"}
        with patch.object(store, "load_project", return_value=self.project), patch.object(store, "save_project"), \
             patch.object(store, "project_animated", return_value=True), patch.object(production.director, "claude") as model:
            production.run("test", Path("claude"))
        model.assert_not_called()
        self.assertIn("розходяться", self.project["production_request"]["error"])


if __name__ == "__main__":
    unittest.main()
