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
    def test_cache_changes_only_edited_phrase(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);settings=lab.validated({'text':'Some sample text.'})
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
    def test_failure_keeps_completed_phrase_and_does_not_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);project={'id':'0'*24,'channel_id':'1'*16};settings=lab.validated({})
            entries=[{'key':'a','text':'First.'},{'key':'b','text':'Second.'}]
            with patch.object(store,'project_dir',return_value=path),patch.object(store,'DATA_ROOT',path),patch.object(lab,'folder',return_value=path),patch.object(lab,'prepared_source',return_value=path/'ref.mp3'),patch.object(lab,'clone',return_value=('secret','voice')),patch.object(lab,'synthesis',side_effect=[b'audio',RuntimeError('provider failed')]) as synth,patch.object(store,'media_duration',return_value=1),patch.object(store,'load_project',return_value=project):
                narration.run(project,'First. Second.',settings,{'sha256':'ref'},[{**e,'cached':False} for e in entries],{'status':'running'})
                self.assertEqual(synth.call_count,2)
                self.assertTrue((path/'narration'/'a.mp3').is_file())
                self.assertEqual(narration.snapshot(project['id'])['job']['status'],'failed')

if __name__=='__main__':unittest.main()
