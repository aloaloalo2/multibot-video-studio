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
        self.stack.enter_context(patch.object(languages.store, 'load_project', return_value={'id': 'test'}))
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
