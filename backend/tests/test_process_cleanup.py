"""Local sleeping children exercise the failure paths without any inference."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import app
import director
import store
import writing_jobs


class ProcessCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.children = []
        self.popen = subprocess.Popen
        self.addCleanup(self.reap)

    def child(self, *args, **kwargs):
        child = self.popen([sys.executable, '-c', 'import time; time.sleep(30)'], **kwargs)
        self.children.append(child)
        return child

    def reap(self):
        for child in self.children:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)

    def test_failed_author_pipe_terminates_and_reaps_the_owned_process(self):
        def broken(*args, **kwargs):
            child = self.child(*args, **kwargs)
            child.communicate = Mock(side_effect=OSError('Pipe failed'))
            return child
        with patch.object(writing_jobs.subprocess, 'Popen', side_effect=broken), writing_jobs.scope({}):
            with self.assertRaisesRegex(OSError, 'Pipe failed'):
                writing_jobs.run(['mock'], 'Full script', self.root, 'failure')
        self.assertIsNotNone(self.children[0].poll())
        self.assertTrue(self.children[0].stdout.closed)
        self.assertFalse(writing_jobs.PROCESSES)
        self.assertEqual(store.read_json(self.root / 'failure-receipt.json')['status'], 'failed')

    def test_director_activity_write_failure_cannot_leave_the_author_running(self):
        activity = self.root / 'activity.json'
        with patch.object(director.subprocess, 'Popen', side_effect=self.child), \
                patch.object(store, 'atomic_json', side_effect=OSError('Disk full')), \
                patch.object(director,'descendants',return_value=[]), \
                patch('spend_report.record_later'):
            with self.assertRaisesRegex(OSError, 'Disk full'):
                director.claude(Path('/mock'), 'Full brief', self.root / 'log', activity, 60)
        self.assertIsNotNone(self.children[0].poll())
        self.assertNotIn(str(activity), director.RUNNING)

    def test_export_progress_write_failure_stops_encoder_before_releasing_the_slot(self):
        source, output, destination = self.root / 'input.json', self.root / 'staging.mp4', self.root / 'final.mp4'
        store.atomic_json(source, {'scenes': []})
        job = {'id': 'job', 'project_id': 'p', 'status': 'queued', 'progress': 0}
        guard = Mock()
        entry = {'job': job, 'process': None, 'cancel': False, 'project_guard': guard}
        def encoder(*args, **kwargs):
            child = self.popen([sys.executable, '-c', 'import json,time; print(json.dumps({"stage":"validated"}),flush=True); time.sleep(30)'], **kwargs)
            self.children.append(child)
            return child
        def save(value):
            if entry['process'] is not None and value['status'] == 'running':
                raise OSError('Disk full')
        with patch.object(app, 'ACTIVE_EXPORTS', {'job': entry}), patch.object(app, 'save_job', side_effect=save), \
                patch.object(app.subprocess, 'Popen', side_effect=encoder):
            app._render_worker(job, source, output, destination, ['mock'])
            self.assertEqual(app.ACTIVE_EXPORTS, {})
        self.assertEqual(job['status'], 'failed')
        self.assertIsNotNone(self.children[0].poll())
        guard.close.assert_called_once()

    def test_optional_language_refresh_does_not_fail_an_already_verified_export(self):
        source, output, destination = self.root / 'input.json', self.root / 'staging.mp4', self.root / 'final.mp4'
        store.atomic_json(source, {'scenes': []})
        job = {'id': 'job', 'project_id': 'p', 'status': 'queued', 'progress': 0}
        guard = Mock()
        entry = {'job': job, 'process': None, 'cancel': False, 'project_guard': guard}
        command = [sys.executable, '-c', 'from pathlib import Path; import sys; Path(sys.argv[1]).write_bytes(b"complete video")', str(output)]
        with patch.object(app, 'ACTIVE_EXPORTS', {'job': entry}), patch.object(app, 'save_job'), \
                patch.object(app, '_check_render'), patch.object(app.language_mix, 'refresh_later', side_effect=RuntimeError('No thread')):
            app._render_worker(job, source, output, destination, command)
        self.assertEqual(job['status'], 'complete')
        self.assertEqual(job['progress'], 100)
        self.assertEqual(destination.read_bytes(), b'complete video')
