"""The 16 November 2026 stability pass: a step after another one either goes on or says why on the page."""
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import director
import episode_pause
import languages
import production
import store


class DirectorHandoffTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.patch = patch.object(director.store, "project_dir", return_value=self.dir)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        director.RETIMING.clear()
        director.WANT_FRAMES.clear()

    def test_a_failure_after_the_move_is_kept_for_the_plan_page(self):
        done = threading.Event()

        def frames(pid):
            done.set()
            raise store.StudioError("Сценарій розходиться з озвучкою", 409)
        with patch.object(director, "workspace_estimated", return_value=True), \
             patch.object(director.store, "load_project_plan", return_value={"timing": {"status": "audio_synced"}}), \
             patch.object(director.store, "load_project", return_value={"id": "p"}), \
             patch.object(director, "animated", return_value=True), \
             patch.object(director, "retime", return_value=True), \
             patch.object(production, "start_from_plan", side_effect=frames):
            director.retime_soon("p", create_video=True)
            self.assertTrue(done.wait(5))
            for _ in range(100):
                if (director.state("p") or {}).get("creation_error"):
                    break
                time.sleep(.05)
        self.assertEqual(director.state("p")["creation_error"], "Сценарій розходиться з озвучкою")

    def test_a_second_caller_asking_for_the_frames_is_heard(self):
        gate, done = threading.Event(), threading.Event()

        def retime(pid):
            gate.wait(5)
            return True
        with patch.object(director, "workspace_estimated", return_value=True), \
             patch.object(director.store, "load_project_plan", return_value={"timing": {"status": "audio_synced"}}), \
             patch.object(director.store, "load_project", return_value={"id": "p"}), \
             patch.object(director, "animated", return_value=True), \
             patch.object(director, "retime", side_effect=retime), \
             patch.object(production, "start_from_plan", side_effect=lambda pid: done.set()) as frames:
            director.retime_soon("p", create_video=False)   # the director's own end: no frames asked
            self.assertTrue(director.retime_soon("p", create_video=True))   # the recognition asks for the whole video
            gate.set()
            self.assertTrue(done.wait(5))
        frames.assert_called_once_with("p")

    def test_after_voice_without_create_video_still_says_why_nothing_went_on(self):
        with patch.object(director.store, "project_plan_mode", return_value="director"), \
             patch.object(director.store, "load_project", return_value={"id": "p"}), \
             patch.object(director.store, "load_project_plan", return_value={}), \
             patch.object(director, "animated", return_value=True), \
             patch.object(director, "start", side_effect=store.StudioError("У випуску немає папки", 409)), \
             patch.object(episode_pause, "note", return_value=False):
            director.after_voice("p")   # no raise: the analysis already applied the voice
        self.assertEqual(director.state("p")["creation_error"], "У випуску немає папки")


class PauseTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.patch = patch.object(episode_pause.store, "project_dir", return_value=self.dir)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_the_card_reads_familiar_words(self):
        store.atomic_json(episode_pause.path("p"), {"stopped": {"director": {"reason": "voice"}}, "pending": {}})
        self.assertEqual(episode_pause.label("p"), "План кадрів")
        store.atomic_json(episode_pause.path("p"), {"stopped": {"languages": [{"kind": "voice", "code": "pl"}]}, "pending": {}})
        self.assertEqual(episode_pause.label("p"), "Озвучуємо переклад · PL")

    def test_a_director_that_left_the_pause_is_not_marked_in_it(self):
        import director as d
        store.atomic_json(episode_pause.path("p"), {"stopped": {}, "pending": {}})
        with patch.object(d, "state", return_value={"started_at": 0}), \
             patch.object(episode_pause.store, "load_project_plan", return_value={}), \
             patch.object(episode_pause.store, "load_project", return_value={}), \
             patch.object(episode_pause.store, "project_plan_file", return_value=None):
            episode_pause._settle_director("p", {})   # used to raise KeyError
        self.assertEqual(episode_pause.paused("p")["stopped"], {})


class FramesTest(unittest.TestCase):
    def test_a_failed_run_points_at_the_button_that_works(self):
        project = {"production_request": {"status": "failed", "script_sha256": "s", "error": "Agent crashed"}}
        with patch.object(episode_pause, "note", return_value=False), \
             patch.object(production.store, "load_project", return_value=project), \
             patch.object(production.store, "load_project_plan", return_value={"frames": [{}], "script_sha256": "s"}), \
             patch.object(production.store, "made_frames", return_value=[]):
            with self.assertRaisesRegex(store.StudioError, "Продовжити створення ролика"):
                production.start_from_plan("p")


class LanguageAutomationTest(unittest.TestCase):
    def test_an_automatic_start_that_failed_shows_in_its_card(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(languages.store, "project_dir", return_value=Path(tmp)):
            languages.record_automation_failure("p" * 24, "pl", "voice", "Немає прикладу голосу")
            job = languages.load_state("p" * 24)["jobs"]["pl|voice"]
            self.assertEqual((job["status"], job["error"]), ("failed", "Немає прикладу голосу"))
            languages.ACTIVE.add(languages.job_key("p" * 24, "pl", "voice"))   # the lane works: left alone
            try:
                languages.record_automation_failure("p" * 24, "pl", "voice", "інше")
            finally:
                languages.ACTIVE.discard(languages.job_key("p" * 24, "pl", "voice"))
            self.assertEqual(languages.load_state("p" * 24)["jobs"]["pl|voice"]["error"], "Немає прикладу голосу")


class NarrationProofTest(unittest.TestCase):
    def test_the_recognition_waits_for_the_narration_to_write_done(self):
        import narration_sequence
        import project_narration
        with tempfile.TemporaryDirectory() as tmp, patch.object(narration_sequence.store, "project_dir", return_value=Path(tmp)):
            root = Path(tmp) / "narration"
            root.mkdir()
            store.atomic_json(root / "job.json", {"status": "running"})
            project_narration.ACTIVE.add("p")

            def finish():
                time.sleep(.3)
                store.atomic_json(root / "job.json", {"status": "done", "asset_id": "other"})
                project_narration.ACTIVE.discard("p")
            threading.Thread(target=finish).start()
            began = time.monotonic()
            self.assertIsNone(narration_sequence.verify({"id": "p"}, {"id": "a"}, "Text."))
            self.assertGreater(time.monotonic() - began, .25)   # it read the finished record, not the running one


if __name__ == "__main__":
    unittest.main()


class ReviewFixesTest(unittest.TestCase):
    def test_a_queued_sentence_revision_never_overwrites_the_finished_narration(self):
        import heygen_voice
        import project_narration
        with tempfile.TemporaryDirectory() as tmp, patch.object(project_narration.store, "project_dir", return_value=Path(tmp)):
            root = project_narration.root("p")
            store.atomic_json(root / "job.json", {"status": "done", "asset_id": "a"})
            heygen_voice.JOB_QUEUE[:] = ["narration:other"]
            job, record = {"id": "r"}, root / "revision-job.json"

            def free():
                time.sleep(.3)
                heygen_voice.queue_leave("narration:other")
            threading.Thread(target=free).start()
            try:
                project_narration.wait_heygen("p", job, record)
            finally:
                heygen_voice.queue_leave(project_narration.heygen_owner("p"))
                heygen_voice.JOB_QUEUE.clear()
            self.assertEqual(store.read_json(root / "job.json")["status"], "done")
            self.assertEqual(store.read_json(record)["status"], "queued")   # it waited in its own file

    def test_a_restart_starts_nothing_on_a_paused_episode(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(director.store, "DATA_ROOT", Path(tmp)), \
             patch.object(director.time, "sleep"), \
             patch.object(director, "workspace_estimated", return_value=True), \
             patch.object(director.store, "load_project_plan", return_value={"timing": {"status": "audio_synced"}, "frame_source": "razgon-direction"}), \
             patch.object(episode_pause, "paused", return_value={"stopped": {}}), \
             patch.object(director, "retime_soon") as move:
            (Path(tmp) / "projects" / "p").mkdir(parents=True)
            (Path(tmp) / "projects" / "p" / "razgon-link.json").write_text("{}")
            director.resume_retimes()
        move.assert_not_called()
