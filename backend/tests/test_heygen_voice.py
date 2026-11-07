import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import heygen_voice as hg
import channel_voice_lab as lab
import store

class HeyGenTests(unittest.TestCase):
    def test_explicit_model_and_no_api_speed(self):
        settings=lab.validated({'provider':'heygen','heygen_voice_id':'voice','speed':1.1})
        with patch.object(hg,'call',side_effect=[{'data':{'status':'ACTIVE','mode':'instant'}},{'data':{'audio_url':'https://audio.example/test.mp3'}}]) as call,patch.object(hg.urllib.request,'urlopen',return_value=io.BytesIO(b'audio')):
            self.assertEqual(hg.synthesize(settings),b'audio')
        payload=call.call_args.args[1]
        self.assertEqual(payload['model'],'heygen-voice-1-turbo-free')
        self.assertNotIn('speed',payload)
        self.assertEqual(call.call_count,2)
    def test_turbo_rejects_professional_without_paid_fallback(self):
        settings=lab.validated({'provider':'heygen','heygen_voice_id':'voice'})
        with patch.object(hg,'call',return_value={'data':{'status':'ACTIVE','mode':'professional'}}) as call:
            with self.assertRaises(store.StudioError):hg.synthesize(settings)
        self.assertEqual(call.call_count,1)
    def test_voice_pages_and_pending_filter(self):
        with patch.object(hg,'call',side_effect=[{}, {'data':[{'voice_id':'a','status':'PENDING'}],'has_more':True,'next_token':'next'}, {'data':[{'voice_id':'b','status':'ACTIVE'}]}, {'data':[{'voice_id':'c','status':'ACTIVE'}]}]) as call:
            self.assertEqual([v['voice_id'] for v in hg.voices()['voices']],['b','c'])
            self.assertIn('token=next',call.call_args_list[2].args[0])
    def test_speed_reuses_cached_original(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(store,'DATA_ROOT',Path(tmp)),patch.object(store,'media_duration',return_value=1),patch.object(hg,'synthesize',return_value=b'audio') as synth,patch.object(lab,'paced_audio',return_value=b'paced'):
            settings=lab.validated({'provider':'heygen','heygen_voice_id':'voice'});ref={'sha256':'voice'}
            lab.heygen_synthesis(settings,ref)
            lab.heygen_synthesis({**settings,'speed':1.1},ref)
            self.assertEqual(synth.call_count,1)
            self.assertNotEqual(lab.fingerprint(settings,ref),lab.fingerprint({**settings,'speed':1.1},ref))

if __name__=='__main__':unittest.main()
