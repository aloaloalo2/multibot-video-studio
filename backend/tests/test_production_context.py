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

    def test_joined_shot_requires_only_the_parts_overlapping_each_frame(self):
        story={'shots':[{'id':'s1','start':0,'end':9,'parts':[
            {'id':'s1','start':0},{'id':'s2','start':3},{'id':'s3','start':6}]}]}
        (self.rz/'story/shots.json').write_text(json.dumps(story))
        (self.rz/'scenes/a.js').write_text("take(['s1','s2'], {});")
        packet=context.build(self.project,self.request)
        self.assertEqual([f['takes'] for f in packet['frames']],[['s1'],['s2'],['s3']])
        self.assertEqual([f['missing_takes'] for f in packet['frames']],[[],[],['s3']])

    def test_scoped_creation_has_consistent_frame_limits_in_every_action(self):
        request={**self.request,'frames':53,'total_frames':53,'session_frames':list(range(21,41))}
        text=production.brief(self.project,request)
        self.assertIn('лише кадри студії 21-40',text)
        self.assertNotIn('кадри 1–53',text)
        self.assertIn('--frames '+','.join(map(str,range(21,41))),text)
        self.assertNotIn('після 53-го',text)
        guide=context.instructions('Current work',batch=True)
        self.assertIn('поточної частини',guide)
        self.assertNotIn('Після завершення кожного кадру',guide)

    def test_sparse_photo_scope_never_uses_all_text_or_unscoped_slots(self):
        request={**self.request,'frames':53,'total_frames':53,'session_frames':[21,23,25]}
        text=production.photo_brief(self.project,request)
        self.assertIn('лише кадри студії 21,23,25',text)
        self.assertIn('--frames 21,23,25 --todo',text)
        self.assertIn('summary test --frames 21-25',text)
        self.assertIn('slots --razgon <проєкт Razgon> --frames 21,23,25',text)
        self.assertNotIn('all-text',text)

    def test_selected_repair_targets_ready_frames_and_only_keeps_neighbours_as_context(self):
        packet=context.build(self.project,{**self.request,'repair_frames':[2]},repair=True)
        self.assertEqual(packet['pending_frames'],[2])
        self.assertEqual(packet['frame_batches'],[[2]])
        self.assertEqual([(f['number'],f['editable']) for f in packet['frames']],[(1,False),(2,True),(3,False)])
        self.assertIn('Правки ЛИШЕ до кадрів: 2',context.text(packet))

    def test_repair_stores_valid_selected_frames_and_uses_a_compact_scoped_brief(self):
        self.project['production_request']={**self.request,'status':'done','session_id':'previous'}
        with patch.object(store,'load_project',return_value=self.project),patch.object(store,'save_project'),patch.object(production,'start') as start:
            production.fix('test','Make the caption larger',frame_numbers=[2,2])
            kept=self.project['production_request']
            self.assertEqual(kept['repair_frames'],[2])
            self.assertEqual(kept['previous_session_id'],'previous')
            self.assertFalse(kept['continue_session'])
            brief=production.repair_brief(self.project,kept,'Make the caption larger')
            self.assertIn('ЛИШЕ до кадрів: 2',brief)
            self.assertIn('Make the caption larger',brief)
            self.assertLess(len(brief),2000)
            start.assert_called_once()

    def test_invalid_repair_scope_never_starts_paid_work(self):
        self.project['production_request']={**self.request,'status':'done'}
        with patch.object(store,'load_project',return_value=self.project),patch.object(production,'start') as start:
            for selected in [[],[0],[4],[True],[2.0],'2']:
                with self.subTest(selected=selected),self.assertRaises(store.StudioError):
                    production.fix('test','Fix',frame_numbers=selected)
            start.assert_not_called()

    def test_batches_only_include_unfinished_frames_in_groups_of_five(self):
        self.request['frames'] = 13
        self.plan['frames'] = [dict(self.plan['frames'][0], number=n) for n in range(1, 14)]
        packet = context.build(self.project, self.request)
        self.assertEqual(packet['batch_size'], 5)
        self.assertEqual(packet['frame_batches'], [[3,4,5,6,7], [8,9,10,11,12], [13]])
        self.assertIn('Пакет 1: 3, 4, 5, 6, 7', context.text(packet))
        self.assertIn('рівно 5',context.instructions(context.text(packet)))
        self.assertNotIn('пакет до 5',context.instructions(context.text(packet)))

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
