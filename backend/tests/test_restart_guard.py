import os,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app,store,languages

class RestartGuardTest(unittest.TestCase):
    def tearDown(self):
        app.UPDATE_RESTARTING=False
        languages.ACTIVE.clear()

    def test_restart_is_refused_while_a_thumbnail_or_an_inflight_mutation_runs(self):
        with patch.object(app,'IN_FLIGHT',2):
            with self.assertRaises(store.StudioError):app.prepare_local_restart()
        with patch.object(app,'IN_FLIGHT',1),patch.object(app.agent_view,'studio_status',return_value={'busy':['мови: channel / project']}):
            with self.assertRaises(store.StudioError):app.prepare_local_restart()
        self.assertFalse(app.UPDATE_RESTARTING)

    def test_preparation_closes_the_gate_before_another_request_can_start(self):
        with patch.object(app,'IN_FLIGHT',1),patch.object(app.agent_view,'studio_status',return_value={'busy':[]}),patch.object(app.threading,'Timer'):
            self.assertTrue(app.prepare_local_restart()['prepared'])
            self.assertTrue(app.UPDATE_RESTARTING)
            with self.assertRaises(store.StudioError):app.prepare_local_restart()

    def test_active_language_worker_blocks_restart_even_if_disk_status_is_stale(self):
        pid='a'*24;languages.ACTIVE.add(languages.job_key(pid,'pl','thumbnail'))
        with patch.object(store,'load_project',return_value={}),patch.object(app.analysis_jobs,'latest',return_value={}), \
             patch.object(app.director,'state',return_value={}),patch.object(app.thumbnail_gen,'state',return_value={}), \
             patch.object(app.agent_runtime,'snapshot',return_value={}),patch.object(languages,'load_state',return_value={'jobs':{'pl|thumbnail':{'status':'failed'}}}):
            self.assertEqual(app.project_jobs(pid)['мови'],'running')
