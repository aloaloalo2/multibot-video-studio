import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import director  # noqa: E402
import store  # noqa: E402

PROJECT = {"id": "a" * 24, "name": "05 Test", "channel_id": "c" * 16, "episode_path": str(store.YOUTUBE_ROOT / "What If" / "05 Test")}


class DirectorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plan = {}
        self.kind = "animated"
        patches = [patch.object(store, "project_dir", return_value=Path(self.tmp.name)),
                   patch.object(store, "load_project", return_value=PROJECT),
                   patch.object(store, "load_project_plan", side_effect=lambda pid: self.plan),
                   patch.object(store, "list_channels", side_effect=lambda: [{"id": "c" * 16, "settings": {"channel_kind": self.kind}}])]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.addCleanup(self.tmp.cleanup)
        director.ACTIVE.clear()

    def test_brief_names_the_episode_steps_and_the_limits(self):
        text = director.brief(PROJECT)
        for part in (PROJECT["id"], "What If/05 Test", 'tools/razgon_bridge.py" prepare', "gen_shots.py", "direction_check.py",
                     'tools/razgon_bridge.py" plan', "Не малюй сцени"):
            self.assertIn(part, text)

    def test_only_animated_channels_and_only_when_direction_is_due(self):
        with patch.object(director, "start") as start:
            self.kind = "regular"
            director.after_voice(PROJECT["id"])
            start.assert_not_called()
            self.kind = "animated"
            self.plan = {"frame_source": "razgon-direction"}
            director.after_voice(PROJECT["id"])          # same sentences: the director's frames stay
            start.assert_not_called()
            self.plan = {"frame_source": "razgon-direction", "director_stale": True}
            director.after_voice(PROJECT["id"])
            start.assert_called_once_with(PROJECT["id"], "voice")
        self.kind = "regular"
        with self.assertRaises(store.StudioError):
            director.start(PROJECT["id"])

    def test_a_run_left_by_a_restart_reads_as_failed(self):
        director.save(PROJECT["id"], {"status": "running", "started_at": time.time()})
        self.assertEqual(director.state(PROJECT["id"])["status"], "failed")

    def test_run_is_done_only_when_a_fresh_director_plan_arrived(self):
        plan_file = Path(self.tmp.name) / "plan.json"
        answer = json.dumps({"is_error": False, "result": "12 шотів, 30 кадрів", "total_cost_usd": 1.5, "num_turns": 40})
        with patch.object(store, "project_plan_file", return_value=plan_file), \
                patch.object(director, "claude", return_value=(0, json.loads(answer))):
            plan_file.write_text("{}")
            os.utime(plan_file, (1, 1))                     # an old plan: the run wrote nothing
            self.plan = {"frame_source": "razgon-direction", "frames": [1] * 30}
            director.ACTIVE.add(PROJECT["id"])
            director.run(PROJECT["id"], Path("claude"))
            self.assertEqual(director.state(PROJECT["id"])["status"], "failed")
            plan_file.write_text("{}")                      # now the plan is newer than the run's start
            director.ACTIVE.add(PROJECT["id"])
            with patch.object(time, "time", return_value=plan_file.stat().st_mtime - 5):
                director.run(PROJECT["id"], Path("claude"))
            result = director.state(PROJECT["id"])
            self.assertEqual((result["status"], result["frames"], result["summary"]), ("done", 30, "12 шотів, 30 кадрів"))
            self.assertNotIn(PROJECT["id"], director.ACTIVE)


if __name__ == "__main__":
    unittest.main()
