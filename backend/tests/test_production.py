import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import production  # noqa: E402
import store  # noqa: E402

REQUEST = {"id": "r1", "frames": 3, "total_frames": 73, "start": 0.0, "end": 120.5, "status": "requested"}


class ProductionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        episode = base / "What If" / "05 Test"
        episode.mkdir(parents=True)
        self.project = {"id": "a" * 24, "name": "05 Test", "channel_id": "c" * 16, "episode_path": str(episode),
                        "production_request": dict(REQUEST), "tracks": [{"clips": [{"kind": "animation"}] * 3}]}
        for item in (patch.object(store, "load_project", side_effect=lambda pid: json.loads(json.dumps(self.project))),
                     patch.object(store, "save_project", side_effect=lambda project: self.project.update(project)),
                     patch.object(store, "project_dir", return_value=base)):
            item.start()
            self.addCleanup(item.stop)
        production.ACTIVE.clear()

    def test_brief_names_the_frames_and_the_limits(self):
        text = production.brief(self.project, REQUEST)
        for part in ("кадри студії 1–3 з 73", "--frames 1,2,3", "codex_image.py", '"assets": false', "Не роби фінальний MP4"):
            self.assertIn(part, text)

    def test_done_only_when_the_frames_are_pictures_on_the_timeline(self):
        answer = json.dumps({"result": "Кадри 1–3 готові", "total_cost_usd": 4.2, "usage": {"input_tokens": 10, "output_tokens": 5}, "duration_ms": 60000})
        with patch.object(production.director, "claude", return_value=(0, json.loads(answer))):
            production.ACTIVE.add(self.project["id"])
            production.run(self.project["id"], Path("claude"))
            self.assertEqual(self.project["production_request"]["status"], "failed")     # still code blocks
            self.project["tracks"] = [{"clips": [{"kind": "video"}] * 3}]
            production.ACTIVE.add(self.project["id"])
            production.run(self.project["id"], Path("claude"))
        request = self.project["production_request"]
        self.assertEqual((request["status"], request["cost_usd"]), ("done", 4.2))
        self.assertGreaterEqual(request["minutes"], 0)                                 # wall clock from the start
        mirror = json.loads((Path(self.project["episode_path"]) / "Запит на створення.json").read_text())
        self.assertEqual(mirror["status"], "done")
        self.assertNotIn(self.project["id"], production.ACTIVE)

    def test_a_run_stopped_by_the_subscription_limit_is_a_pause_that_resumes_its_session(self):
        answer = {"is_error": True, "api_error": "usage_limit_reached", "session_id": "s1", "total_cost_usd": 3.0,
                  "result": "You've hit your session limit · resets 12:50pm (Europe/Kiev)"}
        with patch.object(production.director, "claude", return_value=(1, answer)):
            production.ACTIVE.add(self.project["id"])
            production.run(self.project["id"], Path("claude"))
        request = self.project["production_request"]
        self.assertEqual((request["status"], request["limit"], request["session_id"]), ("failed", True, "s1"))
        self.assertEqual(request["error"], "Закінчився ліміт підписки Claude, він оновиться о 12:50.")
        with patch.object(production, "start") as start:
            production.resume(self.project["id"])
        start.assert_called_once_with(self.project["id"], production.RESUME)    # notes: the run picks its session up
        self.assertEqual(self.project["production_request"]["status"], "requested")
        self.project["production_request"].update(status="failed", limit=False, error="Кадри не з'явилися")
        with self.assertRaises(store.StudioError):
            production.resume(self.project["id"])


if __name__ == "__main__":
    unittest.main()
