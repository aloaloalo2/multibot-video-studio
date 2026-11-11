import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import narration_sequence as sequence
import store


class NarrationSequenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        p = patch.object(store, 'project_dir', return_value=self.folder)
        p.start();self.addCleanup(p.stop)
        self.root = self.folder / 'narration';self.root.mkdir()
        self.script = 'First complete sentence. Second complete sentence.'
        self.rows = []
        for i, text in enumerate(['First complete sentence.', 'Second complete sentence.']):
            key = hashlib.sha256(text.encode()).hexdigest()
            subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-f', 'lavfi', '-i',
                            f'sine=frequency={440+i*110}:duration=0.3', str(self.root/(key+'.mp3'))], check=True)
            self.rows.append({'key': key, 'text': text})
        (self.root/'concat.txt').write_text('\n'.join("file '"+r['key']+".mp3'" for r in self.rows))
        self.baseline = self.root/'speed-original.mp3'
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-f', 'concat', '-safe', '0', '-i',
                        str(self.root/'concat.txt'), '-c', 'copy', str(self.baseline)], check=True, capture_output=True)
        self.audio = self.folder/'voice.mp3';shutil.copyfile(self.baseline,self.audio)
        self.project = {'id': '1'*24}
        self.asset = {'id': 'voice', 'path': str(self.audio), 'narration_ending': {
            'source_sha256': store.audio_fingerprint(self.baseline), 'sha256': store.audio_fingerprint(self.audio)}}
        store.atomic_json(self.root/'job.json', {'status':'done','asset_id':'voice','script':self.script})
        store.atomic_json(self.root/'phrases.json', self.rows)

    def test_exact_assembly_is_verified_and_reused_without_another_render(self):
        proof = sequence.verify(self.project,self.asset,self.script)
        self.assertEqual(proof['sentences'],2)
        with patch.object(sequence.subprocess,'run',side_effect=AssertionError('reuse local proof')):
            self.assertEqual(sequence.verify(self.project,self.asset,self.script),proof)

    def prepare_ended_audio(self, ratio=1.):
        source = self.baseline
        job = store.read_json(self.root/'job.json');job['speed'] = ratio
        store.atomic_json(self.root/'speed-original.json', {'speed': 1.})
        if ratio != 1.:
            source = self.folder/'paced.mp3'
            subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-i', str(self.baseline), '-af',
                            f'atempo={ratio:.6f}', '-b:a', '128k', str(source)], check=True, capture_output=True)
            job['tempo_derivation'] = {'baseline_sha256': store.audio_fingerprint(self.baseline),
                'source_sha256': store.audio_fingerprint(source), 'speed': ratio, 'baseline_speed': 1.}
        store.atomic_json(self.root/'job.json', job)
        self.audio = self.folder/'ended.flac'
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-i', str(source),
                        '-af', 'apad=pad_dur=1.5', '-c:a', 'flac', str(self.audio)], check=True, capture_output=True)
        duration = store.media_duration(self.audio)
        self.asset.update(path=str(self.audio), duration=duration, narration_ending={
            'source_sha256': store.audio_fingerprint(source), 'sha256': store.audio_fingerprint(self.audio),
            'speech_duration': round(duration - 1.5, 3)})
        return duration

    def test_measured_take_boundaries_exclude_closing_pause_and_reuse_their_proof(self):
        for ratio in (1., .9, 1.05):
            with self.subTest(ratio=ratio):
                duration = self.prepare_ended_audio(ratio)
                proof = sequence.verify(self.project, self.asset, self.script)
                self.assertEqual(proof['version'], 2)
                spans = proof['sentence_timings']
                self.assertEqual(len(spans), 2)
                self.assertEqual(spans[0]['start'], 0)
                self.assertEqual(spans[0]['end'], spans[1]['start'])
                self.assertAlmostEqual(spans[-1]['end'], duration - 1.5, places=3)
                with patch.object(sequence.subprocess, 'run', side_effect=AssertionError('reuse measured boundary proof')):
                    self.assertEqual(sequence.verify(self.project, self.asset, self.script), proof)

    def test_recognition_spelling_missing_words_or_false_overlap_cannot_reject_proven_takes(self):
        duration = self.prepare_ended_audio()
        proof = sequence.verify(self.project, self.asset, self.script)
        cut = proof['sentence_timings'][1]['start']
        words = [{'text': 'Misrecognized', 'start': 0., 'end': cut + .02, 'probability': .2},
                 {'text': 'Second', 'start': cut + .04, 'end': cut + .09, 'probability': .99}]
        report = sequence.align(self.script, words, duration, proof)
        self.assertEqual(report['status'], 'matched')
        self.assertEqual(report['matched_phrases'], 2)
        self.assertEqual([w['text'] for w in report['aligned_words']], self.script.split())
        for word in report['aligned_words']:
            span = proof['sentence_timings'][word['sentence'] - 1]
            self.assertGreaterEqual(word['start'], span['start'])
            self.assertLessEqual(word['end'], span['end'])
            self.assertGreater(word['end'], word['start'])
        self.assertTrue(report['phrases'][0]['recognition_issues'])
        self.assertTrue(any(w['estimated'] for w in report['aligned_words']))

    def test_unknown_audio_or_resegmented_script_cannot_use_take_boundaries(self):
        self.assertIsNone(sequence.align(self.script, [], 3, None))
        self.assertIsNone(sequence.verify(self.project, self.asset, self.script.replace('. Second', ', second')))

    def test_modified_script_asset_or_audio_never_gets_trusted(self):
        self.assertIsNone(sequence.verify(self.project,self.asset,self.script.replace('First','Wrong')))
        self.assertIsNone(sequence.verify(self.project,{**self.asset,'id':'different'},self.script))
        self.audio.write_bytes(b'changed voice')
        self.assertIsNone(sequence.verify(self.project,self.asset,self.script))

    def test_swapping_takes_cannot_reuse_a_previous_order_receipt(self):
        self.assertTrue(sequence.verify(self.project,self.asset,self.script))
        a,b=[self.root/(r['key']+'.mp3') for r in self.rows]
        first,second=a.read_bytes(),b.read_bytes();a.write_bytes(second);b.write_bytes(first)
        self.assertIsNone(sequence.verify(self.project,self.asset,self.script))

    def test_missing_take_or_changed_concat_list_falls_back_to_normal_recognition(self):
        (self.root/'concat.txt').write_text('wrong order')
        self.assertIsNone(sequence.verify(self.project,self.asset,self.script))
        (self.root/'concat.txt').write_text('\n'.join("file '"+r['key']+".mp3'" for r in self.rows))
        (self.root/(self.rows[0]['key']+'.mp3')).unlink()
        self.assertIsNone(sequence.verify(self.project,self.asset,self.script))

    def test_local_speed_derivation_keeps_the_original_order_proof(self):
        subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-i',str(self.baseline),'-af','atempo=1.05',str(self.audio)],check=True,capture_output=True)
        changed=store.audio_fingerprint(self.audio)
        self.asset['narration_ending'].update(sha256=changed,source_sha256=changed)
        store.atomic_json(self.root/'speed-original.json',{'speed':1.})
        job=store.read_json(self.root/'job.json')
        job.update(speed=1.05,tempo_derivation={'baseline_sha256':store.audio_fingerprint(self.baseline),
                   'source_sha256':changed,'speed':1.05,'baseline_speed':1.})
        store.atomic_json(self.root/'job.json',job)
        self.assertTrue(sequence.verify(self.project,self.asset,self.script))
        job['tempo_derivation']['baseline_sha256']='unrelated recording'
        store.atomic_json(self.root/'job.json',job)
        self.assertIsNone(sequence.verify(self.project,self.asset,self.script))

    def test_legacy_tempo_is_rebuilt_exactly_then_reused_without_changing_the_job(self):
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-i', str(self.baseline),
                        '-af', 'atempo=1.050000', '-b:a', '128k', str(self.audio)], check=True, capture_output=True)
        changed = store.audio_fingerprint(self.audio)
        self.asset['narration_ending'].update(sha256=changed, source_sha256=changed)
        store.atomic_json(self.root/'speed-original.json', {'speed': 1.})
        job = store.read_json(self.root/'job.json');job['speed'] = 1.05
        store.atomic_json(self.root/'job.json', job)
        self.assertTrue(sequence.verify(self.project, self.asset, self.script))
        self.assertEqual(store.read_json(self.root/'job.json'), job)
        with patch.object(sequence.subprocess, 'run', side_effect=AssertionError('reuse both byte proofs')):
            self.assertTrue(sequence.verify(self.project, self.asset, self.script))
        job['speed'] = 1.02;store.atomic_json(self.root/'job.json', job)
        self.assertIsNone(sequence.verify(self.project, self.asset, self.script))

    def test_legacy_tempo_rejects_missing_metadata_and_an_unrelated_recording(self):
        self.audio.write_bytes(b'unrelated audio')
        changed = store.audio_fingerprint(self.audio)
        self.asset['narration_ending'].update(sha256=changed, source_sha256=changed)
        job = store.read_json(self.root/'job.json');job['speed'] = 1.05
        store.atomic_json(self.root/'job.json', job)
        self.assertIsNone(sequence.verify(self.project, self.asset, self.script))
        store.atomic_json(self.root/'speed-original.json', {'speed': 1.})
        self.assertIsNone(sequence.verify(self.project, self.asset, self.script))
        self.assertFalse((self.root/'tempo-verification.json').exists())
