import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import narration_audio as audio
import narration_profile as profile
import dubbing_fit


@unittest.skipUnless(shutil.which('ffmpeg'),'ffmpeg required')
class NarrationAudioTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name)

    def fixture(self,name='take.wav'):
        rate=audio.RATE
        # Include a breath inside the phrase and a very quiet consonant at both
        # edges. Only the outer quiet padding is removable.
        voice=np.r_[np.full(960,.004), .2*np.sin(2*np.pi*230*np.arange(rate)/rate),
                    np.zeros(rate//4), .2*np.sin(2*np.pi*330*np.arange(rate)/rate),np.full(960,.004)]
        signal=np.r_[np.zeros(rate//2),voice,np.zeros(rate//2)]
        path=self.folder/name
        with wave.open(str(path),'wb') as out:
            out.setparams((1,2,rate,0,'NONE','not compressed'))
            out.writeframes((signal*32767).astype('<i2').tobytes())
        return path,signal

    def test_only_outer_quiet_is_removed_with_low_level_speech_and_guards_preserved(self):
        path,_=self.fixture();original=path.read_bytes()
        measured=audio.inspect(path,self.folder/'cache')
        self.assertAlmostEqual(measured['removed_leading'],.47)
        self.assertAlmostEqual(measured['removed_trailing'],.47)
        self.assertAlmostEqual(measured['length'],2.35)
        self.assertEqual(path.read_bytes(),original)
        decoded=dubbing_fit.command(['-i',path,'-af',audio.FORMAT,'-f','f32le','pipe:1'])
        fitted=dubbing_fit.command(['-i',path,'-af',audio.filters({'trim':measured},1),'-f','f32le','pipe:1'])
        self.assertEqual(fitted,decoded[measured['start_sample']*4:measured['end_sample']*4])
        self.assertEqual(len(fitted)/4/audio.RATE,measured['length'])

    def test_cache_uses_audio_content_and_never_trusts_a_changed_file(self):
        path,_=self.fixture();cache=self.folder/'cache'
        first=audio.inspect(path,cache)
        with patch.object(audio.subprocess,'run',side_effect=AssertionError('Already measured')):
            self.assertEqual(audio.inspect(path,cache),first)
            copy=self.folder/'copy.wav';shutil.copy2(path,copy)
            self.assertEqual(audio.inspect(copy,cache),first)
        with wave.open(str(path),'wb') as out:
            out.setparams((1,2,audio.RATE,0,'NONE','not compressed'))
            out.writeframes(np.full(audio.RATE,1000,dtype='<i2').tobytes())
        changed=audio.inspect(path,cache)
        self.assertNotEqual(changed['fingerprint'],first['fingerprint'])
        self.assertEqual(changed['length'],1.)

    def test_silent_or_invalid_audio_stops_without_destroying_original(self):
        path=self.folder/'silent.wav'
        with wave.open(str(path),'wb') as out:
            out.setparams((1,2,audio.RATE,0,'NONE','not compressed'));out.writeframes(b'\0\0'*audio.RATE)
        previous=path.read_bytes()
        with self.assertRaisesRegex(RuntimeError,'немає придатного звуку'):
            audio.inspect(path,self.folder/'cache')
        self.assertEqual(path.read_bytes(),previous)

    def test_real_complete_refit_uses_padding_budget_and_keeps_raw_hashes(self):
        path,_=self.fixture();digest=hashlib.sha256(path.read_bytes()).hexdigest()
        items=[{'index':i,'file':path.name,'start':i*2.5,'original_start':i*2.5,
                'original_end':i*2.5+2.3,'length':3.29} for i in range(4)]
        with self.assertRaisesRegex(RuntimeError,'при межі 7%'):
            dubbing_fit.fitting_speeds(items,10.)
        result=dubbing_fit.rebuild(self.folder,items,self.folder/'full.mp3',10.)
        self.assertEqual(len(result['phrases']),4)
        for item in result['phrases']:
            self.assertTrue(.93<=item['speed']<=1.07)
            self.assertAlmostEqual(item['trim']['removed_leading'],.47)
        self.assertLessEqual(result['phrases'][-1]['end'],10.)
        decoded=dubbing_fit.command(['-i',self.folder/'full.mp3','-ar',audio.RATE,'-ac',1,'-f','f32le','pipe:1'])
        self.assertAlmostEqual(len(decoded)/4/audio.RATE,10.,delta=.025)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest)


class NarrationProfileTest(unittest.TestCase):
    def test_an_oversized_block_is_refined_even_when_the_whole_film_fits(self):
        texts=['a'*100]*20
        segments=[{'start':i*5.,'end':(i+1)*5.} for i in range(10)]
        segments += [{'start':50+(i-10)*15.,'end':50+(i-9)*15.} for i in range(10,20)]
        plan=profile.refinement(texts,segments,200.,{'seconds_per_character':.08,'observations':30})
        self.assertEqual(plan['over_by'],0)
        self.assertTrue(plan['ids'])
        self.assertTrue(all(i<10 for i in plan['ids']))
        self.assertTrue(all(value>=88 for value in plan['targets'].values()))
        self.assertEqual(plan['windows'][0]['start_index'],0)

    def test_profile_isolated_by_voice_model_language_and_reused_only_once(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);identity={'model':'v4','voice':'one','language':'uk'}
            observations=[('a'*100,{'fingerprint':str(i),'length':8.}) for i in range(5)]
            profile.remember(root,identity,observations)
            self.assertAlmostEqual(profile.read(root,identity)['seconds_per_character'],.08*1.03)
            profile.remember(root,identity,observations)
            self.assertEqual(profile.read(root,identity)['observations'],5)
            for changed in [{'model':'other'},{'voice':'other'},{'language':'es'}]:
                self.assertIsNone(profile.read(root,{**identity,**changed}))
            self.assertNotIn('a'*100,profile.location(root,identity).read_text())

    def test_explicit_translation_targets_largest_timing_overruns_without_mutating_text(self):
        texts=['a'*100,'b'*180,'c'*80];original=texts.copy()
        segments=[{'start':0,'end':9},{'start':10,'end':14},{'start':15,'end':25}]
        plan=profile.refinement(texts,segments,25,{'seconds_per_character':.08,'observations':50})
        self.assertIn(1,plan['ids'])
        self.assertGreater(180-plan['targets'][1],0)
        self.assertEqual(texts,original)
        self.assertEqual(profile.refinement(texts,segments,50,None),{'ids':[]})
        self.assertEqual(profile.refinement(texts,segments,50,{'seconds_per_character':.08,'observations':50})['ids'],[])


if __name__=='__main__':unittest.main()
