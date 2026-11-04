"""A film's duration is not evidence that its translated sentences match scenes."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dubbing_fit as fit
import narration_pacing as pacing
import narration_profile


class PhraseAlignmentTest(unittest.TestCase):
    def test_sync_score_penalizes_early_late_and_end_drift_instead_of_only_counting_valid_phrases(self):
        original=[{'index':0,'start':10,'end':15}]
        self.assertEqual(fit.synchronization_score(original,original)['percent'],100)
        for shift in (2,-2):
            translated=[{'index':0,'start':10+shift,'end':15+shift}]
            report=fit.synchronization_score(original,translated)
            self.assertAlmostEqual(report['percent'],51,delta=.1)
            self.assertEqual(report['outside_limit'],0)
        stretched=fit.synchronization_score(original,[{'start':10,'end':18}])
        self.assertAlmostEqual(stretched['percent'],32.7,delta=.1)
        limit=fit.synchronization_score(original,[{'start':17,'end':22}])
        self.assertEqual(limit['percent'],0)
        self.assertEqual(limit['outside_limit'],0)
        outside=fit.synchronization_score(original,[{'start':18,'end':23}])
        self.assertEqual(outside['outside_limit'],1)

    def test_sync_score_is_equal_weight_timing_only_and_unavailable_for_incomplete_audio(self):
        original=[{'index':0,'start':0,'end':100}, {'index':1,'start':100,'end':102}]
        translated=[{**original[0],'speed':1.08,'text':'Any text'},
                    {'index':1,'start':107,'end':109}]
        report=fit.synchronization_score(original,translated)
        self.assertEqual(report['percent'],50)
        self.assertEqual(report['mean_shift_seconds'],3.5)
        self.assertTrue(report['timing_only'])
        for left,right in [([],[]), (original,translated[:1]),
                           (original,[translated[1],translated[0]]),
                           (original,[translated[0],{'index':1,'start':100,'end':float('nan')}])]:
            self.assertIsNone(fit.synchronization_score(left,right))

    def phrases(self, lengths, span=5):
        return [{'index':i,'start':i*span,'original_start':i*span,'original_end':(i+1)*span,
                 'length':length,'fitted_length':length,'speed':1.}
                for i,length in enumerate(lengths)]

    def assert_aligned(self, result, total):
        self.assertTrue(fit.alignment_report(result)['within_limit'])
        self.assertGreaterEqual(result[0]['start'],0)
        self.assertLessEqual(result[-1]['end'],total+1e-6)
        for item in result:
            self.assertLessEqual(abs(item['start']-item['original_start']),7.000001)
            self.assertLessEqual(abs(item['end']-item['original_end']),7.000001)
        for a,b in zip(result,result[1:]):
            self.assertGreaterEqual(b['start']-a['end'],.049999)

    def test_shorter_dub_uses_pauses_and_returns_to_each_source_anchor(self):
        items=self.phrases([2.5]*40)
        original=copy.deepcopy(items)
        result=fit.centered_schedule(items,200)
        self.assert_aligned(result,200)
        self.assertEqual(items,original)
        self.assertGreater(result[-1]['start'],195)
        self.assertTrue(all(b['start']-a['end']>2 for a,b in zip(result,result[1:])))

    def test_long_silent_source_gap_cannot_centre_speech_far_from_its_scene(self):
        items=[{'index':0,'start':0,'original_start':0,'original_end':2,'fitted_length':2},
               {'index':1,'start':90,'original_start':90,'original_end':92,'fitted_length':2}]
        result=fit.centered_schedule(items,100)
        self.assert_aligned(result,100)
        self.assertLessEqual(result[0]['start'],7)
        self.assertGreater(result[1]['start']-result[0]['end'],70)

    def test_fitting_checks_local_drift_even_when_whole_audio_already_fits(self):
        items=self.phrases([5.3]*40+[4.4]*40)
        self.assertLess(sum(x['fitted_length'] for x in items)+.05*79,400)
        calls=[]
        def render(item,speed):
            calls.append((item['index'],speed))
            return item['length']/speed
        result=fit.fit_measured(items,400,render)
        placed=fit.centered_schedule(result,400)
        self.assert_aligned(placed,400)
        self.assertTrue(calls)
        self.assertTrue(all(fit.MIN_SPEED<=x['speed']<=fit.MAX_SPEED for x in result))
        self.assertEqual([x['length'] for x in result],[x['length'] for x in items])

    def test_end_anchor_is_checked_as_well_as_start(self):
        items=self.phrases([13],span=5)
        with self.assertRaises(fit.AlignmentError):fit.centered_schedule(items,30)
        self.assertFalse(fit.alignment_report([{**items[0],'end':13}])['within_limit'])

    def test_dense_early_section_cannot_borrow_silence_a_minute_later(self):
        items=self.phrases([6]*40+[3]*40)
        render=Mock(side_effect=lambda item,speed:item['length']/speed)
        with self.assertRaises(fit.AlignmentError):fit.fit_measured(items,400,render)
        self.assertLessEqual(render.call_count,len(items)*3)
        with self.assertRaises(fit.AlignmentError):fit.centered_schedule(items,400)

    def test_measured_saved_prefix_blocks_more_spending_before_generation(self):
        segments=[{'start':i*5,'end':(i+1)*5} for i in range(100)]
        # Plenty of total film remains, but this already paid section is late.
        with self.assertRaisesRegex(RuntimeError,'Нові платні запити зупинено'):
            pacing.require_alignment(segments,{i:6 for i in range(20)},500)
        self.assertTrue(pacing.require_alignment(segments,{0:5,20:5,90:5},500)['within_limit'])

    def test_publication_refuses_out_of_bounds_audio_but_keeps_review_data(self):
        manifest=[{'index':2,'start':30,'end':35,'original_start':10,'original_end':15}]
        report=fit.alignment_report(manifest)
        self.assertEqual(report['max_shift_seconds'],20)
        self.assertEqual(report['issues'][0]['index'],2)
        with self.assertRaisesRegex(RuntimeError,'Попередній файл'):
            fit.require_valid_alignment(manifest)

    def test_translation_refinement_catches_cumulative_block_drift(self):
        texts=['a'*56]*40+['b'*44]*40
        segments=[{'start':i*5,'end':(i+1)*5} for i in range(80)]
        profile={'seconds_per_character':.107,'observations':80}
        result=narration_profile.refinement(texts,segments,400,profile)
        proposed={i:result['targets'].get(i,len(text))*.107/fit.MAX_SPEED for i,text in enumerate(texts)}
        self.assertTrue(pacing.alignment_check(segments,proposed,400)['within_limit'])
        self.assertTrue(any(i<40 for i in result['ids']))
        self.assertEqual(texts[0],'a'*56)


if __name__ == '__main__':unittest.main()
