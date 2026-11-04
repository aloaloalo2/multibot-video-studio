import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import narration_pacing as pacing
import languages


class NarrationPacingTest(unittest.TestCase):
    def test_forecast_uses_measured_join_silence_and_reserves_only_missing_edges(self):
        texts=['a'*100]*10;known={i:8. for i in range(9)}
        edge={'leading':.06,'trailing':.06,'speed':1.}
        forecast=pacing.plan(texts,known,80.,9,{i:edge for i in known})
        self.assertLess(forecast['join_seconds'],.01)
        self.assertLess(forecast['predicted_seconds'],80.01)

    def test_uses_measured_voice_pace_without_rewriting_future_words(self):
        texts=['a'*100]*100;known={i:8.0 for i in range(5)}
        plan=pacing.plan(texts,known,700,5)
        self.assertGreater(plan['predicted_seconds'],700)
        self.assertEqual(plan['targets'],{})
        self.assertTrue(plan['requires_review'])
        self.assertGreater(plan['predicted_minimum_seconds'],700)
        self.assertEqual(texts,['a'*100]*100)

    def test_shorter_lines_and_small_calibration_do_not_trigger_rewrites(self):
        self.assertEqual(pacing.plan(['x'*100]*20,{i:5 for i in range(4)},130,4)['targets'],{})
        self.assertEqual(pacing.plan(['x'*100]*20,{i:5 for i in range(5)},130,5)['targets'],{})

    def test_cached_later_phrases_are_never_rewritten_or_rebought(self):
        texts=['a'*100]*100;known={i:8. for i in [0,1,2,3,4,6,9]}
        targets=pacing.plan(texts,known,700,5)['targets']
        self.assertNotIn(6,targets);self.assertNotIn(9,targets)

    def test_impossible_cache_reports_review_and_preserves_allowed_tempo(self):
        report=pacing.plan(['a'*100]*20,{i:8 for i in range(20)},140,0)
        self.assertTrue(report['requires_review'])
        self.assertAlmostEqual(report['measured_excess_seconds'],160/pacing.MAX_SPEED-140,places=3)
        self.assertEqual(report['targets'],{})
        self.assertEqual(pacing.MAX_SPEED,1.12)

    def test_all_cached_takes_are_not_rejected_for_unmeasured_extra_pause_padding(self):
        # The takes include pauses already. Unmeasured extra padding must reach
        # measured assembly rather than trigger a false stop.
        texts=['a'*100]*100
        known={i:10.4 for i in range(100)}
        self.assertGreater(sum(known.values())/pacing.MAX_SPEED+.05*99,930.)
        self.assertEqual(pacing.plan(texts,known,930.,0)['measured_phrases'],100)
        self.assertTrue(pacing.plan(texts,known,920.,0)['requires_review'])

    def test_severe_required_shortening_requests_review(self):
        report=pacing.plan(['a'*100]*100,{i:15 for i in range(5)},700,5)
        self.assertTrue(report['requires_review'])
        self.assertEqual(report['remaining_phrases'],95)
        self.assertEqual(report['targets'],{})

    def test_fit_forecast_uses_all_allowed_tempo_even_near_completion(self):
        # The old 1.03 budget subtracted already measured raw takes and wrongly
        # stopped after 95 phrases, although the complete voice fits at 1.08.
        texts=['a'*100]*100
        for count in (5,55,95,99):
            forecast=pacing.plan(texts,{i:10. for i in range(count)},940.,count)
            self.assertAlmostEqual(forecast['predicted_seconds'],1004.95,places=3)
            self.assertLess(forecast['expected_minimum_seconds'],940.)
            self.assertEqual(forecast['remaining_phrases'],100-count)
            self.assertEqual(forecast['targets'],{})
        self.assertEqual(pacing.MAX_SPEED,1.12)

    def test_reserved_future_duration_does_not_discount_already_measured_audio(self):
        forecast=pacing.plan(['a'*100]*100,{i:8. for i in range(90)},760.,90)
        self.assertAlmostEqual(forecast['predicted_seconds'],804.95,places=3)
        self.assertAlmostEqual(forecast['expected_minimum_seconds'],800/pacing.MAX_SPEED+4.95,places=3)
        self.assertAlmostEqual(forecast['predicted_minimum_seconds'],(720+80*1.03)/pacing.MAX_SPEED+4.95,places=3)

    def test_does_not_accept_missing_lines_or_a_summary(self):
        for value in [{},{0:'too short'},{0:'a'*91}]:
            with self.assertRaises(RuntimeError):pacing.validate_edits(['a'*100],{0:90},value)
        pacing.validate_edits(['a'*100],{0:90},{0:'a'*85})

    def test_dense_line_can_borrow_budget_without_expanding_or_losing_meaning_checks(self):
        texts=['a'*100,'b'*100]
        pacing.validate_edits(texts,{0:90,1:90},{0:'a'*100,1:'b'*80})
        for replacements in [{0:'a'*100,1:'b'*81},{0:'a'*110,1:'b'*70}]:
            with self.assertRaises(RuntimeError):pacing.validate_edits(texts,{0:90,1:90},replacements)

    def test_price_is_frozen_for_the_run(self):
        with patch.object(languages,'price',side_effect=[200,500]) as prices:
            price=languages.fixed_price('elevenlabs','eleven_v4_turbo')
            self.assertEqual(price('a'*100),20)
            self.assertEqual(price('b'*100),20)
            self.assertEqual(prices.call_count,1)
