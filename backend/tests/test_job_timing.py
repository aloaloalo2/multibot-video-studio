import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import job_timing
import store


class JobTimingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / 'project'
        self.folder.mkdir()
        self.pid = 'a' * 24
        self.patches = [patch.object(store, 'project_dir', return_value=self.folder),
                        patch.object(store, 'load_project', return_value={'id': self.pid})]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.clock = SimpleNamespace(now=0., wall=1000.)
        clock = SimpleNamespace(monotonic=lambda: self.clock.now, time=lambda: self.clock.wall,
                                time_ns=lambda: int(self.clock.wall * 1_000_000_000))
        self.clock_patch = patch.object(job_timing, 'time', clock)
        self.clock_patch.start()
        self.addCleanup(self.clock_patch.stop)
        self.assertFalse(job_timing.ACTIVE)

    def step(self, seconds):
        self.clock.now += seconds
        self.clock.wall += seconds

    def runs(self):
        return job_timing.overview(self.pid)['runs']

    def test_nested_stages_count_exclusive_time_and_keep_worker_result(self):
        state = {'id': 'job-1', 'status': 'running'}

        @job_timing.track('analysis', project='pid', job='job')
        def work(pid, job):
            self.step(2)
            with job_timing.span('queue'):
                self.step(3)
            with job_timing.span('service'):
                self.step(4)
                with job_timing.span('service'):
                    self.step(2)
                with job_timing.span('verification'):
                    self.step(1)
            with job_timing.span('saving'):
                self.step(2)
            job['status'] = 'done'
            return 'same result'

        self.assertEqual(work(self.pid, state), 'same result')
        row = self.runs()[0]
        self.assertEqual(row['status'], 'complete')
        self.assertEqual(row['elapsed_ms'], 14000)
        self.assertEqual({key: value['ms'] for key, value in row['stages'].items()},
                         {'preparation': 2000, 'queue': 3000, 'service': 6000, 'verification': 1000, 'saving': 2000})
        self.assertEqual(sum(value['ms'] for value in row['stages'].values()), row['elapsed_ms'])
        self.assertFalse(job_timing.ACTIVE)
        self.assertIsNone(job_timing.CURRENT.get())

    def test_failed_worker_and_cancel_keep_their_original_exceptions(self):
        class Cancelled(Exception):
            pass

        for error, status in [(ValueError('original error'), 'failed'), (Cancelled(), 'cancelled')]:
            @job_timing.track('narration', project='pid')
            def work(pid):
                self.step(1)
                with job_timing.span('service'):
                    self.step(2)
                    raise error
            with self.assertRaises(type(error)) as caught:
                work(self.pid)
            self.assertIs(caught.exception, error)
            self.assertEqual(self.runs()[0]['status'], status)
            self.assertFalse(job_timing.ACTIVE)
            self.assertIsNone(job_timing.CURRENT.get())

    def test_disk_failure_cannot_retry_or_fail_the_actual_work(self):
        calls = []

        @job_timing.track('script', project='pid')
        def work(pid):
            calls.append(pid)
            for _ in range(500):
                with job_timing.span('service'):
                    self.step(.001)
            return 'accepted script'

        with patch.object(job_timing, 'atomic_json', side_effect=OSError('disk full')) as writes:
            self.assertEqual(work(self.pid), 'accepted script')
        self.assertEqual(writes.call_count, 2)
        self.assertEqual(calls, [self.pid])
        self.assertFalse(job_timing.ACTIVE)

    def test_read_is_live_but_never_writes_or_finishes_a_running_job(self):
        @job_timing.track('planning', project='pid')
        def work(pid):
            path = next((self.folder / 'performance').glob('*.json'))
            original = path.read_bytes()
            self.step(8)
            first = self.runs()[0]
            self.step(2)
            second = self.runs()[0]
            self.assertEqual(first['elapsed_ms'], 8000)
            self.assertEqual(second['elapsed_ms'], 10000)
            self.assertEqual(second['status'], 'running')
            self.assertEqual(path.read_bytes(), original)
        work(self.pid)
        self.assertEqual(self.runs()[0]['status'], 'complete')

    def test_wall_clock_changes_do_not_change_elapsed_time(self):
        @job_timing.track('export', project='pid')
        def work(pid):
            self.step(2)
            self.clock.wall -= 300
            self.step(3)
        work(self.pid)
        self.assertEqual(self.runs()[0]['elapsed_ms'], 5000)

    def test_closed_worker_status_is_read_even_when_it_catches_an_error(self):
        state = {'status': 'running'}

        @job_timing.track('production', project='pid', job=lambda values: state)
        def work(pid):
            self.step(3)
            state['status'] = 'failed'
        work(self.pid)
        self.assertEqual(self.runs()[0]['status'], 'failed')

    def test_late_finish_never_recreates_a_deleted_project(self):
        @job_timing.track('script', project='pid')
        def work(pid):
            shutil.rmtree(self.folder)
            self.step(1)
        work(self.pid)
        self.assertFalse(self.folder.exists())
        self.assertFalse(job_timing.ACTIVE)

    def test_old_runs_are_bounded_and_other_project_files_stay_intact(self):
        media = self.folder / 'original.mp3'
        media.write_bytes(b'accepted audio')

        @job_timing.track('thumbnail', project='pid')
        def work(pid):
            self.step(1)
        with patch.object(job_timing, 'MAX_RUNS', 3):
            for _ in range(8):
                work(self.pid)
            self.assertEqual(len(self.runs()), 3)
            self.assertEqual(len(list((self.folder / 'performance').glob('*.json'))), 3)
        self.assertEqual(media.read_bytes(), b'accepted audio')

    def test_interrupted_or_malformed_reports_do_not_mutate_saved_data(self):
        trace = job_timing.Measurement(self.pid, 'analysis')
        self.step(4)
        trace.flush(force=True)
        job_timing.ACTIVE.pop(trace.id)
        original = trace.path.read_bytes()
        self.assertEqual(self.runs()[0]['status'], 'interrupted')
        self.assertEqual(trace.path.read_bytes(), original)
        row = json.loads(original)
        row['id'] = 'b' * 32
        row['stages']['preparation']['ms'] = 'bad value'
        (trace.path.parent / 'bad.json').write_text(json.dumps(row))
        (trace.path.parent / 'broken.json').write_text('{bad json')
        self.assertEqual(len(self.runs()), 1)

    def test_thread_contexts_are_independent(self):
        self.clock_patch.stop()
        barrier = threading.Barrier(3)
        release = threading.Event()
        errors = []

        @job_timing.track('narration', project='pid', job='job')
        def work(pid, job):
            try:
                with job_timing.span(job['stage']):
                    barrier.wait(3)
                    release.wait(3)
                    self.assertEqual(job_timing.CURRENT.get().job_id, job['id'])
                job['status'] = 'done'
            except Exception as error:
                errors.append(error)

        threads = [threading.Thread(target=work, args=(self.pid, {'id': name, 'stage': stage}))
                   for name, stage in [('one', 'service'), ('two', 'recognition')]]
        for thread in threads:
            thread.start()
        try:
            barrier.wait(3)
            self.assertEqual({row['active_stage'] for row in self.runs()}, {'service', 'recognition'})
        finally:
            release.set()
            for thread in threads:
                thread.join(3)
        self.assertFalse(errors, errors)
        self.assertFalse(job_timing.ACTIVE)
        for row in self.runs():
            other = 'recognition' if row['job_id'] == 'one' else 'service'
            self.assertNotIn(other, row['stages'])


if __name__ == '__main__':
    unittest.main()
