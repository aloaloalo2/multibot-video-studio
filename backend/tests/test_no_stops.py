"""A stopped run goes on by itself, a bounded number of times (26 November 2026: «ніяких стопорних моментів»)."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.tests import test_backend as support  # noqa: F401  (sys.path)
import director
import motion_direction
import production
import store


class NoStopsTest(unittest.TestCase):
    def setUp(self):
        on = patch.dict('os.environ', {'VIDEOKEY_NO_AUTO_RETRY': ''})   # this test checks them
        on.start(); self.addCleanup(on.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.request = {}
        self.direction = {}
        for item in (patch.object(store, 'project_dir', return_value=self.dir),
                     patch.object(store, 'load_project', side_effect=lambda pid: {'id': pid, 'production_request': self.request}),
                     patch.object(director, 'state', side_effect=lambda pid: self.direction),
                     patch.object(director, 'stop_asked', return_value=False)):
            item.start()
            self.addCleanup(item.stop)

    def test_a_stopped_frame_run_continues_twice_then_waits(self):
        self.request.update(status='failed', error='Поточний пакет кадрів не завершений')
        with patch.object(production, 'resume') as resume:
            for _ in range(4):
                production.auto_continue('p' * 24)
        self.assertEqual(resume.call_count, 2)
        self.request.update(status='done')
        production.auto_continue('p' * 24)
        self.assertFalse((self.dir / 'production-auto.json').exists())   # a run that ends done starts the count again

    def test_a_pause_or_a_limit_waits_for_the_author(self):
        with patch.object(production, 'resume') as resume:
            for fields in ({'status': 'failed', 'paused': True}, {'status': 'failed', 'limit': True}):
                self.request.clear(); self.request.update(fields)
                production.auto_continue('p' * 24)
        resume.assert_not_called()

    def test_a_failed_direction_runs_again_once(self):
        self.direction.update(status='failed', error='Режисура не записала план кадрів у студію', create_video=True)
        with patch.object(director, 'start') as start:
            director.retry_once('p' * 24)
            director.retry_once('p' * 24)
        start.assert_called_once_with('p' * 24, 'create_video')

    def test_the_agents_are_told_never_to_ask(self):
        self.assertIn('Ніколи не зупиняйся з питанням до автора', motion_direction.NO_QUESTIONS)


if __name__ == '__main__':
    unittest.main()
