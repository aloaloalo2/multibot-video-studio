import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import narration_pacing as pacing
import languages


class NarrationPacingTest(unittest.TestCase):
    def test_uses_measured_same_voice_pace_and_only_edits_unpaid_lines(self):
        texts=['a'*100]*100;known={i:8.0 for i in range(5)}
        plan=pacing.plan(texts,known,700,5)
        self.assertGreater(plan['predicted_seconds'],700)
        self.assertEqual(set(plan['targets']),set(range(5,15)))
        self.assertTrue(all(65<=n<100 for n in plan['targets'].values()))
        self.assertEqual(texts,['a'*100]*100)

    def test_shorter_lines_and_small_calibration_do_not_trigger_rewrites(self):
        self.assertEqual(pacing.plan(['x'*100]*20,{i:5 for i in range(4)},130,4)['targets'],{})
        self.assertEqual(pacing.plan(['x'*100]*20,{i:5 for i in range(5)},130,5)['targets'],{})

    def test_cached_later_phrases_are_never_rewritten_or_rebought(self):
        texts=['a'*100]*100;known={i:8. for i in [0,1,2,3,4,6,9]}
        targets=pacing.plan(texts,known,700,5)['targets']
        self.assertNotIn(6,targets);self.assertNotIn(9,targets)

    def test_impossible_cache_stops_before_payment_and_preserves_seven_percent(self):
        with self.assertRaisesRegex(RuntimeError,'Нові платні запити зупинено'):
            pacing.plan(['a'*100]*20,{i:8 for i in range(20)},140,0)
        self.assertEqual(pacing.MAX_SPEED,1.07)

    def test_severe_required_shortening_requests_review(self):
        with self.assertRaisesRegex(RuntimeError,'надто сильного скорочення'):
            pacing.plan(['a'*100]*100,{i:15 for i in range(5)},700,5)

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
