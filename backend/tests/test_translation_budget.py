import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import translation_budget as budget


class TranslationBudgetTest(unittest.TestCase):
    def test_phrase_overruns_do_not_cancel_even_when_whole_script_matches(self):
        sources = ['s'*200, 's'*200, 's'*100]
        texts = ['a'*236, 'b'*164, 'c'*102]
        plan = budget.number_refinement_plan('\n'.join(sources), texts, sources, 'en', 'uk')
        self.assertTrue(plan['report']['within_budget'])
        self.assertFalse(plan['within_budget'])
        self.assertEqual(plan['pending_ids'], [0, 1])
        self.assertEqual(plan['directions'], {0: 'shorten', 1: 'expand'})
        self.assertEqual(plan['phrases'][0]['difference_percent'], 18)
        self.assertNotIn(2, plan['line_targets'])

    def test_phrase_boundaries_are_inclusive_and_number_expansion_is_discounted(self):
        sources = ['s'*100]*4 + ['In 2017.']
        texts = ['t'*n for n in (92, 93, 107, 108)] + ['In dos mil diecisiete.']
        plan = budget.number_refinement_plan('\n'.join(sources), texts, sources, 'en', 'es')
        self.assertEqual(plan['pending_ids'], [0, 3])
        self.assertEqual(plan['phrases'][4]['difference_percent'], 0)
        self.assertEqual(texts[-1], 'In dos mil diecisiete.')

    def test_phrase_batches_prioritize_worst_outliers_and_preserve_short_line_bounds(self):
        sources = ['s'*100]*23 + ['abc']
        texts = ['t'*(110+i) for i in range(23)] + ['xy']
        plan = budget.number_refinement_plan('\n'.join(sources), texts, sources, 'en', 'uk')
        self.assertEqual(len(plan['ids']), 20)
        self.assertIn(23, plan['ids'])
        self.assertNotIn(0, plan['ids'])
        self.assertEqual((plan['phrases'][23]['min_chars'], plan['phrases'][23]['max_chars']), (3, 3))
        self.assertEqual(plan['line_targets'][23], 3)

    def test_phrase_plan_rejects_missing_mapping_and_marks_unsupported_grammar(self):
        with self.assertRaises(ValueError):
            budget.number_refinement_plan('abc', ['def'], [], 'en', 'uk')
        plan = budget.number_refinement_plan('abc', ['def'], ['abc'], 'en', 'ja')
        self.assertFalse(plan['available'])
        self.assertEqual(plan['ids'], [])

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

    def test_refinement_selects_bounded_subset_with_exact_measured_caps(self):
        lines = ['a'*120]*20
        source_units = ['s'*100]*20
        plan = budget.refinement_plan('s'*2300, lines, source_units)
        self.assertEqual(plan['direction'], 'shorten')
        self.assertEqual(plan['target_chars'], 2369-12)
        self.assertEqual(plan['required_change'], 2419-plan['target_chars'])
        self.assertLess(len(plan['ids']), len(lines))
        selected_chars = sum(len(lines[i]) for i in plan['ids'])
        self.assertEqual(sum(plan['line_targets'].values()), selected_chars-plan['required_change'])
        self.assertTrue(all(1 <= plan['line_targets'][i] <= len(lines[i]) for i in plan['ids']))
        self.assertEqual(lines, ['a'*120]*20)

    def test_refinement_ranks_expansion_but_never_requires_source_length_per_phrase(self):
        lines = ['a'*100, 'b'*100, 'c'*100]
        plan = budget.refinement_plan('s'*290, lines, ['s'*120, 's'*30, 's'*120])
        self.assertEqual(plan['ids'], [1])
        self.assertGreater(plan['line_targets'][1], 30)

    def test_refinement_grows_short_translation_and_retains_separators(self):
        lines = ['a'*60]*10
        plan = budget.refinement_plan('s'*630, lines)
        self.assertEqual(plan['direction'], 'expand')
        result = list(lines)
        for i in plan['ids']:
            result[i] = 'a'*plan['line_targets'][i]
        self.assertEqual(budget.count(budget.join_lines(result)), plan['target_chars'])
        self.assertEqual(sum(plan['line_targets'][i]-len(lines[i]) for i in plan['ids']),
                         plan['required_change'])

    def test_refinement_large_gap_uses_multiple_passes_without_extreme_phrase_caps(self):
        lines = ['a'*100]*4
        plan = budget.refinement_plan('s'*200, lines)
        self.assertEqual(plan['ids'], [0, 1, 2, 3])
        self.assertEqual(plan['required_change'], 48)
        self.assertTrue(all(value == 88 for value in plan['line_targets'].values()))
        self.assertGreater(403-plan['required_change'], plan['target_chars'])

    def test_refinement_no_work_within_budget_and_rejects_bad_source_mapping(self):
        self.assertEqual(budget.refinement_plan('s'*100, ['a'*100])['ids'], [])
        with self.assertRaises(ValueError):
            budget.refinement_plan('s'*100, ['a'*120], [])
        with self.assertRaises(ValueError):
            budget.refinement_plan('s', ['a', 'b'])

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
        self.assertEqual(rewrite.call_count, 3)
        self.assertIn('unchanged', rewrite.call_args_list[1].args[1]['last_issue'])
        self.assertEqual(failure.exception.lines, ['t'*120])

    def test_malformed_response_does_not_discard_completed_source_units(self):
        rewrite = Mock(side_effect=[{}, ['a'*110], ['a'*100]])
        result = budget.fit('s'*100, ['a'*120], rewrite)
        self.assertEqual(result['passes'], 3)
        self.assertEqual(rewrite.call_count, 3)
        self.assertIn('Every original phrase', rewrite.call_args_list[1].args[1]['last_issue'])

    def test_exhaustion_preserves_latest_draft_for_review(self):
        rewrite = Mock(side_effect=[['a'*119], ['a'*118], ['a'*117]])
        with self.assertRaises(budget.BudgetError) as failure:
            budget.fit('s'*100, ['a'*120], rewrite, max_passes=3)
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

    def test_continues_beyond_three_passes_while_progressing(self):
        rewrite = Mock(side_effect=[['a'*n] for n in (150, 140, 130, 120, 110, 100)])
        result = budget.fit('s'*100, ['a'*160], rewrite)
        self.assertEqual(result['passes'], 6)
        self.assertTrue(result['report']['within_budget'])
        self.assertIsNone(rewrite.call_args.args[1]['max_passes'])

    def test_regressing_draft_never_replaces_best_and_progress_resets_stall(self):
        rewrite = Mock(side_effect=[['a'*110], ['a'*140], ['a'*110], ['a'*105], ['a'*100]])
        result = budget.fit('s'*100, ['a'*120], rewrite)
        self.assertEqual(result['passes'], 5)
        self.assertEqual(rewrite.call_args_list[2].args[0], ['a'*110])
        self.assertEqual(rewrite.call_args_list[3].args[0], ['a'*110])
        self.assertEqual(rewrite.call_args_list[4].args[1]['stalled_passes'], 0)

    def test_partial_updates_merge_and_preserve_untouched_phrase_ids(self):
        rewrite = Mock(side_effect=[{1: 'b'*55}, {0: 'a'*44}])
        checkpoints = Mock()
        result = budget.fit('s'*100, ['a'*80, 'b'*80], rewrite, on_checkpoint=checkpoints)
        self.assertEqual(result['lines'], ['a'*44, 'b'*55])
        self.assertEqual(rewrite.call_args_list[1].args[0], ['a'*80, 'b'*55])
        self.assertEqual(rewrite.call_args_list[1].args[1]['pending_ids'], [0])
        self.assertEqual(checkpoints.call_args_list[1].args[0], ['a'*80, 'b'*55])

    def test_valid_partial_survives_invalid_and_duplicate_other_ids(self):
        response = {0: 'a'*30, 1: 'invalid', '1': 'ambiguous', 2: '', 99: 'unknown'}
        with self.assertRaises(budget.BudgetError) as failure:
            budget.fit('s'*100, ['a'*60, 'b'*60, 'c'*60], Mock(return_value=response), max_passes=1)
        self.assertEqual(failure.exception.lines, ['a'*30, 'b'*60, 'c'*60])
        self.assertEqual(failure.exception.reason, 'pass_limit')
        self.assertTrue(failure.exception.resumable)

    def test_stalled_pause_preserves_best_and_can_resume_without_repeating_work(self):
        saved = []
        rewrite = Mock(side_effect=[['a'*110], ['a'*150], ['a'*140], ['a'*130]])
        with self.assertRaises(budget.BudgetError) as failure:
            budget.fit('s'*100, ['a'*120], rewrite,
                       on_checkpoint=lambda *args: saved.append(args))
        error = failure.exception
        self.assertEqual((error.lines, error.reason, error.passes), (['a'*110], 'stalled', 4))
        self.assertTrue(error.resumable)
        self.assertEqual(saved[-1][0], error.lines)
        self.assertIn('saved', saved[-1][3])
        resumed_rewrite = Mock(return_value=['a'*100])
        result = budget.fit('s'*100, error.lines, resumed_rewrite)
        self.assertEqual(resumed_rewrite.call_args.args[0], ['a'*110])
        self.assertEqual(result['passes'], 1)

    def test_meaning_correction_gets_refitted_and_audited_again(self):
        validate = Mock(side_effect=[['correct '*17], True])
        rewrite = Mock(return_value=['b'*100])
        saved = Mock()
        result = budget.fit('s'*100, ['a'*100], rewrite, validate=validate, on_checkpoint=saved)
        self.assertEqual(validate.call_count, 2)
        self.assertEqual(rewrite.call_args.args[0], [('correct '*17).strip()])
        self.assertEqual(result['lines'], ['b'*100])
        self.assertEqual(saved.call_args_list[1].args[0], [('correct '*17).strip()])

    def test_within_budget_corrections_are_reaudited_and_unchanged_list_accepts(self):
        rewrite = Mock()
        validate = Mock(side_effect=[['b'*100], ['b'*100]])
        result = budget.fit('s'*100, ['a'*100], rewrite, validate=validate)
        self.assertEqual(result['lines'], ['b'*100])
        self.assertEqual(result['passes'], 0)
        self.assertEqual(validate.call_count, 2)
        rewrite.assert_not_called()

    def test_semantic_cycle_and_endless_changes_pause(self):
        for corrections, reason in [([['b'*100], ['a'*100]], 'validation_cycle'),
                                    ([['b'*100], ['c'*100], ['d'*100], ['e'*100]], 'validation_stalled')]:
            with self.subTest(reason=reason):
                rewrite = Mock()
                with self.assertRaises(budget.BudgetError) as failure:
                    budget.fit('s'*100, ['a'*100], rewrite, validate=Mock(side_effect=corrections))
                self.assertEqual(failure.exception.reason, reason)
                self.assertEqual(failure.exception.lines, corrections[-1])
                rewrite.assert_not_called()

    def test_third_semantic_correction_is_audited_before_stopping(self):
        validate = Mock(side_effect=[['b'*100], ['c'*100], ['d'*100], True])
        result = budget.fit('s'*100, ['a'*100], Mock(), validate=validate)
        self.assertEqual(result['lines'], ['d'*100])
        self.assertEqual(validate.call_count, 4)

    def test_semantic_repairs_continue_while_issue_count_decreases(self):
        corrections = [{'lines': [letter*100], 'issue_count': count}
                       for letter, count in zip('bcdef', (5, 4, 3, 2, 1))]
        validate = Mock(side_effect=corrections+[True])
        result = budget.fit('s'*100, ['a'*100], Mock(), validate=validate)
        self.assertEqual(result['lines'], ['f'*100])
        self.assertEqual(validate.call_count, 6)

    def test_semantic_issue_stagnation_and_invalid_counts_cannot_publish(self):
        corrections = [{'lines': [letter*100], 'issue_count': 5} for letter in 'bcdef']
        with self.assertRaises(budget.BudgetError) as failure:
            budget.fit('s'*100, ['a'*100], Mock(), validate=Mock(side_effect=corrections))
        self.assertEqual(failure.exception.reason, 'validation_stalled')
        for count in (True, -1, None, float('nan')):
            with self.subTest(count=count):
                with self.assertRaises(budget.BudgetError):
                    budget.fit('s'*100, ['a'*100], Mock(),
                               validate=lambda _: {'lines': ['a'*100], 'issue_count': count})
        with self.assertRaises(budget.BudgetError):
            budget.fit('s'*100, ['a'*100], Mock(),
                       validate=lambda _: {'lines': ['a'*100], 'issue_count': 1})

    def test_invalid_semantic_partial_cannot_publish(self):
        with self.assertRaises(budget.BudgetError) as failure:
            budget.fit('s'*100, ['a'*49, 'b'*50], Mock(), validate=lambda _: {0: 'c'*49})
        self.assertEqual(failure.exception.reason, 'validation')
        self.assertEqual(failure.exception.lines, ['a'*49, 'b'*50])

    def test_checkpoint_and_callbacks_receive_detached_inputs(self):
        original = ['a'*120]
        def checkpoint(lines, state, passes, issue):
            lines[0] = 'corrupted'
            state['within_budget'] = True
        result = budget.fit('s'*100, original, Mock(return_value=['b'*100]), on_checkpoint=checkpoint)
        self.assertEqual(original, ['a'*120])
        self.assertEqual(result['lines'], ['b'*100])
        self.assertEqual(result['report']['translated_chars'], 100)

    def test_invalid_limits_and_impossible_budget_do_not_rewrite(self):
        for kwargs in [{'max_passes': -1}, {'max_passes': True}, {'max_passes': 1.5},
                       {'max_stalled_passes': 0}, {'max_stalled_passes': True}]:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    budget.fit('s'*100, ['a'*120], Mock(), **kwargs)
        rewrite = Mock()
        with self.assertRaises(budget.BudgetError) as failure:
            budget.fit('s', ['a', 'b'], rewrite)
        self.assertEqual(failure.exception.reason, 'invalid_budget')
        rewrite.assert_not_called()


class InformationalAssessmentTest(unittest.TestCase):
    def test_spelled_numbers_do_not_create_a_length_failure(self):
        state = budget.assessment('In 2004, he gained 25 pounds in 30 days.',
            'En dos mil cuatro ganó veinticinco libras en treinta días.')
        self.assertTrue(state['advisory_only'])
        self.assertFalse(state['duration_estimate'])
        self.assertEqual(state['source_numeric_tokens'], 3)
        self.assertEqual(state['translated_numeric_tokens'], 0)
        self.assertTrue(state['numeric_forms_differ'])
        self.assertNotIn('within_budget', state)

    def test_counts_remain_exact_for_costs_without_quality_threshold(self):
        state = budget.assessment('abc', 'un texto mucho más largo')
        self.assertEqual(state['source_chars'], 3)
        self.assertEqual(state['translated_chars'], 24)
        self.assertTrue(state['advisory_only'])
        self.assertNotIn('max_chars', state)


if __name__ == '__main__':
    unittest.main()
