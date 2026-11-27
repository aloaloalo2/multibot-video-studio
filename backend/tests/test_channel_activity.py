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
        for status in ['failed', 'interrupted', 'running', None]:
            notices = Notices()
            notices.update(['channel'], [self.task(), self.task('two')], lambda task: None)
            result = notices.update([], [], lambda task: status if task['project_id'] == 'two' else 'done')
            self.assertEqual(result['channel']['status'], 'stopped')

    def test_the_authors_own_stop_or_pause_is_quiet(self):
        for status in ['cancelled', 'paused_by_user']:
            notices = Notices()
            notices.update(['channel'], [self.task(), self.task('two')], lambda task: None)
            result = notices.update([], [], lambda task: status if task['project_id'] == 'two' else 'done')
            self.assertEqual(result['channel']['status'], 'paused')

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


class PublishedCheckTest(unittest.TestCase):
    """After a publication the channel's check is the publication's blue, even with other work beside it (27 November 2026:
    «після публікації галочка сіра… має бути синя»)."""
    def test_a_publication_beside_an_export_still_marks_the_channel_published(self):
        notices = Notices()
        tasks = [{'channel_id': 'c', 'project_id': 'p', 'kind': 'публікація'}, {'channel_id': 'c', 'project_id': 'p', 'kind': 'експорт'}]
        notices.update(['c'], tasks, lambda task: 'done')
        self.assertTrue(notices.update([], [], lambda task: 'done')['c'].get('publish'))

    def test_work_without_a_publication_stays_grey(self):
        notices = Notices()
        notices.update(['c'], [{'channel_id': 'c', 'project_id': 'p', 'kind': 'експорт'}], lambda task: 'done')
        self.assertNotIn('publish', notices.update([], [], lambda task: 'done')['c'])


class EventSoundsOutcomeTest(unittest.TestCase):
    """27 November 2026: «кадри готові, а галочки біля каналу не було, а лише пауза»."""

    def test_sounds_of_a_regular_film_count_as_done(self):
        from unittest.mock import patch
        import app
        with patch.object(app.razgon_sound, 'state', return_value=None):
            self.assertEqual(app.channel_task_outcome({'kind': 'музика й ефекти', 'channel_id': 'c', 'project_id': 'p'}), 'done')
        with patch.object(app.razgon_sound, 'state', return_value={'status': 'failed'}), \
                patch.object(app, 'project_jobs', return_value={'музика й ефекти': 'failed'}), \
                patch.object(app.episode_pause, 'paused', return_value=None):
            self.assertEqual(app.channel_task_outcome({'kind': 'музика й ефекти', 'channel_id': 'c', 'project_id': 'p'}), 'failed')
