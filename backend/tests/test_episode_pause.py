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

    def test_work_started_by_hand_leaves_the_pause(self):
        store = episode_pause.store
        store.atomic_json(episode_pause.path("p"), {"stopped": {"languages": [{"kind": "voice", "code": "pl"}, {"kind": "voice", "code": "es"}]}, "pending": {}})
        episode_pause.started_by_hand("p", "languages", kind="voice", code="pl")
        self.assertEqual(episode_pause.paused("p")["stopped"]["languages"], [{"kind": "voice", "code": "es"}])
        episode_pause.started_by_hand("p", "languages", kind="voice", code="es")
        self.assertIsNone(episode_pause.paused("p"))   # nothing left: the episode is no longer paused
        episode_pause.started_by_hand("p", "languages", kind="voice", code="es")   # no pause: nothing happens

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
        project = {"id": "p", "voice_script": {"text": "Текст."}}
        with patch.object(director, "start") as start, patch.object(project_narration, "start") as voice, \
             patch.object(episode_pause.store, "load_project", return_value=project), \
             patch.object(episode_pause.store, "load_project_plan", return_value={}), \
             patch.object(director, "ACTIVE", set()), patch.object(project_narration, "ACTIVE", set()):
            episode_pause.resume("p")
        voice.assert_called_once_with(project, "Текст.", resume=True)
        start.assert_called_once_with("p", "script")

    def test_a_script_edited_during_the_pause_is_not_narrated_in_its_old_form(self):
        episode_pause.store.atomic_json(episode_pause.path("p"), {"stopped": {"narration": {"script": "Старий."}}, "pending": {}})
        import director
        import project_narration
        with patch.object(project_narration, "start") as voice, \
             patch.object(episode_pause.store, "load_project", return_value={"id": "p", "voice_script": {"text": "Новий."}}), \
             patch.object(director, "ACTIVE", set()), patch.object(project_narration, "ACTIVE", set()):
            result = episode_pause.resume("p")
        voice.assert_not_called()
        self.assertTrue(result["errors"])

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


class LanguagePauseTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        p = patch.object(episode_pause.store, "project_dir", return_value=self.dir); p.start(); self.addCleanup(p.stop)

    def test_a_translation_voice_stops_at_once_and_goes_on_after(self):
        import director, languages, production, project_narration
        state = {"jobs": {"de|voice": {"kind": "voice", "code": "de", "status": "running"}}}
        with patch.object(episode_pause.store, "load_project", return_value={"id": "p"}), \
             patch.object(languages, "load_state", return_value=state), \
             patch.object(languages, "ACTIVE", {"p|de|voice"}), patch.object(director, "ACTIVE", set()), \
             patch.object(project_narration, "ACTIVE", set()), patch.object(languages, "cancel") as cancel:
            data = episode_pause.pause("p")
        cancel.assert_called_once_with("p", "de|voice")
        self.assertEqual(data["stopped"]["languages"], [{"kind": "voice", "code": "de"}])
        with patch.object(languages, "ACTIVE", set()), patch.object(director, "ACTIVE", set()), \
             patch.object(project_narration, "ACTIVE", set()), patch.object(languages, "start") as start:
            episode_pause.resume("p")
        start.assert_called_once_with("p", "voice", "de")


class StoppedNarrationTest(unittest.TestCase):
    def test_an_old_narration_never_takes_over_once_the_film_follows_a_voice(self):
        import project_narration
        folder = Path(tempfile.mkdtemp())
        episode_pause.store.atomic_json(folder / "job.json", {"status": "cancelled", "script": "Текст.", "completed": 3, "total": 100})
        with patch.object(episode_pause.store, "project_dir", return_value=folder), \
             patch.object(project_narration, "root", return_value=folder), \
             patch.object(episode_pause.store, "load_project", return_value={"id": "p", "voice_script": {"text": "Текст."}}), \
             patch.object(episode_pause.store, "load_project_plan", return_value={"timing": {"status": "audio_synced"}}), \
             patch.object(project_narration, "ACTIVE", set()):
            self.assertFalse(episode_pause.resumable("p"))

    def test_a_narration_stopped_half_way_can_go_on(self):
        import project_narration
        folder = Path(tempfile.mkdtemp())
        episode_pause.store.atomic_json(folder / "job.json", {"status": "cancelled", "script": "Текст.", "completed": 30, "total": 100})
        project = {"id": "p", "voice_script": {"text": "Текст."}}
        with patch.object(episode_pause.store, "project_dir", return_value=folder), \
             patch.object(project_narration, "root", return_value=folder), \
             patch.object(episode_pause.store, "load_project", return_value=project), \
             patch.object(episode_pause.store, "load_project_plan", return_value={}), \
             patch.object(project_narration, "ACTIVE", set()), patch.object(project_narration, "start") as start:
            self.assertTrue(episode_pause.resumable("p"))
            episode_pause.resume("p")
        start.assert_called_once_with(project, "Текст.", resume=True)
