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
            with patch.object(store,'project_dir',return_value=path),patch.object(lab,'snapshot',return_value=profile):
                _,_,entries,_=narration.spec(project,'First sentence. Second sentence.')
                for entry in entries:(narration.root(project['id'])/(entry['key']+'.mp3')).write_bytes(b'cached')
                _,_,updated,quote=narration.spec(project,'First sentence. Changed sentence.')
                self.assertTrue(updated[0]['cached']);self.assertFalse(updated[1]['cached'])
                self.assertEqual(quote['cached'],1)
                self.assertEqual(quote['characters'],len('Changed sentence.'))
                settings['stability']=.95
                _,_,_,quote=narration.spec(project,'First sentence. Second sentence.')
                self.assertEqual(quote['cached'],0)
    def test_invalid_text_rejected_before_paid_work(self):
        for text in [None,'',123,'x'*200001]:
            with self.assertRaises(store.StudioError):narration.phrases(text)
    def test_failure_keeps_completed_phrase_and_does_not_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);project={'id':'0'*24,'channel_id':'1'*16};settings=lab.validated({})
            entries=[{'key':'a','text':'First.'},{'key':'b','text':'Second.'}]
            with patch.object(store,'project_dir',return_value=path),patch.object(lab,'prepared_source',return_value=path/'ref.mp3'),patch.object(lab,'clone',return_value=('secret','voice')),patch.object(lab,'synthesis',side_effect=[b'audio',RuntimeError('provider failed')]) as synth,patch.object(store,'media_duration',return_value=1):
                narration.run(project,'First. Second.',settings,{'sha256':'ref'},[{**e,'cached':False} for e in entries],{'status':'running'})
                self.assertEqual(synth.call_count,2)
                self.assertTrue((path/'narration'/'a.mp3').is_file())
                self.assertEqual(narration.snapshot(project['id'])['job']['status'],'failed')

if __name__=='__main__':unittest.main()
