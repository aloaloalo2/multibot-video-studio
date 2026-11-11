import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store,languages,language_defaults,eleven_api

class LanguageDefaultsTest(unittest.TestCase):
    def test_imported_remote_defaults_need_no_reference_files_or_clone_requests(self):
        cid='c'*16;version='f'*32
        payload={'settings':{'provider':'fishaudio','fish_engine':'s2.1-pro-free'},'languages':['uk'],
                 'voices':{'uk':{'remote_only':True,'voice_ids':{'fishaudio':'fish-id','elevenlabs':'eleven-id'},'clone':'eleven-id'}}}
        store.atomic_json(language_defaults.root(cid)/'current.json',{'version':version,'payload':payload,'signature':language_defaults.signature(payload)})
        with patch.object(languages,'request',side_effect=AssertionError('no upload')):
            project=store.create_project(cid,'Imported IDs');pid=project['id']
            self.assertEqual(languages.voice_id(pid,'fishaudio','uk')['model_id'],'fish-id')
            self.assertEqual(languages.voice_id(pid,'elevenlabs','uk')['id'],'eleven-id')
            self.assertFalse((languages.work_dir(pid,'uk')/'own-voice.mp3').exists())
            self.assertEqual(languages.voice_cache_context(pid,'uk','fishaudio')[0]['reference_id'],'fish-id')
            language_defaults.pin_narration(pid,'uk')
            self.assertEqual(languages.load_state(pid)['languages']['uk']['voice_ids']['fishaudio'],'fish-id')
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

    def test_channel_voices_expose_saved_provider_model_without_remote_requests(self):
        cid='c'*16
        with patch.object(languages,'channel_voice',return_value=None),patch.object(eleven_api,'get',side_effect=AssertionError('metadata must stay local')):
            self.assertIsNone(languages.channel_voices(cid)['narration_defaults'])
            language_defaults.save(self.pid)
            self.assertEqual(languages.channel_voices(cid)['narration_defaults'],{
                'provider':'elevenlabs','provider_name':'ElevenLabs','engine':'eleven_v4_turbo',
                'engine_name':'Eleven v4 Turbo','style':None,'style_name':None})
            languages.update(self.pid,lambda data:data.update(provider='fishaudio'))
            # An unsaved episode choice must not appear as a saved channel default.
            self.assertEqual(languages.channel_voices(cid)['narration_defaults']['provider'],'elevenlabs')
            language_defaults.save(self.pid,'uk')
            saved=languages.channel_voices(cid)['narration_defaults']
            self.assertEqual((saved['provider_name'],saved['engine_name'],saved['style_name']),('Fish Audio','Drama 3','Звичайно'))

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

    def test_legacy_excerpt_matches_full_recording_only_in_defaults_status(self):
        import numpy as np,subprocess
        from unittest.mock import Mock
        short=self.root/'short.mp3';full=self.root/'full.mp3'
        short.write_bytes(b'short');full.write_bytes(b'full')
        rng=np.random.default_rng(23);a=(rng.standard_normal(45*8000)*.1).astype('<f4')
        decoded={str(short):a.tobytes(),str(full):(a*.8).astype('<f4').tobytes()}
        def decode(command,**kw):return Mock(stdout=decoded[command[command.index('-i')+1]])
        with patch.object(store,'media_duration',side_effect=lambda p:45 if p==short else 1600),patch.object(subprocess,'run',side_effect=decode):
            self.assertTrue(language_defaults.same_reference(full,short))
            # Equal lengths/names do not qualify; a changed recording must compare anew.
            full.write_bytes(b'other recording')
            decoded[str(full)]=(rng.standard_normal(45*8000)*.1).astype('<f4').tobytes()
            self.assertFalse(language_defaults.same_reference(full,short))

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

    def reference(self,pid,code,audio,clone):
        folder=languages.work_dir(pid,code);folder.mkdir(parents=True,exist_ok=True)
        path=folder/'own-voice.mp3';path.write_bytes(audio)
        (folder/'own-voice.txt').write_text('Saved reference')
        store.atomic_json(folder/'own-voice.json',{'filename':f'{code}.mp4',
            'example_level_version':languages.EXAMPLE_LEVEL_VERSION,
            'example_source_stamp':languages.example_source_stamp(path),'example_normalized_copy':False})
        languages.update(pid,lambda data:data.setdefault('clones',{}).update({f'elevenlabs-{code}-episode-{path.stat().st_mtime_ns}':clone}))

    def test_language_save_preserves_other_voices_across_old_and_new_projects(self):
        self.reference(self.pid,'es',b'spanish original','es-original')
        language_defaults.save(self.pid)
        second=store.create_project('c'*16,'Second')['id']
        self.reference(second,'uk',b'ukrainian full reference','uk-full')
        with patch.object(languages,'request',side_effect=AssertionError('no paid requests')):
            language_defaults.save(second,'uk')
            first_status=language_defaults.status(self.pid)['by_language']
            self.assertTrue(first_status['es'])
            self.assertFalse(first_status['uk'])
            self.assertEqual(language_defaults.saved_clone('c'*16,'es'),'es-original')
            self.assertEqual(language_defaults.reference('c'*16,'es')['path'].read_bytes(),b'spanish original')
            # Saving Spanish from an older project must not restore its obsolete Ukrainian voice.
            self.reference(self.pid,'es',b'spanish new reference','es-new')
            language_defaults.save(self.pid,'es')
            third=store.create_project('c'*16,'Third')['id']
            self.assertEqual(languages.own_voice(third,'uk')['path'].read_bytes(),b'ukrainian full reference')
            self.assertEqual(languages.own_voice(third,'es')['path'].read_bytes(),b'spanish new reference')
            self.assertEqual(languages.voice_id(third,'elevenlabs','uk')['id'],'uk-full')
            self.assertEqual(languages.voice_id(third,'elevenlabs','es')['id'],'es-new')
            self.assertTrue(language_defaults.status(third)['saved'])
            # Re-saving unchanged Spanish is idempotent despite the old project's other voice.
            saved=language_defaults.root('c'*16)/'current.json';before=saved.read_bytes()
            self.assertTrue(language_defaults.save(self.pid,'es')['by_language']['es'])
            self.assertEqual(saved.read_bytes(),before)

    def test_legacy_save_keeps_languages_missing_from_the_project(self):
        self.reference(self.pid,'es',b'spanish reference','es-clone')
        language_defaults.save(self.pid)
        second=store.create_project('c'*16,'Only Ukrainian')['id']
        languages.update(second,lambda data:data.update(languages={'uk':{}}))
        self.reference(second,'uk',b'new ukrainian reference','uk-new')
        language_defaults.save(second)
        self.assertTrue(language_defaults.status(self.pid)['by_language']['es'])
        self.assertEqual(language_defaults.reference('c'*16,'es')['path'].read_bytes(),b'spanish reference')
        self.assertEqual(language_defaults.saved_clone('c'*16,'es'),'es-clone')

    def test_scoped_save_does_not_publish_other_new_languages_or_invalid_codes(self):
        language_defaults.save(self.pid,'uk')
        saved=language_defaults.root('c'*16)/'current.json'
        self.assertEqual(store.read_json(saved,{})['payload']['languages'],['uk'])
        before=saved.read_bytes()
        for code in ('pl','invalid',[]):
            with self.assertRaises(store.StudioError):language_defaults.save(self.pid,code)
            self.assertEqual(saved.read_bytes(),before)

    def test_language_models_are_independent_and_keep_other_paid_cache_identity(self):
        with patch.object(languages,'overview',side_effect=lambda pid:languages.load_state(pid)):
            before=languages.voice_cache_context(self.pid,'uk','elevenlabs')[0]
            languages.set_provider(self.pid,'fishaudio','drama-3','normal',code='es')
            self.assertEqual(languages.narration_choices(self.pid,'uk')['provider'],'elevenlabs')
            self.assertEqual(languages.narration_choices(self.pid,'es')['provider'],'fishaudio')
            self.assertEqual(languages.voice_cache_context(self.pid,'uk','elevenlabs')[0],before)
            language_defaults.pin_narration(self.pid,'es')
            languages.set_provider(self.pid,'elevenlabs','eleven_v4',code='uk')
            self.assertEqual(languages.narration_choices(self.pid,'es')['provider'],'fishaudio')
            self.assertEqual(languages.eleven_engine(self.pid,'uk'),'eleven_v4')

    def test_language_defaults_save_preserves_other_models_and_applies_to_new_project(self):
        language_defaults.save(self.pid)
        with patch.object(languages,'overview',side_effect=lambda pid:languages.load_state(pid)):
            languages.set_provider(self.pid,'fishaudio','drama-3','normal',code='es')
            dirty=language_defaults.status(self.pid)['by_language']
            self.assertTrue(dirty['uk']);self.assertFalse(dirty['es'])
            language_defaults.save(self.pid,'es')
            later=store.create_project('c'*16,'Separate voices')['id']
            self.assertEqual(languages.narration_choices(later,'es')['provider'],'fishaudio')
            self.assertEqual(languages.fish_engine(later,'es'),'drama-3')
            self.assertEqual(languages.narration_choices(later,'uk')['provider'],'elevenlabs')
            self.assertTrue(language_defaults.status(later)['saved'])
            self.assertEqual(languages.voice_id(later,'elevenlabs','uk')['id'],'known-clone')

    def test_running_language_does_not_lock_other_language_settings(self):
        languages.ACTIVE.add(languages.job_key(self.pid,'uk','voice'))
        try:
            with patch.object(languages,'overview',side_effect=lambda pid:languages.load_state(pid)):
                languages.set_provider(self.pid,'fishaudio','drama-3',code='es')
                before=languages.load_state(self.pid)
                with self.assertRaises(store.StudioError):languages.set_provider(self.pid,'fishaudio',code='uk')
                with self.assertRaises(store.StudioError):languages.set_provider(self.pid,'fishaudio')
                self.assertEqual(languages.load_state(self.pid),before)
        finally:languages.ACTIVE.clear()
