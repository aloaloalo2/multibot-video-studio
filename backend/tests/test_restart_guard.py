import os,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app,store,languages
import episode_ideas

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


    def test_update_waits_for_frame_worker_even_when_project_is_missing_from_status(self):
        pid='b'*24
        with patch.object(app.production,'ACTIVE',{pid}),patch.object(app,'IN_FLIGHT',1), \
             patch.object(app.agent_view,'studio_status',side_effect=lambda *args:{'busy':[],'activities':[],'active_channels':[]}), \
             patch.object(episode_ideas,'active_work',return_value=[]), \
             patch.object(app.trending_videos,'busy',return_value=False), \
             patch.object(app.title_translation,'busy',return_value=False), \
             patch.object(app.channel_translation_voices,'busy',return_value=False), \
             patch.object(app.UPDATE_MANAGER,'apply') as apply,patch.object(app.threading,'Timer') as timer:
            with self.assertRaises(store.StudioError):app.begin_update()
            apply.assert_not_called();timer.assert_not_called()
            self.assertFalse(app.UPDATE_RESTARTING)
            with self.assertRaises(store.StudioError):app.prepare_local_restart()
            app.production.ACTIVE.clear()
            self.assertTrue(app.begin_update())
            apply.assert_called_once()
            timer.return_value.start.assert_called_once()
