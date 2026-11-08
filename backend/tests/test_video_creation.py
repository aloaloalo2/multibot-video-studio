"""The one-step action advances safely through existing recognition, direction and frame jobs."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analysis_jobs
import director
import production
import store


class CreationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = {'id': 'a'*24, 'channel_id': 'c'*16, 'episode_path': str(self.root), 'tracks': []}
        self.plan = {'script_sha256': 'script', 'frame_source': 'razgon-direction', 'frames': [{}, {}, {}]}
        for item in (patch.object(store, 'project_dir', return_value=self.root),
                     patch.object(store, 'load_project', side_effect=lambda pid: self.project),
                     patch.object(store, 'load_project_plan', side_effect=lambda pid: self.plan),
                     patch.object(store, 'project_plan_mode', return_value='director')):
            item.start(); self.addCleanup(item.stop)
        director.ACTIVE.clear(); production.ACTIVE.clear()
        self.addCleanup(director.ACTIVE.clear); self.addCleanup(production.ACTIVE.clear)

    def test_existing_ready_plan_goes_straight_to_frames_only_for_combined_action(self):
        with patch.object(production, 'start_from_plan') as frames, patch.object(director, 'start') as plan:
            director.after_voice(self.project['id'])
            frames.assert_not_called()
            director.after_voice(self.project['id'], create_video=True)
            frames.assert_called_once_with(self.project['id']); plan.assert_not_called()

    def test_new_plan_keeps_automatic_intent_and_current_direction_can_be_joined(self):
        self.plan = {}
        with patch.object(director, 'start') as start:
            director.after_voice(self.project['id'], create_video=True)
            start.assert_called_once_with(self.project['id'], 'create_video')
        director.ACTIVE.add(self.project['id'])
        store.atomic_json(self.root/'director.json', {'status':'running'})
        director.start(self.project['id'], 'create_video')
        self.assertTrue(director.state(self.project['id'])['create_video'])

    def test_direction_releases_its_lock_before_continuing_and_never_continues_a_failure(self):
        pid=self.project['id']; director.ACTIVE.add(pid)
        store.atomic_json(self.root/'director.json', {'status':'done', 'create_video':True})
        with patch.object(director, '_run'), patch.object(production, 'start_from_plan', side_effect=lambda p:self.assertNotIn(p,director.ACTIVE)) as frames:
            director.run(pid, Path('fixture'))
            frames.assert_called_once_with(pid)
        store.atomic_json(self.root/'director.json', {'status':'failed', 'create_video':True})
        with patch.object(director, '_run'), patch.object(production, 'start_from_plan') as frames:
            director.run(pid,Path('fixture'));frames.assert_not_called()

    def test_all_frames_are_requested_once_and_ready_frames_are_reused(self):
        def request(pid,count):
            self.project['production_request']={'status':'requested','frames':count}
            return self.project
        with patch.object(store,'made_frames',return_value=[1]), patch.object(store,'request_production',side_effect=request) as request, patch.object(production,'start') as start:
            production.start_from_plan(self.project['id']);production.start_from_plan(self.project['id'])
            request.assert_called_once_with(self.project['id'],3);start.assert_called_once()
        self.project.pop('production_request')
        with patch.object(store,'made_frames',return_value=[1,2,3]), patch.object(store,'request_production') as request:
            production.start_from_plan(self.project['id']);request.assert_not_called()

    def test_paused_or_uncertain_failed_work_is_never_automatically_replayed(self):
        self.project['production_request']={'status':'failed','script_sha256':'script','paused':True}
        with patch.object(store,'made_frames',return_value=[]), patch.object(store,'request_production') as request:
            with self.assertRaises(store.StudioError):production.start_from_plan(self.project['id'])
            request.assert_not_called()

    def test_cached_recognition_advances_without_another_whisper_or_paid_request(self):
        text='Saved speech.';digest=hashlib.sha256(text.encode()).hexdigest();self.plan['script_sha256']=digest
        job={'id':'j','status':'complete'}
        report={'applied':True,'script_sha256':digest,'source':{'asset_id':'voice','sha256':'audio'}}
        with patch.object(analysis_jobs,'latest',return_value={'job':job,'report':report}), patch.object(store,'resolve_asset',return_value={'path':'voice.mp3'}), patch.object(store,'audio_fingerprint',return_value='audio'), patch.object(store,'load_project_narration',return_value=self.plan), patch.object(director,'after_voice') as after, patch.object(analysis_jobs,'start') as recognize:
            result=analysis_jobs.create_video(self.project,'voice',lambda j:None,lambda i:None,text)
            self.assertEqual(result['id'],'j');self.assertTrue(result['create_video'])
            after.assert_called_once_with(self.project['id'],create_video=True);recognize.assert_not_called()
        self.assertTrue(store.read_json(self.root/'analysis-state.json',{})['create_video'])

    def test_number_formatted_saved_script_keeps_its_recognition_cache(self):
        spoken='Twenty years.';numeric='20 years.'
        spoken_hash=hashlib.sha256(spoken.encode()).hexdigest();numeric_hash=hashlib.sha256(numeric.encode()).hexdigest()
        report={'applied':True,'script_sha256':spoken_hash,'studio_script_sha256':numeric_hash,'source':{'asset_id':'voice','sha256':'audio'}}
        self.plan['script_sha256']=numeric_hash
        with patch.object(analysis_jobs,'latest',return_value={'job':{'id':'j','status':'complete'},'report':report}),patch.object(store,'resolve_asset',return_value={'path':'voice.mp3'}),patch.object(store,'audio_fingerprint',return_value='audio'),patch.object(store,'load_project_narration',return_value=self.plan),patch.object(director,'after_voice') as after,patch.object(analysis_jobs,'start') as recognize:
            analysis_jobs.create_video(self.project,'voice',lambda j:None,lambda i:None,numeric)
            after.assert_called_once_with(self.project['id'],create_video=True);recognize.assert_not_called()

    def test_status_shows_each_stage_and_a_visible_failure(self):
        pid=self.project['id'];store.atomic_json(self.root/'analysis-state.json',{'job_id':'j','create_video':True})
        current={'job':{'status':'running','progress':40},'report':None}
        with patch.object(analysis_jobs,'latest',return_value=current):
            self.assertEqual(analysis_jobs.creation_status(self.project,lambda i:None)['stage'],'recognizing')
            current.update(job={'status':'complete'},report={'applied':True})
            store.atomic_json(self.root/'director.json',{'status':'running'});director.ACTIVE.add(pid)
            self.assertEqual(analysis_jobs.creation_status(self.project,lambda i:None)['stage'],'planning')
            store.atomic_json(self.root/'director.json',{'status':'done'});director.ACTIVE.clear()
            self.project['production_request']={'status':'in_progress','frames':3}
            store.atomic_json(self.root/'director.json',{'status':'done','creation_error':'Previous handoff failed'})
            result=analysis_jobs.creation_status(self.project,lambda i:None)
            self.assertEqual(result['stage'],'creating');self.assertEqual(result['status'],'running')
            self.project['production_request']['status']='done'
            self.assertEqual(analysis_jobs.creation_status(self.project,lambda i:None)['status'],'done')
            self.project.pop('production_request')
            result=analysis_jobs.creation_status(self.project,lambda i:None)
            self.assertEqual(result['stage'],'creating');self.assertEqual(result['status'],'failed')

    def test_a_second_click_joins_running_recognition_without_another_worker(self):
        job={'id':'j','status':'running','source_asset_id':'voice'}
        with patch.object(analysis_jobs,'latest',return_value={'job':job}),patch.object(store,'load_project_narration',return_value=None),patch.object(store,'resolve_asset',return_value={'kind':'audio','name':'voice'}),patch.object(analysis_jobs.threading,'Thread') as worker:
            result=analysis_jobs.start(self.project,'voice',lambda j:None,lambda i:job,create_video=True)
            self.assertEqual(result['id'],'j');self.assertTrue(result['create_video']);worker.assert_not_called()
        self.assertTrue(store.read_json(self.root/'analysis-state.json',{})['create_video'])
