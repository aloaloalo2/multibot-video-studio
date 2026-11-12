from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import production_sessions as sessions


class ProductionSessionsTest(unittest.TestCase):
    def run_job(self,launch=None,verify=None,checkpoint=None,cancelled=None,previous=None):
        self.launch=launch or Mock(side_effect=lambda frames,summary,index:(0,{'result':f'Batch {index}','session_id':str(index),'total_cost_usd':.1,'usage':{'input_tokens':10}}))
        self.receipt=checkpoint or Mock()
        return sessions.run(range(1,46),self.launch,verify or (lambda _:True),self.receipt,cancelled or (lambda:False),lambda answer:answer.get('limit'),previous=previous)

    def test_long_work_is_scoped_and_costs_include_all_fresh_sessions(self):
        code,answer=self.run_job();self.assertEqual(code,0)
        self.assertEqual([len(call.args[0]) for call in self.launch.call_args_list],[20,20,5])
        self.assertEqual(answer['usage']['input_tokens'],30);self.assertAlmostEqual(answer['total_cost_usd'],.3)
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
        self.assertEqual(code,0);self.assertEqual(self.launch.call_args_list[0].args[0],list(range(21,41)))
        self.assertEqual(self.launch.call_count,2)

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
