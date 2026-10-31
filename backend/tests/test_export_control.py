import time
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.tests import test_backend as support

app, store = support.app, support.store


class ExportControlTest(unittest.TestCase):
    setUpClass = classmethod(support.BackendTest.setUpClass.__func__)
    tearDownClass = classmethod(support.BackendTest.tearDownClass.__func__)
    request = support.BackendTest.request

    def test_export_is_blocked_while_agent_owns_project(self):
        project = store.create_project(store.channel_id(self.channel), 'Agent export lock')
        guard = app.agent_runtime.acquire_project_guard(project['id'], 'agent')
        self.assertIsNotNone(guard)
        ready = {'stage': 'audio_synced', 'plan_ready': True, 'export_ready': True, 'reason': ''}
        try:
            with patch.object(store, 'plan_readiness', return_value=ready), patch.object(app, 'normalize_for_engine', return_value={'timeline_layers': []}):
                with self.assertRaises(store.StudioError):
                    app.start_export(project, True)
        finally:
            guard.close()

    @unittest.skipUnless(__import__('sys').platform=='darwin' and __import__('os').uname().machine=='arm64'
                         and __import__('shutil').which('swiftc'), 'Apple Silicon GPU required')
    def test_gpu_export_runs_through_the_studio_job(self):
        import os
        project = store.create_project(store.channel_id(self.channel), 'GPU studio export')
        manifest = {'width':320,'height':180,'fps':25,'duration':1,'layer_mode':'item',
                    'timeline_layers':[{'clips':[{'type':'animation','content_type':'shape','color':'#a65b24',
                                                  'start':0,'duration':1,'x':.5,'y':.5,'width':1.,'height':1.}]}]}
        ready = {'stage':'audio_synced','plan_ready':True,'export_ready':True,'reason':''}
        with patch.dict(os.environ,{'MULTIBOT_GPU_EXPORT':'1'}), \
             patch.object(store,'plan_readiness',return_value=ready), \
             patch.object(app,'normalize_for_engine',return_value=manifest):
            job=app.start_export(project,True)
            deadline=time.monotonic()+40
            while time.monotonic()<deadline:
                job=app.load_job(job['id'])
                if job['status'] in {'complete','failed','cancelled'}:break
                time.sleep(.05)
            self.assertEqual(job['status'],'complete',job)
            self.assertEqual(job.get('render_mode'),'gpu')
            self.assertFalse(job.get('gpu_fallback'))
            self.assertEqual(job['progress'],100)
            self.assertGreater(Path(job['output_path']).stat().st_size,1024)

    def test_gpu_fallback_resets_progress_and_keeps_project_locked(self):
        project = store.create_project(store.channel_id(self.channel), 'GPU fallback')
        script = Path(self.tmp.name) / 'gpu_fallback_engine.py'
        script.write_text('import json,time\n'
                          'print(json.dumps({"stage":"gpu_start"}),flush=True)\n'
                          'print(json.dumps({"stage":"scene_done","rendered_duration":.8,"total_duration":1}),flush=True)\n'
                          'print(json.dumps({"stage":"gpu_fallback","message":"test"}),flush=True)\n'
                          'time.sleep(30)\n')
        ready = {'stage':'audio_synced', 'plan_ready':True, 'export_ready':True, 'reason':''}
        with patch.object(app,'ENGINE_SCRIPT',script), patch.object(store,'plan_readiness',return_value=ready), \
             patch.object(app,'normalize_for_engine',return_value={'timeline_layers':[]}):
            job = app.start_export(project,True)
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                job=app.load_job(job['id'])
                if job.get('gpu_fallback'):break
                time.sleep(.02)
            self.assertTrue(job.get('gpu_fallback'))
            self.assertEqual(job.get('gpu_fallback_reason'),'test')
            self.assertEqual(job['render_mode'],'standard')
            self.assertEqual(job['progress'],0)
            self.assertIsNone(job['remaining_seconds'])
            self.assertEqual(self.request('/api/projects/'+project['id']+'/actions','POST',{'type':'undo'})[0],423)
            app.cancel_export(job['id'])
            deadline=time.monotonic()+5
            while time.monotonic()<deadline and app.load_job(job['id'])['status']!='cancelled':time.sleep(.02)
            self.assertEqual(app.load_job(job['id'])['status'],'cancelled')

    def test_export_reports_cloud_material_progress(self):
        project = store.create_project(store.channel_id(self.channel), 'Cloud preparation')
        script = Path(self.tmp.name) / 'cloud_engine.py'
        script.write_text('import json,time\nprint(json.dumps({"stage":"preparing_cloud","completed":1,"total":3}),flush=True)\ntime.sleep(30)\n')
        ready = {'stage': 'audio_synced', 'plan_ready': True, 'export_ready': True, 'reason': ''}
        with patch.object(app, 'ENGINE_SCRIPT', script), patch.object(store, 'plan_readiness', return_value=ready), patch.object(app, 'normalize_for_engine', return_value={'timeline_layers': []}):
            job=app.start_export(project,True)
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                job=app.load_job(job['id'])
                if job.get('stage')=='preparing_cloud':break
                time.sleep(.02)
            self.assertEqual((job['cloud_completed'],job['cloud_total']),(1,3))
            self.assertIsNone(job['remaining_seconds'])
            app.cancel_export(job['id'])
            deadline=time.monotonic()+5
            while time.monotonic()<deadline and app.load_job(job['id'])['status']!='cancelled':time.sleep(.02)
            self.assertEqual(app.load_job(job['id'])['status'],'cancelled')

    def test_export_estimates_time_from_rendered_duration(self):
        project = store.create_project(store.channel_id(self.channel), 'Export estimate')
        script = Path(self.tmp.name) / 'progress_engine.py'
        script.write_text('import json,time\ntime.sleep(.3)\nprint(json.dumps({"stage":"scene_done","scene":1,"total":20,"rendered_duration":3,"total_duration":20}),flush=True)\ntime.sleep(30)\n')
        ready = {'stage': 'audio_synced', 'plan_ready': True, 'export_ready': True, 'reason': ''}
        with patch.object(app, 'ENGINE_SCRIPT', script), patch.object(store, 'plan_readiness', return_value=ready), patch.object(app, 'normalize_for_engine', return_value={'timeline_layers': []}):
            job = app.start_export(project, True)
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                job=app.load_job(job['id'])
                if job['progress']>0:break
                time.sleep(.02)
            self.assertEqual(job['progress'],12)
            self.assertGreaterEqual(job['remaining_seconds'],1)
            self.assertEqual(job['stage'],'rendering')
            app.cancel_export(job['id'])
            deadline=time.monotonic()+5
            while time.monotonic()<deadline and app.load_job(job['id'])['status']!='cancelled':time.sleep(.02)
            self.assertEqual(app.load_job(job['id'])['status'],'cancelled')

    def test_export_failure_reports_scene_and_error(self):
        project = store.create_project(store.channel_id(self.channel), 'Export error')
        script = Path(self.tmp.name) / 'failing_engine.py'
        script.write_text('import json,sys\nprint(json.dumps({"stage":"scene_start","scene":3,"total":4}),flush=True)\nprint(json.dumps({"stage":"error","message":"test encoder failure"}),flush=True)\nsys.exit(1)\n')
        ready = {'stage': 'audio_synced', 'plan_ready': True, 'export_ready': True, 'reason': ''}
        with patch.object(app, 'ENGINE_SCRIPT', script), patch.object(store, 'plan_readiness', return_value=ready), patch.object(app, 'normalize_for_engine', return_value={'timeline_layers': []}):
            job = app.start_export(project, True)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                job = app.load_job(job['id'])
                if job['status'] == 'failed': break
                time.sleep(.02)
            self.assertEqual(job['status'], 'failed')
            self.assertEqual(job['error'], 'Сцена 3: test encoder failure')

    def test_cancel_stops_a_render_that_outlives_its_exporter(self):
        # razgon_bridge.py export dies on SIGTERM, while a Razgon render it started ignores it and keeps the output open
        project = store.create_project(store.channel_id(self.channel), 'Export cancellation of a stubborn render')
        script = Path(self.tmp.name) / 'stubborn_engine.py'
        script.write_text('import subprocess,sys,time\n'
                          'code="import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"\n'
                          'subprocess.Popen([sys.executable,"-c",code])\n'
                          'print("started",flush=True)\n'
                          'time.sleep(60)\n')
        ready = {'stage': 'audio_synced', 'plan_ready': True, 'export_ready': True, 'reason': ''}
        with patch.object(app, 'ENGINE_SCRIPT', script), patch.object(app, 'STOP_GRACE', 0.3), \
                patch.object(store, 'plan_readiness', return_value=ready), patch.object(app, 'normalize_for_engine', return_value={'timeline_layers': []}):
            code, first = self.request('/api/projects/'+project['id']+'/export', 'POST', {'confirm_export': True})
            jid = first['job']['id']
            deadline = time.monotonic() + 5
            while app.ACTIVE_EXPORTS.get(jid, {}).get('process') is None and time.monotonic() < deadline: time.sleep(.02)
            time.sleep(.5)
            self.request('/api/jobs/'+jid+'/cancel', 'POST', {})
            deadline = time.monotonic() + 5
            while app.load_job(jid)['status'] != 'cancelled' and time.monotonic() < deadline: time.sleep(.05)
            self.assertEqual(app.load_job(jid)['status'], 'cancelled')

    def test_cancel_duplicate_and_project_lock(self):
        project = store.create_project(store.channel_id(self.channel), 'Export cancellation')
        pid = project['id']
        script = Path(self.tmp.name) / 'slow_engine.py'
        script.write_text('import subprocess,sys,time\n'
                          'from pathlib import Path\n'
                          'out=Path(sys.argv[sys.argv.index("--output")+1])\n'
                          'child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"])\n'
                          'out.with_suffix(".childpid").write_text(str(child.pid))\n'
                          'print("started",flush=True)\n'
                          'time.sleep(60)\n')
        ready = {'stage': 'audio_synced', 'plan_ready': True, 'export_ready': True, 'reason': ''}
        with patch.object(app, 'ENGINE_SCRIPT', script), patch.object(store, 'plan_readiness', return_value=ready), patch.object(app, 'normalize_for_engine', return_value={'timeline_layers': []}):
            code, first = self.request('/api/projects/'+pid+'/export', 'POST', {'confirm_export': True})
            self.assertEqual(code, 202)
            jid = first['job']['id']
            code, duplicate = self.request('/api/projects/'+pid+'/export', 'POST', {'confirm_export': True})
            self.assertEqual(code, 202)
            self.assertEqual(duplicate['job']['id'], jid)
            self.assertEqual(self.request('/api/projects/'+pid+'/export/active')[1]['job']['id'], jid)
            self.assertIn(jid,[item['id'] for item in self.request('/api/exports/active')[1]['jobs']])
            self.assertEqual(self.request('/api/projects/'+pid+'/actions', 'POST', {'type':'undo'})[0], 423)
            self.assertNotEqual(self.request('/api/projects/'+pid+'/razgon-live', 'POST', {})[0], 423)   # it changes nothing
            childfile = store.project_dir(pid) / 'renders' / (jid+'.childpid')
            deadline = time.monotonic() + 5
            while not childfile.exists() and time.monotonic() < deadline: time.sleep(.02)
            self.assertTrue(childfile.exists())
            child = int(childfile.read_text())
            code, result = self.request('/api/jobs/'+jid+'/cancel', 'POST', {})
            self.assertEqual(code, 202)
            self.assertIn(result['job']['status'], {'cancelling', 'cancelled'})
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                job = app.load_job(jid)
                if job['status'] == 'cancelled': break
                time.sleep(.02)
            self.assertEqual(job['status'], 'cancelled')
            self.assertIsNone(job['output_path'])
            self.assertIsNone(self.request('/api/projects/'+pid+'/export/active')[1]['job'])
            self.assertNotIn(jid,[item['id'] for item in self.request('/api/exports/active')[1]['jobs']])
            self.assertNotEqual(self.request('/api/projects/'+pid+'/actions', 'POST', {'type':'undo'})[0], 423)
            self.assertFalse((store.project_dir(pid)/'renders'/(jid+'.mp4')).exists())
            # A terminated child can briefly remain as a zombie until reaped by its parent.
            state = subprocess_state(child)
            self.assertIn(state, {'', 'Z'})


def subprocess_state(pid):
    import subprocess
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'stat='], capture_output=True, text=True)
    return result.stdout.strip()[:1]


if __name__ == '__main__':
    unittest.main()
