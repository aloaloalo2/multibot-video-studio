"""Exercise cancellation and interrupted accounting with local child processes only."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import store
import writing_jobs as jobs


class WritingJobsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def receipt(self):
        return store.read_json(self.root / 'test-receipt.json')

    def amount(self):
        return store.read_json(self.root / 'project-costs.json')['events']['claude_code:test']['amount']

    def test_completed_local_process_records_one_charge(self):
        cmd = [sys.executable, '-c', 'import json; print(json.dumps({"result":"ok","total_cost_usd":.12}))']
        with jobs.scope({}):
            code, answer = jobs.run(cmd, 'text', self.root, 'test')
        self.assertEqual((code, answer['result']), (0, 'ok'))
        self.assertEqual(self.receipt()['status'], 'complete')
        self.assertEqual(self.amount(), .12)
        self.assertEqual(len(store.read_json(self.root / 'project-costs.json')['events']), 1)

    def test_timeout_retains_unknown_cost_and_reaps_child(self):
        with jobs.scope({}), self.assertRaises(subprocess.TimeoutExpired):
            jobs.run([sys.executable, '-c', 'import time; time.sleep(20)'], '', self.root, 'test', timeout=.1)
        self.assertEqual(self.receipt()['status'], 'interrupted')
        self.assertIsNone(self.amount())
        self.assertFalse(jobs.PROCESSES)

    def test_cancel_kills_only_owned_author_and_waits_for_exit(self):
        ready = threading.Event()
        original = jobs.subprocess.Popen
        job, caught = {}, []
        def popen(*args, **kwargs):
            process = original(*args, **kwargs)
            ready.set()
            return process
        def work():
            with jobs.scope(job):
                try:
                    jobs.run([sys.executable, '-c', 'import time; time.sleep(20)'], '', self.root, 'test')
                except jobs.Cancelled:
                    caught.append(True)
        with patch.object(jobs.subprocess, 'Popen', side_effect=popen):
            worker = threading.Thread(target=work)
            worker.start()
            self.assertTrue(ready.wait(2))
            jobs.cancel(job)
            worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(caught, [True])
        self.assertEqual(self.receipt()['status'], 'cancelled')
        self.assertFalse(jobs.PROCESSES)
        self.assertIsNone(self.amount())

    def test_cancel_before_launch_starts_nothing_and_restores_scope(self):
        with patch.object(jobs.subprocess, 'Popen') as process:
            with jobs.scope({'cancelled': True}), self.assertRaises(jobs.Cancelled):
                jobs.run([], '', self.root, 'test')
        process.assert_not_called()
        self.assertFalse((self.root / 'test-receipt.json').exists())
        self.assertIsNone(getattr(jobs.LOCAL, 'job', None))

    def test_author_uses_channel_effort_without_tools_or_old_session(self):
        import episode_ideas
        with patch.object(store,'channel_effort',return_value='medium') as effort, \
                patch.object(episode_ideas.director,'executable',return_value=Path('claude')), \
                patch.object(jobs,'run',return_value=(0,{'result':'{"script":"example"}'})) as run:
            result=episode_ideas.opus('Prompt',self.root,'test','channel')
        effort.assert_called_once_with({'channel_id':'channel'})
        command=run.call_args.args[0]
        self.assertEqual(command[command.index('--effort')+1],'medium')
        self.assertEqual(command[command.index('--tools')+1],'')
        self.assertNotIn('--resume',command)
        self.assertEqual(result['script'],'example')
