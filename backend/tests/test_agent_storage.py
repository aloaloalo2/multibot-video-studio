import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent_storage
import store


class AgentStorageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.old = store.YOUTUBE_ROOT, store.DATA_ROOT, store.PROJECTS_ROOT
        store.YOUTUBE_ROOT = root / "youtube"
        store.DATA_ROOT = root / "data"
        store.PROJECTS_ROOT = store.DATA_ROOT / "projects"
        self.channel = store.YOUTUBE_ROOT / "Channel"
        self.channel.mkdir(parents=True)
        (self.channel / "video-plan.json").write_text("{}")
        self.cid = store.channel_id(self.channel)

    def tearDown(self):
        store.YOUTUBE_ROOT, store.DATA_ROOT, store.PROJECTS_ROOT = self.old
        self.temp.cleanup()

    def test_project_chats_and_channel_memory_are_isolated(self):
        first = store.create_project(self.cid, "First")
        second = store.create_project(self.cid, "Second")
        agent_storage.add_message(first["id"], "user", "Hello")
        agent_storage.add_cost(first["id"], "chat", "model", .02)
        agent_storage.add_cost(first["id"], "image", "model", None)
        agent_storage.set_memory(self.cid, "Keep titles readable")
        saved = agent_storage.get_conversation(first["id"])
        self.assertEqual(saved["messages"][0]["content"], "Hello")
        self.assertEqual(agent_storage.cost_summary(saved["costs"]), {"known_total_usd": .02, "unknown_count": 1, "request_count": 2})
        self.assertEqual(agent_storage.get_conversation(second["id"]), {"messages": [], "costs": []})
        self.assertEqual(agent_storage.get_memory(self.cid), "Keep titles readable")
        other = store.YOUTUBE_ROOT / "Other"
        other.mkdir()
        (other / "video-plan.json").write_text("{}")
        self.assertEqual(agent_storage.get_memory(store.channel_id(other)), "")

    def test_rejects_invalid_costs_and_channels(self):
        project = store.create_project(self.cid, "Project")
        for amount in (-1, float("nan"), True):
            with self.assertRaises(store.StudioError):
                agent_storage.add_cost(project["id"], "chat", "model", amount)
        with self.assertRaises(store.StudioError):
            agent_storage.get_memory("../bad")

    def test_reasoning_settings_are_persisted_per_project(self):
        first = store.create_project(self.cid, "First")
        second = store.create_project(self.cid, "Second")
        self.assertEqual(agent_storage.get_settings(first["id"])["reasoning_effort"], "auto")
        agent_storage.set_settings(first["id"], "max")
        self.assertEqual(agent_storage.get_settings(first["id"])["reasoning_effort"], "max")
        self.assertEqual(agent_storage.get_settings(second["id"])["reasoning_effort"], "auto")
        for invalid in ("medium", None, [], ""):
            with self.assertRaises(store.StudioError):
                agent_storage.set_settings(first["id"], invalid)
        self.assertEqual(agent_storage.get_settings(first["id"])["reasoning_effort"], "max")


if __name__ == "__main__":
    unittest.main()
