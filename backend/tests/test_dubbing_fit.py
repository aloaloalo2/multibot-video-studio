import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dubbing_fit
import languages

class DubbingFitTest(unittest.TestCase):
    def test_join_padding_counts_native_silence_with_tempo_and_edge_guards(self):
        edge={'leading':.035,'trailing':.035,'speed':.92}
        extra=dubbing_fit.join_gaps([{'edge_silence':edge},{'edge_silence':edge}])[0]
        self.assertAlmostEqual(extra,.05-2*(.035*.92/1.08-.01))
        self.assertEqual(dubbing_fit.join_gaps([{},{}]),[.05])
        for value in [None,-1,float('nan'),float('inf'),'1']:
            bad={'leading':value,'trailing':value,'speed':1.}
            self.assertEqual(dubbing_fit.join_gaps([{'edge_silence':bad}]*2),[.05])

    def test_boundary_measurement_preserves_signal_and_does_not_trust_silent_takes(self):
        import numpy as np
        signal=np.r_[np.zeros(50),np.full(800,.2),np.zeros(150)]
        original=signal.copy()
        self.assertEqual(dubbing_fit.quiet_edges(signal,1000),{'leading':.05,'trailing':.15,'speed':1.})
        self.assertTrue(np.array_equal(signal,original))
        for signal in [np.zeros(1000),np.array([]),np.array([float('nan')])]:
            self.assertEqual(dubbing_fit.quiet_edges(signal,1000)['trailing'],0.)

    @unittest.skipUnless(shutil.which('ffmpeg'),'ffmpeg needed')
    def test_real_cached_rebuild_avoids_double_pauses_and_keeps_every_complete_take(self):
        import hashlib
        import numpy as np
        import wave
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);rate=48000;items=[];hashes=[]
            for n in range(4):
                signal=np.r_[np.zeros(round(.06*rate)),
                             .2*np.sin(2*np.pi*(220+n*100)*np.arange(rate)/rate),
                             np.zeros(round(.06*rate))]
                path=folder/f'{n}.wav'
                with wave.open(str(path),'wb') as audio:
                    audio.setparams((1,2,rate,0,'NONE','not compressed'))
                    audio.writeframes((signal*32767).astype('<i2').tobytes())
                hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())
                items.append({'index':n,'file':path.name,'length':len(signal)/rate,
                              'start':n,'original_start':n,'original_end':n+1})
            total=4.28
            # Adding 50 ms again would reject this film even at the speed limit.
            with self.assertRaisesRegex(RuntimeError,'при межі 8%'):
                dubbing_fit.fitting_speeds(items,total)
            report=dubbing_fit.rebuild(folder,items,folder/'joined.mp3',total)
            fitted=report['phrases']
            self.assertEqual(len(fitted),4)
            self.assertAlmostEqual(languages.store.media_duration(folder/'joined.mp3'),total,delta=.05)
            self.assertLessEqual(fitted[-1]['end'],total)
            self.assertTrue(all(.92<=x['speed']<=1.08 for x in fitted))
            for a,b in zip(fitted,fitted[1:]):
                self.assertLessEqual(a['end'],b['start'])
                breath=a['edge_silence']['trailing']+b['edge_silence']['leading']+b['start']-a['end']
                self.assertGreaterEqual(breath,.05)
            self.assertEqual(hashes,[hashlib.sha256((folder/x['file']).read_bytes()).hexdigest() for x in items])

    def test_centres_free_time_and_borrows_neighbouring_gaps_without_overlap(self):
        solo=dubbing_fit.centered_schedule([{'start':0,'fitted_length':4}],10,gap=0)[0]
        self.assertEqual((solo['start'],10-solo['end']),(3,3))
        items=[{'start':0,'fitted_length':2},{'start':3,'fitted_length':4},{'start':5,'fitted_length':1}]
        placed=dubbing_fit.centered_schedule(items,10)
        self.assertGreaterEqual(placed[0]['start'],0)
        self.assertLessEqual(placed[-1]['end'],10)
        for a,b in zip(placed,placed[1:]):self.assertGreaterEqual(b['start']-a['end'],.04999)
        self.assertEqual([x['fitted_length'] for x in placed],[2,4,1])

    def test_keeps_all_takes_and_refuses_a_physically_impossible_fit(self):
        with self.assertRaisesRegex(RuntimeError,'Усі аудіофрагменти збережені'):
            dubbing_fit.centered_schedule([{'start':0,'fitted_length':11}],10)

    def test_review_names_the_exact_time_tempo_and_shift(self):
        result=dubbing_fit.review_items([
            {'index':0,'start':2,'end':4,'original_start':1,'speed':1.1,'text':'First'},
            {'index':1,'start':5,'end':8,'original_start':5,'speed':.9,'text':'Second'},
            {'index':2,'start':9,'end':10,'original_start':9,'speed':1,'text':'Third'}])
        self.assertEqual([(x['index'],x['start'],x['speed'],x['shift']) for x in result],[(0,2,1.1,1),(1,5,.9,0)])
    def test_bounded_fit_preserves_short_breath_and_does_not_stretch_into_next_line(self):
        self.assertEqual(dubbing_fit.fit_speed(5, 9, 8), .92)
        self.assertEqual(dubbing_fit.fit_speed(5, 9, 5.3), 1)
        self.assertEqual(dubbing_fit.fit_speed(5, 5.8, 8), .92)
        self.assertEqual(dubbing_fit.fit_speed(8, 5, 5), 1.08)

    def test_paid_takes_and_previous_voice_are_archived(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'parts').mkdir();(p/'parts/raw.mp3').write_bytes(b'paid take')
            (p/'voice.mp3').write_bytes(b'accepted');(p/'text.txt').write_text('words')
            languages.archive_voice_parts(p)
            history=next((p/'voice-history').iterdir())
            self.assertEqual((history/'parts/raw.mp3').read_bytes(),b'paid take')
            self.assertEqual((history/'voice.mp3').read_bytes(),b'accepted')
            self.assertEqual((p/'voice.mp3').read_bytes(),b'accepted')
            self.assertEqual((p/'text.txt').read_text(),'words')

    def test_uses_global_spare_time_without_exceeding_eight_percent(self):
        items=[{'start':0,'original_start':0,'original_end':6,'length':5.2},
               {'start':6,'original_start':6,'original_end':10,'length':5.2}]
        speeds=dubbing_fit.fitting_speeds(items,10.1)
        self.assertTrue(all(.92<=s<=1.08 for s in speeds))
        self.assertLessEqual(sum(x['length']/s for x,s in zip(items,speeds))+.05,10.1)
        with self.assertRaisesRegex(RuntimeError,'Усі аудіофрагменти збережені'):
            dubbing_fit.fitting_speeds(items,9)

    def test_forecast_safety_margin_does_not_reject_an_exact_fit(self):
        items=[{'start':0,'original_start':0,'original_end':10,'length':10.8}]
        self.assertEqual(dubbing_fit.fitting_speeds(items,10),[1.08])

    @unittest.skipUnless(shutil.which('ffmpeg'),'ffmpeg needed')
    def test_recovery_and_refit_keep_anchors_and_reduce_artificial_gap(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);rate=48000
            signal=np.zeros(rate*8,dtype='<f4')
            for a,b in [(0,2),(5,7)]:signal[a*rate:b*rate]=.2*np.sin(2*np.pi*220*np.arange((b-a)*rate)/rate)
            signal.tofile(p/'raw.f32')
            dubbing_fit.command(['-f','f32le','-ar',rate,'-ac',1,'-i',p/'raw.f32',p/'old.wav'])
            segs=[{'start':0,'end':4},{'start':5,'end':7}]
            m=dubbing_fit.recover(p/'old.wav',segs,p/'parts')
            r=dubbing_fit.rebuild(p/'parts',m,p/'new.mp3',8)
            self.assertGreater(r['phrases'][0]['start'],0)
            self.assertGreaterEqual(r['phrases'][1]['start'],5)
            self.assertLess(r['phrases'][0]['gap_after'],5-m[0]['length'])
            self.assertGreaterEqual(r['phrases'][0]['speed'],.92)
            self.assertLessEqual(r['phrases'][0]['speed'],1.08)
            self.assertLess(r['phrases'][0]['end'],5)
            self.assertTrue((p/'parts/00000.wav').exists())
            self.assertAlmostEqual(languages.store.media_duration(p/'new.mp3'),8,delta=.05)

    @unittest.skipUnless(shutil.which('ffmpeg'),'ffmpeg needed')
    def test_refuses_to_cut_continuous_speech_at_uncertain_boundary(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            dubbing_fit.command(['-f','lavfi','-i','sine=frequency=220:duration=4',p/'old.wav'])
            with self.assertRaisesRegex(RuntimeError,'No safe silence'):
                dubbing_fit.recover(p/'old.wav',[{'start':0,'end':2},{'start':2,'end':4}],p/'parts')
