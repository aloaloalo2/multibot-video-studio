import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from channel_activity import Notices


class ChannelActivityTest(unittest.TestCase):
    def task(self, pid='one', kind='кадри'):
        return {'channel_id': 'channel', 'project_id': pid, 'kind': kind}

    def test_done_notice_only_after_all_channel_work_finishes(self):
        notices = Notices()
        self.assertEqual(notices.update(['channel'], [self.task(), self.task('two')], lambda task: 'done'), {})
        self.assertEqual(notices.update(['channel'], [self.task('two')], lambda task: 'done'), {})
        result = notices.update([], [], lambda task: 'done')
        self.assertEqual(result['channel']['status'], 'done')
        self.assertEqual(notices.update([], [], lambda task: self.fail()), result)

    def test_failure_or_unreadable_receipt_is_never_success(self):
        for status in ['failed', 'cancelled', 'running', None]:
            notices = Notices()
            notices.update(['channel'], [self.task(), self.task('two')], lambda task: None)
            result = notices.update([], [], lambda task: status if task['project_id'] == 'two' else 'done')
            self.assertEqual(result['channel']['status'], 'stopped')

    def test_successful_new_cycle_replaces_failure_with_new_identity(self):
        notices = Notices()
        notices.update(['channel'], [self.task()], lambda task: None)
        previous = notices.update([], [], lambda task: 'failed')['channel']
        notices.update(['channel'], [self.task()], lambda task: None)
        current = notices.update([], [], lambda task: 'done')['channel']
        self.assertEqual(current['status'], 'done')
        self.assertNotEqual(current['id'], previous['id'])

    def test_no_historical_scan_and_channels_are_independent(self):
        notices = Notices()
        self.assertEqual(notices.update([], [], lambda task: self.fail()), {})
        notices.update(['channel', 'other'], [self.task(), {**self.task(), 'channel_id': 'other'}], lambda task: None)
        result = notices.update(['other'], [], lambda task: 'complete')
        self.assertEqual(set(result), {'channel'})

    def test_read_failure_is_stopped(self):
        notices = Notices()
        notices.update(['channel'], [self.task()], lambda task: None)
        def broken(task):
            raise OSError('unavailable')
        self.assertEqual(notices.update([], [], broken)['channel']['status'], 'stopped')
