import copy
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import channel_translation_voices as voices
import language_defaults
import languages
import store


class ChannelTranslationVoicesTest(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        self.cid='c'*16;self.examples={}
        for code in ('uk','es'):
            source=self.root/(code+'.mp3');source.write_bytes((code+' voice').encode()*200)
            meta=source.with_suffix('.json');store.atomic_json(meta,{'heard':True})
            self.examples[code]={'path':source,'meta':meta,'text':voices.TEXTS[code],'stamp':source.stat().st_mtime_ns,
                                 'duration':3,'heard':True,'filename':code+'.mp3','from':'channel'}
        for item in (patch.object(store,'DATA_ROOT',self.root/'data'),patch.object(store,'get_channel_folder',return_value=self.root),
                     patch.object(store,'media_duration',return_value=3),patch.object(languages,'channel_voice',side_effect=lambda cid,code:self.examples.get(code)),
                     patch.object(languages.language_quality,'require')):
            item.start();self.addCleanup(item.stop)
        voices.ACTIVE.clear();self.addCleanup(voices.ACTIVE.clear)
        self.eleven={'provider':'elevenlabs','eleven_engine':'eleven_v4_turbo'}

    def test_each_language_keeps_its_own_settings_and_ready_project_is_untouched(self):
        voices.save(self.cid,{'uk':self.eleven,'es':{'provider':'fishaudio','fish_engine':'s2.1-pro-free'}})
        before=copy.deepcopy(language_defaults.settings(self.cid,'es'))
        voices.save(self.cid,{'uk':{'provider':'elevenlabs','eleven_engine':'eleven_v4'}})
        self.assertEqual(language_defaults.settings(self.cid,'uk')['eleven_engine'],'eleven_v4')
        self.assertEqual(language_defaults.settings(self.cid,'es'),before)
        with patch.object(store,'load_project',return_value={'channel_id':self.cid}),patch.object(languages,'load_state',return_value={'languages':{'uk':{'narration':self.eleven}}}):
            self.assertEqual(languages.narration_choices('existing','uk')['eleven_engine'],'eleven_v4_turbo')

    def test_new_episode_inherits_language_choices_without_creating_a_voice(self):
        voices.save(self.cid,{'uk':self.eleven,'es':{'provider':'fishaudio','fish_engine':'drama-3'}})
        project={'id':'p','channel_id':self.cid}
        with patch.object(languages,'work_dir',return_value=self.root/'episode'),patch.object(languages,'save_state') as save,patch.object(languages,'request') as request:
            self.assertTrue(language_defaults.apply(project))
        data=save.call_args.args[1]
        self.assertEqual(data['languages']['uk']['narration']['eleven_engine'],'eleven_v4_turbo')
        self.assertEqual(data['languages']['es']['narration']['fish_engine'],'drama-3')
        self.assertNotIn('use_original_voice',data['languages']['uk']);request.assert_not_called()

    def test_options_reads_and_quotes_never_call_speech_or_clone_services(self):
        with patch.object(languages,'speak') as speak,patch.object(languages,'key') as key,patch.object(voices,'_voice') as clone:
            self.assertEqual({option['id'] for option in voices.options()['providers']},{'elevenlabs','fishaudio','heygen'})
            result=voices.describe(self.cid,'uk',self.eleven)
        self.assertTrue(result['available']);self.assertEqual(result['text'],voices.TEXTS['uk'])
        self.assertEqual(result['estimate']['unit'],'credits');speak.assert_not_called();key.assert_not_called();clone.assert_not_called()

    def test_heygen_sample_and_episode_use_same_model_voice_and_language(self):
        settings={'provider':'heygen','heygen_voice_id':'uk-channel-voice'}
        result=voices.describe(self.cid,'uk',settings)
        self.assertTrue(result['available'])
        self.assertEqual(result['estimate']['amount'],0)
        choices=result['settings']
        self.assertEqual(choices['heygen_model'],'heygen-voice-1-turbo-free')
        voice=voices._voice(self.cid,'uk',choices,None,{})
        voices.save(self.cid,{'uk':settings})
        with patch.object(store,'load_project',return_value={'channel_id':self.cid}),patch.object(languages,'load_state',return_value={}),patch.object(languages,'remote_voice_ids',return_value={}):
            self.assertEqual(languages.voice_id('episode','heygen','uk'),voice)
        target=self.root/'test.mp3'
        with patch.object(languages.heygen_voice,'synthesize',return_value=b'mock audio') as tts:
            languages.speak('heygen',voice,voices.TEXTS['uk'],target)
        tts.assert_called_once_with({'language':'uk','heygen_model':choices['heygen_model'],'heygen_voice_id':'uk-channel-voice','text':voices.TEXTS['uk']})
        self.assertEqual(target.read_bytes(),b'mock audio')
        self.assertNotEqual(result['key'],voices.describe(self.cid,'uk',{**settings,'heygen_model':'starfish'})['key'])

    def test_heygen_uses_language_recording_once_and_starfish_requires_id(self):
        import channel_voice_lab as lab
        choices=voices.choices(self.cid,'es',{'provider':'heygen'})
        example=self.examples['es']
        with patch.object(languages,'run'),patch.object(store,'channel_record',return_value={'name':'channel'}),patch.object(lab.heygen_voice,'clone_instant',return_value='es-clone') as clone:
            for _ in range(2):
                self.assertEqual(voices._voice(self.cid,'es',choices,example,{})['heygen_voice_id'],'es-clone')
            self.assertEqual(clone.call_count,1)
            self.assertEqual(clone.call_args.args[2],'es')
        self.assertFalse(voices.describe(self.cid,'es',{**choices,'heygen_model':'starfish'})['available'])

    def test_invalid_choices_and_paths_fail_before_provider_work(self):
        with patch.object(languages,'speak') as speak:
            for raw in ({'provider':'unknown'},{'eleven_engine':'other'},{'fish_engine':'other'},{'fish_style':'other'},{'fish_styles':[]}):
                with self.subTest(raw=raw),self.assertRaises(store.StudioError):voices.describe(self.cid,'uk',raw)
            with self.assertRaises(store.StudioError):voices.audio_file(self.cid,'uk','../outside')
            with self.assertRaises(store.StudioError):voices.start(self.cid,'uk',self.eleven,'','test')
        speak.assert_not_called()

    def test_sample_identity_tracks_the_selected_voice_model_language_and_text(self):
        base=voices.describe(self.cid,'uk',self.eleven)
        self.assertEqual(voices.describe(self.cid,'uk',{**self.eleven,'fish_engine':'drama-3'})['key'],base['key'])
        for code,raw,text in [('uk',{**self.eleven,'eleven_engine':'eleven_v4'},None),('es',self.eleven,None),('uk',self.eleven,'Інший текст зразка.')]:
            self.assertNotEqual(voices.describe(self.cid,code,raw,text)['key'],base['key'])
        self.examples['uk']['path'].write_bytes(b'new recording')
        self.assertNotEqual(voices.describe(self.cid,'uk',self.eleven)['key'],base['key'])

    def test_start_is_reserved_once_and_uses_an_immutable_reference_and_settings(self):
        settings=dict(self.eleven)
        with patch.object(voices.threading,'Thread') as thread:
            first=voices.start(self.cid,'uk',settings,None,'request-a')
            again=voices.start(self.cid,'uk',settings,None,'request-a')
            with self.assertRaises(store.StudioError):voices.start(self.cid,'uk',settings,None,'request-b')
        self.assertEqual(thread.call_count,1);self.assertTrue(first['working']);self.assertTrue(again['working'])
        args=thread.call_args.kwargs['args'];original=args[3]['path'].read_bytes()
        self.examples['uk']['path'].write_bytes(b'replaced source');settings['eleven_engine']='eleven_v4'
        self.assertEqual(args[3]['path'].read_bytes(),original);self.assertEqual(args[2]['eleven_engine'],'eleven_v4_turbo')
        self.assertTrue(voices.busy(self.cid))

    def test_success_is_playable_and_reused_without_another_paid_request(self):
        def speak(provider,voice,text,target):target.write_bytes(b'mp3 sample'*200);return 12
        with patch.object(voices.threading,'Thread') as thread:
            voices.start(self.cid,'uk',self.eleven,None,'request-a')
        with patch.object(voices,'_voice',return_value={'id':'voice','engine':'eleven_v4_turbo','language':'uk'}),patch.object(languages,'speak',side_effect=speak) as synthesis:
            voices._run(*thread.call_args.kwargs['args'])
            result=voices.start(self.cid,'uk',self.eleven,None,'request-b')
        self.assertEqual(synthesis.call_count,1);self.assertEqual(synthesis.call_args.args[0],'elevenlabs')
        self.assertEqual(result['sample']['duration'],3);self.assertEqual(result['estimate']['amount'],0);self.assertFalse(voices.busy())
        self.assertTrue(voices.audio_file(self.cid,'uk',result['key']).is_file())

    def test_failed_or_interrupted_sample_does_not_restart_on_status_reads(self):
        with patch.object(voices.threading,'Thread') as thread:voices.start(self.cid,'uk',self.eleven,None,'request-a')
        with patch.object(voices,'_voice',side_effect=RuntimeError('Provider offline')) as provider:
            voices._run(*thread.call_args.kwargs['args'])
            for _ in range(3):self.assertEqual(voices.describe(self.cid,'uk',self.eleven)['job']['status'],'failed')
            voices.start(self.cid,'uk',self.eleven,None,'request-a')
        provider.assert_called_once();self.assertFalse(voices.busy())
        target=voices.folder(self.cid,'uk')/'job.json';job=store.read_json(target,{});job['status']='running';store.atomic_json(target,job)
        self.assertEqual(voices.describe(self.cid,'uk',self.eleven)['job']['status'],'failed')

    def test_languages_can_test_independently_and_remote_voices_need_no_file(self):
        with patch.object(voices.threading,'Thread') as thread:
            voices.start(self.cid,'uk',self.eleven,None,'uk-request');voices.start(self.cid,'es',self.eleven,None,'es-request')
        self.assertEqual(thread.call_count,2)
        with patch.object(language_defaults,'remote_ids',return_value={'elevenlabs':'existing'}):
            self.assertTrue(voices.describe(self.cid,'pl',self.eleven)['available'])
        self.assertFalse(voices.describe(self.cid,'pl',self.eleven)['available'])

    def test_complete_audio_with_a_missing_receipt_is_recovered_without_paying_again(self):
        state=voices.describe(self.cid,'uk',self.eleven);target=voices.folder(self.cid,'uk')/(state['key']+'.mp3')
        target.parent.mkdir(parents=True);target.write_bytes(b'complete audio')
        with patch.object(languages,'speak') as speech,patch.object(voices.threading,'Thread') as thread:
            result=voices.start(self.cid,'uk',self.eleven,None,'recover')
        self.assertIsNotNone(result['sample']);speech.assert_not_called();thread.assert_not_called()

    def test_sample_clone_is_reused_by_portable_channel_defaults(self):
        import channel_voice_lab
        voices.save(self.cid,{'uk':self.eleven})
        with patch.object(channel_voice_lab,'clone',return_value=('test-key','existing-clone')) as clone:
            result=voices._voice(self.cid,'uk',voices.choices(self.cid,'uk'),self.examples['uk'],{})
        self.assertEqual(result['engine'],'eleven_v4_turbo');self.assertEqual(result['id'],'existing-clone')
        self.assertEqual(clone.call_args.args[2]['clone_owner'],self.cid)
        self.assertEqual(language_defaults.saved_clone(self.cid,'uk'),'existing-clone')
        with patch.object(languages,'fish_model') as create:
            voice=voices._voice(self.cid,'es',voices.choices(self.cid,'es'),self.examples['es'],{})
        create.assert_not_called();self.assertEqual(voice['audio'],self.examples['es']['path'].read_bytes())

    def test_changing_a_model_does_not_copy_the_channel_recordings_again(self):
        voices.save(self.cid,{'uk':self.eleven})
        before=store.read_json(language_defaults.root(self.cid)/'current.json',{})['version']
        with patch.object(shutil,'copy2') as copy_file:
            voices.save(self.cid,{'uk':{**self.eleven,'eleven_engine':'eleven_v4'}})
        copy_file.assert_not_called()
        self.assertEqual(store.read_json(language_defaults.root(self.cid)/'current.json',{})['version'],before)

    def test_remote_identity_and_known_clone_are_frozen_for_the_requested_voice(self):
        with patch.object(language_defaults,'remote_ids',return_value={'elevenlabs':'first'}):first=voices.describe(self.cid,'uk',self.eleven)['key']
        with patch.object(language_defaults,'remote_ids',return_value={'elevenlabs':'second'}):second=voices.describe(self.cid,'uk',self.eleven)['key']
        self.assertNotEqual(first,second)
        voices.save(self.cid,{'uk':self.eleven})
        path=language_defaults.root(self.cid)/'current.json';saved=store.read_json(path,{})
        saved['payload']['voices']['uk']['clone']='original-clone';store.atomic_json(path,saved)
        with patch.object(voices.threading,'Thread') as thread:voices.start(self.cid,'uk',self.eleven,None,'frozen')
        args=thread.call_args.kwargs['args'];saved['payload']['voices']['uk']['clone']='later-clone';store.atomic_json(path,saved)
        self.assertEqual(args[3]['known_clone'],'original-clone');self.assertEqual(args[4]['remote_ids'],{})


class ChannelTranslationVoiceHTTPTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import test_backend
        cls.fixture=test_backend.BackendTest;cls.fixture.setUpClass();cls.base_url=cls.fixture.base_url
    @classmethod
    def tearDownClass(cls):cls.fixture.tearDownClass()
    def request(self,*args,**kwargs):return self.fixture.request(self,*args,**kwargs)
    def test_status_settings_sample_and_origin_guard(self):
        cid=store.channel_id(self.fixture.channel);base='/api/channels/'+cid+'/voices'
        with patch.object(voices,'describe',return_value={'available':True,'sample':None}) as describe,patch.object(voices,'start',return_value={'working':True}) as start:
            self.assertEqual(self.request(base+'/uk/sample')[0],200);start.assert_not_called()
            self.assertEqual(self.request(base+'/uk/sample','POST',{'settings':{},'text':'Текст.','client_id':'test'})[0],202)
            self.assertEqual(self.request(base+'/uk/sample','POST',{},headers={'Origin':'https://outside.example'})[0],403)
            start.assert_called_once();describe.assert_called_once()
        code,result=self.request(base+'/settings','POST',{'languages':{'uk':{'provider':'elevenlabs','eleven_engine':'eleven_v4_turbo'}}})
        self.assertEqual(code,200,result);self.assertEqual(language_defaults.settings(cid,'uk')['eleven_engine'],'eleven_v4_turbo')
    def test_a_sample_blocks_restart_and_channel_replacement(self):
        cid=store.channel_id(self.fixture.channel)
        with patch.object(voices,'ACTIVE',{(cid,'uk')}):
            code,result=self.request('/api/studio/status');self.assertEqual(code,200)
            self.assertIn('зразки голосів перекладу',result['busy']);self.assertIn(cid,result['active_channels'])


if __name__=='__main__':unittest.main()
