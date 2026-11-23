import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import project_narration as narration
import channel_voice_lab as lab
import store

class NarrationTests(unittest.TestCase):
    def test_all_service_ids_quote_without_local_reference_or_synthesis(self):
        for provider,field in [('fishaudio','fish_voice_id'),('elevenlabs','eleven_voice_id'),('heygen','heygen_voice_id')]:
            with self.subTest(provider=provider),tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp);settings=lab.validated({'provider':provider,field:'saved-service-voice'})
                project={'id':'0'*24,'channel_id':'1'*16}
                with patch.object(store,'project_dir',return_value=path),patch.object(store,'DATA_ROOT',path),patch.object(lab,'folder',return_value=path),patch.object(lab,'snapshot',return_value={'settings':settings,'reference':None}),patch.object(lab,'reference',side_effect=AssertionError('Local reference must not be read')),patch.object(lab,'estimate',return_value={'amount':0}),patch.object(lab.eleven_api,'balance',return_value={}),patch.object(lab,'fish_synthesis') as fish,patch.object(lab,'synthesis') as eleven,patch.object(lab.heygen_voice,'synthesize') as heygen:
                    _,ref,entries,quote=narration.spec(project,'First complete sentence. Second complete sentence.')
                    # HeyGen Turbo Free and ElevenLabs read both sentences of the paragraph in one request (lab.sentences_per_request)
                    self.assertTrue(ref['sha256']);self.assertEqual(len(entries),2 if provider=='fishaudio' else 1)
                    self.assertEqual(quote['provider'],provider);self.assertEqual(quote['estimated_usd'],0)
                    fish.assert_not_called();eleven.assert_not_called();heygen.assert_not_called()

    def test_cache_changes_only_edited_phrase(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);settings=lab.validated({'text':'Some sample text.','eleven_sentences':1})   # a request a sentence
            profile={'settings':settings,'reference':{'sha256':'voice'}}
            project={'id':'0'*24,'channel_id':'1'*16}
            with patch.object(store,'project_dir',return_value=path),patch.object(store,'DATA_ROOT',path),patch.object(lab,'snapshot',return_value=profile),patch.object(lab.eleven_api,'balance',return_value={'credit_usd_rate':.00022}):
                _,_,entries,_=narration.spec(project,'First sentence. Second sentence.')
                for entry in entries:(narration.root(project['id'])/(entry['key']+'.mp3')).write_bytes(b'cached')
                _,_,updated,quote=narration.spec(project,'First sentence. Changed sentence.')
                self.assertTrue(updated[0]['cached']);self.assertFalse(updated[1]['cached'])
                self.assertEqual(quote['cached'],1)
                self.assertEqual(quote['characters'],len('Changed sentence.'))
                settings['stability']=.95
                _,_,_,quote=narration.spec(project,'First sentence. Second sentence.')
                self.assertEqual(quote['cached'],0)
    def test_completed_speed_uses_same_original_and_never_synthesizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);source=folder/'ready.mp3';source.write_bytes(b'original')
            project={'id':'0'*24,'channel_id':'1'*16,'revision':1,'assets':[{'id':'old','path':str(source),'duration':10}], 'tracks':[{'clips':[{'asset_id':'old','duration':10}]}]}
            with patch.object(store,'project_dir',return_value=folder),patch.object(store,'load_project',return_value=project),patch.object(store,'save_project'),patch.object(store,'media_duration',return_value=9),patch.object(narration.narration_ending,'import_audio',return_value={'id':'new','duration':9}),patch.object(lab,'paced_audio',return_value=b'paced') as pace,patch.object(lab,'fish_synthesis') as paid,patch.object(narration,'snapshot',return_value={}):
                store.atomic_json(narration.root(project['id'])/'job.json',{'status':'done','speed':1.,'asset_id':'old'})
                narration.change_speed(project['id'],1.05)
                self.assertEqual(pace.call_args.args[1],1.05)
                self.assertEqual(pace.call_args.args[0].read_bytes(),b'original')
                self.assertEqual(project['tracks'][0]['clips'][0]['asset_id'],'new')
                self.assertEqual(project['tracks'][0]['clips'][0]['duration'],9)
                self.assertFalse(paid.called)
                for speed in [True,None,.86,1.06,float('nan')]:
                    with self.assertRaises(store.StudioError):narration.change_speed(project['id'],speed)
    def test_removed_or_pre_restart_audio_cannot_return_or_change_speed(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);audio=folder/'voice.mp3';audio.write_bytes(b'audio')
            project={'id':'0'*24,'channel_id':'1'*16,'restarted_at':20,'assets':[{'id':'voice','path':str(audio)}]}
            job={'status':'done','asset_id':'voice','started_at':10,'speed':1.}
            with patch.object(store,'project_dir',return_value=folder),patch.object(store,'load_project',return_value=project):
                store.atomic_json(narration.root(project['id'])/'job.json',job)
                self.assertEqual(narration.snapshot(project['id'])['job'],{})
                with self.assertRaises(store.StudioError):narration.change_speed(project['id'],1.05)
                project.pop('restarted_at');project['assets']=[]
                self.assertEqual(narration.snapshot(project['id'])['job'],{})
    def test_invalid_text_rejected_before_paid_work(self):
        for text in [None,'',123,'x'*200001]:
            with self.assertRaises(store.StudioError):narration.phrases(text)
    def test_interrupted_cancellation_returns_retryable_status_without_restarting_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            pid='0'*24
            with patch.object(store,'project_dir',return_value=Path(tmp)),patch.object(store,'load_project',return_value={'id':pid}),patch.object(narration,'ACTIVE',set()),patch.object(narration,'run') as worker:
                store.atomic_json(narration.root(pid)/'job.json',{'status':'cancelling'})
                self.assertEqual(narration.snapshot(pid)['job']['status'],'failed')
                worker.assert_not_called()
    def test_failure_keeps_completed_phrase_and_does_not_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);project={'id':'0'*24,'channel_id':'1'*16};settings=lab.validated({})
            entries=[{'key':'a','text':'First.'},{'key':'b','text':'Second.'}]
            with patch.object(store,'project_dir',return_value=path),patch.object(store,'DATA_ROOT',path),patch.object(lab,'folder',return_value=path),patch.object(lab,'prepared_source',return_value=path/'ref.mp3'),patch.object(lab,'clone',return_value=('secret','voice')),patch.object(lab,'synthesis',side_effect=lambda secret,voice,params:(_ for _ in ()).throw(RuntimeError('provider failed')) if 'Second' in params['text'] else b'audio') as synth,patch.object(store,'media_duration',return_value=1),patch.object(store,'load_project',return_value=project):
                narration.run(project,'First. Second.',settings,{'sha256':'ref'},[{**e,'cached':False} for e in entries],{'status':'running'})
                self.assertEqual(synth.call_count,2)
                self.assertTrue((path/'narration'/'a.mp3').is_file())
                self.assertEqual(narration.snapshot(project['id'])['job']['status'],'failed')

    def test_eleven_runs_requests_at_once_and_waits_out_a_busy_refusal(self):
        # user, 23 November 2026: «одночасні запити, групи речень»; a 429 for too many at once is not billed
        import threading,time as clock
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);project={'id':'0'*24,'channel_id':'1'*16};settings=lab.validated({'eleven_sentences':1})
            entries=[{'key':k,'text':t} for k,t in [('a','One.'),('b','Two.'),('c','Three.'),('d','Four.')]]
            live=[0];peak=[0];busy=[True];guard=threading.Lock()
            def synth(secret,voice,params):
                with guard:
                    if params['text']=='Two.' and busy[0]:
                        busy[0]=False;raise RuntimeError('ElevenLabs: помилка 429. Забагато одночасних запитів')
                    live[0]+=1;peak[0]=max(peak[0],live[0])
                threading.Event().wait(.05)   # time.sleep is patched for the retry wait
                with guard:live[0]-=1
                return b'audio'
            with patch.object(store,'project_dir',return_value=path),patch.object(store,'DATA_ROOT',path),patch.object(lab,'folder',return_value=path),patch.object(lab,'prepared_source',return_value=path/'ref.mp3'),patch.object(lab,'clone',return_value=('secret','voice')),patch.object(lab,'synthesis',side_effect=synth) as call,patch.object(store,'media_duration',return_value=1),patch.object(store,'load_project',return_value=project),patch.object(narration.time,'sleep'),patch.object(narration.languages,'run'),patch.object(narration.narration_ending,'import_audio',return_value={'id':'x','duration':1}),patch('episode_automation.after_voice'):
                narration.run(project,'One. Two. Three. Four.',settings,{'sha256':'ref'},[{**e,'cached':False} for e in entries],{'status':'running'})
                self.assertEqual(call.call_count,5)                       # the refused one asked again
                self.assertGreater(peak[0],1)                             # several requests at once
                self.assertLessEqual(peak[0],lab.ELEVEN_SLOTS)
                for key in 'abcd':self.assertTrue((path/'narration'/(key+'.mp3')).is_file())

if __name__=='__main__':unittest.main()
