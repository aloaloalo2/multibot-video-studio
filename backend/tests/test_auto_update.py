"""The studio updates itself once nothing runs and the author is idle (26 November 2026)."""
import time
import unittest
from unittest.mock import patch

from backend.tests import test_backend as support  # noqa: F401  (sys.path)
import app
import store


class AutoUpdateTest(unittest.TestCase):
    def run_once(self, status='available', last_change=0.0, begin=None):
        calls = {'begin': 0, 'queued': []}
        def fake_begin():
            calls['begin'] += 1
            if begin:
                raise begin
            return True
        with patch.dict(app.UPDATE_MANAGER.state, {'status': status}, clear=True), \
             patch.object(app, 'LAST_CHANGE', last_change), patch.object(app, 'UPDATE_QUEUED', None), \
             patch.object(app, 'UPDATE_RESTARTING', False), patch.object(app, 'begin_update', fake_begin), \
             patch.object(app, 'queue_update', lambda reason: calls['queued'].append(reason)):
            app.auto_update()
        return calls

    def test_a_new_version_is_applied_when_idle(self):
        self.assertEqual(self.run_once()['begin'], 1)

    def test_nothing_happens_without_a_new_version_or_after_a_failed_one(self):
        self.assertEqual(self.run_once('current')['begin'], 0)
        self.assertEqual(self.run_once('update_failed')['begin'], 0)

    def test_an_author_at_work_is_not_interrupted(self):
        self.assertEqual(self.run_once(last_change=time.time())['begin'], 0)

    def test_running_work_queues_the_update_until_it_ends(self):
        calls = self.run_once(begin=store.StudioError('Зараз працює режисер', 409))
        self.assertEqual(calls['queued'], ['Зараз працює режисер'])


if __name__ == '__main__':
    unittest.main()
