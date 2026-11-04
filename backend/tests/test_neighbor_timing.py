"""Small tempo changes must help adjacent speech, not just fit the film's end."""
import copy
import math
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dubbing_fit as fit
import narration_alignment


class NeighborTimingTest(unittest.TestCase):
    def item(self, index, start, end, raw, speed=1.):
        return {'index':index, 'original_start':start, 'original_end':end,
                'start':start, 'length':raw, 'speed':speed, 'fitted_length':raw/speed,
                'text':f'unchanged phrase {index}',
                'edge_silence':{'leading':.1,'trailing':.1,'speed':speed}}

    def error(self, placed):
        return sum((p[e]-p[f'original_{e}'])**2 for p in placed for e in ('start','end'))

    def test_previous_tempo_is_optimized_for_the_following_chain_and_isolated_speech_is_untouched(self):
        # First take can fit its own slot, but it leaves no room for its neighbours.
        items=[self.item(0,0,10,10),self.item(1,10,15,5.5,1.07),
               self.item(2,15,20,5.5,1.07),self.item(3,20,25,5.3,1.04),
               self.item(4,50,55,5)]
        original=copy.deepcopy(items);calls=[]
        def render(item,speed):
            calls.append(item['index'])
            return item['length']/speed
        before=fit.centered_schedule(items,60)
        result=fit.fit_measured(items,60,render)
        after=fit.centered_schedule(result,60)
        self.assertLess(self.error(after),self.error(before)*.5)
        self.assertGreater(result[0]['speed'],1.01)
        self.assertNotIn(4,calls)
        self.assertTrue(all(.92<=p['speed']<=1.08 for p in result))
        self.assertEqual(items,original)
        self.assertEqual([p['text'] for p in result],[p['text'] for p in items])
        self.assertTrue(fit.alignment_report(after)['within_limit'])
        self.assertTrue(all(a['end']<=b['start']+1e-6 for a,b in zip(after,after[1:])))

    def test_early_speech_can_slow_and_use_pauses_to_reset_to_source(self):
        items=[self.item(0,10,20,9.6,1.04),self.item(1,20.5,25.5,5),
               self.item(2,50,55,5)]
        result=fit.fit_measured(items,60,lambda item,speed:item['length']/speed)
        placed=fit.centered_schedule(result,60)
        self.assertLess(result[0]['speed'],1)
        self.assertAlmostEqual(placed[1]['start'],20.5,places=4)
        self.assertAlmostEqual(placed[2]['start'],50,places=4)
        self.assertGreater(placed[2]['start']-placed[1]['end'],24)

    def test_actual_duration_rejects_bad_prediction_and_restores_fitted_buffers(self):
        items=[self.item(0,0,10,10.5),self.item(1,11,21,10)]
        buffers={p['index']:p['fitted_length'] for p in items};calls=[]
        def render(item,speed):
            calls.append((item['index'],speed))
            length=items[item['index']]['fitted_length'] if speed==items[item['index']]['speed'] else 50.
            buffers[item['index']]=length
            return length
        result=fit.fit_measured(items,25,render)
        self.assertTrue(calls)
        self.assertEqual(result,items)
        self.assertEqual(buffers,{p['index']:p['fitted_length'] for p in items})

    def test_missing_anchors_or_nonconvergent_optimizer_retains_valid_audio(self):
        items=[self.item(0,0,10,10)]
        with patch('narration_alignment.propose',return_value=None):
            self.assertEqual(fit.fit_measured(items,10,lambda *_:self.fail('No rendering needed')),items)

    def test_long_packed_chain_converges_with_active_neighbour_constraints(self):
        # Many adjacent constraints stay active at once. Local projection sweeps
        # used to time out on a real 341-phrase narration and keep the capped fit.
        items=[self.item(i, i*5., (i+1)*5.,
                         (5.+.08*math.sin(i/19))*1.08, 1.08) for i in range(341)]
        total=max(341*5.,sum(x['fitted_length'] for x in items))+1
        speeds=narration_alignment.propose(items,total,[0.]*340,
            min_speed=fit.MIN_SPEED,max_speed=fit.MAX_SPEED,max_shift=fit.MAX_SHIFT)
        self.assertIsNotNone(speeds)
        candidate=[{**x,'speed':s,'fitted_length':x['length']/s} for x,s in zip(items,speeds)]
        placed=fit.centered_schedule(candidate,total,gap=0)
        before=fit.centered_schedule(items,total,gap=0)
        self.assertLessEqual(self.error(placed),self.error(before)+1e-4)
        self.assertTrue(fit.alignment_report(placed)['within_limit'])
        self.assertTrue(all(.92<=s<=1.08 for s in speeds))
        self.assertTrue(all(a['end']<=b['start']+1e-6 for a,b in zip(placed,placed[1:])))

    def test_joint_solution_matches_known_single_phrase_optimum(self):
        # Source span 10, natural take 10.5: quarter-weight duration penalty
        # yields duration (10 + .5*10.5)/1.5, centred on the source midpoint.
        item=self.item(0,10,20,10.5)
        speed=narration_alignment.propose([item],40,[],min_speed=.92,max_speed=1.08,max_shift=7)[0]
        self.assertAlmostEqual(speed,10.5/((10+.5*10.5)/1.5),places=6)

    def test_locally_infeasible_chain_has_no_proposal(self):
        # Total free space is large but no permitted tempo fits this short anchor.
        item=self.item(0,10,11,30,1.08)
        speeds=narration_alignment.propose([item],100,[],min_speed=.92,max_speed=1.08,max_shift=7)
        self.assertIsNone(speeds)


if __name__=='__main__':unittest.main()
