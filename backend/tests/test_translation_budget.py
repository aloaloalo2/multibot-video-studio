import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import translation_budget as budget


class TranslationBudgetTest(unittest.TestCase):
    def test_inclusive_three_percent_boundaries(self):
        for length, valid in [(96, False), (97, True), (100, True), (103, True), (104, False)]:
            with self.subTest(length=length):
                state = budget.report('x'*100, 'a'*length)
                self.assertEqual(state['within_budget'], valid)
                self.assertEqual((state['min_chars'], state['max_chars']), (97, 103))
        self.assertEqual(budget.report('x'*100, 'a'*104)['over_by'], 1)
        self.assertEqual(budget.report('x'*100, 'a'*96)['under_by'], 1)

    def test_spaces_and_newlines_count_but_outer_whitespace_does_not(self):
        self.assertEqual(budget.count('  a  b\nс  '), 6)
        self.assertEqual(budget.join_lines(['  a  b ', ' с ']), 'a  b\nс')
        self.assertEqual(budget.report('a b', 'a  b')['difference_chars'], 1)

    def test_short_sources_round_to_attainable_integer_bounds(self):
        self.assertEqual((budget.report('abc', '')['min_chars'], budget.report('abc', '')['max_chars']), (3, 3))
        self.assertTrue(budget.report('', '  ')['within_budget'])
        self.assertFalse(budget.report('', 'a')['within_budget'])

    def test_line_hints_sum_to_whole_budget_including_separators(self):
        lines = ['a'*20, 'b'*80, 'c'*10]
        targets = budget.allocate_targets(lines, 100)
        self.assertEqual(set(targets), {0, 1, 2})
        self.assertEqual(sum(targets.values())+2, 100)
        self.assertGreater(targets[1], targets[0])
        self.assertGreater(targets[0], targets[2])
        self.assertEqual(budget.allocate_targets(['a', 'b'], 3), {0: 1, 1: 1})
        with self.assertRaises(ValueError):
            budget.allocate_targets(['a', 'b'], 2)

    def test_total_budget_allows_dense_line_to_borrow_and_keeps_ids_in_order(self):
        original = ['a'*80, 'b'*80]
        rewrite = Mock(return_value={'1': 'y'*29, '0': 'x'*70})
        validate = Mock()
        result = budget.fit('s'*100, original, rewrite, validate=validate)
        self.assertEqual(result['lines'], ['x'*70, 'y'*29])
        self.assertEqual(result['report']['translated_chars'], 100)
        self.assertEqual(original, ['a'*80, 'b'*80])
        self.assertEqual(result['passes'], 1)
        validate.assert_called_once_with(result['lines'])

    def test_within_budget_does_not_rewrite_but_still_validates(self):
        rewrite, validate = Mock(), Mock()
        result = budget.fit('s'*100, ['t'*100], rewrite, validate=validate)
        self.assertEqual(result['passes'], 0)
        rewrite.assert_not_called()
        validate.assert_called_once()

    def test_growing_short_translation_uses_same_total_budget(self):
        rewrite = Mock(return_value=['t'*99])
        result = budget.fit('s'*100, ['t'*80], rewrite)
        self.assertEqual(result['report']['translated_chars'], 99)
        self.assertEqual(rewrite.call_args.args[1]['under_by'], 17)

    def test_unchanged_draft_gets_feedback_then_stops_without_looping(self):
        rewrite = Mock(return_value=['t'*120])
        with self.assertRaises(budget.BudgetError) as failure:
            budget.fit('s'*100, ['t'*120], rewrite)
        self.assertEqual(rewrite.call_count, 2)
        self.assertIn('unchanged', rewrite.call_args_list[1].args[1]['last_issue'])
        self.assertEqual(failure.exception.lines, ['t'*120])

    def test_at_most_three_refinement_passes_and_complete_source_units_preserved(self):
        rewrite = Mock(side_effect=[{}, ['a'*110], ['a'*100]])
        result = budget.fit('s'*100, ['a'*120], rewrite)
        self.assertEqual(result['passes'], 3)
        self.assertEqual(rewrite.call_count, 3)
        self.assertIn('Every original phrase', rewrite.call_args_list[1].args[1]['last_issue'])

    def test_exhaustion_preserves_latest_draft_for_review(self):
        rewrite = Mock(side_effect=[['a'*119], ['a'*118], ['a'*117]])
        with self.assertRaises(budget.BudgetError) as failure:
            budget.fit('s'*100, ['a'*120], rewrite)
        self.assertEqual(failure.exception.passes, 3)
        self.assertEqual(failure.exception.report['over_by'], 14)
        self.assertEqual(failure.exception.lines, ['a'*117])

    def test_meaning_or_language_rejection_cannot_publish_a_short_draft(self):
        rewrite = Mock(return_value=['a'*100])
        with self.assertRaisesRegex(budget.BudgetError, 'validation'):
            budget.fit('s'*100, ['a'*120], rewrite, validate=lambda _: False)
        with self.assertRaisesRegex(RuntimeError, 'wrong language'):
            budget.fit('s'*100, ['a'*120], rewrite,
                       validate=Mock(side_effect=RuntimeError('wrong language')))

    def test_invalid_or_duplicate_phrase_ids_cannot_be_accepted(self):
        for response in [{0: 'a', '0': 'b'}, {1: 'a'*100}, ['a\nb'], []]:
            with self.subTest(response=response):
                with self.assertRaises(budget.BudgetError):
                    budget.fit('s'*100, ['a'*120], Mock(return_value=response), max_passes=1)


if __name__ == '__main__':
    unittest.main()
