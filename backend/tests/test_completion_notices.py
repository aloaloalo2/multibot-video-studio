import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import store
import completion_notices as notices

class CompletionNoticeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.patch=patch.object(store,'project_dir',return_value=self.root);self.patch.start()
        self.project={'id':'a'*24,'production_request':{'status':'done','finished_at':10}}
    def tearDown(self):
        self.patch.stop();self.tmp.cleanup()
    def test_process_export_priority_seen_and_new_completion(self):
        self.assertEqual(notices.notice(self.project)['kind'],'process')
        job={'id':'b'*24,'project_id':self.project['id'],'status':'complete','output_path':'film.mp4'}
        notices.record(job,15)
        self.assertEqual(notices.notice(self.project)['kind'],'export')
        with patch.object(notices.time,'time',return_value=20):notices.seen(self.project['id'])
        self.assertIsNone(notices.notice(self.project))
        notices.record(job,25) # re-saving an old receipt never marks it unread again
        self.assertIsNone(notices.notice(self.project))
        self.project['production_request']['finished_at']=30
        self.assertEqual(notices.notice(self.project)['kind'],'process')
        notices.record({**job,'id':'c'*24},35)
        self.assertEqual(notices.notice(self.project)['kind'],'export')
    def test_failed_and_cancelled_exports_never_add_a_mark(self):
        for status in ['failed','cancelled','running']:
            notices.record({'id':'b'*24,'project_id':self.project['id'],'status':status,'output_path':'x.mp4'},15)
        self.project['production_request']['status']='failed'
        self.assertIsNone(notices.notice(self.project))

    def test_acknowledgement_of_a_visible_notice_does_not_consume_a_later_export(self):
        pid=self.project['id']
        notices.record({'id':'first','project_id':pid,'status':'complete','output_path':'one.mp4'},15)
        notices.record({'id':'second','project_id':pid,'status':'complete','output_path':'two.mp4'},25)
        with patch.object(notices.time,'time',return_value=30):notices.seen(pid,15)
        self.assertEqual(notices.notice(self.project)['at'],25)
        with patch.object(notices.time,'time',return_value=30):notices.seen(pid,25)
        self.assertIsNone(notices.notice(self.project))
        with patch.object(notices.time,'time',return_value=30):notices.seen(pid,15)
        self.assertEqual(store.read_json(notices.path(pid))['seen_at'],25)

    def test_invalid_acknowledgement_cannot_hide_future_completions(self):
        for value in ('15',float('nan'),float('inf'),-1,True):
            with self.assertRaises(store.StudioError):notices.seen(self.project['id'],value)

class ReadyStageTests(unittest.TestCase):
    def setUp(self):
        CompletionNoticeTests.setUp(self)
        self.project={'id':'a'*24}

    def tearDown(self):
        CompletionNoticeTests.tearDown(self)

    def test_hooks_stay_ready_after_opening_and_during_a_failed_script(self):
        store.atomic_json(self.root/'episode-draft.json', {'project_id':self.project['id'], 'stage':'script','status':'failed','openings':[{'text':'Saved opening.'}]})
        self.assertEqual(notices.ready_stage(self.project,{},{}),'openings')
        notices.seen(self.project['id'])
        self.assertEqual(notices.ready_stage(self.project,store.read_json(notices.path(self.project['id'])),{}),'openings')
        self.project['voice_script']={'text':'Full saved script'}
        self.assertEqual(notices.ready_stage(self.project,{},{}),'script')

    def test_saved_milestones_and_incomplete_frames(self):
        self.assertEqual(notices.ready_stage(self.project,{},{}),'draft')
        self.assertEqual(notices.ready_stage(self.project,{}, {'voice_duration':15}),'voice')
        self.project['plan_source']='plan.json'
        with patch.object(store,'listed_plan',return_value={'frame_source':'razgon-direction','frames':[{}]}):
            self.assertEqual(notices.ready_stage(self.project,{}, {'plan_stage':'audio_synced'}),'plan')
        self.project.pop('plan_source')
        self.project['production_request']={'status':'failed','frames':5,'made':5,'quality':{'passed':False}}
        self.assertEqual(notices.ready_stage(self.project,{},{}),'draft')
        self.project['production_request']['status']='done';self.project['production_request']['quality']['passed']=True
        self.assertEqual(notices.ready_stage(self.project,{},{}),'frames')
        self.assertEqual(notices.ready_stage(self.project,{'export':{'at':100}},{}),'export')

    def test_cancelled_or_foreign_hooks_are_not_ready(self):
        for data in ({'project_id':self.project['id'],'status':'cancelled'}, {'project_id':'b'*24,'status':'done'}):
            store.atomic_json(self.root/'episode-draft.json',{**data,'openings':[{'text':'Old hook'}]})
            self.assertEqual(notices.ready_stage(self.project,{},{}),'draft')

    def test_synthesized_voice_is_ready_before_recognition_and_reset_removes_it(self):
        audio=self.root/'voice.mp3';audio.write_bytes(b'fixture')
        self.project['assets']=[{'id':'voice','path':str(audio)}]
        store.atomic_json(self.root/'narration/job.json',{'status':'done','asset_id':'voice','started_at':10})
        self.assertEqual(notices.ready_stage(self.project,{},{}),'voice')
        self.project['restarted_at']=20
        self.assertEqual(notices.ready_stage(self.project,{},{}),'draft')
