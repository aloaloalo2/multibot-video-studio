import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store,languages,language_defaults

class LanguageDefaultsTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.channel=self.root/'Channel';self.channel.mkdir()
        for p in [patch.object(store,'DATA_ROOT',self.root/'data'),patch.object(store,'PROJECTS_ROOT',self.root/'data/projects'),
                  patch.object(store,'get_channel_folder',return_value=self.channel),patch.object(store,'note_topics'),
                  patch.object(languages,'key',return_value='test-secret'),
                  patch.object(store,'global_settings',return_value={}),patch.object(store,'media_duration',return_value=3)]:
            p.start();self.addCleanup(p.stop)
        self.project=store.create_project('c'*16,'First');self.pid=self.project['id']
        w=languages.work_dir(self.pid,'uk');w.mkdir(parents=True)
        (w/'own-voice.mp3').write_bytes(b'saved voice');(w/'own-voice.txt').write_text('Приклад голосу')
        store.atomic_json(w/'own-voice.json',{'filename':'Мій голос.wav','example_level_version':languages.EXAMPLE_LEVEL_VERSION,
            'example_source_stamp':languages.example_source_stamp(w/'own-voice.mp3'),'example_normalized_copy':False})
        stamp=(w/'own-voice.mp3').stat().st_mtime_ns
        languages.save_state(self.pid,{'provider':'elevenlabs','eleven_engine':'eleven_v4_turbo',
            'languages':{'uk':{},'es':{}},'clones':{f'elevenlabs-uk-episode-{stamp}':'known-clone'},
            'fish_engine':'drama-3','fish_styles':{'drama-3':'normal'}})

    def test_new_project_inherits_choices_and_voice_without_paid_generation(self):
        self.assertFalse(language_defaults.status(self.pid)['saved'])
        language_defaults.save(self.pid)
        self.assertTrue(language_defaults.status(self.pid)['saved'])
        with patch.object(languages,'request',side_effect=AssertionError('no paid requests')):
            new=store.create_project('c'*16,'Second');pid=new['id'];data=languages.load_state(pid)
            self.assertEqual(data['eleven_engine'],'eleven_v4_turbo')
            self.assertEqual(data['provider'],'elevenlabs')
            self.assertEqual(list(data['languages']),['uk','es'])
            self.assertEqual(languages.voice_id(pid,'elevenlabs','uk')['id'],'known-clone')
            self.assertEqual(languages.own_voice(pid,'uk')['text'],'Приклад голосу')
            self.assertEqual(languages.own_voice(pid,'uk')['filename'],'Мій голос.wav')
            self.assertIsNone(languages.own_voice(pid,'es'))
            self.assertFalse((languages.work_dir(pid,'uk')/'voice.mp3').exists())
            self.assertTrue(language_defaults.status(pid)['saved'])
        self.assertEqual(languages.load_state(self.pid)['eleven_engine'],'eleven_v4_turbo')

    def test_existing_projects_keep_their_own_choices_and_default_changes_are_explicit(self):
        existing=store.create_project('c'*16,'Existing')
        language_defaults.save(self.pid)
        self.assertEqual(languages.load_state(existing['id']),{})
        languages.update(self.pid,lambda d:d.update(eleven_engine='eleven_v4'))
        self.assertFalse(language_defaults.status(self.pid)['saved'])
        new=store.create_project('c'*16,'Later')
        self.assertEqual(languages.eleven_engine(new['id']),'eleven_v4_turbo')
        language_defaults.save(self.pid)
        newest=store.create_project('c'*16,'Newest')
        self.assertEqual(languages.eleven_engine(newest['id']),'eleven_v4')
        self.assertEqual(languages.eleven_engine(new['id']),'eleven_v4_turbo')

    def test_explicit_apply_to_old_project_preserves_translation_and_generated_audio(self):
        existing=store.create_project('c'*16,'Existing');pid=existing['id']
        languages.save_state(pid,{'languages':{'uk':{'voice':{'made_at':9}}}})
        w=languages.work_dir(pid,'uk');w.mkdir(parents=True);(w/'text.txt').write_text('Existing translation')
        (w/'voice.mp3').write_bytes(b'existing audio')
        language_defaults.save(self.pid)
        with patch.object(languages,'overview',side_effect=lambda p:languages.load_state(p)):
            applied=language_defaults.apply_existing(pid)
        self.assertEqual(applied['eleven_engine'],'eleven_v4_turbo')
        self.assertEqual((w/'text.txt').read_text(),'Existing translation')
        self.assertEqual((w/'voice.mp3').read_bytes(),b'existing audio')
        with patch.object(languages,'request',side_effect=AssertionError('do not upload again')):
            self.assertEqual(languages.voice_id(pid,'elevenlabs','uk')['id'],'known-clone')

    def test_existing_project_automatically_finds_saved_reference_without_applying(self):
        existing=store.create_project('c'*16,'Before defaults');pid=existing['id']
        languages.save_state(pid,{'languages':{'uk':{}}})
        language_defaults.save(self.pid)
        with patch.object(languages,'request',side_effect=AssertionError('no duplicate clone upload')):
            self.assertEqual(languages.voice_for(pid,'uk',original=False)['from'],'defaults')
            self.assertEqual(languages.voice_id(pid,'elevenlabs','uk')['id'],'known-clone')

    def test_removing_reference_changes_default_state_and_does_not_restore_it_implicitly(self):
        language_defaults.save(self.pid)
        with patch.object(languages,'overview',side_effect=lambda p:languages.load_state(p)):
            languages.remove_own_voice(self.pid,'uk')
        self.assertFalse(language_defaults.status(self.pid)['saved'])
        self.assertIsNone(languages.voice_for(self.pid,'uk',original=False))

    def test_defaults_are_isolated_per_channel(self):
        language_defaults.save(self.pid)
        other=store.create_project('d'*16,'Other channel')
        self.assertEqual(languages.load_state(other['id']),{})

    def test_saving_during_another_narration_only_updates_channel_defaults(self):
        languages.ACTIVE.add(languages.job_key(self.pid,'uk','voice'))
        languages.update(self.pid,lambda d:d.update(jobs={'uk|voice':{'status':'running','code':'uk','kind':'voice'}}))
        try:
            before=languages.load_state(self.pid)
            self.assertTrue(language_defaults.save(self.pid)['saved'])
            self.assertEqual(languages.load_state(self.pid),before)
        finally:languages.ACTIVE.clear()

    def test_inherited_run_keeps_audio_model_and_clone_when_other_project_saves_defaults(self):
        language_defaults.save(self.pid)
        project=store.create_project('c'*16,'Running episode');pid=project['id']
        shutil=__import__('shutil');shutil.rmtree(languages.work_dir(pid,'uk'))
        languages.save_state(pid,{'languages':{'uk':{}}})
        language_defaults.pin_narration(pid,'uk')
        example=languages.voice_for(pid,'uk');audio=example['path'].read_bytes()
        reference=languages.work_dir(self.pid,'uk')/'own-voice.mp3'
        reference.write_bytes(b'another saved voice')
        meta=store.read_json(reference.with_suffix('.json'),{})
        meta['example_source_stamp']=languages.example_source_stamp(reference)
        store.atomic_json(reference.with_suffix('.json'),meta)
        languages.update(self.pid,lambda d:d.update(eleven_engine='eleven_v4'))
        language_defaults.save(self.pid)
        self.assertEqual(languages.eleven_engine(pid),'eleven_v4_turbo')
        self.assertEqual(languages.voice_for(pid,'uk')['path'].read_bytes(),audio)
        with patch.object(languages,'request',side_effect=AssertionError('no upload')):
            self.assertEqual(languages.voice_id(pid,'elevenlabs','uk')['id'],'known-clone')

    def test_saved_check_compares_open_language_and_active_engine_only(self):
        language_defaults.save(self.pid)
        languages.update(self.pid,lambda d:d.update(languages={'uk':{},'es':{},'pl':{}},fish_engine='s2.1-pro-free'))
        status=language_defaults.status(self.pid)
        self.assertTrue(status['by_language']['uk'])
        self.assertTrue(status['by_language']['es'])
        self.assertFalse(status['by_language']['pl'])
        languages.update(self.pid,lambda d:d.update(eleven_engine='eleven_v4'))
        self.assertFalse(language_defaults.status(self.pid)['by_language']['uk'])

    def test_missing_settings_inherit_channel_without_overwriting_explicit_choices(self):
        language_defaults.save(self.pid)
        existing=store.create_project('c'*16,'Existing');pid=existing['id']
        languages.save_state(pid,{'languages':{'uk':{}}})
        self.assertEqual(languages.eleven_engine(pid),'eleven_v4_turbo')
        self.assertEqual(languages.narration_settings(pid)['provider'],'elevenlabs')
        self.assertTrue(language_defaults.status(pid)['by_language']['uk'])
        languages.update(pid,lambda d:d.update(eleven_engine='eleven_v4'))
        self.assertFalse(language_defaults.status(pid)['by_language']['uk'])

    def test_saving_during_translation_and_repeated_save_are_safe(self):
        languages.ACTIVE.add(languages.job_key(self.pid,'uk','voice'))
        languages.update(self.pid,lambda d:d.update(jobs={'uk|voice':{'status':'running','code':'uk','kind':'translate'}}))
        try:
            language_defaults.save(self.pid)
            path=language_defaults.root('c'*16)/'current.json';before=path.read_bytes()
            self.assertTrue(language_defaults.save(self.pid)['saved'])
            self.assertEqual(path.read_bytes(),before)
        finally:languages.ACTIVE.clear()

    def test_language_order_does_not_falsely_mark_saved_defaults_dirty(self):
        language_defaults.save(self.pid)
        languages.update(self.pid,lambda d:d.update(languages={'es':{},'uk':{}}))
        self.assertTrue(language_defaults.status(self.pid)['saved'])

    def test_resaving_an_automatically_available_voice_keeps_the_existing_clone(self):
        existing=store.create_project('c'*16,'Episode');pid=existing['id']
        language_defaults.save(self.pid)
        languages.save_state(pid,{'languages':{'uk':{}},'provider':'elevenlabs','eleven_engine':'eleven_v4'})
        language_defaults.save(pid)
        self.assertEqual(language_defaults.saved_clone('c'*16,'uk'),'known-clone')
