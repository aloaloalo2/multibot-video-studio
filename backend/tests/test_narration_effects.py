from array import array
import hashlib
import math
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import wave

import store
import narration_effects as effects
import channel_voice_lab as lab


class NarrationEffectsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        p=patch.object(store,'DATA_ROOT',self.root/'studio');p.start();self.addCleanup(p.stop)

    def test_validation_and_disabled_defaults(self):
        self.assertEqual(effects.identity(None),'')
        for value in (False,[],{'enabled':'yes'},{'preset':'unknown'},{'amount':float('nan')},{'amount':True},{'amount':101}):
            with self.assertRaises(store.StudioError):effects.normalize(value)
        for value in (True,[],{'enabled':1},{'amount':-1},{'amount':float('inf')}):
            with self.assertRaises(store.StudioError):effects.noise_options(value)
        self.assertEqual(effects.identity({'enabled':False,'preset':'hall'}),'')
        self.assertNotEqual(effects.identity(None,{'enabled':True}),effects.identity({'enabled':True}))

    def test_effects_never_change_paid_request_or_original_cache_identity(self):
        base=lab.validated({});ref={'sha256':'voice'}
        changed=lab.validated({**base,'reverb':{'enabled':True},'room_noise':{'enabled':True}})
        self.assertEqual(lab.fingerprint(base,ref),lab.fingerprint(changed,ref))
        self.assertEqual(lab.original_path(base,ref),lab.original_path(changed,ref))
        self.assertEqual(lab.sample_fingerprint(base,ref),lab.sample_fingerprint(changed,ref))
        self.assertEqual(lab.sample_fingerprint(base,ref),lab.fingerprint(base,ref))

    def test_four_spaces_are_distinct_and_cached_inside_studio(self):
        digests=[]
        for preset in effects.PRESETS:
            path=effects.impulse(preset);digests.append(hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertTrue(path.is_relative_to(store.DATA_ROOT))
            before=path.stat().st_mtime_ns
            self.assertEqual(effects.impulse(preset).stat().st_mtime_ns,before)
            with wave.open(str(path),'rb') as wav:
                self.assertEqual(wav.getnchannels(),2)
                self.assertEqual(wav.getframerate(),48000)
        self.assertEqual(len(set(digests)),4)
        with self.assertRaises(store.StudioError):effects.impulse('../elsewhere')

    def test_four_room_recordings_are_distinct_and_loopable(self):
        digests=[]
        for preset in effects.NOISE_PRESETS:
            path=effects.microphone_noise(preset);digests.append(hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(effects.microphone_noise(preset),path)
            with wave.open(str(path),'rb') as wav:
                pcm=array('h');pcm.frombytes(wav.readframes(wav.getnframes()))
                self.assertGreater(wav.getnframes()/wav.getframerate(),10)
                self.assertLess(abs(pcm[0]-pcm[-1]),5000)
        self.assertEqual(len(set(digests)),4)
        with self.assertRaises(store.StudioError):effects.microphone_noise('../other')

    def test_real_render_keeps_duration_and_room_noise_is_quiet(self):
        source=self.root/'original.wav'
        samples=array('h',(round(8000*math.sin(2*math.pi*330*i/48000)) if i<4800 else 0 for i in range(76800)))
        with wave.open(str(source),'wb') as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(48000);wav.writeframes(samples.tobytes())
        before=source.read_bytes()
        for preset in effects.PRESETS:
            target=self.root/(preset+'.flac')
            effects.render(source,{'enabled':True,'preset':preset,'amount':75},target)
            self.assertAlmostEqual(store.media_duration(target),1.6,places=3)
            raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(target),'-ac','1','-f','f32le','-'])
            decoded=array('f');decoded.frombytes(raw)
            self.assertGreater(max(abs(v) for v in decoded[5000:7000]),.0001)
            self.assertLess(max(abs(v) for v in decoded),.98)
        target=self.root/'noise.flac'
        effects.render(source,None,target,{'enabled':True,'amount':100})
        raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(target),'-ac','1','-f','f32le','-'])
        decoded=array('f');decoded.frombytes(raw)
        rms=math.sqrt(sum(v*v for v in decoded[24000:48000])/24000)
        self.assertGreater(rms,.015);self.assertLess(rms,.06)
        self.assertEqual(source.read_bytes(),before)

    def test_background_gain_ranges_from_quiet_to_audible_without_amplifying_the_voice(self):
        self.assertAlmostEqual(20*math.log10(effects.noise_gain({'amount':35})*.1),-49.5)
        self.assertAlmostEqual(20*math.log10(effects.noise_gain({'amount':100})*.1),-30)
        self.assertEqual(effects.noise_gain({'amount':0}),0)

    def test_effect_only_sample_reuses_a_paid_original(self):
        # No synthesis/clone transport is reachable when the original is cached.
        settings=lab.validated({'reverb':{'enabled':True},'room_noise':{'enabled':True}})
        ref={'sha256':'voice'};source=lab.original_path(settings,ref)
        source.parent.mkdir(parents=True);source.write_bytes(b'original')
        with patch.object(lab,'synthesis') as paid,patch.object(lab,'paced_audio',return_value=b'original'):
            self.assertEqual(lab.eleven_local_synthesis('unused','voice',settings,ref),b'original')
            paid.assert_not_called()

    def test_saved_reverb_matches_browser_impulse_gain_and_timing(self):
        source=self.root/'pulse.wav'
        pcm=array('h',[12000]+[0]*95999)
        with wave.open(str(source),'wb') as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(48000);wav.writeframes(pcm.tobytes())
        ir=effects.impulse('office')
        with wave.open(str(ir),'rb') as wav:
            coefficients=array('h');coefficients.frombytes(wav.readframes(wav.getnframes()))
        at=max(range(0,len(coefficients),2),key=lambda i:abs(coefficients[i]))
        target=self.root/'convolution.flac'
        effects.render(source,{'enabled':True,'preset':'office','amount':100},target)
        raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(target),'-ac','2','-f','f32le','-'])
        rendered=array('f');rendered.frombytes(raw)
        expected=(12000/32768)*effects.gains({'preset':'office','amount':100})[1]*(coefficients[at]/32768)
        self.assertAlmostEqual(rendered[at],expected,delta=.00003)

    def test_doctor_office_is_diffuse_short_and_keeps_the_direct_voice_dominant(self):
        import numpy as np
        with wave.open(str(effects.impulse('office')),'rb') as wav:
            rate=wav.getframerate();ir=np.frombuffer(wav.readframes(wav.getnframes()),'<i2').reshape(-1,2)/32768
        power=np.sum(ir*ir,axis=1);energy=float(sum(power))
        self.assertTrue(np.all(ir[:round(rate*.006)]==0))
        self.assertLess(float(sum(power[round(rate*.12):]))/energy,.003)
        # No isolated millisecond may dominate the reflected room response.
        self.assertLess(max(np.convolve(power,np.ones(48),'valid'))/energy,.20)
        dry,wet=effects.gains({'preset':'office','amount':25})
        self.assertGreater(dry,.99);self.assertLess(wet,.035)
        self.assertLessEqual(effects.gains({'preset':'office','amount':100})[1],.10)
