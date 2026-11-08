import copy
import json
import sys
import tempfile
import threading
import urllib.request
from http.server import ThreadingHTTPServer
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent_runtime
import analysis_jobs
import app
import director
import planner
import store


class DirectWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for field, value in {
            'YOUTUBE_ROOT': root / 'youtube', 'DATA_ROOT': root / 'data',
            'PROJECTS_ROOT': root / 'data/projects', 'DISABLED_PATH': root / 'disabled.json',
            'GLOBAL_SETTINGS_PATH': root / 'settings.json',
        }.items():
            p = patch.object(store, field, value)
            p.start()
            self.addCleanup(p.stop)
        self.channel = store.YOUTUBE_ROOT / 'Test'
        self.channel.mkdir(parents=True)
        store.atomic_json(self.channel / store.PLAN_CONFIG, {'weights': {'stock_photo': 100}})
        self.cid = store.channel_id(self.channel)
        self.project = store.create_project(self.cid, 'Episode')
        self.pid = self.project['id']
        self.script = 'First sentence. Second sentence.'
        self.timings = {'duration': 6, 'sentences': [
            {'text': 'First sentence.', 'start': 0.1, 'end': 2.8},
            {'text': 'Second sentence.', 'start': 3, 'end': 5.8},
        ]}
        self.callbacks = {'export_active': lambda _: False}

    def direct(self):
        store.update_channel_settings(self.cid, {'plan_mode': 'direct'})
        self.project = store.apply_action(self.pid, 'set_plan_mode', {'mode':'direct'})

    def source(self):
        return store.generate_project_plan(self.cid, self.project['name'], self.project['episode_path'],
                                           project_id=self.pid, script=self.script, timings=self.timings)

    def test_project_kind_uses_channel_default_only_at_creation(self):
        self.assertFalse(store.project_animated(self.project))
        store.update_channel_settings(self.cid, {'channel_kind':'animated'})
        animated = store.create_project(self.cid, 'Animated episode')
        self.assertTrue(store.project_animated(animated))
        self.assertFalse(store.project_animated(store.load_project(self.pid)))
        store.update_channel_settings(self.cid, {'channel_kind':'regular'})
        self.assertTrue(store.project_animated(store.load_project(animated['id'])))

    def test_channel_mode_is_only_a_creation_default(self):
        store.update_channel_settings(self.cid, {'plan_mode':'direct'})
        new = store.create_project(self.cid, 'Direct episode')
        self.assertEqual(store.project_plan_mode(new), 'direct')
        self.assertEqual(store.project_plan_mode(self.project), 'director')
        store.update_channel_settings(self.cid, {'plan_mode':'director'})
        self.assertEqual(store.project_plan_mode(store.load_project(new['id'])), 'direct')
        before = copy.deepcopy(self.project['tracks'])
        for mode in ('direct', 'director'):
            changed = store.apply_action(self.pid, 'set_plan_mode', {'mode':mode})
            self.assertEqual(changed['tracks'], before)
            self.assertEqual(store.project_plan_mode(store.load_project(self.pid)), mode)

    def test_default_planned_mode_and_invalid_mode(self):
        self.assertEqual(store.project_plan_mode(self.project), 'director')
        self.assertFalse(store.plan_readiness(self.project)['editor_ready'])
        with self.assertRaises(store.StudioError):
            store.update_channel_settings(self.cid, {'plan_mode': 'wrong'})
        self.assertFalse(store.plan_readiness(self.project)['export_ready'])

    def test_empty_direct_project_is_editable_but_export_requires_real_visible_montage(self):
        self.direct()
        readiness = store.plan_readiness(self.project)
        self.assertTrue(readiness['editor_ready'])
        self.assertFalse(readiness['plan_ready'])
        self.assertFalse(readiness['export_ready'])
        result = agent_runtime.execute(self.pid, 'add_clip', {
            'layer_id': 'layer-1', 'kind': 'text', 'text': 'A real scene', 'start': 0,
            'duration': 6, 'expected_revision': self.project['revision'],
        }, self.callbacks, False)
        edited = store.load_project(self.pid)
        self.assertEqual(result['revision'], self.project['revision'] + 1)
        self.assertTrue(store.plan_readiness(edited)['export_ready'])
        self.assertTrue(app.normalize_for_engine(edited)['timeline_layers'])
        edited['tracks'][0]['hidden'] = True
        self.assertFalse(store.plan_readiness(edited)['export_ready'])

    def test_mode_switch_invalidates_cached_readiness_without_rewriting_project(self):
        old_bytes = store.project_path(self.pid).read_bytes()
        self.assertFalse(app.derived_state(self.project)[0]['editor_ready'])
        self.direct()
        self.assertTrue(app.derived_state(self.project)[0]['editor_ready'])
        store.update_channel_settings(self.cid, {'plan_mode': 'director'})
        self.assertTrue(app.derived_state(self.project)[0]['editor_ready'])
        before = copy.deepcopy(self.project['tracks'])
        self.project = store.apply_action(self.pid, 'set_plan_mode', {'mode':'director'})
        self.assertFalse(app.derived_state(self.project)[0]['editor_ready'])
        self.assertEqual(self.project['tracks'], before)

    def test_real_source_saved_without_fabricated_frames_or_timeline_change(self):
        self.direct()
        before = copy.deepcopy(self.project['tracks'])
        with patch.object(planner, 'build_plan', side_effect=AssertionError('Must not build a plan')):
            result = self.source()
        self.assertIsNone(result['plan'])
        self.assertNotIn('frames', result['source'])
        self.assertEqual(result['source']['timing']['sentences'], [dict(item, number=i) for i, item in enumerate(self.timings['sentences'], 1)])
        current = store.load_project(self.pid)
        self.assertNotIn('plan_source', current)
        self.assertEqual(current['tracks'], before)
        self.assertEqual(store.load_project_narration(self.pid), result['source'])
        self.assertFalse((Path(current['episode_path']) / 'План видео.json').exists())
        source = agent_runtime.execute(self.pid, 'get_source', {'offset': 0}, self.callbacks, False)
        self.assertEqual(source['total'], 2)
        self.assertEqual(source['sentences'][0]['text'], 'First sentence.')

    def test_new_source_preserves_legacy_plan_and_mode_chooses_correct_source(self):
        legacy = self.source()['plan']
        old_bytes = Path(store.load_project(self.pid)['plan_source']).read_bytes()
        self.direct()
        self.script = 'A fresh sentence. Second sentence.'
        self.timings['sentences'][0]['text'] = 'A fresh sentence.'
        result = self.source()
        self.assertEqual(Path(store.load_project(self.pid)['plan_source']).read_bytes(), old_bytes)
        self.assertEqual(store.load_project_narration(self.pid)['script'], self.script)
        store.update_channel_settings(self.cid, {'plan_mode': 'director'})
        store.apply_action(self.pid, 'set_plan_mode', {'mode':'director'})
        self.assertEqual(store.load_project_narration(self.pid)['script'], legacy['script'])
        self.assertEqual(store.load_project_source(self.pid), result['source'])

    def test_bad_source_timings_do_not_replace_previous_source(self):
        self.direct()
        self.source()
        path = store.project_dir(self.pid) / 'source-timing.json'
        previous = path.read_bytes()
        self.timings['sentences'][1]['start'] = 0
        with self.assertRaises(store.StudioError):
            self.source()
        self.assertEqual(path.read_bytes(), previous)

    def test_director_and_frame_production_never_start_in_direct_mode(self):
        self.direct()
        with patch.object(director, 'executable') as cli:
            with self.assertRaisesRegex(store.StudioError, 'Без плану'):
                director.start(self.pid)
            cli.assert_not_called()
        with patch.object(director, 'start') as start:
            director.after_voice(self.pid)
            start.assert_not_called()
        with self.assertRaisesRegex(store.StudioError, 'Без плану'):
            store.request_production(self.pid, 1)

    def test_whisper_applies_source_and_does_not_start_director(self):
        self.direct()
        obsolete = store.project_dir(self.pid) / "old-plan.json"
        obsolete.write_text("{broken")
        current = store.load_project(self.pid)
        current["plan_source"] = str(obsolete)
        store.save_project(current)
        audio = {'id': 'a' * 20, 'name': 'voice.wav', 'kind': 'audio', 'path': str(Path(self.tmp.name) / 'voice.wav')}
        with wave.open(audio['path'],'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000); wav.writeframes(b'\0\0'*48000)
        original=Path(audio['path']).read_bytes()
        audio=store.import_asset_file(store.load_project(self.pid), Path(audio['path']), 'upload')
        job = {'id': 'b' * 24, 'project_id': self.pid, 'source_asset_id': audio['id'], 'script_from': 'request'}
        report = {'status': 'matched', 'timings': {**self.timings,'duration':7.5}}
        with patch.object(analysis_jobs.speech, 'transcribe', return_value=([], {'language': 'en'})), \
             patch.object(analysis_jobs.speech_repair, 'repair', return_value=([], [])), \
             patch.object(analysis_jobs.speech, 'compare_script', return_value=report), \
             patch.object(analysis_jobs.threading, 'Thread') as thread, \
             patch.object(director, 'start') as start:
            analysis_jobs.worker(job, self.script, lambda value: None)
        self.assertEqual(job['status'], 'complete', job.get('error'))
        self.assertTrue(job['applied'])
        self.assertEqual(obsolete.read_text(), "{broken")
        prepared_id=store.load_project_source(self.pid)['timing']['audio']['asset_id']
        prepared=next(a for a in store.load_project(self.pid)['assets'] if a['id']==prepared_id)
        self.assertEqual(prepared['narration_ending']['seconds'],1.5)
        self.assertAlmostEqual(prepared['duration'],7.5,places=2)
        self.assertEqual((Path(self.tmp.name)/'voice.wav').read_bytes(),original)
        start.assert_not_called()

    def test_http_project_and_source_routes_reflect_current_mode(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_port}/api/projects/{self.pid}"
        def get(path=""):
            with urllib.request.urlopen(base + path, timeout=3) as response:
                return json.load(response)
        self.assertEqual(get()["project"]["plan_mode"], "director")
        self.direct()
        self.source()
        project = get()["project"]
        self.assertEqual(project["plan_mode"], "direct")
        self.assertTrue(project["production"]["editor_ready"])
        data = get("/plan")
        self.assertIsNone(data["plan"])
        self.assertEqual(data["source"]["script"], self.script)
        store.update_channel_settings(self.cid, {"plan_mode": "director"})
        self.assertEqual(get()["project"]["plan_mode"], "direct")
        store.apply_action(self.pid, "set_plan_mode", {"mode":"director"})
        data = get("/plan")
        self.assertIsNone(data["source"])
        self.assertFalse(get()["project"]["production"]["editor_ready"])

    def test_obsolete_corrupt_plan_cannot_block_direct_source_route(self):
        self.direct()
        path = store.project_dir(self.pid) / "old-plan.json"
        path.write_text("{broken JSON")
        project = store.load_project(self.pid)
        project["plan_source"] = str(path)
        store.save_project(project)
        server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_port}/api/projects/{self.pid}/plan"
        with urllib.request.urlopen(url, timeout=3) as response:
            self.assertEqual(json.load(response), {"plan": None, "source": None, "settings_match": None})
        self.source()
        with urllib.request.urlopen(url, timeout=3) as response:
            self.assertEqual(json.load(response)["source"]["script"], self.script)
        self.assertEqual(path.read_text(), "{broken JSON")

    def test_full_frame_text_uses_own_source_in_direct_mode_with_retained_plan(self):
        self.source()
        self.direct()
        project = store.load_project(self.pid)
        clip = {'text': 'Independent full frame'}
        store.apply_text_binding(project, clip, {'text_role': 'full_frame', 'source_text': clip['text']})
        self.assertEqual(clip['source_text'], 'Independent full frame')


if __name__ == '__main__':
    unittest.main()
