import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import production_edits as edits
import production
import store


class EditQueueTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.pid='a'*24
        self.folder=self.root/'projects'/self.pid;self.folder.mkdir(parents=True)
        self.project={'id':self.pid,'production_request':{'id':'job','frames':3,'fixes':0,'status':'done'}}
        self.stack=[]
        for p in [patch.object(store,'DATA_ROOT',self.root),patch.object(store,'project_dir',return_value=self.folder),
                  patch.object(store,'load_project',side_effect=lambda pid:self.project),
                  patch.object(store,'load_project_plan',return_value={'frames':[{'number':i} for i in [1,2,3]]})]:
            p.start();self.addCleanup(p.stop)
        production.ACTIVE.clear();self.addCleanup(production.ACTIVE.clear)

    def enqueue(self,n,notes='Fix text'):
        return edits.enqueue(self.pid,notes,[n],f'client-id-{n}')

    def start(self,pid,notes,frame_numbers):
        self.project['production_request'].update(status='in_progress',notes=notes,repair_frames=frame_numbers,
            fixes=self.project['production_request']['fixes']+1)
        production.ACTIVE.add(pid)

    def test_edits_can_be_saved_while_the_agent_is_busy_and_survive_reload(self):
        self.project['production_request']['status']='in_progress'
        self.enqueue(2)
        with patch.object(production,'fix') as start:edits.tick();start.assert_not_called()
        self.assertEqual(edits.overview(self.pid)['queued'],1)
        self.assertEqual(edits.read(self.pid)[0]['frame_numbers'],[2])

    def test_fifo_runs_one_edit_at_a_time_and_never_retries_completed_work(self):
        self.enqueue(2);self.enqueue(3,'Change picture')
        with patch.object(production,'fix',side_effect=self.start) as start:
            edits.tick();edits.tick();self.assertEqual(start.call_count,1)
            self.assertEqual([j['status'] for j in edits.read(self.pid)],['running','queued'])
            production.ACTIVE.clear();self.project['production_request']['status']='done'
            edits.tick();self.assertEqual(start.call_count,2)
            self.assertEqual(start.call_args.kwargs['frame_numbers'],[3])
            self.assertEqual([j['status'] for j in edits.read(self.pid)],['done','running'])

    def test_duplicate_submission_is_idempotent(self):
        self.enqueue(2);self.enqueue(2)
        self.assertEqual(len(edits.read(self.pid)),1)
        with self.assertRaises(store.StudioError):self.enqueue(2,'Different edit')

    def test_waiting_edits_can_be_removed_and_export_blocks_start(self):
        job=self.enqueue(2)['jobs'][0]
        with patch.object(production,'fix') as start:edits.tick([self.pid]);start.assert_not_called()
        edits.cancel(self.pid,job['id'])
        self.assertEqual(edits.overview(self.pid)['queued'],0)

    def test_quota_or_author_pause_does_not_start_another_paid_turn(self):
        self.enqueue(2);self.project['production_request'].update(status='failed',limit=True)
        with patch.object(production,'fix') as start:edits.tick();start.assert_not_called()

    def test_uncertain_start_after_restart_is_not_replayed(self):
        job=self.enqueue(2)['jobs'][0]
        job.update(status='starting',request_id='job',fixes=1)
        store.atomic_json(edits.path(self.pid),[job])
        with patch.object(production,'fix') as start:edits.tick();start.assert_not_called()
        self.assertEqual(edits.read(self.pid)[0]['status'],'failed')


if __name__=='__main__':unittest.main()
