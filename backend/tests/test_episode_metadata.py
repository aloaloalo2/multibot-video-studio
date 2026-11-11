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
        self.script = 'A selected opening. ' + 'Natural spoken words for this episode. ' * 32
        self.value = {'titles': [self.project['name'], 'Another fresh angle', 'A third fresh angle'],
                      'description': 'Thanks for watching. Subscribe for more.\n\nThis video is for entertainment.',
                      'tags': ['story', 'fiction', 'curiosity']}

    def draft(self):
        return {'id': self.pid, 'project_id': self.pid, 'context': {}, 'stage': 'script', 'status': 'running',
                'channel_id': self.cid, 'selected': {'title': self.project['name']},
                'opening': 'A selected opening.', 'target_words': 200}

    def test_metadata_recovery_uses_bounded_excerpts_without_resending_the_full_script(self):
        script = 'Opening context. ' + 'MiddleDetailsOnly ' * 500 + 'Ending context.'
        store.save_project_source(self.project, script)
        data = self.draft()
        data.update(stage='metadata',target_words=ideas.words(script))
        with patch.object(ideas,'opus',return_value={'metadata':self.value}) as model:
            ideas.work(self.cid,data)
        model.assert_called_once()
        prompt = model.call_args.args[0]
        self.assertNotIn(script,prompt)
        self.assertIn('Opening context.',prompt)
        self.assertIn('Ending context.',prompt)
        self.assertLess(prompt.count('MiddleDetailsOnly'),100)
        self.assertEqual(data['status'],'done')

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
        with patch.object(ideas, 'opus', side_effect=[{'script': self.script},RuntimeError('Metadata provider unavailable')]) as model, \
                (patch.object(ideas.author_rules, 'check', return_value=(True, 'OK')) if hasattr(ideas,'author_rules') else nullcontext()):
            ideas.work(self.cid, data)
        self.assertEqual(model.call_count,2)
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

    def test_manual_metadata_recovery_records_its_actual_author(self):
        metadata.save(self.project,self.value,self.script,author='Codex')
        receipt=store.read_json(store.project_dir(self.pid)/'publication-metadata.json')
        self.assertEqual(receipt['author'],'Codex')
        metadata.save(self.project,None,self.script)
        self.assertEqual(store.read_json(store.project_dir(self.pid)/'publication-metadata.json')['author'],'Codex')

    def test_persistence_error_does_not_regenerate_already_valid_metadata(self):
        metadata.path(self.project).touch()
        with patch.object(ideas,'opus') as model:
            with self.assertRaisesRegex(ValueError,'порожній'):
                metadata.save_generated(self.project,self.value,self.script,model)
        model.assert_not_called()

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

    def test_optional_correction_failure_keeps_original_and_recovers_metadata_locally(self):
        data = self.draft()
        with patch.object(ideas, 'opus', side_effect=[{'script':self.script, 'metadata':self.value}, RuntimeError('offline')]), \
                patch.object(ideas.author_rules, 'check', return_value=(False,'Concrete issue')):
            ideas.work(self.cid, data)
        self.assertEqual(data['status'], 'failed')
        self.assertEqual(store.load_project(self.pid)['voice_script']['text'], self.script.strip())
        saved = store.read_json(store.project_dir(self.pid)/'script-draft.json')
        self.assertEqual(saved['metadata'], self.value)
        with patch.object(ideas, 'opus') as model, patch.object(ideas, 'Thread') as worker:
            result = ideas.start_project(self.pid, {'action':'metadata'})
        model.assert_not_called(); worker.assert_not_called()
        self.assertTrue(result['metadata_saved'])
        self.assertFalse(result['check']['passed'])

    def test_metadata_recovery_preserves_legacy_accepted_script_under_new_length_minimum(self):
        script=self.script_with_words(160)
        store.save_project_source(self.project,script)
        saved={**self.draft(),'status':'done','completed':True,'actual_words':160}
        store.atomic_json(store.project_dir(self.pid)/'episode-draft.json',saved)
        with patch.object(ideas,'Thread') as worker:
            ideas.start_project(self.pid,{'action':'metadata'})
        worker.assert_called_once()
        retry=store.read_json(store.project_dir(self.pid)/'episode-draft.json')
        with patch.object(ideas,'opus',return_value={'metadata':self.value}) as model,patch.object(store,'save_project_source') as write_script:
            ideas.work(self.cid,retry)
        model.assert_called_once();write_script.assert_not_called()
        self.assertTrue(retry['metadata_saved']);self.assertTrue(retry['completed'])
        self.assertFalse(retry['length']['passed'])
        self.assertEqual(store.load_project(self.pid)['voice_script']['text'],script.strip())

    def test_legacy_metadata_length_acceptance_does_not_apply_to_a_changed_script(self):
        script=self.script_with_words(160)
        store.save_project_source(self.project,script)
        store.atomic_json(store.project_dir(self.pid)/'episode-draft.json',{**self.draft(),'status':'done','completed':True})
        with patch.object(ideas,'Thread'):
            ideas.start_project(self.pid,{'action':'metadata'})
        retry=store.read_json(store.project_dir(self.pid)/'episode-draft.json')
        store.save_project_source(store.load_project(self.pid),self.script_with_words(150))
        with patch.object(ideas,'opus') as model:
            ideas.work(self.cid,retry)
        model.assert_not_called();self.assertEqual(retry['status'],'failed')
        self.assertFalse(metadata.exists(self.project))

    def test_missing_checker_requires_review_without_paid_correction(self):
        data = self.draft()
        with patch.object(ideas,'opus',return_value={'script':self.script,'metadata':self.value}) as model, \
                patch.object(ideas.author_rules,'check',return_value=(None,'Unavailable')):
            ideas.work(self.cid,data)
        model.assert_called_once()
        self.assertTrue(data['review_required'])
        self.assertTrue(data['completed'])

    def script_with_words(self, count):
        return 'A selected opening. ' + 'detail ' * (count-3)

    def test_length_and_content_issues_share_one_correction_and_corrected_count_is_checked(self):
        data=self.draft();short=self.script_with_words(160);corrected=self.script_with_words(200)
        with patch.object(ideas,'opus',side_effect=[{'script':short,'metadata':self.value},{'script':corrected}]) as model, \
                patch.object(ideas.author_rules,'check',side_effect=[(False,'A concrete content issue'),(True,'OK')]):
            ideas.work(self.cid,data)
        self.assertEqual(model.call_count,2)
        self.assertIn('A concrete content issue',model.call_args_list[1].args[0])
        self.assertIn('186 to 214',model.call_args_list[1].args[0])
        self.assertEqual(data['actual_words'],200)
        self.assertTrue(data['length']['passed'])
        self.assertTrue(data['completed'])
        self.assertEqual(store.load_project(self.pid)['voice_script']['text'],corrected.strip())

    def test_failed_length_correction_keeps_draft_without_marking_complete_or_metadata_bypass(self):
        data=self.draft();short=self.script_with_words(160)
        with patch.object(ideas,'opus',return_value={'script':short,'metadata':self.value}) as model, \
                patch.object(ideas.author_rules,'check',return_value=(True,'OK')):
            ideas.work(self.cid,data)
        self.assertEqual(model.call_count,2)
        self.assertEqual(data['status'],'failed')
        self.assertFalse(data['completed'])
        self.assertFalse(data['length']['passed'])
        self.assertIn('186 до 214',data['error'])
        self.assertEqual(store.load_project(self.pid)['voice_script']['text'],short.strip())
        self.assertFalse(metadata.exists(store.load_project(self.pid)))
        with patch.object(ideas,'Thread') as worker:
            with self.assertRaisesRegex(store.StudioError,'±7%'):
                ideas.start_project(self.pid,{'action':'metadata'})
        worker.assert_not_called()

    def test_author_edit_during_check_cannot_be_overwritten(self):
        data = self.draft()
        def check(*args):
            store.save_project_source(store.load_project(self.pid),'Author changed this script.')
            return True,'OK'
        with patch.object(ideas,'opus',return_value={'script':self.script,'metadata':self.value}), \
                patch.object(ideas.author_rules,'check',side_effect=check):
            ideas.work(self.cid,data)
        self.assertEqual(data['status'],'failed')
        self.assertEqual(store.load_project(self.pid)['voice_script']['text'],'Author changed this script.')


    def test_changed_primary_title_and_escaped_paragraphs_are_repaired_without_model_work(self):
        value={**self.value,'titles':['The model changed my title',*self.value['titles'][1:]],'description':self.value['description'].replace('\n','\\n')}
        with patch.object(ideas,'opus') as model:
            metadata.save_generated(self.project,value,self.script,model)
        model.assert_not_called()
        self.assertIn(self.project['name'],metadata.path(self.project).read_text())
        self.assertNotIn('\\n',metadata.path(self.project).read_text())

    def test_missing_metadata_is_completed_once_without_rewriting_saved_script(self):
        data=self.draft()
        with patch.object(ideas,'opus',side_effect=[{'script':self.script},{'metadata':self.value}]) as model, patch.object(ideas.author_rules,'check',return_value=(True,'OK')):
            ideas.work(self.cid,data)
        self.assertEqual(model.call_count,2)
        self.assertTrue(data['metadata_saved']);self.assertTrue(data['completed'])
        self.assertIn('Do not rewrite the script',model.call_args.args[0])
        self.assertNotIn(self.script.strip(),model.call_args.args[0])


class ScriptLengthTest(unittest.TestCase):
    def test_seven_percent_bounds_are_inclusive_and_use_exact_integer_arithmetic(self):
        for count,passed in ((1952,False),(1953,True),(2100,True),(2247,True),(2248,False)):
            report=ideas.script_length('word '*count,2100)
            self.assertEqual((report['minimum'],report['maximum']),(1953,2247))
            self.assertEqual(report['passed'],passed)
        report=ideas.script_length('word '*93,101)
        self.assertEqual((report['minimum'],report['maximum']),(94,108))
        self.assertIsNone(ideas.script_length('Manual source',None))
