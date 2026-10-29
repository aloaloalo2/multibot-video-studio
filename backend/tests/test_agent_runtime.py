import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent_runtime
import agent_storage
import store


class Vault:
    def configured(self, service):
        return True


class AgentRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.old = store.YOUTUBE_ROOT, store.DATA_ROOT, store.PROJECTS_ROOT
        store.YOUTUBE_ROOT, store.DATA_ROOT = root / "youtube", root / "data"
        store.PROJECTS_ROOT = store.DATA_ROOT / "projects"
        channel = store.YOUTUBE_ROOT / "Channel"
        channel.mkdir(parents=True)
        (channel / "video-plan.json").write_text("{}")
        self.project = store.create_project(store.channel_id(channel), "Episode")
        self.callbacks = {"search": lambda q, k, n: [], "import": lambda *args: None, "export_active": lambda p: False, "image_count": [0]}

    def tearDown(self):
        agent_runtime.JOBS.clear()
        store.YOUTUBE_ROOT, store.DATA_ROOT, store.PROJECTS_ROOT = self.old
        self.temp.cleanup()

    def test_project_actions_require_synced_plan_and_revision(self):
        pid = self.project["id"]
        args = {"layer_id": "layer-1", "kind": "text", "text": "Test", "start": 0, "duration": 2, "expected_revision": 0}
        with patch.object(agent_runtime.store, "plan_readiness", return_value={"plan_ready": False}):
            with self.assertRaises(store.StudioError):
                agent_runtime.execute(pid, "add_clip", args, self.callbacks, False)
        with patch.object(agent_runtime.store, "plan_readiness", return_value={"plan_ready": True}):
            result = agent_runtime.execute(pid, "add_clip", args, self.callbacks, False)
            self.assertEqual(result["revision"], 1)
            with self.assertRaises(store.StudioError):
                agent_runtime.execute(pid, "add_clip", args, self.callbacks, False)
        self.assertEqual(len(store.load_project(pid)["tracks"][0]["clips"]), 1)

    def test_image_generation_requires_explicit_permission(self):
        with patch.object(agent_runtime.agent_image, "generate_transparent_asset") as generate:
            with self.assertRaises(store.StudioError):
                agent_runtime.execute(self.project["id"], "generate_transparent_png", {"prompt": "apple"}, self.callbacks, False)
            generate.assert_not_called()

    def test_agent_selection_and_deletion_preserve_undo(self):
        pid = self.project["id"]
        agent_runtime.JOBS[pid] = {"id": "test", "status": "running"}
        with patch.object(store, "plan_readiness", return_value={"plan_ready": True}):
            first = agent_runtime.execute(pid, "add_clip", {"layer_id": "layer-1", "kind": "text", "text": "First", "start": 0, "duration": 2, "expected_revision": 0}, self.callbacks, False)
            group = agent_runtime.execute(pid, "group_clips", {"clip_ids": [first["clip_id"]], "title": "Frame", "expected_revision": first["revision"]}, self.callbacks, False)
            selected = agent_runtime.execute(pid, "select_elements", {"group_ids": [group["group_id"]]}, self.callbacks, False)
            self.assertEqual(selected["selected"]["clip_ids"], [first["clip_id"]])
            self.assertEqual(agent_runtime.snapshot(pid)["selection"], selected["selected"])
            with self.assertRaises(store.StudioError):
                agent_runtime.execute(pid, "select_elements", {"clip_ids": ["missing"]}, self.callbacks, False)
            with self.assertRaises(store.StudioError):
                agent_runtime.execute(pid, "delete_group", {"group_id": group["group_id"], "expected_revision": 0}, self.callbacks, False)
            agent_runtime.execute(pid, "delete_group", {"group_id": group["group_id"], "expected_revision": group["revision"]}, self.callbacks, False)
            self.assertFalse(store.load_project(pid)["scene_groups"])
            restored = store.apply_action(pid, "undo", {})
            self.assertEqual(restored["scene_groups"][0]["id"], group["group_id"])

    def test_agent_groups_frame_elements_and_rejects_duplicate_members(self):
        pid = self.project["id"]
        first = {"layer_id": "layer-1", "kind": "text", "text": "Scene", "start": 0, "duration": 2, "expected_revision": 0}
        with patch.object(agent_runtime.store, "plan_readiness", return_value={"plan_ready": True}):
            clip = agent_runtime.execute(pid, "add_clip", first, self.callbacks, False)
            group = agent_runtime.execute(pid, "group_clips", {"clip_ids": [clip["clip_id"]], "title": "Кадр 1", "expected_revision": clip["revision"]}, self.callbacks, False)
            second = {"layer_id": "layer-1", "kind": "text", "text": "Overlay", "start": 0, "duration": 2, "group_id": group["group_id"], "font_size": 72, "font_weight": 700, "text_align": "center", "color": "#FFCC00", "x": .5, "y": .5, "width": .8, "height": .4, "expected_revision": group["revision"]}
            overlay = agent_runtime.execute(pid, "add_clip", second, self.callbacks, False)
            state = agent_runtime.execute(pid, "get_project", {}, self.callbacks, False)
            self.assertEqual(state["groups"][0]["role"], "scene")
            self.assertEqual(state["groups"][0]["clip_ids"], [clip["clip_id"], overlay["clip_id"]])
            saved = next(c for layer in store.load_project(pid)["tracks"] for c in layer["clips"] if c["id"] == overlay["clip_id"])
            self.assertEqual((saved["font_size"], saved["font_weight"], saved["text_align"], saved["color"]), (72, 700, "center", "#FFCC00"))
            with self.assertRaises(store.StudioError):
                agent_runtime.execute(pid, "add_clip", {**second, "color": "invalid", "expected_revision": overlay["revision"]}, self.callbacks, False)
            with self.assertRaises(store.StudioError):
                agent_runtime.execute(pid, "group_clips", {"clip_ids": [clip["clip_id"]], "title": "Duplicate", "expected_revision": overlay["revision"]}, self.callbacks, False)
            with self.assertRaises(store.StudioError):
                agent_runtime.execute(pid, "group_clips", {"clip_ids": [overlay["clip_id"]], "title": "Stale", "expected_revision": 0}, self.callbacks, False)
        args = {"clip_ids": [clip["clip_id"]], "title": "Blocked", "expected_revision": overlay["revision"]}
        with patch.object(agent_runtime.store, "plan_readiness", return_value={"plan_ready": False}):
            with self.assertRaises(store.StudioError):
                agent_runtime.execute(pid, "group_clips", args, self.callbacks, False)
        with patch.dict(self.callbacks, {"export_active": lambda p: True}):
            with self.assertRaises(store.StudioError):
                agent_runtime.execute(pid, "group_clips", args, self.callbacks, False)
        self.assertEqual(store.load_project(pid)["revision"], overlay["revision"])

    def test_project_guard_prevents_agent_during_export(self):
        pid = self.project["id"]
        guard = agent_runtime.acquire_project_guard(pid, "export")
        self.assertIsNotNone(guard)
        try:
            with patch.object(agent_runtime.agent_openrouter.credentials, "vault", return_value=Vault()):
                with self.assertRaises(store.StudioError):
                    agent_runtime.start(pid, "Збери відео", self.callbacks)
            self.assertEqual(agent_storage.get_conversation(pid)["messages"], [])
        finally:
            guard.close()

    def test_stop_request_prevents_further_tools(self):
        pid = self.project["id"]
        def reply(*args, **kwargs):
            agent_runtime.cancel(pid)
            return {"role": "assistant", "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "search_stock", "arguments": '{"query":"apple","kind":"image"}'}}]}
        with patch.object(agent_runtime.agent_openrouter.credentials, "vault", return_value=Vault()), patch.object(agent_runtime.agent_openrouter, "chat", side_effect=reply), patch.object(agent_runtime, "execute") as execute:
            agent_runtime.start(pid, "Переглянь план", self.callbacks)
            for _ in range(100):
                if agent_runtime.snapshot(pid)["status"] == "cancelled":
                    break
                time.sleep(.01)
            self.assertEqual(agent_runtime.snapshot(pid)["status"], "cancelled")
            execute.assert_not_called()

    def test_chat_tool_loop_persists_project_conversation(self):
        pid = self.project["id"]
        agent_storage.set_settings(pid, "max")
        responses = [{"role": "assistant", "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "get_plan", "arguments": '{"offset":0}'}}]}, {"role": "assistant", "content": "План переглянуто."}]
        with patch.object(agent_runtime.agent_openrouter.credentials, "vault", return_value=Vault()), patch.object(agent_runtime.agent_openrouter, "chat", side_effect=responses) as model, patch.object(agent_runtime.store, "load_project_plan", return_value={"frames": [{"number": 1}]}):
            agent_runtime.start(pid, "Переглянь план", self.callbacks)
            for _ in range(100):
                if agent_runtime.snapshot(pid)["status"] in {"complete", "failed"}:
                    break
                time.sleep(.01)
        self.assertEqual(agent_runtime.snapshot(pid)["status"], "complete")
        self.assertIn("Відповідай якомога коротше", model.call_args_list[0].args[1][0]["content"])
        self.assertEqual([call.kwargs["reasoning_effort"] for call in model.call_args_list], ["max", "max"])
        messages = agent_storage.get_conversation(pid)["messages"]
        self.assertEqual([m["role"] for m in messages], ["user", "assistant"])
        self.assertEqual(messages[-1]["content"], "План переглянуто.")


if __name__ == "__main__":
    unittest.main()
