"""Translation publication waits for the global text budget and meaning checks."""
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
        self.source = {'script': 's'*100, 'duration': 20, 'title': 'Source title'}
        self.lines = [{'start': 0, 'end': 20, 'source': 's'*100}]
        self.job = {'key': 'length-test'}
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
        self.initial = self.stack.enter_context(patch.object(languages, 'translate_lines', return_value=(['t'*120], .1)))
        self.ask = self.stack.enter_context(patch.object(languages, 'ask'))
        self.save = self.stack.enter_context(patch.object(languages, 'save_translation'))
        self.speak = self.stack.enter_context(patch.object(languages, 'speak'))

    def test_timed_translation_fits_before_publication_and_counts_refinement_cost(self):
        self.ask.side_effect = [(json.dumps({'0': 't'*100}), .02),
                                (json.dumps({'ok': True, 'ids': [0]}), .01)]
        languages._translate('test', 'es', self.job)
        saved = self.save.call_args.args
        self.assertEqual(saved[4], 't'*100)
        self.assertAlmostEqual(saved[5], .13)
        self.assertEqual(saved[7], self.lines)
        self.assertTrue(self.job['translation_length']['within_budget'])
        self.assertEqual(self.ask.call_count, 2)
        self.speak.assert_not_called()

    def test_semantic_failure_preserves_the_previous_translation(self):
        self.ask.side_effect = [(json.dumps({'0': 't'*100}), .02),
                                (json.dumps({'ok': False}), .01)]
        with self.assertRaisesRegex(RuntimeError, 'змісту'):
            languages._translate('test', 'es', self.job)
        self.save.assert_not_called()
        self.assertEqual((self.work/'text.txt').read_text(), 'Accepted previous translation\n')
        self.speak.assert_not_called()

    def test_unchanged_drafts_stop_without_publication_or_tts(self):
        self.ask.return_value = json.dumps({'0': 't'*120}), .02
        with self.assertRaisesRegex(RuntimeError, 'межа 3%'):
            languages._translate('test', 'es', self.job)
        self.assertEqual(self.ask.call_count, 2)
        self.save.assert_not_called()
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

    def test_within_budget_translation_still_needs_source_meaning_and_proper_name_audit(self):
        self.initial.return_value = (['t'*100], .1)
        self.ask.return_value = json.dumps({'ok': False}), .001
        with self.assertRaisesRegex(RuntimeError, 'змісту'):
            languages._translate('test', 'es', self.job)
        self.assertEqual(self.ask.call_count, 1)
        prompt = self.ask.call_args.args[0][0]['content']
        self.assertIn('proper names', prompt)
        self.assertIn('pounds becoming kilograms', prompt)
        self.save.assert_not_called()
        self.speak.assert_not_called()

    def test_large_translation_uses_batches_of_twenty_and_audits_every_changed_batch(self):
        originals, translated = ['s'*10]*45, ['t'*12]*45
        src = {'script': '\n'.join(originals)}
        sizes = []
        def ask(messages, max_tokens=12000):
            items = json.loads(messages[1]['content'])
            if 'Independently compare' in messages[0]['content']:
                return json.dumps({'ok': True, 'ids': [item['id'] for item in items]}), .001
            sizes.append(len(items))
            return json.dumps({item['id']: 't'*10 for item in items}), .001
        self.ask.side_effect = ask
        result, cost = languages.before_translate('test', 'es', src, translated, originals, self.job)
        self.assertEqual(result, ['t'*10]*45)
        self.assertEqual(sizes, [20, 20, 5])
        self.assertAlmostEqual(cost, .006)
        self.assertEqual(translated, ['t'*12]*45)
        self.speak.assert_not_called()

    def test_revised_numbers_must_remain_spoken_words(self):
        self.ask.return_value = json.dumps({'0': 't'*97+' 13'}), .02
        with self.assertRaisesRegex(RuntimeError, 'числа'):
            languages._translate('test', 'es', self.job)
        self.save.assert_not_called()
        self.speak.assert_not_called()


if __name__ == '__main__':
    unittest.main()
