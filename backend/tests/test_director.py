import json
import os
import signal
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
                   patch.object(store, "list_channels", side_effect=lambda: [{"id": "c" * 16, "settings": {"channel_kind": self.kind}}]),
                   patch.object(store, "project_animated", side_effect=lambda project: self.kind == "animated")]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.addCleanup(self.tmp.cleanup)
        director.ACTIVE.clear()

    def test_saved_channel_preferences_reach_the_director(self):
        with patch.object(director, "channel_settings", return_value={"accents": True, "generated_image_style": "Наукові схеми"}), \
                patch.object(director.agent_storage, "get_memory", return_value="Сині плашки для важливих тез") as memory:
            text = director.brief(PROJECT)
        memory.assert_called_once_with(PROJECT["channel_id"])
        self.assertIn("Наукові схеми", text)
        self.assertIn("Сині плашки", text)
        self.assertIn("Правила Агентів", text)
        self.assertIn("створенні й доборі кадрів", text)
        self.assertIn("Акценти на кадрах увімкнені", text)

    def test_claude_memory_reaches_the_director_with_a_bounded_budget(self):
        import author_rules
        with patch.object(director.agent_storage, "get_memory", return_value="Поточні правила каналу"), \
                patch.object(store, "get_channel_folder", return_value=Path("/channels/Test")), \
                patch.object(author_rules, "claude_memory", return_value="Нотатки автора") as memory:
            text = director.channel_memory(PROJECT)
        memory.assert_called_once_with("Test", limit=20000)
        self.assertIn("Поточні правила каналу", text)
        self.assertIn("Нотатки автора", text)

    def test_brief_names_the_episode_steps_and_the_limits(self):
        text = director.brief(PROJECT)
        for part in (PROJECT["id"], "What If/05 Test", 'tools/razgon_bridge.py" prepare', "gen_shots.py", "direction_check.py",
                     'tools/razgon_bridge.py" plan', "Не малюй сцени"):
            self.assertIn(part, text)

    def test_saved_style_and_description_reach_planning_and_scene_generation(self):
        import production
        settings={'animation':{'style':'care','title_font':'Noto Serif','assets':False}}
        request={'frames':1,'total_frames':1,'start':0,'end':10}
        import style_lab
        with patch.object(director,'channel_settings',return_value=settings), \
                patch.object(style_lab,'presets',return_value=[{'id':'care','desc':'pastel fixture style'}]):
            text=director.brief(PROJECT)
            self.assertIn('pastel',text)
            self.assertIn('"style": "care"',text)
            self.assertIn('Noto Serif',text)
            self.assertIn('mood().sky',text)
            self.assertIn('S().ui',text)
        self.assertNotIn('Стиль, герої й декорації як у попередніх',production.brief(PROJECT,request))

    def test_photo_channels_get_their_frames_from_the_director_too(self):
        self.kind = "regular"
        text = director.brief(PROJECT)
        for part in (PROJECT["id"], 'tools/studio.py" sentences', 'tools/studio.py" frames', "--dry-run", "director-frames.json", "Не шукай стоки"):
            self.assertIn(part, text)
        self.assertNotIn("razgon_bridge", text)

    def test_direction_starts_after_the_voice_only_when_it_is_due(self):
        with patch.object(director, "start") as start:
            self.kind = "regular"
            director.after_voice(PROJECT["id"])          # a photo channel goes to the director as well
            start.assert_called_once_with(PROJECT["id"], "voice")
            start.reset_mock()
            montage = {**PROJECT, "tracks": [{"clips": [{"id": "p", "kind": "image"}]}], "scene_groups": []}
            with patch.object(store, "load_project", return_value=montage):
                director.after_voice(PROJECT["id"])      # cut on an older plan already: that montage stays as it is
            start.assert_not_called()
            self.kind = "animated"
            self.plan = {"frame_source": "razgon-direction"}
            director.after_voice(PROJECT["id"])          # same sentences: the director's frames stay
            start.assert_not_called()
            self.plan = {"frame_source": "razgon-direction", "director_stale": True}
            director.after_voice(PROJECT["id"])
            start.assert_called_once_with(PROJECT["id"], "voice")

    def test_stopping_a_run_stops_a_render_in_a_process_group_of_its_own(self):
        # the way Claude Code runs a command: the render sits in its own group under the run
        code = ("import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], "
                "start_new_session=True); time.sleep(60)")
        run = subprocess.Popen([sys.executable, "-c", code], start_new_session=True)
        self.addCleanup(run.kill)
        for _ in range(50):
            render = director.descendants(run.pid)
            if render:
                break
            time.sleep(0.1)
        self.assertEqual(len(render), 1)
        director.kill(run)
        run.wait(10)
        for _ in range(50):
            try:
                os.kill(render[0], 0)
            except ProcessLookupError:
                break
            time.sleep(0.1)
        else:
            os.kill(render[0], 9)
            self.fail("the render outlived the stopped run")

    def test_agents_run_with_the_render_left_to_the_export(self):
        with patch.object(director.subprocess, "Popen", side_effect=OSError("no claude")) as popen:
            with self.assertRaises(OSError):
                director.claude(Path("claude"), "brief", Path(self.tmp.name) / "log", Path(self.tmp.name) / "feed.json", 60)
        self.assertEqual(popen.call_args.kwargs["env"][director.NO_RENDER], "1")
        command = popen.call_args.args[0]
        self.assertEqual(command[command.index('--disallowedTools') + 1:command.index('--disallowedTools') + 3], ['Agent', 'Task'])
        self.assertNotIn('Agent', director.ALLOWED)

    def test_selected_model_and_effort_reach_the_cli(self):
        for model in store.DIRECTOR_MODELS:
            for effort in ['low', 'medium', 'high', 'xhigh']:
                with patch.object(director.subprocess, 'Popen', side_effect=OSError('no paid call')) as popen:
                    with self.assertRaises(OSError):
                        director.claude(Path('claude'), 'brief', Path(self.tmp.name)/'log',
                                        Path(self.tmp.name)/'feed.json', 60, model=model, effort=effort)
                command = popen.call_args.args[0]
                self.assertEqual(command[command.index('--model')+1], model)
                self.assertEqual(command[command.index('--effort')+1], effort)
        with patch.object(director.subprocess, 'Popen') as popen:
            with self.assertRaises(store.StudioError):
                director.claude(Path('claude'), 'brief', Path('log'), Path('feed'), 60, model='wrong')
            popen.assert_not_called()

    def test_planning_uses_channel_model_and_reports_it(self):
        with patch.object(store, 'channel_director_model', return_value='claude-fable-5-2'), \
                patch.object(store, 'channel_effort', return_value='low'), \
                patch.object(director, 'brief', return_value='brief'), \
                patch.object(director, 'claude', return_value=(1, {'result': 'test stopped'})) as model:
            director.run(PROJECT['id'], Path('claude'))
        self.assertEqual(model.call_args.kwargs['model'], 'claude-fable-5-2')
        self.assertEqual(model.call_args.kwargs['effort'], 'low')
        self.assertEqual(director.state(PROJECT['id'])['model'], 'claude-fable-5-2')

    def test_terminal_result_finishes_even_when_a_background_tool_keeps_stdout_open(self):
        cli=Path(self.tmp.name)/'fake-claude'
        child_pid=Path(self.tmp.name)/'background.pid'
        result={'type':'result','subtype':'success','is_error':False,'result':'45 frames ready','total_cost_usd':1.25}
        cli.write_text(f'#!{sys.executable}\nimport subprocess,sys,time,json\n'
            f'child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"],start_new_session=True)\n'
            f'open({str(child_pid)!r},"w").write(str(child.pid))\n'
            f'print({json.dumps(json.dumps(result))},flush=True)\n'
            'time.sleep(60)\n')
        cli.chmod(0o700)
        started=time.monotonic()
        with patch.object(director,'RESULT_EXIT_GRACE',.1),patch('spend_report.record_later'):
            code,answer=director.claude(cli,'brief',Path(self.tmp.name)/'stream.log',Path(self.tmp.name)/'activity.json',3)
        self.assertLess(time.monotonic()-started,2)
        self.assertEqual(code,0)
        self.assertEqual(answer,result)
        self.assertNotIn(str(Path(self.tmp.name)/'activity.json'),director.RUNNING)
        pid=int(child_pid.read_text())
        for _ in range(30):
            try:os.kill(pid,0)
            except ProcessLookupError:break
            time.sleep(.05)
        else:
            os.kill(pid,signal.SIGKILL)
            self.fail('The background tool survived the terminal result')

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
