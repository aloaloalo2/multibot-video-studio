import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import channel_voice_lab as lab
import store

class ImmediateThread:
    def __init__(self,target,args,**kwargs):self.target,self.args=target,args
    def start(self):self.target(*self.args)

class VoiceLabTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.patches=[patch.object(store,'DATA_ROOT',self.root),patch.object(store,'get_channel_folder',return_value=self.root)]
        for p in self.patches:p.start()
        self.cid=lab.TRIAL_CHANNEL;lab.ACTIVE.clear()
    def tearDown(self):
        lab.ACTIVE.clear()
        for p in self.patches:p.stop()
        self.tmp.cleanup()
    def reference(self):
        root=lab.folder(self.cid);(root/'reference.mp3').write_bytes(b'preserved reference')
        store.atomic_json(root/'reference.json',{'filename':'test.mp3','sha256':'same','duration':30})
    def test_only_trial_channel_and_supported_settings(self):
        with self.assertRaises(store.StudioError):lab.snapshot('0'*16)
        for change in [{'stability':float('nan')},{'similarity_boost':2},{'model':'fake'}, {'language':'xx'},
                       {'provider':'unknown'}, {'fish_engine':'unknown'}, {'temperature':-1}, {'top_p':True}]:
            with self.assertRaises(store.StudioError):lab.validated({**lab.DEFAULTS,**change})
        text='One sentence. Another sentence. Third sentence. Fourth sentence. Fifth sentence.'
        self.assertNotIn('Fifth',lab.validated({'text':text})['text'])
    def test_sample_reuses_audio_and_request_nonce(self):
        self.reference()
        with patch.object(lab.threading,'Thread',ImmediateThread),patch.object(lab,'clone',return_value=('secret','voice')) as clone, \
             patch.object(lab,'synthesis',return_value=b'mock audio') as synth,patch.object(store,'media_duration',return_value=12), \
             patch.object(lab.languages.language_quality,'require'),patch.object(lab.eleven_api,'invalidate_balance'):
            first=lab.start(self.cid,lab.DEFAULTS,'a'*20)
            self.assertEqual(first['job']['status'],'done')
            repeated=lab.start(self.cid,lab.DEFAULTS,'a'*20)
            cached=lab.start(self.cid,lab.DEFAULTS,'b'*20)
            self.assertTrue(cached['job']['cached']);self.assertTrue(cached['cached_sample'])
            self.assertEqual(synth.call_count,1);self.assertEqual(clone.call_count,1)
            changed=lab.start(self.cid,{**lab.DEFAULTS,'stability':.3},'c'*20)
            self.assertNotEqual(first['job']['fingerprint'],changed['job']['fingerprint'])
            self.assertEqual(synth.call_count,2)
    def test_failed_call_is_not_automatically_replayed(self):
        self.reference()
        with patch.object(lab.threading,'Thread',ImmediateThread),patch.object(lab,'clone',side_effect=RuntimeError('Stopped')) as clone, \
             patch.object(lab.languages.language_quality,'require'):
            result=lab.start(self.cid,lab.DEFAULTS,'a'*20)
            self.assertEqual(result['job']['status'],'failed')
            lab.start(self.cid,lab.DEFAULTS,'a'*20)
            self.assertEqual(clone.call_count,1)
    def test_remove_keeps_previous_recording_and_does_not_delete_cloud_voice(self):
        self.reference();lab.remove(self.cid)
        self.assertIsNone(lab.reference(self.cid))
        self.assertTrue(list((lab.folder(self.cid)/'previous').glob('*reference.mp3')))

    def test_fish_routes_to_connected_service_and_keeps_separate_sample_cache(self):
        self.reference()
        settings={**lab.DEFAULTS,'provider':'fishaudio','temperature':.6}
        with patch.object(lab.threading,'Thread',ImmediateThread),patch.object(lab.languages,'key',return_value='mock') as key, \
             patch.object(lab,'fish_reference',return_value={'audio':b'ref','text':'Reference words'}) as reference, \
             patch.object(lab,'fish_synthesis',return_value=b'fish audio') as synth, \
             patch.object(lab,'clone') as eleven,patch.object(store,'media_duration',return_value=12), \
             patch.object(lab.languages.language_quality,'require'):
            first=lab.start(self.cid,settings,'a'*20)
            self.assertEqual(first['job']['status'],'done');self.assertEqual(first['job']['provider'],'fishaudio')
            key.assert_called_once_with('fishaudio');eleven.assert_not_called()
            lab.start(self.cid,settings,'b'*20)
            synth.assert_called_once();reference.assert_called_once()
            self.assertNotEqual(lab.fingerprint(settings,lab.reference(self.cid)),lab.fingerprint(lab.DEFAULTS,lab.reference(self.cid)))
            # Hidden ElevenLabs controls must not invalidate a paid Fish sample.
            lab.start(self.cid,{**settings,'stability':.1},'c'*20)
            synth.assert_called_once()
            changed=lab.start(self.cid,{**settings,'temperature':.8},'d'*20)
            self.assertNotEqual(first['job']['fingerprint'],changed['job']['fingerprint'])
            self.assertEqual(synth.call_count,2)

    def test_fish_request_uses_real_reference_transcript_and_sampling_controls(self):
        self.reference();settings={**lab.DEFAULTS,'provider':'fishaudio','fish_engine':'s2.1-pro-free','temperature':.4,'top_p':.6}
        with patch.object(lab.languages,'run') as convert,patch.object(lab.languages,'heard',return_value='Words actually in reference') as heard, \
             patch.object(store,'media_duration',return_value=30):
            def converted(*args):
                Path(args[0][-1]).write_bytes(b'bounded reference')
            convert.side_effect=converted
            voice=lab.fish_reference(self.cid,settings,lab.reference(self.cid))
            lab.fish_reference(self.cid,settings,lab.reference(self.cid));heard.assert_called_once()
            self.assertEqual(voice['text'],'Words actually in reference')
        with patch.object(lab.languages,'request',return_value=b'audio') as request, \
             patch.object(lab.languages,'msgpack',return_value=b'packed') as pack:
            lab.fish_synthesis('mock',voice,settings)
            body=pack.call_args.args[0]
            self.assertEqual(body['references'],[voice]);self.assertEqual(body['temperature'],.4);self.assertEqual(body['top_p'],.6)
            self.assertEqual(body['text'],settings['text']);self.assertEqual(body['language'],'ru')
            self.assertEqual(request.call_args.args[2]['model'],'s2.1-pro-free')
