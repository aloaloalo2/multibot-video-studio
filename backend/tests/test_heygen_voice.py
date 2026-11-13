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
    def test_new_voice_waits_for_active_then_sends_one_speech_request(self):
        settings=lab.validated({'provider':'heygen','heygen_voice_id':'new-voice'})
        replies=[{'data':{'status':status,'mode':'instant'}} for status in ('PENDING','PENDING','ACTIVE')]
        replies.append({'data':{'audio_url':'https://audio.example/sample.mp3'}})
        with patch.object(hg,'call',side_effect=replies) as call,patch.object(hg.time,'sleep') as sleep,patch.object(hg.urllib.request,'urlopen',return_value=io.BytesIO(b'mp3')):
            self.assertEqual(hg.synthesize(settings),b'mp3')
        path='/v3/models/audio/voices/new-voice'
        self.assertEqual([args.args for args in call.call_args_list[:-1]],[(path,)]*3)
        self.assertEqual(call.call_args.args[0],'/v3/models/audio/tts')
        self.assertEqual(sleep.call_count,2)

    def test_pending_timeout_and_failed_voice_do_not_submit_speech(self):
        settings=lab.validated({'provider':'heygen','heygen_voice_id':'new-voice'})
        for data,message in [({'status':'PENDING'},'усе ще готує'),({'status':'FAILED','failure_reason':'INVALID_AUDIO'},'прочитати запис')]:
            with self.subTest(data=data),patch.object(hg,'VOICE_READY_TIMEOUT',0),patch.object(hg,'call',return_value={'data':data}) as call:
                with self.assertRaisesRegex(store.StudioError,message):hg.synthesize(settings)
                call.assert_called_once_with('/v3/models/audio/voices/new-voice')

    def test_starfish_catalog_uses_engine_and_keeps_compatible_voices(self):
        with patch.object(hg,'call',side_effect=[{}, {'data':[{'voice_id':'a','available_engines':['starfish']},{'voice_id':'b','available_engines':['elevenlabs']}]}, {'data':[]}]) as call:
            self.assertEqual([v['voice_id'] for v in hg.voices('starfish')['voices']],['a'])
            self.assertIn('/v3/voices?',call.call_args_list[1].args[0])
            self.assertIn('engine=starfish',call.call_args_list[1].args[0])

    def test_starfish_request_and_audio_conversion(self):
        settings=lab.validated({'provider':'heygen','heygen_model':'starfish','heygen_voice_id':'voice',
            'heygen_starfish_speed':1.25,'heygen_starfish_ssml':True,'heygen_starfish_locale':'uk-UA'})
        def convert(args,*unused):Path(args[-1]).write_bytes(b'mp3')
        with patch.object(hg,'call',side_effect=[{'data':{'status':'ACTIVE'}},{'data':{'audio_url':'https://audio.example/a.wav'}}]) as call,patch.object(hg.urllib.request,'urlopen',return_value=io.BytesIO(b'RIFF')),patch.object(lab.languages,'run',side_effect=convert):
            self.assertEqual(hg.synthesize(settings),b'mp3')
            path,payload=call.call_args.args
            self.assertEqual(path,'/v3/voices/speech')
            self.assertEqual(payload['speed'],1.25)
            self.assertEqual(payload['input_type'],'ssml')
            self.assertEqual(payload['locale'],'uk-UA')
            self.assertNotIn('expressiveness_boost',payload)
            self.assertNotIn('model',payload)
            self.assertEqual(call.call_count,2)

    def test_starfish_failure_never_falls_back(self):
        settings=lab.validated({'provider':'heygen','heygen_model':'starfish','heygen_voice_id':'voice'})
        with patch.object(hg,'call',side_effect=[{'data':{'status':'ACTIVE'}},store.StudioError('failed')]) as call:
            with self.assertRaises(store.StudioError):hg.synthesize(settings)
            self.assertEqual(call.call_count,2)

    def test_starfish_cache_and_validation(self):
        settings=lab.validated({'provider':'heygen','heygen_model':'starfish','heygen_voice_id':'voice'})
        for field,value in [('heygen_starfish_speed',1.25),('heygen_starfish_ssml',True),('heygen_starfish_locale','uk-UA')]:
            self.assertNotEqual(lab.original_path(settings,{}),lab.original_path({**settings,field:value},{}))
        self.assertEqual(lab.fingerprint(settings,{}),lab.fingerprint({**settings,'heygen_expressiveness':.9},{}))
        for field,value in [('heygen_starfish_speed',True),('heygen_starfish_speed',float('nan')),('heygen_starfish_speed',2.1),('heygen_starfish_ssml','yes'),('heygen_starfish_locale','bad code')]:
            with self.assertRaises(store.StudioError):lab.validated({field:value})
        self.assertAlmostEqual(lab.estimate({**settings,'text':'x'*28000})['amount'],3.7333333333)
        self.assertAlmostEqual(lab.estimate({**settings,'text':'x'*900,'heygen_starfish_speed':2.})['amount'],.06)

    def test_starfish_ssml_is_not_split_inside_tags(self):
        import project_narration as narration
        settings=lab.validated({'provider':'heygen','heygen_model':'starfish','heygen_voice_id':'voice','heygen_starfish_ssml':True})
        with tempfile.TemporaryDirectory() as tmp,patch.object(store,'DATA_ROOT',Path(tmp)),patch.object(lab,'snapshot',return_value={'settings':settings}),patch.object(narration,'root',return_value=Path(tmp)):
            text='<speak>Hello. <break time="1s"/> More words.</speak>'
            entries=narration.spec({'id':'p','channel_id':'c'},text)[2]
            self.assertEqual([e['text'] for e in entries],[text])
            with self.assertRaises(store.StudioError):narration.spec({'id':'p','channel_id':'c'},'<speak>'+'x'*5000+'</speak>')
        with patch.object(hg,'call') as call:
            with self.assertRaises(store.StudioError):hg.synthesize({**settings,'text':'<speak>unclosed'})
            call.assert_not_called()

    def test_explicit_model_and_no_api_speed(self):
        settings=lab.validated({'provider':'heygen','heygen_voice_id':'voice','speed':1.05,'heygen_expressiveness':.85})
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
            lab.heygen_synthesis({**settings,'speed':1.05},ref)
            self.assertEqual(synth.call_count,1)
            self.assertNotEqual(lab.fingerprint(settings,ref),lab.fingerprint({**settings,'speed':1.05},ref))

if __name__=='__main__':unittest.main()
