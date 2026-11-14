from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import production_sessions as sessions


class ProductionSessionsTest(unittest.TestCase):
    def run_job(self,launch=None,verify=None,checkpoint=None,cancelled=None,previous=None,parallel=1):
        self.launch=launch or Mock(side_effect=lambda frames,summary,index:(0,{'result':f'Batch {index}','session_id':str(index),'total_cost_usd':.1,'usage':{'input_tokens':10}}))
        self.receipt=checkpoint or Mock()
        return sessions.run(range(1,46),self.launch,verify or (lambda _:True),self.receipt,cancelled or (lambda:False),lambda answer:answer.get('limit'),previous=previous,parallel=parallel)

    def test_long_work_is_scoped_and_costs_include_all_fresh_sessions(self):
        code,answer=self.run_job();self.assertEqual(code,0)
        self.assertEqual([len(call.args[0]) for call in self.launch.call_args_list],[10,10,10,10,5])
        self.assertEqual(answer['usage']['input_tokens'],50);self.assertAlmostEqual(answer['total_cost_usd'],.5)
        self.assertEqual(self.receipt.call_args.args[0]['remaining_frames'],[])

    def test_short_work_keeps_the_existing_single_session(self):
        launch=Mock(return_value=(0,{'result':'done'}))
        sessions.run([41,42,43],launch,lambda _:True,Mock(),lambda:False,lambda _:False)
        launch.assert_called_once_with([41,42,43],'',0)

    def test_empty_work_never_opens_a_paid_session(self):
        launch=Mock()
        code,_=sessions.run([],launch,lambda _:True,Mock(),lambda:False,lambda _:False)
        self.assertEqual(code,0)
        launch.assert_not_called()

    def test_verified_checkpoint_skips_completed_work_without_paid_replay(self):
        code,_=self.run_job(previous={'completed_frames':list(range(1,21)),'summary':'Earlier work'})
        self.assertEqual(code,0);self.assertEqual(self.launch.call_args_list[0].args[0],list(range(21,31)))
        self.assertEqual(self.launch.call_count,3)

    def test_partial_checkpoint_resumes_only_unapproved_or_changed_frames(self):
        saved={1,2,3,4,5}
        current={1,2,4,5}
        def launch(frames,summary,index):
            self.assertEqual(frames,[3,6,7,8])
            current.update(frames)
            return 0, {'result':'ready'}
        code,_=sessions.run(list(range(1,9)),launch,lambda ns:set(ns)<=current,Mock(),
                            lambda:False,lambda _:False,previous={'completed_frames':sorted(saved)})
        self.assertEqual(code,0)

    def test_failure_quota_or_incomplete_frames_never_launch_another_session(self):
        for answer,valid in (({'is_error':True},True),({'limit':True},True),({'result':'not complete'},False)):
            launch=Mock(return_value=(0,answer));code,_=self.run_job(launch=launch,verify=lambda _:valid)
            self.assertNotEqual(code,0);self.assertEqual(launch.call_count,1);self.receipt.assert_not_called()

    def test_cancellation_and_failed_checkpoint_stop_before_another_paid_session(self):
        cancelled=Mock(side_effect=[False,True])
        with self.assertRaises(InterruptedError):self.run_job(cancelled=cancelled)
        self.assertEqual(self.launch.call_count,1);self.receipt.assert_not_called()
        save=Mock(side_effect=OSError('disk full'))
        with self.assertRaises(OSError):self.run_job(checkpoint=save)
        self.assertEqual(self.launch.call_count,1)

    def test_stale_visual_review_continues_only_pending_frames_and_records_both_costs(self):
        launch=Mock(side_effect=lambda ns,summary,index:(0,{'result':'reviewed','total_cost_usd':.1,'usage':{'input_tokens':20}}))
        verify=Mock(side_effect=[False,True]);save=Mock()
        code,answer=sessions.run(range(21,31),launch,verify,save,lambda:False,lambda _:False,pending_review=lambda:[25])
        self.assertEqual(code,0)
        self.assertEqual([call.args[0] for call in launch.call_args_list],[list(range(21,31)),[25]])
        self.assertIn('лише актуальний візуальний огляд',launch.call_args_list[1].args[1])
        self.assertAlmostEqual(answer['total_cost_usd'],.2)
        self.assertEqual(answer['usage']['input_tokens'],40)
        self.assertEqual(save.call_args.args[0]['completed_frames'],list(range(21,31)))

    def test_final_review_covers_earlier_frames_in_bounded_fresh_sessions(self):
        launch=Mock(return_value=(0,{'result':'reviewed','total_cost_usd':.1,'usage':{'input_tokens':20}}))
        code,answer=sessions.finish_review([*range(1,31),39,40],launch,lambda ns:True,lambda:False,lambda _:False)
        self.assertEqual(code,0)
        self.assertEqual([call.args[0] for call in launch.call_args_list],[list(range(1,11)),list(range(11,21)),list(range(21,31)),[39,40]])
        self.assertTrue(all(call.args[2]>=2000 for call in launch.call_args_list))
        self.assertIn('лише актуальний візуальний огляд',launch.call_args.args[1])
        combined=sessions.merge_answers({'total_cost_usd':1,'usage':{'input_tokens':100}},answer)
        self.assertAlmostEqual(combined['total_cost_usd'],1.4)
        self.assertEqual(combined['usage']['input_tokens'],180)

    def test_visual_review_continuation_is_bounded_and_never_expands_its_scope(self):
        for pending,count in (([5],2),([15],1)):
            launch=Mock(return_value=(0,{'result':'returned'}))
            code,_=sessions.run(range(1,11),launch,lambda _:False,Mock(),lambda:False,lambda _:False,pending_review=lambda:pending)
            self.assertNotEqual(code,0)
            self.assertEqual(launch.call_count,count)

    def test_two_sessions_run_side_by_side_and_cover_every_frame_once(self):
        # Two sessions of ten at once (user, 14 November 2026): the same frames and costs, about half the time.
        import threading, time
        live, peak, seen, lock = [], [0], [], threading.Lock()
        def launch(frames, summary, index):
            with lock:
                live.append(index); peak[0] = max(peak[0], len(live)); seen.extend(frames)
            time.sleep(.05)
            with lock:
                live.remove(index)
            return 0, {'result': f'Batch {index}', 'total_cost_usd': .1}
        code, answer = sessions.run(range(1, 46), launch, lambda _: True, Mock(), lambda: False, lambda _: False, parallel=2)
        self.assertEqual(code, 0)
        self.assertEqual(peak[0], 2)
        self.assertEqual(sorted(seen), list(range(1, 46)))
        self.assertAlmostEqual(answer['total_cost_usd'], .5)

    def test_a_failed_side_session_starts_no_new_session(self):
        calls = []
        def launch(frames, summary, index):
            calls.append(index)
            return (0, {'is_error': True}) if index == 1 else (0, {'result': 'ok'})
        code, _ = sessions.run(range(1, 46), launch, lambda _: True, Mock(), lambda: False, lambda _: False, parallel=2)
        self.assertNotEqual(code, 0)
        self.assertLessEqual(len(calls), 2)


if __name__ == '__main__':
    unittest.main()
