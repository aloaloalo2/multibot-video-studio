"""Auto-picked opening: DeepSeek scores hooks, the studio starts the script itself."""
import unittest
from unittest.mock import patch
import test_backend as fixtures
import store
import episode_ideas as ideas


class AutoOpeningTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.BackendTest.setUpClass()
        cls.cid = store.channel_id(fixtures.BackendTest.channel)

    @classmethod
    def tearDownClass(cls):
        fixtures.BackendTest.tearDownClass()

    def setUp(self):
        ideas.ACTIVE.clear()
        ideas.path(self.cid).unlink(missing_ok=True)
        ideas.topics_path(self.cid).unlink(missing_ok=True)
        ctx = {'channel': 'Fixture', 'previous_titles': [], 'samples': [], 'target_words': 1200, 'sample_count': 0}
        patcher = patch.object(ideas, 'context', return_value=ctx); patcher.start(); self.addCleanup(patcher.stop)
        self.hooks = [{'text': f'Opening {n}. ' + 'Natural complete spoken words. ' * 5, 'uk': ''} for n in range(4)]
        store.atomic_json(ideas.path(self.cid), {'id': 'topics', 'ideas': [{'title': f'Fresh topic {n}', 'uk': ''} for n in range(5)],
                          'day': ideas.today(), 'target_words': 1200, 'sample_count': 0, 'context': ctx, 'status': 'done', 'stage': 'ideas'})

    def run_openings(self, enabled, scores):
        with patch.object(ideas, 'Thread'):
            ideas.start(self.cid, {'action': 'openings', 'index': 0, 'new_episode': True})
        data = store.read_json(ideas.path(self.cid))
        with patch.object(ideas, 'opus', return_value={'openings': self.hooks}), \
             patch.object(ideas, 'deepseek', return_value={'scores': scores}) as judge, \
             patch.object(ideas, 'auto_opening_enabled', return_value=enabled), \
             patch.object(ideas, 'start_project') as chain:
            ideas.work(self.cid, data)
        return ideas.read_project(data['project_id']), judge, chain

    def test_best_total_is_picked_and_script_starts(self):
        scores = [{'index': i, 'interest': 5, 'clarity': 5, 'originality': 5, 'low_slop': 5, 'beauty': 5 + (i == 2) * 4, 'reason_uk': 'ok'} for i in range(4)]
        saved, judge, chain = self.run_openings(True, scores)
        self.assertEqual(saved['auto_opening']['index'], 2)
        self.assertEqual(saved['auto_opening']['status'], 'chosen')
        chain.assert_called_once_with(saved['project_id'], {'action': 'script', 'index': 2})

    def test_disabled_setting_never_calls_deepseek(self):
        saved, judge, chain = self.run_openings(False, [])
        judge.assert_not_called(); chain.assert_not_called()
        self.assertNotIn('auto_opening', saved)
        self.assertEqual(saved['openings'], self.hooks)

    def test_bad_scores_leave_manual_choice(self):
        saved, judge, chain = self.run_openings(True, [{'index': 0}])
        self.assertEqual(saved['auto_opening']['status'], 'failed')
        self.assertEqual(saved['status'], 'done')
        chain.assert_not_called()


if __name__ == '__main__':
    unittest.main()
