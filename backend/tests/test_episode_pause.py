import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import episode_pause


class EpisodePauseTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.patch = patch.object(episode_pause.store, "project_dir", return_value=self.dir)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_a_step_on_a_paused_episode_waits_and_runs_on_resume(self):
        self.assertFalse(episode_pause.note("p", "production"))   # not paused: the step goes on
        episode_pause.store.atomic_json(episode_pause.path("p"), {"stopped": {}, "pending": {}})
        self.assertTrue(episode_pause.note("p", "after_voice", create_video=True))
        import director
        import project_narration
        with patch.object(director, "after_voice") as after_voice, \
             patch.object(director, "ACTIVE", set()), patch.object(project_narration, "ACTIVE", set()):
            result = episode_pause.resume("p")
        after_voice.assert_called_once_with("p", create_video=True)
        self.assertEqual(result["resumed"], ["after_voice"])
        self.assertIsNone(episode_pause.paused("p"))

    def test_resume_restarts_what_the_pause_stopped(self):
        episode_pause.store.atomic_json(episode_pause.path("p"), {"stopped": {
            "narration": {"script": "Текст."}, "director": {"reason": "script", "create_video": False}}, "pending": {}})
        import director
        import project_narration
        with patch.object(director, "start") as start, patch.object(project_narration, "start") as voice, \
             patch.object(episode_pause.store, "load_project", return_value={"id": "p"}), \
             patch.object(director, "ACTIVE", set()), patch.object(project_narration, "ACTIVE", set()):
            episode_pause.resume("p")
        voice.assert_called_once_with({"id": "p"}, "Текст.", resume=True)
        start.assert_called_once_with("p", "script")

    def test_a_director_stopped_in_the_early_kit_is_not_run_again(self):
        episode_pause.store.atomic_json(episode_pause.path("p"), {"stopped": {
            "director": {"reason": "script", "directed": True}}, "pending": {}})
        import director
        import project_narration
        with patch.object(director, "start") as start, \
             patch.object(director, "ACTIVE", set()), patch.object(project_narration, "ACTIVE", set()):
            episode_pause.resume("p")
        start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
