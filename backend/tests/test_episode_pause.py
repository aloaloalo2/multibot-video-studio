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

    def test_opus_writing_pauses_and_play_starts_the_same_step_again(self):
        import episode_ideas
        with patch.object(episode_pause, "running", return_value={"writing": {"stage": "script", "index": 2}}), \
             patch.object(episode_ideas, "start_project") as start:
            episode_pause.pause("p")
        start.assert_called_once_with("p", {"action": "cancel"})
        self.assertEqual(episode_pause.label("p"), "Сценарій на паузі")
        with patch.object(episode_ideas, "start_project") as start, patch.object(episode_ideas, "ACTIVE", {}), \
             patch.object(episode_pause.store, "load_project", return_value={"id": "p"}):
            episode_pause.resume("p")
        body = start.call_args[0][1]
        self.assertEqual((body["action"], body["index"]), ("script", 2))
        self.assertIsNone(episode_pause.paused("p"))

    def test_a_self_review_that_stopped_by_itself_offers_play_and_starts_again(self):
        import episode_ideas
        episode_pause.store.atomic_json(self.dir / "episode-draft.json", {"stage": "editing", "status": "failed",
                                        "author_session": {"session_id": "s"}, "selected_index": -1})
        with patch.object(episode_ideas, "ACTIVE", {}):
            self.assertTrue(episode_pause.resumable("p"))
            self.assertEqual(episode_pause.label("p"), "Саморедактура зупинилась")
            with patch.object(episode_ideas, "start_project") as start, \
                 patch.object(episode_pause.store, "load_project", return_value={"id": "p"}):
                episode_pause.resume("p")
        self.assertEqual(start.call_args[0][1]["action"], "editing")

    def test_the_plan_page_pauses_and_resumes_the_voice_and_the_director_each_alone(self):
        import director
        import project_narration
        project = {"id": "p", "voice_script": {"text": "Текст."}}
        with patch.object(episode_pause, "running", return_value={"narration": {"script": "Текст."}, "director": {"reason": "script"}}), \
             patch.object(project_narration, "cancel") as cancel, patch.object(director, "stop") as stop:
            episode_pause.pause("p", {"narration"})
        cancel.assert_called_once()
        stop.assert_not_called()   # the director works on
        self.assertEqual(set(episode_pause.paused("p")["stopped"]), {"narration"})
        episode_pause.store.atomic_json(episode_pause.path("p"), {"stopped": {
            "narration": {"script": "Текст."}, "director": {"reason": "script"}}, "pending": {"production": {}}})
        with patch.object(director, "start") as start, patch.object(project_narration, "start") as voice, \
             patch.object(episode_pause.store, "load_project", return_value=project), \
             patch.object(episode_pause.store, "load_project_plan", return_value={}), \
             patch.object(director, "ACTIVE", set()), patch.object(project_narration, "ACTIVE", set()):
            episode_pause.resume("p", {"narration"})
            voice.assert_called_once()
            start.assert_not_called()
            left = episode_pause.paused("p")
            self.assertEqual(set(left["stopped"]), {"director"})   # still paused, its noted step waits for it
            self.assertIn("production", left["pending"])
            episode_pause.resume("p", {"director"})
            start.assert_called_once_with("p", "script")
        self.assertIsNone(episode_pause.paused("p"))

    def test_a_paused_sentence_revision_goes_on_with_its_own_text(self):
        # 17 November 2026: the pause wrote the finished voice's script, so play had nothing to go on with
        import narration_revision
        import project_narration
        import director
        root = self.dir / "narration"
        root.mkdir(exist_ok=True)
        store = episode_pause.store
        store.atomic_json(root / "job.json", {"status": "done", "script": "Старий текст."})
        store.atomic_json(root / "revision-job.json", {"id": "fix-yo-12345", "status": "running", "completed": 1, "total": 4})
        (root / "revisions" / "fix-yo-12345").mkdir(parents=True)
        (root / "revisions" / "fix-yo-12345" / "text.txt").write_text("Новый текст с ё.", encoding="utf-8")
        with patch.object(project_narration, "ACTIVE", {"p"}), patch.object(episode_pause.store, "load_project", return_value={"id": "p"}), \
             patch.object(director, "ACTIVE", set()), patch.object(project_narration, "cancel") as cancel:
            data = episode_pause.pause("p")
        cancel.assert_called_once_with("p")
        self.assertEqual(data["stopped"]["narration"], {"revision": "fix-yo-12345"})
        self.assertEqual(episode_pause.label("p"), "Переозвучка на паузі · 25%")
        with patch.object(narration_revision, "start") as revise, patch.object(project_narration, "start") as voice, \
             patch.object(director, "ACTIVE", set()), patch.object(project_narration, "ACTIVE", set()):
            episode_pause.resume("p")
        voice.assert_not_called()   # never the whole film again with the old text
        body = revise.call_args.args[1]
        self.assertEqual(body["text"], "Новый текст с ё.")
        self.assertEqual(body["expected_sha256"], narration_revision.digest("Старий текст."))
        self.assertRegex(body["client_id"], r"^fix-yo-12345-p\d+$")

    def test_a_revision_stopped_by_heygen_limit_offers_play_and_goes_on(self):
        import narration_revision
        import project_narration
        import director
        root = self.dir / "narration"
        root.mkdir(exist_ok=True)
        store = episode_pause.store
        store.atomic_json(root / "job.json", {"status": "done", "script": "Старий текст.", "started_at": 1})
        (root / "revisions" / "fix-12345678").mkdir(parents=True)
        (root / "revisions" / "fix-12345678" / "text.txt").write_text("Новый текст.", encoding="utf-8")
        store.atomic_json(root / "revision-job.json", {"id": "fix-12345678", "status": "failed", "completed": 3, "total": 6, "started_at": 2,
                                                       "error": "Ліміт запитів HeyGen не відпускає кілька хвилин поспіль. Зроблені фрази збережено, продовжіть пізніше"})
        with patch.object(project_narration, "ACTIVE", set()):
            self.assertTrue(episode_pause.resumable("p"))
            self.assertEqual(episode_pause.label("p"), "Переозвучка на паузі · 50%")
        with patch.object(narration_revision, "start") as revise, patch.object(project_narration, "start") as voice, \
             patch.object(director, "ACTIVE", set()), patch.object(project_narration, "ACTIVE", set()):
            episode_pause.resume("p")
        voice.assert_not_called()
        self.assertEqual(revise.call_args.args[1]["text"], "Новый текст.")
        # a revision that failed on its own text is not offered again
        store.atomic_json(root / "revision-job.json", {"id": "fix-12345678", "status": "failed", "started_at": 2,
                                                       "error": "Змінене речення суттєво відрізняється за тривалістю."})
        with patch.object(project_narration, "ACTIVE", set()):
            self.assertFalse(episode_pause.resumable("p"))

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

    def test_play_after_a_pause_in_the_early_kit_makes_the_kit_beside_the_voice(self):
        # 17 November 2026: the Moon film's kit stopped before its sheets, and play resumed only the voice
        episode_pause.store.atomic_json(episode_pause.path("p"), {"stopped": {
            "director": {"reason": "script", "create_video": False, "stage": "kit", "directed": True}}, "pending": {}})
        import director
        import project_narration
        with patch.object(director, "start_kit", return_value=True) as kit, patch.object(director, "start") as again, \
             patch.object(director, "ACTIVE", set()), patch.object(project_narration, "ACTIVE", set()):
            episode_pause.resume("p")
        kit.assert_called_once_with("p")
        again.assert_not_called()   # the plan is written: no new direction

    def test_play_of_a_stopped_voice_with_its_director_done_starts_a_missing_kit(self):
        # 17 November 2026: this play answered «Внутрішня помилка студії» (run was None) while the voice went on
        import director
        import project_narration
        import script_timing
        episode_pause.store.atomic_json(episode_pause.path("p"), {"stopped": {"narration": {"script": "Текст."}}, "pending": {}})
        project = {"id": "p", "voice_script": {"text": "Текст."}}
        with patch.object(director, "start_kit", return_value=True) as kit, patch.object(director, "state", return_value={"status": "done"}), \
             patch.object(project_narration, "start") as voice, patch.object(script_timing, "estimated", return_value=True), \
             patch.object(episode_pause.store, "load_project", return_value=project), \
             patch.object(episode_pause.store, "load_project_plan", return_value={}), \
             patch.object(director, "ACTIVE", set()), patch.object(project_narration, "ACTIVE", set()):
            result = episode_pause.resume("p")
        voice.assert_called_once()
        kit.assert_called_once_with("p")
        self.assertEqual(result["errors"], [])

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
