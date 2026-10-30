import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import analysis_jobs  # noqa: E402
import director  # noqa: E402
import episode_restart  # noqa: E402
import store  # noqa: E402

PID = "a" * 24


class EpisodeRestartTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.folder, self.episode = base / "project", base / "What If" / "05 Test"
        self.folder.mkdir()
        self.episode.mkdir(parents=True)
        self.project = {"id": PID, "name": "05 Test", "channel_id": "c" * 16, "channel_name": "What If", "episode_path": str(self.episode),
                        "created_at": 1, "schema_version": 2, "layer_mode": "item", "revision": 7, "width": 1920, "height": 1080, "fps": 25,
                        "duration": 120.0, "assets": [{"id": "voice"}], "settings": {"channel_kind": "animated"},
                        "plan_source": str(self.folder / "imported-plan.json"), "voice_script": {"text": "Hello."},
                        "production_request": {"status": "done"}, "scene_groups": [{"id": "g"}],
                        "tracks": [{"id": "layer-1", "clips": [{"kind": "audio"}, {"kind": "video"}]}]}
        (self.folder / "project.json").write_text(json.dumps(self.project))
        for name in ("imported-plan.json", "analysis-state.json", "director.json", "director.log", "director-activity.json", "production-r1.log"):
            (self.folder / name).write_text("{}")
        (self.folder / "history" / "past").mkdir(parents=True)
        (self.folder / "history" / "past" / "0.json").write_text("{}")
        for name in ("План видео.json", "Запит на створення.json"):
            (self.episode / name).write_text("{}")
        (self.episode / "razgon.json").write_text("{}")
        for item in (patch.object(store, "project_dir", return_value=self.folder), patch.object(director, "animated", return_value=True)):
            item.start()
            self.addCleanup(item.stop)

    def test_restart_backs_everything_up_and_leaves_an_empty_episode(self):
        project = episode_restart.restart(PID)
        self.assertEqual(project["tracks"], [{"id": "layer-1", "name": "Шар 1", "type": "universal", "z_index": 0, "clips": []}])
        for key in ("plan_source", "voice_script", "production_request", "scene_groups"):
            self.assertNotIn(key, project)
        self.assertEqual((project["id"], project["episode_path"], project["assets"], project["revision"], project["duration"]),
                         (PID, str(self.episode), [{"id": "voice"}], 8, 0.0))
        backup = next((self.folder / "restarts").iterdir())
        restore = json.loads((backup / "restore.json").read_text())["files"]
        self.assertEqual(restore["випуск - План видео.json"], str(self.episode / "План видео.json"))
        for name in ("project.json", "imported-plan.json", "analysis-state.json", "director.json", "production-r1.log", "history",
                     "випуск - Запит на створення.json"):
            self.assertTrue((backup / name).exists(), name)
        self.assertEqual(json.loads((backup / "project.json").read_text())["tracks"], self.project["tracks"])
        self.assertFalse((self.episode / "План видео.json").exists())
        self.assertTrue((self.episode / "razgon.json").exists())         # what the agents drew stays in the episode
        self.assertFalse((self.folder / "history").exists())

    def test_a_running_agent_is_stopped_and_writes_nothing_back(self):
        director.ACTIVE.add(PID)
        self.addCleanup(director.ACTIVE.discard, PID)
        director.RUNNING[str(director.activity_path(PID, "director"))] = object()
        self.addCleanup(director.RUNNING.clear)
        with patch.object(director, "kill", side_effect=lambda process: director.ACTIVE.discard(PID)) as kill:
            episode_restart.restart(PID)
        kill.assert_called_once()
        self.assertTrue(director.cancelled(PID, "director"))      # its run ends without saving its state
        self.assertFalse(director.cancelled(PID, "director"))

    def test_waits_for_a_recognition_in_progress(self):
        (self.folder / "analysis-state.json").write_text(json.dumps({"job_id": "job1"}))
        analysis_jobs.ACTIVE_JOBS.add("job1")
        self.addCleanup(analysis_jobs.ACTIVE_JOBS.discard, "job1")
        with self.assertRaises(store.StudioError) as caught:
            episode_restart.restart(PID)
        self.assertEqual(caught.exception.status, 409)
        self.assertTrue((self.folder / "imported-plan.json").exists())


if __name__ == "__main__":
    unittest.main()
