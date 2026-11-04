"""Number-aware length refinement preserves meaning, phrase ids and paid audio."""
import contextlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import languages


class TranslationLengthIntegrationTest(unittest.TestCase):
    def test_explicit_translation_uses_voice_pace_and_reaudits_without_synthesizing(self):
        self.ask.side_effect = [(json.dumps({'ok':True,'ids':[0]}), .01),
                                (json.dumps({'0':'t'*96}), .01),
                                (json.dumps({'ok':True,'ids':[0]}), .01)]
        with patch.object(languages,'load_state',return_value={'provider':'elevenlabs'}), \
             patch.object(languages,'voice_cache_context',return_value=({'model':'test'},set())), \
             patch.object(languages.narration_profile,'read',return_value={'seconds_per_character':.22,'observations':30}):
            languages._translate('test','es',self.job)
        self.assertEqual(self.save.call_args.args[4],'t'*96)
        self.assertEqual(self.ask.call_count,3)
        self.assertIn('Measured narration pacing',self.ask.call_args_list[1].args[0][1]['content'])
        self.speak.assert_not_called()

    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        (self.work/'text.txt').write_text('Accepted previous translation\n')
        self.source = {'script': 's'*100, 'duration': 20, 'title': 'Source title', 'language':'en'}
        self.lines = [{'start': 0, 'end': 20, 'source': 's'*100}]
        self.job = {'key': 'length-test', 'translation_model': languages.DEFAULT_TRANSLATION_MODEL}
        self.stack.enter_context(patch.object(languages.store, 'load_project', return_value={'id': 'test','channel_id':'test-channel'}))
        self.stack.enter_context(patch.object(languages.language_defaults,'settings',return_value={}))
        self.stack.enter_context(patch.object(languages.store, 'load_project_plan', return_value={}))
        self.stack.enter_context(patch.object(languages, 'source', return_value=self.source))
        self.stack.enter_context(patch.object(languages, 'segments_of', return_value=self.lines))
        self.stack.enter_context(patch.object(languages, 'work_dir', return_value=self.work))
        self.stack.enter_context(patch.object(languages, 'translation_trace', return_value=contextlib.nullcontext()))
        self.stack.enter_context(patch.object(languages, 'progress'))
        self.stack.enter_context(patch.object(languages, 'translator', return_value='Translate naturally.'))
        self.stack.enter_context(patch.object(languages, 'target_rule', return_value='Spanish only.'))
        self.stack.enter_context(patch.object(languages.language_quality, 'require'))
        self.stack.enter_context(patch.object(languages, 'original_language', return_value='en'))
        self.initial = self.stack.enter_context(patch.object(languages, 'translate_lines', return_value=(['t'*100], .1)))
        self.ask = self.stack.enter_context(patch.object(languages, 'ask'))
        self.save = self.stack.enter_context(patch.object(languages, 'save_translation'))
        self.speak = self.stack.enter_context(patch.object(languages, 'speak'))

    def test_long_translation_is_refined_then_audited_again(self):
        self.initial.return_value = (['t'*120], .1)
        self.ask.side_effect = [(json.dumps({'ok':True,'ids':[0]}),.01),
                               (json.dumps({'0':'t'*104}),.02),
                               (json.dumps({'ok':True,'ids':[0]}),.01)]
        with patch.object(languages.translation_budget, 'fit', side_effect=AssertionError('No character fitting')):
            languages._translate('test', 'es', self.job)
        saved = self.save.call_args.args
        self.assertEqual(saved[4], 't'*104)
        self.assertAlmostEqual(saved[5], .14)
        self.assertEqual(saved[7], self.lines)
        self.assertTrue(self.job['translation_length']['advisory_only'])
        self.assertNotIn('within_budget', self.job['translation_length'])
        self.assertEqual(self.ask.call_count, 3)
        self.speak.assert_not_called()

    def test_pace_profile_follows_this_languages_provider_instead_of_the_old_global_provider(self):
        self.ask.return_value=(json.dumps({'ok':True,'ids':[0]}),.01)
        saved={'provider':'fishaudio','languages':{'es':{'narration':{'provider':'elevenlabs'}}}}
        with patch.object(languages,'load_state',return_value=saved), \
             patch.object(languages,'voice_cache_context',return_value=({'model':'selected'},set())) as context, \
             patch.object(languages.narration_profile,'read',return_value=None):
            languages.before_translate('test','es',self.source,['t'*100],['s'*100],self.job)
        context.assert_called_once_with('test','es','elevenlabs')
        self.speak.assert_not_called()

    def test_whole_script_length_is_refined_inside_phrase_bounds_and_audited_again(self):
        sources=['s'*100]*2;translated=['t'*108,'u'*108]
        self.ask.side_effect=[(json.dumps({'ok':True,'ids':[0,1]}),.01),
                              (json.dumps({'0':'t'*106}),.01),
                              (json.dumps({'ok':True,'ids':[0]}),.01)]
        result,_=languages.before_translate('test','es',
            {'script':'\n'.join(sources),'language':'en'},translated,sources,self.job)
        self.assertEqual(result,['t'*106,'u'*108])
        self.assertEqual(self.job['translation_length']['target_tolerance_percent'],7)
        self.assertTrue(self.job['translation_length']['script_comparison']['within_budget'])
        self.assertEqual(self.job['translation_length']['phrase_comparison']['outside_count'],0)
        self.speak.assert_not_called()

    def test_empty_audit_splits_checks_without_rewriting_valid_text(self):
        originals=['s'*100,'x'*100]
        texts=['t'*100,'y'*100]
        self.ask.side_effect=[('',.01),('{"ok":true,"ids":[0]}',.01),('{"ok":true,"ids":[1]}',.01)]
        result,cost=languages.before_translate('test','es',
            {'script':'\n'.join(originals),'language':'en'},texts,originals,self.job)
        self.assertEqual(result,texts)
        self.assertAlmostEqual(cost,.03)
        self.assertTrue(all('Independently compare' in call.args[0][0]['content'] for call in self.ask.call_args_list))
        self.speak.assert_not_called()

    def test_length_prompt_supplies_number_normalized_forms(self):
        source='In 2017.'
        translated='En dos mil diecisiete fue así.'
        fixed='En dos mil diecisiete.'
        self.ask.side_effect=[('{"ok":true,"ids":[0]}',.01),
                              (json.dumps({'0':fixed}),.01),('{"ok":true,"ids":[0]}',.01)]
        result,_=languages.before_translate('test','es',{'script':source,'language':'en'},[translated],[source],self.job)
        item=json.loads(self.ask.call_args_list[1].args[0][1]['content'])[0]
        self.assertEqual(item['comparison_source'],'In 2017.')
        self.assertEqual(item['comparison_translation'],'En 2017 fue así.')
        self.assertEqual(result,[fixed])

    def test_matching_total_still_refines_each_outlying_phrase_and_reaudits_only_changes(self):
        originals = ['s'*200, 's'*200, 's'*100]
        texts = ['a'*236, 'b'*164, 'c'*102]
        self.ask.side_effect = [
            (json.dumps({'ok': True, 'ids': [0, 1, 2]}), .01),
            (json.dumps({'0': 'a'*208, '1': 'b'*192}), .01),
            (json.dumps({'ok': True, 'ids': [0, 1]}), .01)]
        result, _ = languages.before_translate('test', 'uk',
            {'script': '\n'.join(originals), 'language': 'en'}, texts, originals, self.job)
        self.assertEqual(list(map(len, result)), [208, 192, 102])
        items = json.loads(self.ask.call_args_list[1].args[0][1]['content'])
        self.assertEqual([item['id'] for item in items], [0, 1])
        self.assertIn('remove only optional filler', items[0]['issue'])
        self.assertEqual(self.job['translation_length']['phrase_comparison']['outside_count'], 0)
        self.speak.assert_not_called()

    def test_one_improvement_cannot_hide_a_regression_in_another_phrase(self):
        originals = ['s'*100]*2
        self.ask.side_effect = [
            (json.dumps({'ok': True, 'ids': [0, 1]}), .01),
            (json.dumps({'0': 'a'*100, '1': 'b'*70}), .01),
            (json.dumps({'ok': True, 'ids': [0]}), .01),
            (json.dumps({'1': 'b'*100}), .01),
            (json.dumps({'ok': True, 'ids': [1]}), .01)]
        result, _ = languages.before_translate('test', 'uk',
            {'script': '\n'.join(originals), 'language': 'en'}, ['a'*120, 'b'*80], originals, self.job)
        retry = json.loads(self.ask.call_args_list[3].args[0][1]['content'])
        self.assertEqual([(item['id'], len(item['translation'])) for item in retry], [(1, 80)])
        self.assertEqual(list(map(len, result)), [100, 100])
        self.speak.assert_not_called()

    def test_new_issues_in_different_length_batches_do_not_count_as_stalled_repairs(self):
        originals, texts = ['s'*100]*81, ['t'*120]*81
        repaired = []
        phases = []
        def answer(messages, max_tokens=12000):
            items = json.loads(messages[1]['content'])
            ids = [item['id'] for item in items]
            review = self.job['translation_review']
            phases.append(review['phase'])
            self.assertEqual(review['total'], 81)
            self.assertTrue(review['waiting'])
            self.assertEqual(review['phrases'], [i+1 for i in ids])
            self.assertEqual(self.job['translation_length']['target_tolerance_percent'], 7)
            if 'Independently compare' in messages[0]['content']:
                issues = [{'id':item['id'], 'reason':'Restore the essential source fact.'}
                          for item in items if item['translation'].startswith('x')]
                return json.dumps({'ok':not issues, 'ids':ids, 'issues':issues}), .001
            if items[0]['issue'].startswith('NUMBER-NORMALIZED'):
                # Each separate batch introduces ONE new issue; the preceding
                # batch has already been repaired and independently approved.
                return json.dumps({str(i):('x' if i==ids[0] else 't')*100 for i in ids}), .001
            repaired.extend(ids)
            self.assertTrue(items[0]['rejected_revisions'])
            return json.dumps({str(i):'y'*100 for i in ids}), .001
        self.ask.side_effect = answer
        result, _ = languages.before_translate('test','es',
            {'script':'\n'.join(originals),'language':'en'},texts,originals,self.job)
        self.assertEqual(len(repaired),5)
        self.assertEqual(len(set(repaired)),5)
        self.assertEqual(list(map(len,result)),[100]*81)
        self.assertEqual(set(phases),{'audit','length','meaning'})
        self.assertFalse(self.job['translation_review']['waiting'])
        self.assertEqual(self.job['translation_length']['phrase_comparison']['outside_count'],0)
        self.speak.assert_not_called()

    def test_persistent_issue_identifies_phrase_and_resume_keeps_rejected_wording(self):
        def rejected(messages, max_tokens=12000):
            if 'Independently compare' in messages[0]['content']:
                return json.dumps({'ok':False,'ids':[0],
                    'issues':[{'id':0,'reason':'Required source fact is missing.'}]}), .001
            return json.dumps({'0':'t'*100}), .001
        self.ask.side_effect = rejected
        with self.assertRaisesRegex(RuntimeError,'Потрібно перевірити фрази: 1'):
            languages._translate('test','es',self.job)
        self.assertEqual(self.job['translation_issues'][0]['phrase'],1)
        draft=languages.translation_draft('test','es',self.source,
            [self.lines[0]['source']],self.job,self.lines)
        self.assertEqual(draft.data['rejected']['0'][0]['translation'],'t'*100)
        self.assertEqual(draft.data['rejected']['0'][0]['issue'],'Required source fact is missing.')
        self.save.assert_not_called()
        self.speak.assert_not_called()

    def test_failed_phrase_refinement_retains_old_publication_and_paid_cache(self):
        cache = self.work/'voice-cache'
        cache.mkdir()
        paid = cache/'existing.mp3'
        paid.write_bytes(b'existing paid take')
        self.initial.return_value = (['t'*118], .1)
        self.ask.side_effect = [(json.dumps({'ok': True, 'ids': [0]}), .01)] + [
            (json.dumps({'0': 't'*118}), .01)]*3
        with self.assertRaisesRegex(RuntimeError, 'Фраза №1.*±8\.5%'):
            languages._translate('test', 'uk', self.job)
        self.save.assert_not_called()
        self.assertEqual((self.work/'text.txt').read_text(), 'Accepted previous translation\n')
        self.assertEqual(paid.read_bytes(), b'existing paid take')
        saved = json.loads((self.work/'translation-draft.json').read_text())
        self.assertEqual(saved['lines'], ['t'*118])
        self.assertTrue(saved['resumable'])
        self.speak.assert_not_called()

    def test_incompatible_pace_does_not_oscillate_outside_phrase_band_or_buy_voice(self):
        self.initial.return_value = (['t'*92], .1)
        self.ask.return_value = (json.dumps({'ok': True, 'ids': [0]}), .01)
        # Isolate the phrase-band/pacing conflict from the independently tested whole-script bound.
        with patch.object(languages.translation_budget,'SCRIPT_TOLERANCE',.09), \
             patch.object(languages, 'load_state', return_value={'provider':'elevenlabs'}), \
             patch.object(languages, 'voice_cache_context', return_value=({'model':'test'},set())), \
             patch.object(languages.narration_profile, 'read', return_value={'seconds_per_character':.24,'observations':30}):
            with self.assertRaisesRegex(RuntimeError, 'в межах ±8\.5%.*прогноз голосу'):
                languages._translate('test', 'es', self.job)
        self.assertEqual(self.ask.call_count, 1)
        self.save.assert_not_called()
        self.speak.assert_not_called()

    def test_semantic_failure_preserves_the_previous_translation(self):
        def rejected(messages, max_tokens=12000):
            if 'Independently compare' in messages[0]['content']:
                return json.dumps({'ok': False, 'ids': [0], 'issues': [{'id': 0, 'reason': 'Lost fact.'}]}), .01
            return json.dumps({'0': 't'*100}), .02
        self.ask.side_effect = rejected
        with self.assertRaisesRegex(RuntimeError, 'змісту'):
            languages._translate('test', 'es', self.job)
        self.save.assert_not_called()
        self.assertEqual((self.work/'text.txt').read_text(), 'Accepted previous translation\n')
        self.speak.assert_not_called()

    def test_wrong_year_is_repaired_even_when_model_audit_accepts_it(self):
        self.source['script']='In 1989.'
        self.lines[0]['source']='In 1989.'
        self.initial.return_value=(['En mil ochocientos ochenta y nueve.'],.1)
        fixed='En mil novecientos ochenta y nueve.'
        self.ask.side_effect=[('{"ok":true,"ids":[0]}',.01),
                              (json.dumps({'0':fixed}),.01),('{"ok":true,"ids":[0]}',.01)]
        languages._translate('test','es',self.job)
        self.assertEqual(self.save.call_args.args[4],fixed)
        self.assertIn('1989',self.ask.call_args_list[1].args[0][1]['content'])
        self.speak.assert_not_called()

    def test_unsupported_number_grammar_does_not_break_translation_or_claim_the_goal(self):
        self.ask.return_value=('{"ok":true,"ids":[0]}',.01)
        languages._translate('test','ja',self.job)
        self.save.assert_called_once()
        self.assertIsNone(self.job['translation_length']['target_tolerance_percent'])
        self.speak.assert_not_called()

    def test_short_translation_restores_natural_detail_and_is_audited(self):
        self.initial.return_value = (['t'*50], .1)
        self.ask.side_effect = [(json.dumps({'ok':True,'ids':[0]}),.01),
                               (json.dumps({'0':'t'*96}),.02),
                               (json.dumps({'ok':True,'ids':[0]}),.01)]
        languages._translate('test', 'es', self.job)
        self.assertEqual(self.save.call_args.args[4], 't'*96)
        self.assertEqual(self.ask.call_count, 3)
        self.speak.assert_not_called()

    def test_unsynced_paragraph_units_are_flattened_and_kept_in_order(self):
        self.ask.side_effect = [('a'*25+'\n\n'+'a'*24, .01), ('b'*49, .01),
                                (json.dumps({'ok': True, 'ids': [0, 1]}), .001)]
        with patch.object(languages, 'segments_of', return_value=[]), \
                patch.object(languages, 'chunks', return_value=['s'*50, 's'*49]), \
                patch.object(languages, 'speakable', side_effect=lambda code, texts: (texts, 0)):
            languages._translate('test', 'es', self.job)
        saved = self.save.call_args.args
        self.assertEqual(saved[4], 'a'*25+' '+'a'*24+'\n'+'b'*49)
        self.assertEqual(len(saved[4]), 100)
        self.assertIsNone(saved[7])
        self.assertEqual(self.ask.call_count, 3)

    def test_unsynced_interrupted_chunks_resume_without_repeating_completed_request(self):
        pieces = ['s'*50, 'q'*49]
        with patch.object(languages, 'segments_of', return_value=[]), \
                patch.object(languages, 'chunks', return_value=pieces), \
                patch.object(languages, 'speakable', side_effect=lambda code, texts: (texts, 0)):
            self.ask.side_effect = [('a'*50, .01), RuntimeError('Provider unavailable')]
            with self.assertRaisesRegex(RuntimeError, 'Provider unavailable'):
                languages._translate('test', 'es', self.job)
            checkpoint = json.loads((self.work/'translation-draft.json').read_text())
            self.assertEqual(checkpoint['initial_parts'], {'0': ['a'*50]})
            self.assertAlmostEqual(checkpoint['cost_usd'], .01)
            self.save.assert_not_called()
            self.assertEqual((self.work/'text.txt').read_text(), 'Accepted previous translation\n')
            self.ask.reset_mock()
            self.ask.side_effect = [('b'*49, .02), (json.dumps({'ok': True, 'ids': [0, 1]}), .001)]
            languages._translate('test', 'es', self.job)
        self.assertEqual(self.ask.call_count, 2)
        self.assertEqual(self.ask.call_args_list[0].args[0][1]['content'], pieces[1])
        self.assertEqual(self.job['translation_resumed'], 1)
        self.assertEqual(self.save.call_args.args[4], 'a'*50+'\n'+'b'*49)
        self.assertAlmostEqual(self.save.call_args.args[5], .031)
        self.assertIsNotNone(self.save.call_args.kwargs.get('draft'))
        self.assertTrue(json.loads((self.work/'translation-draft.json').read_text())['completed'])

    def test_unsynced_seed_resumes_full_draft_and_preserves_recorded_cost(self):
        pieces = ['s'*50, 'q'*49]
        with patch.object(languages, 'segments_of', return_value=[]), \
                patch.object(languages, 'chunks', return_value=pieces):
            model = languages.DEFAULT_TRANSLATION_MODEL
            languages.seed_translation_draft('test', 'es', ['a'*50, 'b'*49], model,
                source_script=self.source['script'], source_units=pieces, source_segments=[], cost_usd=.15)
            self.ask.side_effect = [(json.dumps({'ok': True, 'ids': [0, 1]}), .001)]
            languages._translate('test', 'es', self.job)
        self.assertEqual(self.ask.call_count, 1)
        self.assertIn('Independently compare', self.ask.call_args.args[0][0]['content'])
        self.assertEqual(self.job['translation_resumed'], 2)
        self.assertAlmostEqual(self.save.call_args.args[5], .151)

    def test_unsynced_stale_source_restarts_instead_of_reusing_unrelated_chunks(self):
        old_pieces, new_pieces = ['old'*10, 'old'*10], ['s'*50, 'q'*49]
        old_src = {**self.source, 'script': 'old'*20}
        draft = languages.translation_draft('test', 'es', old_src, old_pieces, self.job)
        draft.save(initial_parts={'0': ['outdated text']}, cost_usd=.5)
        with patch.object(languages, 'segments_of', return_value=[]), \
                patch.object(languages, 'chunks', return_value=new_pieces), \
                patch.object(languages, 'speakable', side_effect=lambda code, texts: (texts, 0)):
            self.ask.side_effect = [('a'*50, .01), ('b'*49, .02),
                                    (json.dumps({'ok': True, 'ids': [0, 1]}), .001)]
            languages._translate('test', 'es', self.job)
        self.assertEqual(self.ask.call_count, 3)
        self.assertAlmostEqual(self.save.call_args.args[5], .031)
        self.assertNotIn('outdated', self.save.call_args.args[4])

    def test_within_budget_translation_still_needs_source_meaning_and_proper_name_audit(self):
        self.initial.return_value = (['t'*100], .1)
        def rejected(messages, max_tokens=12000):
            if 'Independently compare' in messages[0]['content']:
                return json.dumps({'ok': False, 'ids': [0], 'issues': [{'id': 0, 'reason': 'Wrong name.'}]}), .001
            return json.dumps({'0': 't'*100}), .001
        self.ask.side_effect = rejected
        with self.assertRaisesRegex(RuntimeError, 'змісту'):
            languages._translate('test', 'es', self.job)
        self.assertEqual(self.ask.call_count, 6)
        prompt = self.ask.call_args_list[0].args[0][0]['content']
        self.assertIn('proper names', prompt)
        self.assertIn('pounds becoming kilograms', prompt)
        self.assertIn('source digits and equivalent', prompt)
        self.assertIn('Compare numeric VALUES and UNITS', prompt)
        self.assertIn('Raw character length is not a quality failure', prompt)
        self.save.assert_not_called()
        self.speak.assert_not_called()

    def test_large_translation_audits_every_batch_without_length_rewrites(self):
        originals, translated = ['s'*10]*45, ['t'*10]*45
        src = {'script': '\n'.join(originals)}
        sizes = []
        def ask(messages, max_tokens=12000):
            self.assertIn('Independently compare', messages[0]['content'])
            items = json.loads(messages[1]['content'])
            sizes.append(len(items))
            return json.dumps({'ok': True, 'ids': [item['id'] for item in items]}), .001
        self.ask.side_effect = ask
        result, cost = languages.before_translate('test', 'es', src, translated, originals, self.job)
        self.assertEqual(result, translated)
        self.assertEqual(sizes, [20, 20, 5])
        self.assertAlmostEqual(cost, .003)
        self.speak.assert_not_called()

    def test_revised_numbers_must_remain_spoken_words(self):
        self.initial.return_value = (['t'*97+' 13'], .1)
        def invalid_number(messages, max_tokens=12000):
            if 'Independently compare' in messages[0]['content']:
                return json.dumps({'ok': True, 'ids': [0]}), .01
            return json.dumps({'0': 't'*97+' 13'}), .02
        self.ask.side_effect = invalid_number
        with self.assertRaisesRegex(RuntimeError, 'числа'):
            languages._translate('test', 'es', self.job)
        self.save.assert_not_called()
        self.speak.assert_not_called()


if __name__ == '__main__':
    unittest.main()
