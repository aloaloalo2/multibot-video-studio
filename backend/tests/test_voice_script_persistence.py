"""An accepted revoice must keep the author's text through later UI and ASR reads."""
import contextlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import analysis_jobs
import project_narration as narration
import store


class VoiceScriptPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
        self.root=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        youtube=self.root/'youtube';youtube.mkdir()
        for key,value in {'YOUTUBE_ROOT':youtube,'DATA_ROOT':self.root/'data',
                          'PROJECTS_ROOT':self.root/'data'/'projects',
                          'DISABLED_PATH':self.root/'disabled.json',
                          'GLOBAL_SETTINGS_PATH':self.root/'settings.json'}.items():
            self.stack.enter_context(patch.object(store,key,value))
        self.stack.enter_context(patch.object(narration,'ACTIVE',set()))
        self.stack.enter_context(patch.object(narration,'HEYGEN_QUEUE',[]))
        self.stack.enter_context(patch.object(narration.lab,'NARRATIONS',{}))
        self.cid=store.create_channel('Fixture')['id']
        self.project=store.create_project(self.cid,'Episode')
        self.pid=self.project['id']

    def test_revoice_preserves_previous_text_and_unchanged_saves_are_idempotent(self):
        old=store.save_voice_script(self.pid,'The earlier full script.')
        new=store.save_voice_script(self.pid,'The edited full script.',source='narration')
        self.assertEqual(store.load_project(self.pid)['voice_script'],new)
        history=list((store.project_dir(self.pid)/'script-history').glob('*.json'))
        self.assertEqual(len(history),1);self.assertEqual(store.read_json(history[0]),old)
        revision=store.load_project(self.pid)['revision']
        self.assertEqual(store.save_voice_script(self.pid,new['text']),new)
        self.assertEqual(store.load_project(self.pid)['revision'],revision)
        with self.assertRaises(store.StudioError):
            store.save_voice_script(self.pid,'A stale editor change.',expected_sha256=old['sha256'])
        self.assertEqual(store.load_project(self.pid)['voice_script'],new)

    def test_narration_persists_accepted_text_before_the_worker_can_start(self):
        old=store.save_voice_script(self.pid,'The earlier full script.')
        text='The edited full script.'
        settings={'provider':'heygen','speed':1}
        observed=[]
        def start_worker():
            observed.append(store.load_project(self.pid)['voice_script']['text'])
        with patch.object(narration,'spec',return_value=(settings,{},[],{'provider':'heygen','total':0})), \
                patch.object(narration.threading,'Thread') as thread:
            thread.return_value.start.side_effect=start_worker
            result=narration.start(self.project,text)
        self.assertEqual(observed,[text]);self.assertEqual(result['voice_script']['text'],text)
        self.assertEqual(thread.call_args.kwargs['args'][1],text)
        self.assertEqual(result['job']['script'],text)
        self.assertEqual(len(list((store.project_dir(self.pid)/'script-history').glob('*.json'))),1)

    def test_script_save_failure_cannot_launch_a_paid_worker_or_keep_a_queue_slot(self):
        with patch.object(narration,'spec',return_value=({'provider':'heygen','speed':1},{},[],{'provider':'heygen','total':0})), \
                patch.object(store,'save_voice_script',side_effect=OSError('Disk full')), \
                patch.object(narration.threading,'Thread') as thread:
            with self.assertRaises(OSError):narration.start(self.project,'The edited full script.')
        thread.assert_not_called();self.assertFalse(narration.ACTIVE)
        self.assertFalse(narration.HEYGEN_QUEUE);self.assertFalse(narration.lab.NARRATIONS)
        self.assertEqual(store.read_json(narration.root(self.pid)/'job.json')['status'],'failed')

    def test_old_recognition_cannot_overwrite_a_newer_author_edit(self):
        old='Saved speech.';new='A newer author script.'
        record=store.save_voice_script(self.pid,old)
        asset={'id':'voice','kind':'audio','name':'Voice','path':str(self.root/'voice.wav')}
        job={'id':'old-recognition','project_id':self.pid,'source_asset_id':'voice',
             'script_from':'request','author_script_sha256':record['sha256']}
        words=[{'text':'Saved','start':0,'end':.4,'probability':.99},
               {'text':'speech.','start':.5,'end':.9,'probability':.99}]
        def transcribe(*args):
            store.save_voice_script(self.pid,new)
            return words,{'language':'en'}
        with patch.object(store,'resolve_asset',return_value=asset), \
                patch.object(store,'audio_fingerprint',return_value='audio'), \
                patch.object(store,'media_duration',return_value=2), \
                patch.object(analysis_jobs.narration_ending,'prepare_asset',return_value=asset), \
                patch.object(analysis_jobs.narration_sequence,'verify',return_value=None), \
                patch.object(analysis_jobs.speech,'transcribe',side_effect=transcribe), \
                patch.object(analysis_jobs.speech_repair,'repair',side_effect=lambda p,w,l:(w,0)), \
                patch.object(analysis_jobs.speech_repair,'repair_script',side_effect=lambda p,s,w,l,**kw:(w,0)), \
                patch.object(store,'generate_project_plan') as apply:
            analysis_jobs.worker(job,old,lambda job:None)
        self.assertEqual(job['status'],'complete');self.assertEqual(job['analysis_status'],'script_changed')
        self.assertFalse(job['applied']);apply.assert_not_called()
        self.assertEqual(store.load_project(self.pid)['voice_script']['text'],new)
