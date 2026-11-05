import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import director  # noqa: E402
import production  # noqa: E402
import razgon_sound  # noqa: E402
import store  # noqa: E402


class RazgonSoundTest(unittest.TestCase):
    """The film's music and effects reach the timeline without a render and without an agent (5 November 2026)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.razgon = base / "razgon" / "projects" / "07"
        self.razgon.mkdir(parents=True)
        episode = base / "What If" / "07 Test"
        episode.mkdir(parents=True)
        self.project = {"id": "a" * 24, "name": "07 Test", "channel_id": "c" * 16, "episode_path": str(episode)}
        self.animated, self.mode = True, "director"
        for item in (patch.object(store, "load_project", side_effect=lambda pid: dict(self.project)),
                     patch.object(store, "project_dir", return_value=base),
                     patch.object(store, "project_animated", side_effect=lambda project: self.animated),
                     patch.object(store, "project_plan_mode", side_effect=lambda project: self.mode),
                     patch.object(store, "razgon_link", side_effect=lambda project: {"project": str(self.razgon)})):
            item.start()
            self.addCleanup(item.stop)
        razgon_sound.ACTIVE.clear()
        razgon_sound.AGAIN.clear()

    def test_only_an_animated_film_with_its_razgon_project_is_due(self):
        self.assertEqual(razgon_sound.due(self.project), {"project": str(self.razgon)})
        self.animated = False                                   # a photo channel: its sound is the Studio's own
        self.assertIsNone(razgon_sound.due(self.project))
        self.animated, self.mode = True, "direct"               # «Без плану»: no frames of a director
        self.assertIsNone(razgon_sound.due(self.project))
        self.mode = "director"
        with patch.object(store, "razgon_link", return_value={"project": str(self.razgon / "gone")}):
            self.assertIsNone(razgon_sound.due(self.project))
        with patch.object(razgon_sound.threading, "Thread") as thread:
            self.animated = False
            self.assertFalse(razgon_sound.start(self.project["id"], "production"))
        thread.assert_not_called()

    def test_the_bridge_runs_its_sound_command_at_a_low_priority_and_reports(self):
        done = subprocess.CompletedProcess([], 0, stdout="Музика й ефекти на таймлайні: «Razgon · музика й ефекти», 53.7 хв\n", stderr="")
        with patch.object(razgon_sound.subprocess, "run", return_value=done) as run:
            razgon_sound.ACTIVE.add(self.project["id"])
            razgon_sound.run(self.project["id"], "production")
        command, kwargs = run.call_args.args[0], run.call_args.kwargs
        self.assertEqual(command[:3], ["nice", "-n", "10"])
        self.assertEqual(command[-3:], ["sound", "--razgon", str(self.razgon)])
        self.assertEqual(kwargs["env"]["MULTIBOT_RENDER_ON_EXPORT"], "1")   # it renders no picture, so the agents' rule holds
        state = razgon_sound.state(self.project["id"])
        self.assertEqual((state["status"], state["reason"]), ("done", "production"))
        self.assertIn("53.7 хв", state["summary"])
        self.assertNotIn(self.project["id"], razgon_sound.ACTIVE)
        failed = subprocess.CompletedProcess([], 1, stdout="", stderr="Traceback\nПлан у студії змінився після prepare\n")
        with patch.object(razgon_sound.subprocess, "run", return_value=failed):
            razgon_sound.ACTIVE.add(self.project["id"])
            razgon_sound.run(self.project["id"], "director")
        state = razgon_sound.state(self.project["id"])
        self.assertEqual((state["status"], state["error"]), ("failed", "План у студії змінився після prepare"))
        self.assertIn("Traceback", (Path(self.tmp.name) / "sound.log").read_text())

    def test_a_second_request_while_one_runs_runs_once_more_after_it(self):
        calls = []
        def bridge(*args, **kwargs):
            calls.append(time.time())
            if len(calls) == 1:
                self.assertTrue(razgon_sound.start(self.project["id"], "production"))   # arrives while the first works
            return subprocess.CompletedProcess([], 0, stdout="ok\n", stderr="")
        with patch.object(razgon_sound.subprocess, "run", side_effect=bridge), patch.object(razgon_sound.threading, "Thread") as thread:
            self.assertTrue(razgon_sound.start(self.project["id"], "director"))
            target = thread.call_args.kwargs
            target["target"](*target["args"])
        self.assertEqual(len(calls), 2)
        self.assertEqual(thread.call_count, 1)
        self.assertEqual(razgon_sound.state(self.project["id"])["reason"], "again")
        self.assertNotIn(self.project["id"], razgon_sound.ACTIVE)

    def test_a_run_left_by_a_restart_reads_as_failed(self):
        store.atomic_json(razgon_sound.state_path(self.project["id"]), {"status": "running"})
        self.assertEqual(razgon_sound.state(self.project["id"])["status"], "failed")

    def test_the_director_and_the_frame_agent_lay_the_sound_when_they_are_done(self):
        plan_file = Path(self.tmp.name) / "plan.json"
        with patch.object(store, "project_plan_file", return_value=plan_file), \
                patch.object(store, "load_project_plan", return_value={"frame_source": "razgon-direction", "frames": [1]}), \
                patch.object(director, "claude", return_value=(0, {"result": "12 шотів"})), \
                patch.object(razgon_sound, "start") as sound:
            plan_file.write_text("{}")
            director.ACTIVE.add(self.project["id"])
            with patch.object(time, "time", return_value=plan_file.stat().st_mtime - 5):
                director.run(self.project["id"], Path("claude"))
            sound.assert_called_once_with(self.project["id"], "director")
            sound.reset_mock()
            director.ACTIVE.add(self.project["id"])
            with patch.object(director, "claude", return_value=(1, {"is_error": True, "result": "збій"})):
                director.run(self.project["id"], Path("claude"))
            sound.assert_not_called()                                                  # a failed direction lays nothing

        request = {"id": "r1", "frames": 2, "total_frames": 9, "start": 0.0, "end": 10.0, "status": "requested"}
        saved = {**self.project, "production_request": request,
                 "tracks": [{"clips": [{"kind": "animation", "title": f"Razgon · кадр {n:03d}"} for n in (1, 2)]}]}
        with patch.object(store, "load_project", side_effect=lambda pid: json.loads(json.dumps(saved))), \
                patch.object(store, "save_project", side_effect=lambda project: saved.update(project)), \
                patch.object(production.director, "claude", return_value=(0, {"result": "Кадри 1–2 готові"})), \
                patch.object(production.frame_progress, "drawn", return_value=[1, 2]), patch.object(production.logo_layer, "place"), \
                patch.object(razgon_sound, "start") as sound:
            production.ACTIVE.add(self.project["id"])
            production.run(self.project["id"], Path("claude"))
            self.assertEqual(saved["production_request"]["status"], "done")
            sound.assert_called_once_with(self.project["id"], "production")
            sound.reset_mock()
            with patch.object(production.frame_progress, "drawn", return_value=[1]):
                production.ACTIVE.add(self.project["id"])
                production.run(self.project["id"], Path("claude"))
            sound.assert_not_called()                                                  # frames missing: no new bed

    def test_the_briefs_ask_for_the_sound_cues_and_keep_them(self):
        text = director.razgon_brief(self.project)
        for part in ("gen_sound.py", '"t": 81.4', "15–25", "0,3 с", '"amb"', 'old.get("sfx", [])', "old_amb", "sound-design.md",
                     "push для цього не потрібен"):
            self.assertIn(part, text)
        self.assertEqual(director.describe("Bash", {"command": "python3 story/gen_sound.py"}),
                         ("opus", "Розставляє звукові ефекти й атмосферу"))
        request = {"frames": 3, "total_frames": 9, "start": 0.0, "end": 10.0}
        self.assertIn("не видаляй і не переписуй його", production.brief(self.project, request))

    def test_the_studio_prunes_a_replaced_m4a_bed(self):
        self.assertTrue(store.RAZGON_RENDER.fullmatch("music_sfx.m4a"))
        self.assertTrue(store.RAZGON_RENDER.fullmatch("music_sfx-1a2b3c4d.m4a"))
        self.assertIsNone(store.RAZGON_RENDER.fullmatch("music_sfx-billionaire-20261105.m4a"))   # 07's own bed stays


if __name__ == "__main__":
    unittest.main()
