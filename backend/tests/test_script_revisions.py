"""Explicit author wishes keep the original session and accepted narration intact."""
import json
import uuid
import unittest
from unittest.mock import patch

import test_backend as fixtures
import episode_ideas as ideas
import script_drafts
import script_editing
import script_revisions as revisions
import store


class ScriptRevisionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.BackendTest.setUpClass()
        cls.cid = store.channel_id(fixtures.BackendTest.channel)
        cls.base_url = fixtures.BackendTest.base_url

    @classmethod
    def tearDownClass(cls):
        fixtures.BackendTest.tearDownClass()

    def setUp(self):
        ideas.ACTIVE.clear()
        self.project = store.create_project(self.cid, 'Script revision ' + uuid.uuid4().hex[:8])
        self.pid = self.project['id']
        self.before = 'Take a walk after lunch. Keep a steady pace.\n\nChoose a route near your home.'
        self.after = 'After lunch, take a walk at a steady pace.\n\nA familiar route near home works well.'
        store.save_project_source(self.project, self.before)
        self.folder = store.project_dir(self.pid)
        self.session = {'session_id': str(uuid.uuid4()), 'model': 'claude-opus-5-5', 'effort': 'medium', 'api_cost_usd': 1.2}
        self.data = {'id': uuid.uuid4().hex, 'project_id': self.pid, 'channel_id': self.cid,
            'context': {'channel': 'Test'}, 'selected': {'title': self.project['name']},
            'stage': 'script', 'status': 'done', 'completed': True, 'target_words': 2000,
            'author_session': self.session}
        store.atomic_json(self.folder / 'episode-draft.json', self.data)
        self.blacklist = patch.object(revisions.word_blacklist, 'current', return_value=[])
        self.blacklist.start();self.addCleanup(self.blacklist.stop)

    def body(self, **changes):
        current = script_drafts.current(self.pid)
        return {'action': 'editing', 'wishes': 'Зроби формулювання природнішими.', 'request_id': str(uuid.uuid4()),
                'expected_version': current['version'], **{k: current[k] for k in ('base_sha256', 'epoch', 'sha256')}, **changes}

    request = fixtures.BackendTest.request

    def test_http_status_and_explicit_post_share_the_existing_episode_transport(self):
        status, data = self.request(f'/api/projects/{self.pid}/script-editing/status')
        self.assertEqual(status, 200)
        self.assertTrue(data['author_revision_supported'])
        self.assertTrue(data['can_revise'])
        self.assertFalse(data['available'])
        with patch.object(ideas, 'Thread') as thread:
            status, data = self.request(f'/api/projects/{self.pid}/episode-draft', 'POST', self.body())
        self.assertEqual(status, 202)
        self.assertTrue(data['manual_revision'])
        self.assertEqual(thread.call_count, 1)

    def start(self, body=None):
        with patch.object(ideas, 'Thread') as thread:
            result = ideas.start_project(self.pid, body or self.body())
        self.assertEqual(thread.call_count, 1)
        return result, ideas.ACTIVE[self.pid]

    def answer(self, prompt, root, identity, cid, **options):
        store.atomic_json(root / (identity + '-receipt.json'), {'identity': identity, 'session_id': self.session['session_id'],
            'total_cost_usd': 1.3, 'incremental_cost_usd': .1, 'usage': {'input_tokens': 20, 'output_tokens': 40}})
        options['session']['api_cost_usd'] = 1.3
        return {'script': self.after, 'summary': 'Речення звучать природніше.'}

    def test_wishes_resume_original_author_once_and_preserve_accepted_narration(self):
        result, job = self.start()
        self.assertEqual(result['status'], 'running')
        with patch.object(ideas, 'opus', side_effect=self.answer) as model, patch('episode_automation.after_script') as auto:
            ideas.work(self.cid, job)
        self.assertEqual(model.call_count, 1)
        self.assertTrue(model.call_args.kwargs['resume'])
        self.assertEqual(model.call_args.kwargs['session']['session_id'], self.session['session_id'])
        self.assertEqual(model.call_args.kwargs['session']['effort'], 'medium')
        self.assertIn('Зроби формулювання природнішими.', model.call_args.args[0])
        self.assertIn('studio_audience_policy',model.call_args.args[0])
        self.assertIn('Росії',model.call_args.args[0])
        auto.assert_not_called()
        self.assertEqual(store.load_project(self.pid)['voice_script']['text'], self.before)
        self.assertEqual(script_drafts.current(self.pid)['text'], self.after)
        self.assertEqual(job['status'], 'done')
        report = script_editing.view(self.pid)
        self.assertTrue(report['matches_current'])
        self.assertEqual(report['mode'], 'author_revision_v1')
        self.assertEqual(report['cost_usd'], .1)
        self.assertTrue(any(row['changed'] for row in report['paragraphs']))
        self.assertTrue(script_drafts.history(self.pid)['versions'])

    def test_saved_manual_draft_is_the_source_of_the_revision(self):
        current = script_drafts.current(self.pid)
        script_drafts.save(self.pid, {'text': 'My manually edited working script.', 'expected_version': current['version'],
            'base_sha256': current['base_sha256'], 'epoch': current['epoch']})
        _, job = self.start()
        with patch.object(ideas, 'opus', side_effect=self.answer) as model:
            ideas.work(self.cid, job)
        self.assertIn('My manually edited working script.', model.call_args.args[0])
        self.assertEqual(script_drafts.current(self.pid)['text'], self.after)

    def test_duplicate_start_does_not_create_another_paid_job(self):
        body = self.body()
        with patch.object(ideas, 'Thread') as thread:
            first = ideas.start_project(self.pid, body)
            second = ideas.start_project(self.pid, body)
        self.assertEqual(first['run_id'], second['run_id'])
        self.assertEqual(thread.call_count, 1)

    def test_empty_wishes_stale_source_and_missing_session_never_start(self):
        for body in (self.body(wishes=' '), self.body(sha256='changed')):
            with patch.object(ideas, 'Thread') as thread, self.assertRaises(store.StudioError):
                ideas.start_project(self.pid, body)
            thread.assert_not_called()
        self.data.pop('author_session')
        store.atomic_json(self.folder / 'episode-draft.json', self.data)
        with patch.object(ideas, 'Thread') as thread, self.assertRaises(store.StudioError):
            ideas.start_project(self.pid, self.body())
        thread.assert_not_called()

    def test_concurrent_author_edit_is_never_overwritten(self):
        _, job = self.start()
        def changed(*args, **kwargs):
            current = script_drafts.current(self.pid)
            script_drafts.save(self.pid, {'text': 'New author changes.', 'expected_version': current['version'],
                'base_sha256': current['base_sha256'], 'epoch': current['epoch']})
            return self.answer(*args, **kwargs)
        with patch.object(ideas, 'opus', side_effect=changed):
            ideas.work(self.cid, job)
        self.assertEqual(job['status'], 'failed')
        self.assertEqual(script_drafts.current(self.pid)['text'], 'New author changes.')
        self.assertTrue((self.folder / 'script-editing' / job['revision_id'] / 'after.txt').is_file())

    def test_empty_or_malformed_answer_does_not_replace_the_script_or_retry(self):
        for answer in ({'script': ''}, {'script': None}, {}):
            _, job = self.start()
            with patch.object(ideas, 'opus', return_value=answer) as model:
                ideas.work(self.cid, job)
            self.assertEqual(job['status'], 'failed')
            self.assertEqual(model.call_count, 1)
            self.assertEqual(script_drafts.current(self.pid)['text'], self.before)

    def test_unchanged_ready_answer_is_accepted_without_manual_review_or_retry(self):
        _, job = self.start()
        with patch.object(ideas, 'opus', return_value={'script': self.before}) as model:
            ideas.work(self.cid, job)
        self.assertEqual(job['status'], 'done')
        self.assertFalse(job['review_required'])
        self.assertEqual(model.call_count, 1)
        self.assertEqual(script_drafts.current(self.pid)['text'], self.before)

    def test_original_session_can_be_recovered_only_from_a_matching_script_receipt(self):
        self.data.pop('author_session');self.data['effort'] = 'medium'
        store.atomic_json(self.folder / 'script-draft.json', {'script': self.before})
        receipt = {'session_id': self.session['session_id'], 'total_cost_usd': 1.2,
            'modelUsage': {'claude-opus-5-5': {}}, 'result': json.dumps({'script': self.before})}
        store.atomic_json(self.folder / 'script-original-receipt.json', receipt)
        found = revisions.author_session(self.pid, self.data)
        self.assertEqual(found['session_id'], self.session['session_id'])
        receipt['result'] = json.dumps({'script': 'Some other script.'})
        store.atomic_json(self.folder / 'script-original-receipt.json', receipt)
        self.assertIsNone(revisions.author_session(self.pid, self.data))

    def test_cancellation_preserves_original_and_blacklist_notes_do_not_veto_author(self):
        _, job = self.start()
        def cancelled(*args, **kwargs):
            job['cancelled'] = True
            return self.answer(*args, **kwargs)
        with patch.object(ideas, 'opus', side_effect=cancelled) as model:
            ideas.work(self.cid, job)
        self.assertEqual(job['status'], 'cancelled')
        self.assertEqual(model.call_count, 1)
        self.assertEqual(script_drafts.current(self.pid)['text'], self.before)
        _, job = self.start()
        with patch.object(ideas, 'opus', side_effect=self.answer) as model, patch.object(revisions.word_blacklist, 'current', return_value=['familiar']):
            ideas.work(self.cid, job)
        self.assertEqual(job['status'], 'done')
        self.assertEqual(model.call_count, 1)
        self.assertEqual(script_drafts.current(self.pid)['text'], self.after)
        self.assertEqual(script_editing.latest(self.pid)['blacklist_final_check']['matches'], ['familiar'])

    def test_one_native_session_cannot_be_resumed_in_two_projects_simultaneously(self):
        ideas.ACTIVE['another-project'] = {'project_id': 'another-project', 'author_session': self.session}
        with patch.object(ideas, 'Thread') as thread, self.assertRaises(store.StudioError):
            ideas.start_project(self.pid, self.body())
        thread.assert_not_called()
