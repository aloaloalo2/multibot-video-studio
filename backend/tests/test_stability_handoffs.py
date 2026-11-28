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
        self.assertEqual(episode_pause.label("p"), "План кадрів на паузі")
        store.atomic_json(episode_pause.path("p"), {"stopped": {"languages": [{"kind": "voice", "code": "pl"}]}, "pending": {}})
        self.assertEqual(episode_pause.label("p"), "Озвучка перекладу на паузі · PL")

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


class SignedOutTest(unittest.TestCase):
    def test_an_expired_login_pauses_like_a_limit_and_says_what_to_do(self):
        answer = {"result": "Failed to authenticate: this login reached its time limit and cannot be renewed. Run `claude auth login` to sign in again"}
        self.assertEqual(director.limit_stop(answer), director.AUTH_NOTE)
        self.assertIn("Claude Code", director.AUTH_NOTE)
        self.assertIsNone(director.limit_stop({"result": "Done."}))
        # a request that already failed this way goes on with «Продовжити» (production.resume accepts it)
        self.assertTrue(director.limit_stop({"result": answer["result"]}))


class ClaudeLoginTest(unittest.TestCase):
    def test_the_state_comes_from_claude_codes_own_answer(self):
        import claude_login
        answer = type("Done", (), {"stdout": '{"loggedIn": true, "email": "a@b.c", "loginExpiresAt": "2026-12-15T07:13:33Z", "authMethod": "claude.ai"}'})()
        with patch.object(claude_login.director, "executable", return_value=Path("/bin/claude")), \
             patch.object(claude_login.subprocess, "run", return_value=answer):
            self.assertEqual(claude_login.status(), {"logged_in": True, "email": "a@b.c", "expires_at": "2026-12-15T07:13:33Z", "method": "claude.ai"})
        with patch.object(claude_login.director, "executable", side_effect=RuntimeError("Не знайдено Claude Code на цьому Mac")):
            self.assertEqual(claude_login.status()["logged_in"], False)

    def test_a_code_is_only_passed_to_a_waiting_sign_in(self):
        import claude_login
        claude_login.LOGIN.clear()
        with self.assertRaises(store.StudioError):
            claude_login.submit_code("not a code; rm -rf /")
        with self.assertRaises(store.StudioError):
            claude_login.submit_code("abcdef123456#state")   # well formed, but nothing waits for it

    def test_the_sign_in_shows_its_page_takes_the_code_and_ends_done(self):
        import claude_login, os, stat
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "claude"
            fake.write_text("#!/bin/sh\necho 'Opening browser to sign in...'\n"
                            "echo \"If the browser didn't open, visit: https://claude.com/cai/oauth/authorize?code=true\"\n"
                            "printf 'Paste code here if prompted > '\nread code\n[ \"$code\" = 'abc123#state' ] && echo 'Login successful.'\n")
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
            with patch.object(claude_login.director, "executable", return_value=fake), \
                 patch.object(claude_login, "status", return_value={"logged_in": False}):
                started = claude_login.start()
                self.assertEqual(started["login"]["url"], "https://claude.com/cai/oauth/authorize?code=true")
                self.assertEqual(started["login"]["state"], "waiting")
                claude_login.submit_code(" abc123#state ")
                for _ in range(50):
                    if claude_login.view()["login"]["state"] != "waiting":
                        break
                    time.sleep(.1)
                self.assertEqual(claude_login.view()["login"]["state"], "done")


class BugsToFixTest(unittest.TestCase):
    def test_a_film_with_only_review_bugs_is_done_with_its_frames_to_fix(self):
        review = {"passed": False, "errors": ["Перевірка кадрів Razgon не підтверджена: BUG кадр 31: стрілка"], "frames": [1, 2]}
        with patch.object(production.production_quality, "bugs", return_value={31: "стрілка всередину", 49: "зникли стовпчики"}):
            done = production.bugs_to_fix({}, {"frames": 131}, review)
        self.assertTrue(done["passed"])
        self.assertEqual(done["fix_later"], {"31": "стрілка всередину", "49": "зникли стовпчики"})

    def test_any_other_failure_stays_a_failure(self):
        other = {"passed": False, "errors": ["Не знайдено сцени Razgon для перевірки."]}
        with patch.object(production.production_quality, "bugs", return_value={31: "x"}):
            self.assertIsNone(production.bugs_to_fix({}, {"frames": 3}, other))

    def test_drawn_frames_only_waiting_for_a_look_are_done(self):
        """The Jupiter film, 21 November 2026: a parallel session's change undid the look at frames 46-60 and a stale
        render line hid them from pending_review; the film read «Кадри 1–71 не вдалися» though every frame was made."""
        error = ("Перевірка кадрів Razgon не підтверджена: Frames reviewed ok: 0/13\n  not reviewed: 46, 47, 49\n"
                 "  changed frames needing fresh stills: 46,47\n  RENDER ERROR  shot error: pin is not defined")
        with patch.object(production.production_quality, "bugs", return_value={}):
            done = production.bugs_to_fix({}, {"frames": 71}, {"passed": False, "errors": [error, "Потрібен огляд готової композиції кадрів Studio: 1, 5"]})
        self.assertTrue(done["passed"])
        self.assertEqual(done["look_later"], [1, 5, 46, 47, 49])

    def test_a_label_a_little_off_screen_is_a_bug_to_fix_not_a_failed_film(self):
        """28 November 2026: «Кадри 1–82 не вдалися. Кадр 63: текст виходить за екран на 0.36 с»."""
        errors = ["Кадр 63: текст виходить за екран на 0.36 с. Зменште або перемістіть його блок.",
                  "Кадр 68: слово не вміщується в текстовий блок. Збільште ширину або змініть текст.",
                  "Потрібен огляд готової композиції кадрів Studio: 61, 63"]
        with patch.object(production.production_quality, "bugs", return_value={68: "стрілка"}):
            done = production.bugs_to_fix({}, {"frames": 82}, {"passed": False, "errors": errors})
        self.assertTrue(done["passed"])
        self.assertIn("текст виходить за екран", done["fix_later"]["63"])
        self.assertTrue(done["fix_later"]["68"].startswith("стрілка; слово не вміщується"))
        self.assertEqual(done["look_later"], [61, 63])
        self.assertTrue(production.review_only_failure({"status": "failed", "quality": {"errors": errors}}))

    def test_a_run_cut_by_a_restart_after_its_frames_is_done(self):
        """28 November 2026, Karl's tides: all 86 frames made, the restart's pause hid the play and the done check."""
        cut = {"status": "failed", "paused": True, "paused_by": "restart", "frames": 86, "error": "Студію перезапущено"}
        self.assertTrue(production.cut_after_drawing(cut))
        self.assertFalse(production.cut_after_drawing({**cut, "paused_by": "user"}))
        self.assertFalse(production.cut_after_drawing({**cut, "review_settle_tried": True}))
        saved = {}
        with patch.object(production, "drawn", return_value=True), \
             patch.object(production.production_quality, "check", return_value={"passed": True, "errors": []}), \
             patch.object(production, "set_request", side_effect=lambda pid, **f: saved.update(f) or f), \
             patch.object(production.razgon_sound, "start"), patch.object(production, "film_sounds"), \
             patch.object(production, "ensure_music") as music:
            production.settle_review_failure("p", {}, cut)
        self.assertEqual((saved["status"], saved["paused"], saved["error"]), ("done", False, None))
        music.assert_called_once_with("p")   # the music the cut run never laid

    def test_a_full_disk_reads_as_a_full_disk(self):
        self.assertIn("закінчилось місце", production.DISK_FULL)
