import unittest
from unittest.mock import patch
import test_backend as fixtures
import episode_ideas as ideas
import store


class ManualProjectOpeningsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.BackendTest.setUpClass()
        cls.base_url = fixtures.BackendTest.base_url
        cls.cid = store.channel_id(fixtures.BackendTest.channel)

    @classmethod
    def tearDownClass(cls):
        ideas.ACTIVE.clear()
        fixtures.BackendTest.tearDownClass()

    request = fixtures.BackendTest.request

    def setUp(self):
        ideas.ACTIVE.clear()
        self.project = store.create_project(self.cid, 'What If Humans Could Live Forever?')
        self.endpoint = '/api/projects/' + self.project['id'] + '/episode-draft'

    def test_manual_title_starts_standard_openings_in_existing_project_once(self):
        with patch.object(ideas, 'context', return_value={'channel': 'Test', 'target_words': 2000, 'sample_count': 0}), \
             patch.object(ideas, 'Thread') as thread, patch.object(store, 'create_project') as create:
            code, result = self.request(self.endpoint, 'POST', {'action': 'openings', 'target_words': 3200, 'request_id': 'same'})
            self.assertEqual(code, 202, result)
            self.assertEqual(result['project_id'], self.project['id'])
            self.assertEqual(result['stage'], 'openings')
            saved = ideas.read_project(self.project['id'])
            self.assertEqual(saved['selected']['title'], self.project['name'])
            self.assertEqual(saved['target_words'], 3200)
            self.assertTrue(saved['manual_topic'])
            self.request(self.endpoint, 'POST', {'action': 'openings', 'request_id': 'same'})
            thread.assert_called_once(); create.assert_not_called()

    def test_existing_script_and_local_draft_are_preserved(self):
        for source in ['voice_script', 'draft']:
            with self.subTest(source=source):
                p = store.load_project(self.project['id'])
                p['voice_script'] = {'text': 'Keep this script.'} if source == 'voice_script' else {}
                store.save_project(p)
                if source == 'draft':
                    store.atomic_json(store.project_dir(p['id']) / 'script-draft.json', {'text': 'Keep my draft.'})
                with patch.object(ideas, 'Thread') as thread:
                    code, result = self.request(self.endpoint, 'POST', {'action': 'openings'})
                self.assertEqual(code, 409, result); thread.assert_not_called()

    def test_bad_target_does_not_launch_or_create_draft(self):
        with patch.object(ideas, 'context', return_value={'target_words': 2000}), patch.object(ideas, 'Thread') as thread:
            for count in [0, True, 15001]:
                code, result = self.request(self.endpoint, 'POST', {'action': 'openings', 'target_words': count})
                self.assertEqual(code, 400, result)
            thread.assert_not_called()
        self.assertFalse((store.project_dir(self.project['id']) / 'episode-draft.json').exists())
