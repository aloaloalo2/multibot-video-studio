import sys
import tempfile
import unittest
import subprocess
import wave
import numpy as np
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
        self.patches=[patch.object(store,'DATA_ROOT',self.root),patch.object(store,'get_channel_folder',return_value=self.root),
                      patch.object(lab,'prepared_source',side_effect=lambda cid,*args:lab.folder(cid)/'reference.mp3')]
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
                       {'provider':'unknown'}, {'fish_engine':'unknown'}, {'temperature':-1}, {'top_p':True},
                       {'chunk_length':99},{'chunk_length':301},{'chunk_length':True},{'direction':'[text]'}, {'noise_cleanup':'yes'}]:
            with self.assertRaises(store.StudioError):lab.validated({**lab.DEFAULTS,**change})
        text='One sentence. Another sentence. Third sentence. Fourth sentence. Fifth sentence.'
        self.assertEqual(lab.validated({'text':text})['text'],text)
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
    def test_changed_settings_are_sent_to_eleven_and_busy_old_sample_is_not_substituted(self):
        self.reference();settings={**lab.DEFAULTS,'stability':.85,'similarity_boost':.95}
        with patch.object(lab.eleven_api,'streamed_dialogue',return_value=b'audio') as request:
            lab.synthesis('mock','voice',settings)
            self.assertEqual(request.call_args.kwargs['voice_settings'],{'stability':.85,'similarity_boost':.95})
        old={'status':'running','fingerprint':lab.fingerprint(lab.DEFAULTS,lab.reference(self.cid))}
        store.atomic_json(lab.folder(self.cid)/'job.json',old);lab.ACTIVE.add(self.cid)
        with self.assertRaises(store.StudioError) as error:lab.start(self.cid,settings,'b'*20)
        self.assertEqual(error.exception.status,409)

    def test_preparation_chunk_and_direction_separate_caches_and_reach_provider(self):
        ref={'sha256':'reference'};fish={**lab.DEFAULTS,'provider':'fishaudio'}
        for field,value in [('chunk_length',300),('noise_cleanup',False)]:
            self.assertNotEqual(lab.fingerprint(fish,ref),lab.fingerprint({**fish,field:value},ref))
        with patch.object(lab.languages,'request',return_value=b'audio') as request, \
             patch.object(lab.languages,'msgpack',return_value=b'packed') as pack:
            lab.fish_synthesis('secret',{'audio':b'voice','text':'reference'},{**fish,'chunk_length':300})
            self.assertEqual(pack.call_args.args[0]['chunk_length'],300)
        directed={**lab.DEFAULTS,'direction':'Warm, casual, measured pace'}
        with patch.object(lab.eleven_api,'streamed_dialogue',return_value=b'audio') as request:
            lab.synthesis('secret','id',directed)
            self.assertTrue(request.call_args.args[2].startswith('[Warm, casual, measured pace] '))
        self.assertNotEqual(lab.fingerprint(directed,ref),lab.fingerprint(lab.DEFAULTS,ref))

    def test_local_cleanup_preserves_source_duration_and_reuses_prepared_copy(self):
        self.patches[-1].stop()  # exercise the actual local FFmpeg path
        root=lab.folder(self.cid);source=root/'reference.mp3'
        sr=16000;t=np.arange(sr*8)/sr
        active=((t>1)&(t<3))|((t>4)&(t<7))
        rng=np.random.default_rng(31)
        signal=(.18*np.sin(2*np.pi*180*t)+.1*np.sin(2*np.pi*440*t))*active + rng.normal(0,.01,len(t))
        wav=root/'input.wav'
        with wave.open(str(wav),'wb') as out:
            out.setnchannels(1);out.setsampwidth(2);out.setframerate(sr);out.writeframes((signal*32767).astype('<i2').tobytes())
        subprocess.run(['ffmpeg','-v','error','-y','-i',str(wav),'-b:a','128k',str(source)],check=True)
        original=source.read_bytes();ref={'sha256':'synthetic'}
        with patch.object(lab.eleven_voices,'clone_files',return_value=[source]):
            cleaned=lab.prepared_source(self.cid,lab.DEFAULTS,ref)
            self.assertEqual(source.read_bytes(),original)
            stamp=cleaned.stat().st_mtime_ns
            self.assertEqual(cleaned,lab.prepared_source(self.cid,lab.DEFAULTS,ref))
            self.assertEqual(cleaned.stat().st_mtime_ns,stamp)
        self.assertLess(abs(store.media_duration(source)-store.media_duration(cleaned)),.15)
        def ratio(path):
            out=subprocess.run(['ffmpeg','-v','error','-i',str(path),'-ac','1','-ar',str(sr),'-f','f32le','pipe:1'],capture_output=True,check=True)
            a=np.frombuffer(out.stdout,dtype='<f4')[:len(t)]
            quiet=a[int(.25*sr):int(.75*sr)];speech=a[int(1.5*sr):int(2.5*sr)]
            self.assertTrue(np.isfinite(a).all());self.assertLess(np.max(np.abs(a)),1)
            return np.sqrt(np.mean(quiet**2))/np.sqrt(np.mean(speech**2))
        self.assertLess(ratio(cleaned),ratio(source)*.85)
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
