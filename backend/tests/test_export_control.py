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
            self.assertEqual(self.request('/api/projects/'+pid+'/actions', 'POST', {'type':'undo'})[0], 423)
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
