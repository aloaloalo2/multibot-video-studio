"""Publication output stays separate from speech and does not repeat script writing."""
import unittest
from contextlib import nullcontext
from unittest.mock import patch

import test_backend as fixtures
import store
import episode_ideas as ideas
import episode_metadata as metadata


class MetadataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.BackendTest.setUpClass()
        cls.cid = store.channel_id(fixtures.BackendTest.channel)

    @classmethod
    def tearDownClass(cls):
        fixtures.BackendTest.tearDownClass()

    def setUp(self):
        ideas.ACTIVE.clear()
        self.project = store.create_project(self.cid, self._testMethodName)
        self.pid = self.project['id']
        self.script = 'A selected opening. ' + 'Natural spoken words for this episode. ' * 30
        self.value = {'titles': [self.project['name'], 'Another fresh angle', 'A third fresh angle'],
                      'description': 'Thanks for watching. Subscribe for more.\n\nThis video is for entertainment.',
                      'tags': ['story', 'fiction', 'curiosity']}

    def draft(self):
        return {'id': self.pid, 'project_id': self.pid, 'context': {}, 'stage': 'script', 'status': 'running',
                'channel_id': self.cid, 'selected': {'title': self.project['name']},
                'opening': 'A selected opening.', 'target_words': 200}

    def test_one_response_saves_both_outputs_and_never_starts_voice(self):
        data = self.draft()
        with patch.object(ideas, 'opus', return_value={'script': self.script, 'metadata': self.value}) as model, \
                (patch.object(ideas.author_rules, 'check', return_value=(True, 'OK')) if hasattr(ideas,'author_rules') else nullcontext()):
            ideas.work(self.cid, data)
        model.assert_called_once()
        self.assertTrue(data['completed'])
        self.assertEqual(store.load_project(self.pid)['voice_script']['text'], self.script.strip())
        self.assertIn('Теги\nstory, fiction, curiosity', metadata.path(self.project).read_text())
        self.assertFalse(store.load_project(self.pid).get('plan_source'))
        self.assertEqual(store.read_json(store.project_dir(self.pid) / 'publication-metadata.json')['author'], 'Opus')

    def test_missing_metadata_preserves_script_then_retries_only_metadata(self):
        data = self.draft()
        with patch.object(ideas, 'opus', return_value={'script': self.script}) as model, \
                (patch.object(ideas.author_rules, 'check', return_value=(True, 'OK')) if hasattr(ideas,'author_rules') else nullcontext()):
            ideas.work(self.cid, data)
        model.assert_called_once()
        self.assertEqual(data['status'], 'failed')
        self.assertTrue(data['script_saved'])
        self.assertFalse(data.get('completed'))
        with patch.object(ideas, 'Thread'):
            ideas.start_project(self.pid, {'action': 'metadata'})
        retry = store.read_json(store.project_dir(self.pid) / 'episode-draft.json')
        with patch.object(ideas, 'opus', return_value={'metadata': self.value}) as model, \
                patch.object(store, 'save_project_source') as write_script:
            ideas.work(self.cid, retry)
        model.assert_called_once()
        write_script.assert_not_called()
        self.assertIn('Do not rewrite the script', model.call_args.args[0])
        self.assertTrue(retry['completed'])
        self.assertEqual(store.load_project(self.pid)['voice_script']['text'], self.script.strip())

    def test_existing_accepted_metadata_survives_even_when_response_is_missing(self):
        file = metadata.path(self.project)
        file.write_text('Accepted author metadata', encoding='utf-8')
        metadata.save(self.project, None, self.script)
        self.assertEqual(file.read_text(), 'Accepted author metadata')

    def test_invalid_tags_cannot_publish_partial_file(self):
        for tags in ([], ['one'], ['same'] * 3, ['one,two', 'three', 'four']):
            with self.subTest(tags=tags), self.assertRaises(ValueError):
                metadata.save(self.project, {**self.value, 'tags': tags}, self.script)
        self.assertFalse(metadata.path(self.project).exists())

    def test_saved_legacy_script_can_request_only_metadata_and_deduplicates(self):
        store.save_project_source(self.project, self.script)
        with patch.object(ideas, 'Thread') as thread:
            for _ in range(2):
                ideas.start_project(self.pid, {'action': 'metadata'})
            self.assertEqual(thread.call_count, 1)
        retry = store.read_json(store.project_dir(self.pid) / 'episode-draft.json')
        with patch.object(ideas, 'opus', return_value={'metadata': self.value}):
            ideas.work(self.cid, retry)
        with patch.object(ideas, 'Thread') as thread:
            result = ideas.start_project(self.pid, {'action': 'metadata'})
            thread.assert_not_called()
            self.assertTrue(result['metadata_saved'])
