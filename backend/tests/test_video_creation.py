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

    def test_failed_alignment_reuses_the_same_audio_words_for_targeted_repair(self):
        text='Saved speech.';digest=hashlib.sha256(text.encode()).hexdigest()
        report={'applied':False,'script_sha256':digest,'source':{'asset_id':'voice','sha256':'audio'},'words':[{'text':'Saved'}]}
        with patch.object(analysis_jobs,'latest',return_value={'job':{'id':'previous','status':'complete'},'report':report}), \
             patch.object(store,'resolve_asset',return_value={'path':'voice.mp3'}), \
             patch.object(store,'audio_fingerprint',return_value='audio'), \
             patch.object(store,'load_project_narration',return_value=None), \
             patch.object(analysis_jobs,'start') as recognize:
            analysis_jobs.create_video(self.project,'voice',lambda j:None,lambda i:None,text)
        self.assertEqual(recognize.call_args.kwargs,{'create_video':True,'reuse_report_id':'previous'})

    def run_cached_analysis(self, previous, sequence=None, recognition_error=None, expect_failure=False, thread_error=None, handoff_error=None):
        text='Saved speech.'
        published=[];handoff=[]
        self.project['name']='Cached recognition'
        words=[{'text':'Saved','start':0,'end':.4,'probability':.99},{'text':'speech.','start':.5,'end':.9,'probability':.99}]
        asset={'id':'voice','path':str(self.root/'voice.wav'),'kind':'audio','name':'voice.wav'}
        store.atomic_json(self.root/'analysis'/'previous'/'result.json',previous)
        job={'id':'next','project_id':self.project['id'],'source_asset_id':'voice','script_from':'request','reuse_report_id':'previous'}
        with patch.object(store,'resolve_asset',return_value=asset), \
             patch.object(store,'audio_fingerprint',return_value='audio'), \
             patch.object(store,'media_duration',return_value=2), \
             patch.object(store,'load_project_narration',return_value=None), \
             patch.object(store,'generate_project_plan',return_value={'plan':{'script_sha256':hashlib.sha256(text.encode()).hexdigest()}}), \
             patch.object(analysis_jobs.narration_ending,'prepare_asset',return_value=asset), \
             patch.object(analysis_jobs.narration_sequence,'verify',return_value=sequence), \
             patch.object(analysis_jobs.speech,'transcribe',side_effect=recognition_error,return_value=(words,{'engine':'fresh','language':'en'})) as recognize, \
             patch.object(analysis_jobs.speech_repair,'repair',side_effect=lambda p,w,l:(w,0)), \
             patch.object(analysis_jobs.speech_repair,'repair_script',side_effect=lambda p,s,w,l,**kw:(w,1)) as repair, \
             patch.object(analysis_jobs.threading,'Thread',side_effect=thread_error), patch.object(director,'after_voice',side_effect=handoff_error or (lambda *args,**kw:handoff.append(dict(published[-1])))):
            analysis_jobs.worker(job,text,lambda j:published.append(dict(j)))
        self.last_job=job
        if expect_failure:
            self.assertEqual(job['status'], 'failed')
            self.assertFalse(handoff)
            repair.assert_not_called()
            return recognize.call_count, job
        self.assertEqual(job['status'],'complete',job.get('error'))
        self.assertTrue(job['applied'])
        if sequence and sequence.get('sentence_timings'):
            repair.assert_not_called()
        else:
            repair.assert_called_once()
            self.assertTrue(repair.call_args.kwargs['order_only'])
        self.handoff_observations=handoff
        return recognize.call_count,store.read_json(self.root/'analysis'/'next'/'result.json')

    def test_proven_take_boundaries_advance_without_repairing_asr_spelling(self):
        proof = {'version': 2, 'source': 'generated_takes', 'sentences': 1,
                 'sentence_timings': [{'start': 0., 'end': 1.5}]}
        _, report = self.run_cached_analysis({}, proof)
        self.assertTrue(report['applied'])
        self.assertEqual(report['timing_source'], 'generated_takes')
        self.assertEqual(report['timings']['sentences'][0]['end'], 1.5)
        self.assertEqual(report['engine']['repaired_script_phrases'], 0)

    def test_uploaded_narration_records_order_policy_without_claiming_generated_assembly(self):
        _, report = self.run_cached_analysis({})
        self.assertTrue(report['applied'])
        self.assertEqual(report['recognition_policy'], 'sentence_order')
        self.assertNotIn('sequence_verification', report)

    def test_failure_status_names_only_real_missing_or_moved_phrases_under_order_policy(self):
        store.atomic_json(self.root/'analysis-state.json', {'job_id':'j','create_video':True})
        report = {'applied':False,'recognition_policy':'sentence_order', 'phrases':[
            {'number':12,'issues':['number_difference']},
            {'number':13,'issues':['low_phrase_match']},
            {'number':95,'issues':['out_of_order']}]}
        with patch.object(analysis_jobs, 'latest', return_value={'job':{'status':'complete'},'report':report}):
            result = analysis_jobs.creation_status(self.project, lambda _:None)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['error'], 'Потрібно уточнити порядок або наявність фраз: 95')

    def test_recognizer_failure_uses_proven_take_times_and_unknown_audio_still_stops(self):
        proof = {'version': 2, 'source': 'generated_takes', 'sentences': 1,
                 'sentence_timings': [{'start': 0., 'end': 1.5}]}
        _, report = self.run_cached_analysis({}, proof, RuntimeError('Local recognizer unavailable'))
        self.assertTrue(report['applied'])
        self.assertEqual(report['engine']['engine'], 'generated-takes')
        self.assertEqual([word['text'] for word in report['aligned_words']], ['Saved', 'speech.'])
        _, job = self.run_cached_analysis({}, recognition_error=RuntimeError('Local recognizer unavailable'), expect_failure=True)
        self.assertIn('Local recognizer unavailable', job['error'])

    def test_analysis_completion_is_published_only_after_director_handoff(self):
        self.run_cached_analysis({})
        self.assertEqual(len(self.handoff_observations),1)
        self.assertEqual(self.handoff_observations[0]['status'],'running')
        self.assertEqual(self.handoff_observations[0]['stage'],'comparing')

    def test_optional_archive_thread_failure_never_prevents_director_handoff(self):
        self.run_cached_analysis({},thread_error=RuntimeError('No archive worker'))
        self.assertEqual(len(self.handoff_observations),1)
        self.assertNotIn('handoff_error',self.last_job)

    def test_director_handoff_failure_preserves_applied_recognition_and_exposes_reason(self):
        self.run_cached_analysis({},handoff_error=RuntimeError('Director could not start'))
        store.atomic_json(self.root/'analysis-state.json',{'job_id':'next','create_video':True})
        with patch.object(analysis_jobs,'latest',return_value={'job':self.last_job,'report':{'applied':True}}):
            status=analysis_jobs.creation_status(self.project,lambda i:None)
        self.assertEqual(self.last_job['status'],'complete')
        self.assertEqual(status['status'],'failed')
        self.assertEqual(status['error'],'Director could not start')

    def test_retry_of_failed_handoff_reuses_recognition_and_clears_old_error(self):
        text='Saved speech.';digest=hashlib.sha256(text.encode()).hexdigest();self.plan['script_sha256']=digest
        job={'id':'j','status':'complete','handoff_error':'Old launch failure'}
        report={'applied':True,'script_sha256':digest,'source':{'asset_id':'voice','sha256':'audio'}}
        saved=[]
        with patch.object(analysis_jobs,'latest',return_value={'job':job,'report':report}),patch.object(store,'resolve_asset',return_value={'path':'voice.mp3'}),patch.object(store,'audio_fingerprint',return_value='audio'),patch.object(store,'load_project_narration',return_value=self.plan),patch.object(director,'after_voice') as after,patch.object(analysis_jobs,'start') as recognize:
            result=analysis_jobs.create_video(self.project,'voice',lambda j:saved.append(dict(j)),lambda i:None,text)
        self.assertNotIn('handoff_error',result)
        self.assertNotIn('handoff_error',saved[-1])
        after.assert_called_once_with(self.project['id'],create_video=True);recognize.assert_not_called()

    def test_worker_keeps_cached_words_only_for_matching_source_prepared_audio_and_script(self):
        digest=hashlib.sha256(b'Saved speech.').hexdigest()
        report={'source':{'sha256':'audio'},'audio':{'sha256':'audio'},'script_sha256':digest,
                'words':[{'text':'Saved','start':0,'end':.4,'probability':.99},{'text':'speech.','start':.5,'end':.9,'probability':.99}],
                'engine':{'engine':'cached','language':'en'}}
        calls,result=self.run_cached_analysis(report)
        self.assertEqual(calls,0)
        self.assertEqual(result['engine']['engine'],'cached')
        self.assertEqual(result['engine']['repaired_script_phrases'],1)
        for key in ['source','audio','script_sha256']:
            changed={**report,key:{'sha256':'different'} if key!='script_sha256' else 'different'}
            with self.subTest(changed=key):
                calls,result=self.run_cached_analysis(changed)
                self.assertEqual(calls,1)
                self.assertEqual(result['engine']['engine'],'fresh')

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
