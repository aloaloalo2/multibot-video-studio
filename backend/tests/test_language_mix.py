import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import language_mix
import languages
import dubbing_fit
import store

@unittest.skipUnless(shutil.which('ffmpeg'),'ffmpeg needed')
class LanguageMixTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.voice=self.root/'voice.wav';self.music=self.root/'music.wav'
        for path,freq in [(self.voice,440),(self.music,220)]:
            dubbing_fit.command(['-f','lavfi','-i',f'sine=frequency={freq}:duration=3',path])
        self.project={'id':'p','episode_path':str(self.root),'duration':3,'tracks':[
            {'clips':[{'kind':'audio','asset_id':'orig','title':'Озвучка','start':0,'duration':3,'volume':1}]},
            {'clips':[{'kind':'audio','asset_id':'bed','title':'Music','start':1,'trim_start':.2,'duration':2,'volume':.3}]},
            {'muted':True,'clips':[{'kind':'audio','asset_id':'missing','title':'SFX','start':0,'duration':2}]}],
            'assets':[{'id':'orig','name':'voice.wav'},{'id':'bed','name':'music.wav'}]}
        self.data={'languages':{'uk':{'voice':{}}}}
        mocks=[patch.object(languages,'load_state',side_effect=lambda _:self.data),patch.object(languages,'voice_current',return_value=True),
               patch.object(languages,'file_path',return_value=self.voice),patch.object(store,'load_project_plan',return_value={}),
               patch.object(store,'resolve_asset',side_effect=lambda p,a:{'path':str(self.music)} if a=='bed' else (_ for _ in ()).throw(AssertionError(a))),
               patch.object(store,'load_project',side_effect=lambda _:self.project),patch.object(languages,'work_dir',return_value=self.root/'work'),
               patch.object(languages,'progress'),patch.object(languages,'update',side_effect=lambda p,f:f(self.data))]
        for mock in mocks:mock.start();self.addCleanup(mock.stop)

    def test_replaces_original_voice_and_respects_background_trim_level_mute(self):
        snap=language_mix.snapshot(self.project,'uk')
        self.assertEqual(len(snap['tracks']),2)
        self.assertEqual(snap['tracks'][0]['source'],str(self.voice))
        self.assertEqual((snap['tracks'][1]['start'],snap['tracks'][1]['trim_start'],snap['tracks'][1]['volume']),(1,.2,.3))
        self.assertIn('Українська',snap['destination'].name)

    def test_save_and_invalidation(self):
        self.assertEqual(language_mix.status(self.project,'uk',None)['state'],'missing')
        language_mix.save('p','uk',{})
        saved=self.data['languages']['uk']['saved_mix']
        self.assertEqual(language_mix.status(self.project,'uk',saved)['state'],'saved')
        self.assertAlmostEqual(store.media_duration(Path(saved['path'])),3,delta=.05)
        import numpy as np
        pcm=dubbing_fit.command(['-i',saved['path'],'-ac','1','-ar','48000','-f','f32le','pipe:1'])
        audio=np.frombuffer(pcm,dtype='<f4')
        def amplitude(start,frequency):
            block=audio[int(start*48000):int((start+.5)*48000)]
            return abs(np.fft.rfft(block)[round(frequency*.5)])
        # The bed begins at its own timeline position; the translated voice remains present throughout.
        self.assertLess(amplitude(.1,220)/amplitude(.1,440),.02)
        self.assertAlmostEqual(amplitude(1.5,220)/amplitude(1.5,440),.3,delta=.04)
        self.project['tracks'][1]['clips'][0]['volume']=.1
        self.assertEqual(language_mix.status(self.project,'uk',saved)['state'],'outdated')
        language_mix.save('p','uk',{})
        self.assertTrue(list((self.root/'work/mix-history').rglob('*.mp3')))
        Path(saved['path']).unlink()
        self.assertEqual(language_mix.status(self.project,'uk',self.data['languages']['uk']['saved_mix'])['state'],'missing')

    def test_duration_mismatch_never_overwrites_a_valid_episode_mix(self):
        language_mix.save('p','uk',{})
        saved=self.data['languages']['uk']['saved_mix']
        original=Path(saved['path']).read_bytes()
        for length,label in [(5,'Тривалість перевищена'),(2,'Тривалість закоротка')]:
            with self.subTest(length=length):
                dubbing_fit.command(['-f','lavfi','-i',f'sine=frequency=440:duration={length}',self.voice])
                self.data['languages']['uk']['voice'].update(duration=length,source_duration=3,timing_status='review')
                with self.assertRaisesRegex(store.StudioError,label):language_mix.save('p','uk',{})
                self.assertEqual(Path(saved['path']).read_bytes(),original)
                self.assertEqual(language_mix.status(self.project,'uk',saved)['state'],'unavailable')
                self.assertTrue(self.voice.is_file())

    def test_automatic_overlong_and_short_voice_skip_mix_without_paid_retry(self):
        for kind in ('voice','refit'):
            for length,label in [(5,'Тривалість перевищена'),(2,'Тривалість закоротка')]:
                with self.subTest(kind=kind,length=length):
                    self.data['languages']['uk']['voice'].update(duration=length,source_duration=3)
                    job={'key':'p|uk|voice','kind':kind,'status':'running','cost':37,'takes':2}
                    with patch.dict(languages.WORK,{kind:lambda *args:None}),patch.object(languages,'put_job'), \
                         patch.object(language_mix,'save') as save,patch.object(languages,'speak') as speak:
                        languages.worker('p',kind,'uk','elevenlabs',job)
                    self.assertEqual(job['status'],'done')
                    self.assertEqual(job['stage'],label)
                    self.assertFalse(job['audio_saved'])
                    self.assertEqual((job['cost'],job['takes']),(37,2))
                    save.assert_not_called();speak.assert_not_called()

    def test_duration_comparison_ignores_only_encoder_rounding(self):
        for duration in (2.98,3.02):
            self.assertEqual(language_mix.duration_check({'duration':duration,'source_duration':3})['state'],'matched')
        self.assertEqual(language_mix.duration_check({'duration':3.11,'source_duration':3})['state'],'too_long')
        self.assertEqual(language_mix.duration_check({'duration':2.89,'source_duration':3})['state'],'too_short')

    def test_relocation_keeps_saved_mix_current_without_hiding_other_edits(self):
        language_mix.save('p','uk',{})
        previous=self.music;self.music=self.root/'relocated.wav';previous.rename(self.music)
        self.assertEqual(language_mix.rebase_saved_after_move('p',{str(previous):str(self.music)}),1)
        self.assertEqual(language_mix.status(self.project,'uk',self.data['languages']['uk']['saved_mix'])['state'],'saved')
        self.project['tracks'][1]['clips'][0]['volume']=.1
        self.assertEqual(language_mix.rebase_saved_after_move('p',{str(previous):str(self.music)}),0)
        self.assertEqual(language_mix.status(self.project,'uk',self.data['languages']['uk']['saved_mix'])['state'],'outdated')

    def test_changed_project_during_render_does_not_publish(self):
        real=languages.run
        def change(cmd,what):
            real(cmd,what);self.project['tracks'][1]['clips'][0]['volume']=.2
        with patch.object(languages,'run',side_effect=change):
            with self.assertRaisesRegex(store.StudioError,'змінилися'):
                language_mix.save('p','uk',{})
        self.assertFalse(list((self.root/'Мови').rglob('*.mp3')))

    def test_missing_enabled_media_is_an_error_and_voice_mute_is_explicit(self):
        self.project['tracks'][1]['clips'][0]['asset_id']='missing'
        with self.assertRaises(AssertionError):language_mix.snapshot(self.project,'uk')
        self.project['tracks'][0]['muted']=True
        with self.assertRaisesRegex(store.StudioError,'Увімкніть'):
            language_mix.snapshot(self.project,'uk')

    def test_music_is_not_misidentified_as_voice(self):
        self.assertFalse(language_mix.voice_clip({'kind':'audio','asset_id':'bed','title':'Razgon · музика й ефекти'}, {}, 'bed'))
        self.assertFalse(language_mix.voice_clip({'kind':'audio','title':'SFX'}, {}, None))

    def test_voice_and_refit_jobs_finish_only_after_the_complete_mix_is_saved(self):
        for kind in ('voice','refit'):
            with self.subTest(kind=kind):
                job={'key':'p|uk|voice','kind':kind,'status':'running','progress':98,'cost':37,'takes':2}
                with patch.dict(languages.WORK,{kind:lambda *args:None}),patch.object(languages,'put_job'), \
                     patch.object(languages,'speak',side_effect=AssertionError('no paid generation in mix')):
                    languages.worker('p',kind,'uk','elevenlabs',job)
                self.assertEqual(job['status'],'done',job.get('error'))
                self.assertTrue(job['audio_saved'])
                self.assertEqual((job['cost'],job['takes']),(37,2))
                saved=self.data['languages']['uk']['saved_mix']
                self.assertEqual(saved['tracks'],2)
                self.assertEqual(language_mix.status(self.project,'uk',saved)['state'],'saved')
                self.assertEqual(Path(job['path']),language_mix.destination(self.project,'uk'))
                self.assertAlmostEqual(store.media_duration(Path(job['path'])),3,delta=.05)
                values=[call.args[2] for call in languages.progress.call_args_list]
                self.assertEqual(values,sorted(values))
                languages.progress.reset_mock()

    def test_failed_automatic_save_preserves_voice_and_can_retry_without_tts(self):
        original=self.voice.read_bytes()
        job={'key':'p|uk|voice','kind':'voice','status':'running','progress':92,'cost':37}
        with patch.dict(languages.WORK,{'voice':lambda *args:None}),patch.object(languages,'put_job'), \
             patch.object(language_mix,'save',side_effect=OSError('Диск недоступний')):
            languages.worker('p','voice','uk','elevenlabs',job)
        self.assertEqual(job['status'],'failed')
        self.assertTrue(job['voice_ready'])
        self.assertIn('Озвучка готова',job['error'])
        self.assertEqual(self.voice.read_bytes(),original)
        retry={'key':'p|uk|voice','kind':'save-audio','status':'running'}
        with patch.object(languages,'put_job'),patch.object(languages,'speak',side_effect=AssertionError('no paid retry')):
            languages.worker('p','save-audio','uk',None,retry)
        self.assertEqual(retry['status'],'done',retry.get('error'))
        self.assertTrue(Path(retry['path']).is_file())
        self.assertEqual(self.voice.read_bytes(),original)

    def test_sample_does_not_publish_a_soundtrack(self):
        job={'key':'p|uk|voice','kind':'sample','status':'running'}
        with patch.dict(languages.WORK,{'sample':lambda *args:None}),patch.object(languages,'put_job'), \
             patch.object(language_mix,'save',side_effect=AssertionError('sample is not full narration')):
            languages.worker('p','sample','uk','elevenlabs',job)
        self.assertEqual(job['status'],'done',job.get('error'))
        self.assertNotIn('saved_mix',self.data['languages']['uk'])

    def test_missing_episode_folder_blocks_full_voice_before_paid_work(self):
        self.project.pop('episode_path')
        with patch.object(languages,'key',side_effect=AssertionError('preflight first')):
            with self.assertRaisesRegex(store.StudioError,'Папку випуску'):
                languages.start('p','voice','uk','elevenlabs')
