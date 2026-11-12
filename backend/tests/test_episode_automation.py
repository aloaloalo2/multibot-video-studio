import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store,episode_automation as auto,project_narration,analysis_jobs

class EpisodeAutomationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.project={'id':'a'*24,'channel_id':'b'*16,'voice_script':{'text':'Saved full script.'}}
        self.flags={}
        self.patches=[patch.object(store,'project_dir',return_value=self.root),patch.object(store,'load_project',return_value=self.project),patch.object(auto,'settings',side_effect=lambda p:self.flags)]
        for item in self.patches:item.start()
    def tearDown(self):
        for item in reversed(self.patches):item.stop()
        self.tmp.cleanup()
    def test_default_is_manual_and_failed_or_cancelled_steps_never_start_paid_work(self):
        with patch.object(project_narration,'start') as start:
            auto.after_script(self.project['id'],{'completed':True})
            self.flags={'auto_narration':True}
            auto.after_script(self.project['id'],{'completed':False})
            auto.after_script(self.project['id'],{'completed':True,'cancelled':True})
        start.assert_not_called()
    def test_script_completion_starts_voice_once_for_the_saved_text(self):
        self.flags={'auto_narration':True}
        with patch.object(project_narration,'start') as start,patch.object(project_narration,'snapshot',return_value={}),patch.object(project_narration,'ACTIVE',set()):
            for _ in range(2):auto.after_script(self.project['id'],{'completed':True})
        start.assert_called_once_with(self.project,'Saved full script.')
    def test_old_editorial_review_flag_cannot_block_completed_author_handoff(self):
        self.flags={'auto_narration':True}
        with patch.object(project_narration,'start') as start,patch.object(project_narration,'snapshot',return_value={}),patch.object(project_narration,'ACTIVE',set()):
            auto.after_script(self.project['id'],{'completed':True,'review_required':True})
        start.assert_called_once_with(self.project,'Saved full script.')
    def test_failed_handoff_does_not_auto_retry_and_surfaces_in_the_narration_player(self):
        self.flags={'auto_narration':True}
        with patch.object(project_narration,'start',side_effect=store.StudioError('No channel voice')) as start,patch.object(project_narration,'snapshot',return_value={}),patch.object(project_narration,'ACTIVE',set()):
            for _ in range(2):auto.after_script(self.project['id'],{'completed':True})
        start.assert_called_once()
        self.assertEqual(store.read_json(self.root/'narration/job.json')['status'],'failed')

    def test_failed_automatic_handoff_never_replaces_a_manual_narration_already_running(self):
        active=set()
        def manual_won():
            active.add(self.project['id'])
            store.atomic_json(self.root/'narration/job.json',{'status':'running','script':'Manual narration'})
            raise store.StudioError('Озвучення вже триває',409)
        with patch.object(project_narration,'ACTIVE',active):
            auto.handoff(self.project['id'],'voice','identity',manual_won)
        self.assertEqual(store.read_json(self.root/'narration/job.json')['status'],'running')
        self.assertEqual(store.read_json(self.root/'narration/job.json')['script'],'Manual narration')

    def test_direct_montage_only_recognizes_the_completed_voice_without_requesting_frames(self):
        self.flags={'auto_montage':True}
        self.project['plan_mode']='direct'
        callbacks=(lambda job:None,lambda jid:None)
        with patch.object(auto,'JOB_CALLBACKS',callbacks),patch.object(analysis_jobs,'start') as recognize, \
                patch.object(analysis_jobs,'create_video') as create:
            auto.after_voice(self.project['id'],{'status':'done','asset_id':'voice','started_at':10,'script':'Saved full script.'})
        recognize.assert_called_once_with(self.project,'voice',*callbacks,script='Saved full script.')
        create.assert_not_called()
    def test_successful_voice_hands_the_existing_audio_to_create_video_once_without_export(self):
        self.flags={'auto_montage':True};job={'status':'done','asset_id':'voice','started_at':10,'script':'Saved full script.'}
        callbacks=(lambda j:None,lambda jid:None)
        with patch.object(auto,'JOB_CALLBACKS',callbacks),patch.object(analysis_jobs,'create_video') as create:
            for _ in range(2):auto.after_voice(self.project['id'],job)
        create.assert_called_once_with(self.project,'voice',*callbacks,script='Saved full script.')
    def test_cancel_reset_or_changed_script_prevents_montage(self):
        self.flags={'auto_montage':True}
        with patch.object(analysis_jobs,'create_video') as create:
            auto.after_voice(self.project['id'],{'status':'failed','asset_id':'voice'})
            auto.after_voice(self.project['id'],{'status':'done','asset_id':'voice','script':'Old words'})
            self.project['restarted_at']=20
            auto.after_voice(self.project['id'],{'status':'done','asset_id':'voice','started_at':10})
        create.assert_not_called()
