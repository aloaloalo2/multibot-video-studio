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


class UnpackTest(unittest.TestCase):
    def test_a_draft_then_a_corrected_answer_reads_as_the_last_one(self):
        import episode_ideas
        text = '{"openings":[{"text":"draft"}]}\n\n\n\n{"openings":[{"text":"final"}]}'
        self.assertEqual(episode_ideas.unpack(text)['openings'][0]['text'], 'final')
        self.assertEqual(episode_ideas.unpack('```json\n{"a":1}\n```'), {'a': 1})
        with self.assertRaises(ValueError):
            episode_ideas.unpack('not json at all')


class SafetyRetryTest(unittest.TestCase):
    def test_a_safety_refusal_is_retried_once_in_a_new_session(self):
        import episode_ideas, writing_jobs, director
        from unittest import mock
        refused = {'is_error': True, 'stop_reason': 'refusal', 'result': "API Error: Opus 5.5's safeguards flagged this message"}
        calls = []
        def run(cmd, prompt, root, identity, **options):
            calls.append(cmd[cmd.index('--session-id') + 1])
            if len(calls) == 1:
                return 1, refused
            return 0, {'result': '{"script":"ok"}', 'session_id': calls[-1], 'modelUsage': {}}
        session = {'session_id': 'first', 'model': director.MODEL, 'effort': 'high', 'api_cost_usd': 0}
        with mock.patch.object(writing_jobs, 'run', side_effect=run), mock.patch.object(writing_jobs, 'check'):
            self.assertEqual(episode_ideas.opus('p', None, 'script-x', 'c', session=session), {'script': 'ok'})
        self.assertEqual(len(calls), 2); self.assertNotEqual(calls[0], calls[1]); self.assertEqual(session['session_id'], calls[1])
        calls.clear()
        with mock.patch.object(writing_jobs, 'run', return_value=(1, refused)), mock.patch.object(writing_jobs, 'check'):
            with self.assertRaises(RuntimeError) as error:
                episode_ideas.opus('p', None, 'script-y', 'c', session=dict(session))
        self.assertIn('Фільтр безпеки', str(error.exception))

    def test_a_lost_connection_resumes_the_same_session_again_and_again(self):
        import episode_ideas, writing_jobs, director
        from unittest import mock
        lost = {'is_error': True, 'terminal_reason': 'api_error', 'result': 'API Error: Connection lost mid-response. The response above may be incomplete.'}
        calls = []
        def run(cmd, prompt, root, identity, **options):
            calls.append((cmd, prompt))
            if len(calls) == 1:
                return 1, lost
            return 0, {'result': '{"script":"ok"}', 'session_id': 'first', 'modelUsage': {}}
        session = {'session_id': 'first', 'model': director.MODEL, 'effort': 'high', 'api_cost_usd': 0}
        with mock.patch.object(writing_jobs, 'run', side_effect=run), mock.patch.object(writing_jobs, 'check'), \
             mock.patch.object(episode_ideas.time, 'sleep'):
            self.assertEqual(episode_ideas.opus('p', None, 'edit-x', 'c', session=session, resume=True), {'script': 'ok'})
        self.assertEqual(len(calls), 2)
        self.assertIn('--resume', calls[1][0]); self.assertIn('first', calls[1][0])
        self.assertTrue(calls[1][1].startswith(episode_ideas.RESEND))
        with mock.patch.object(writing_jobs, 'run', return_value=(1, lost)) as runs, mock.patch.object(writing_jobs, 'check'), \
             mock.patch.object(episode_ideas.time, 'sleep'):
            with self.assertRaises(RuntimeError) as error:
                episode_ideas.opus('p', None, 'edit-y', 'c', session=dict(session), resume=True)
        # two drops in the author's session move to a fresh session, which also gets one more try (19 November 2026)
        self.assertEqual(runs.call_count, 2 * (episode_ideas.LOST_RETRIES + 1))
        self.assertIn("обривалось", str(error.exception))

    def test_the_writer_gets_no_model_routing_sections(self):
        import writer_context
        text = '## Живая речь\nПиши живо.\n\n## Сценарии только Claude Opus 5.5 Medium\nУсилие medium.\n\n## Теги\nТри тега.'
        out = writer_context.writer_rules(text)
        self.assertIn('Пиши живо', out); self.assertIn('Три тега', out); self.assertNotIn('Opus', out)
