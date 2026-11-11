import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import channel_voice_lab as lab
import fish_voice
import store


class ImmediateThread:
    def __init__(self,target,args,**kwargs):self.target,self.args=target,args
    def start(self):self.target(*self.args)


class VoiceIDsTest(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name);self.cid='c'*16
        for p in (patch.object(store,'DATA_ROOT',self.root),patch.object(store,'get_channel_folder',return_value=self.root),
                  patch.object(store,'channel_record',return_value={'name':'Test'}),patch.object(lab.languages,'key',return_value='test-key')):
            p.start();self.addCleanup(p.stop)
        lab.ACTIVE.clear();self.addCleanup(lab.ACTIVE.clear)

    def test_ids_validate_and_isolate_cache_without_a_local_recording(self):
        for provider,field in [('fishaudio','fish_voice_id'),('elevenlabs','eleven_voice_id')]:
            settings=lab.validated({'provider':provider,field:'existing'})
            ref=lab.effective_reference(self.cid,settings)
            self.assertIsNotNone(ref)
            self.assertNotEqual(lab.original_path(settings,ref),lab.original_path({**settings,field:'another'},lab.effective_reference(self.cid,{**settings,field:'another'})))
            self.assertEqual(lab.fingerprint(settings,ref),lab.fingerprint({**settings,'noise_cleanup':False},ref))
            for bad in [42,True,'https://example.com/id','x'*129]:
                with self.assertRaises(store.StudioError):lab.validated({field:bad})

    def test_fish_sample_uses_id_without_reference_upload_or_recognition(self):
        settings=lab.validated({'provider':'fishaudio','fish_voice_id':'existing'})
        bodies=[]
        with patch.object(lab.threading,'Thread',ImmediateThread),patch.object(lab.languages,'msgpack',side_effect=lambda body:(bodies.append(body) or b'payload')), \
             patch.object(lab.languages,'request',return_value=b'audio') as request,patch.object(store,'media_duration',return_value=2), \
             patch.object(lab.languages.language_quality,'require'),patch.object(lab,'prepared_source') as prepare,patch.object(lab.languages,'heard') as heard:
            result=lab.start(self.cid,settings,'a'*20)
            self.assertEqual(result['job']['status'],'done')
            self.assertEqual(bodies[0]['reference_id'],'existing')
            self.assertNotIn('references',bodies[0]);prepare.assert_not_called();heard.assert_not_called();request.assert_called_once()

    def test_eleven_id_bypasses_clone_creation(self):
        s=lab.validated({'provider':'elevenlabs','eleven_voice_id':'existing'})
        with patch.object(lab.eleven_voices,'resolve') as resolve:
            self.assertEqual(lab.clone(self.cid,s,{}),('test-key','existing'));resolve.assert_not_called()

    def test_fish_create_is_private_does_not_synthesize_and_reuses_receipt(self):
        root=lab.folder(self.cid);(root/'reference.mp3').write_bytes(b'original')
        s=lab.validated({'provider':'fishaudio'})
        with patch.object(lab,'prepared_source',return_value=root/'reference.mp3'),patch.object(lab,'fish_reference',return_value={'audio':b'reference','text':'Reference'}),patch.object(fish_voice,'create',return_value='cloud-id') as create:
            first=lab.create_fish_voice(self.cid,s)
            self.assertEqual(first['settings']['fish_voice_id'],'cloud-id')
            lab.create_fish_voice(self.cid,s)
            create.assert_called_once()
        self.assertEqual(list((self.root/'fish-clones').glob('*.json')).__len__(),1)

    def test_uncertain_fish_creation_cannot_upload_twice(self):
        root=lab.folder(self.cid);(root/'reference.mp3').write_bytes(b'original')
        s=lab.validated({'provider':'fishaudio'})
        with patch.object(lab,'prepared_source',return_value=root/'reference.mp3'),patch.object(lab,'fish_reference',return_value={'audio':b'reference','text':'Reference'}),patch.object(fish_voice,'create',side_effect=TimeoutError) as create:
            with self.assertRaises(TimeoutError):lab.create_fish_voice(self.cid,s)
            with self.assertRaises(store.StudioError):lab.create_fish_voice(self.cid,s)
            create.assert_called_once();self.assertNotIn(self.cid,lab.ACTIVE)

    def test_fish_http_creation_disables_publication_and_preview_generation(self):
        source=self.root/'reference.mp3';source.write_bytes(b'voice')
        with patch.object(fish_voice.urllib.request,'urlopen',return_value=io.BytesIO(b'{"_id":"cloud-id"}')) as request:
            self.assertEqual(fish_voice.create(source,'Reference','Test','secret'),'cloud-id')
            body=request.call_args.args[0].data
            self.assertIn(b'name="visibility"\r\n\r\nprivate',body)
            self.assertIn(b'name="generate_sample"\r\n\r\nfalse',body)
            self.assertNotIn(b'/v1/tts',body)


if __name__=='__main__':unittest.main()
