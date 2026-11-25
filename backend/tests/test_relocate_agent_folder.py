"""The frame agent's «кадри» in the episode folder moves into the studio's media with its asset ids and undo snapshots
(user, 25 November 2026: «папка кадри… це типу сміття технічне»)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import store


class RelocateAgentFolderTest(unittest.TestCase):
    def test_the_agent_folder_leaves_the_episode_with_ids_and_history(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            episode, studio = root / "episode", root / "studio"
            (episode / "кадри" / "асети").mkdir(parents=True)
            (studio / "history" / "past").mkdir(parents=True)
            used, spare, prop = episode / "кадри" / "кадр_001.png", episode / "кадри" / "кадр_002.png", episode / "кадри" / "асети" / "a.png"
            for path in (used, spare, prop):
                path.write_bytes(b"\x89PNG")
            (episode / "Сценарий.txt").write_text("текст")
            asset = {"id": "a1", "path": str(used.resolve()), "kind": "image"}
            project = {"id": "p1", "revision": 3, "episode_path": str(episode), "assets": [asset]}
            saved = {}
            (studio / "history" / "past" / "1.json").write_text(json.dumps({"assets": [dict(asset)]}))
            with mock.patch.object(store, "project_dir", lambda pid: studio), \
                    mock.patch.object(store, "load_project", lambda pid: json.loads(json.dumps(project))), \
                    mock.patch.object(store, "read_json", side_effect=lambda path, default=None: {"revision": 3} if str(path).endswith("project.json") else json.loads(Path(path).read_text())), \
                    mock.patch.object(store, "project_path", lambda pid: studio / "project.json"), \
                    mock.patch.object(store, "save_project", lambda p: saved.update(p)):
                result = store.relocate_media("p1")
            self.assertEqual(result["moved"], 3)
            self.assertFalse((episode / "кадри").exists())                 # the agent's folder is gone from the episode
            self.assertTrue((episode / "Сценарий.txt").is_file())          # the author's files stay
            moved = Path(saved["assets"][0]["path"])
            self.assertEqual(saved["assets"][0]["id"], "a1")
            self.assertTrue(moved.is_file() and store.under(moved, studio / "media" / "кадри"))
            self.assertTrue((studio / "media" / "кадри" / "асети" / "a.png").is_file())
            history = json.loads((studio / "history" / "past" / "1.json").read_text())
            self.assertEqual(history["assets"][0]["path"], str(moved))


if __name__ == "__main__":
    unittest.main()
