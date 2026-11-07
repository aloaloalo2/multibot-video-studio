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
        settings=lab.validated({'provider':'heygen','heygen_voice_id':'voice','speed':1.1,'heygen_expressiveness':.85})
        with patch.object(hg,'call',side_effect=[{'data':{'status':'ACTIVE','mode':'instant'}},{'data':{'audio_url':'https://audio.example/test.mp3'}}]) as call,patch.object(hg.urllib.request,'urlopen',return_value=io.BytesIO(b'audio')):
            self.assertEqual(hg.synthesize(settings),b'audio')
        payload=call.call_args.args[1]
        self.assertEqual(payload['model'],'heygen-voice-1-turbo-free')
        self.assertNotIn('speed',payload)
        self.assertEqual(payload['expressiveness_boost'],.85)
        self.assertEqual(call.call_count,2)
    def test_expression_changes_synthesis_cache_but_not_other_providers(self):
        original=lab.validated({'provider':'heygen','heygen_voice_id':'voice'});ref={'sha256':'voice'}
        changed={**original,'heygen_expressiveness':.85}
        self.assertNotEqual(lab.fingerprint(original,ref),lab.fingerprint(changed,ref))
        self.assertNotEqual(lab.original_path(original,ref),lab.original_path(changed,ref))
        for provider in ['elevenlabs','fishaudio']:
            self.assertEqual(lab.fingerprint({**original,'provider':provider},ref),lab.fingerprint({**changed,'provider':provider},ref))
        for value in [-.1,1.1,True,float('nan')]:
            with self.assertRaises(store.StudioError):lab.validated({'heygen_expressiveness':value})
    def test_turbo_rejects_professional_without_paid_fallback(self):
        settings=lab.validated({'provider':'heygen','heygen_voice_id':'voice'})
        with patch.object(hg,'call',return_value={'data':{'status':'ACTIVE','mode':'professional'}}) as call:
            with self.assertRaises(store.StudioError):hg.synthesize(settings)
        self.assertEqual(call.call_count,1)
    def test_validation_reason_is_visible_and_secret_is_redacted(self):
        import urllib.error
        body=b'{"error":{"param":"voice_id","message":"This voice is not compatible with heygen-voice-1-turbo-free. Create a new instant voice."}}'
        error=urllib.error.HTTPError('https://api.heygen.com',400,'Bad request',{},io.BytesIO(body))
        with patch.object(hg,'key',return_value='test-secret'),patch.object(hg.urllib.request,'urlopen',side_effect=error):
            with self.assertRaises(store.StudioError) as caught:hg.call('/v3/models/audio/tts',{})
        self.assertIn('несумісний',str(caught.exception))
        self.assertNotIn('test-secret',str(caught.exception))
    def test_clone_is_explicit_instant_with_stable_idempotency(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'ref.mp3';path.write_bytes(b'audio')
            with patch.object(hg,'call',return_value={'data':{'voice_id':'created'}}) as call:
                self.assertEqual(hg.clone_instant(path,'Narrator','ru','stable-key'),'created')
                payload=call.call_args.args[1]
                self.assertEqual(payload['mode'],'instant')
                self.assertEqual(payload['audio'][0]['type'],'base64')
                self.assertFalse(payload['remove_background_noise'])
                self.assertEqual(call.call_args.kwargs['idempotency_key'],'stable-key')
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
