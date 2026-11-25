"""The sound passes do the same work faster (25 November 2026): one effects bed for the language mix, a catalogue read
once, peaks and measures kept, library effects cloned instead of copied, waveforms at the timeline's detail."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np

import audio_level
import language_mix
import sfx_library
import sound_settings
import soundtrack
import store
import waveforms


def tone(path, seconds, freq, rate=48000, channels=1):
    t = np.arange(int(seconds * rate)) / rate
    data = (np.sin(2 * np.pi * freq * t) * .3 * 32767).astype('<i2')
    if channels == 2:
        data = np.repeat(data[:, None], 2, axis=1)
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(channels); out.setsampwidth(2); out.setframerate(rate)
        out.writeframes(data.tobytes())


def pcm(path):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(path), '-f', 'f32le', '-ac', '2', '-ar', '48000', '-'],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, '<f4').reshape(-1, 2)


@unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg needed')
class EffectsBedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        tone(self.root / 'voice.wav', 6, 300)
        tone(self.root / 'click.wav', .4, 1200, rate=44100)
        tone(self.root / 'whoosh.wav', 1.2, 700, channels=2)
        tracks = [{'source': str(self.root / 'voice.wav'), 'start': 0, 'trim_start': 0, 'duration': 6, 'volume': 1, 'voice': True}]
        for n in range(14):   # overlapping, trimmed, quiet and loud, one past the film's end
            name = 'click.wav' if n % 2 else 'whoosh.wav'
            tracks.append({'source': str(self.root / name), 'start': .37 * n, 'trim_start': .05 * (n % 3),
                           'duration': .3 if n % 2 else 1.1, 'volume': .07 * (1 + n % 4), 'voice': False})
        tracks.append({'source': str(self.root / 'whoosh.wav'), 'start': 5.6, 'trim_start': 0, 'duration': 1.2, 'volume': .5, 'voice': False})
        self.snap = {'tracks': tracks, 'duration': 6.0}

    def test_a_bed_mixes_the_same_sound_as_every_effect_its_own_input(self):
        plain, bedded, bed = self.root / 'plain.mp3', self.root / 'bed.mp3', self.root / 'sfx.flac'
        subprocess.run(language_mix.ffmpeg_command(self.snap, plain), check=True, capture_output=True)
        short = [t for t in self.snap['tracks'] if language_mix._short(t)]
        self.assertEqual(len(short), 15)
        language_mix.write_bed(short, self.snap['duration'], bed)
        command = language_mix.ffmpeg_command(self.snap, bedded, bed)
        self.assertEqual(command.count('-i'), 3)   # the voice, the bed and the silence under them
        subprocess.run(command, check=True, capture_output=True)
        a, b = pcm(plain), pcm(bedded)
        self.assertEqual(len(a), len(b))
        self.assertGreater(float(np.sqrt(np.mean(a ** 2))), .1)
        self.assertLess(float(np.sqrt(np.mean((a - b) ** 2))), 2e-3)   # MP3 of the same samples
        self.assertEqual(len(self.snap['tracks']), 16)                  # the snapshot itself is left as it was

    def test_save_uses_the_bed(self):
        calls = []
        def run(command, what):
            calls.append(command)
            subprocess.run(command, check=True, capture_output=True)
        snap = {**self.snap, 'destination': self.root / 'Мови' / 'uk' / 'mix.mp3', 'signature': 's'}
        with patch.object(language_mix, 'snapshot', return_value=snap), patch.object(store, 'load_project', return_value={}), \
                patch('languages.run', side_effect=run), patch('languages.progress'), patch('languages.update'), \
                patch('languages.work_dir', return_value=self.root / 'work'):
            language_mix.save('p', 'uk', {})
        self.assertEqual(calls[0].count('-i'), 3)
        self.assertAlmostEqual(store.media_duration(snap['destination']), 6, delta=.06)


class CatalogueTest(unittest.TestCase):
    def test_the_catalogue_is_read_again_only_when_its_folder_changes(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(sfx_library, 'ROOT', Path(tmp)):
            root = Path(tmp)
            tone(root / '1.wav', .2, 500)
            (root / 'catalog.json').write_text(json.dumps([{'mixkit_id': '1', 'label': 'A', 'category': 'appear', 'duration_seconds': .2},
                                                           {'mixkit_id': '2', 'label': 'B', 'category': 'appear', 'duration_seconds': .2}]))
            self.assertEqual([r['mixkit_id'] for r in sfx_library.catalog()], ['1'])
            with patch.object(json, 'loads', side_effect=AssertionError('read again')):
                sfx_library.catalog(); sfx_library.find(str(root / '1.wav'))
            tone(root / '2.wav', .2, 600)   # a file added: read again
            self.assertEqual([r['mixkit_id'] for r in sfx_library.catalog()], ['1', '2'])
            sfx_library.catalog()[0]['label'] = 'changed'   # callers get their own rows
            self.assertEqual(sfx_library.find(str(root / '1.wav'))['label'], 'A')
            (root / '2.wav').unlink()
            self.assertIsNone(sfx_library.find(str(root / '2.wav')))


@unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg needed')
class PeakAndCopyTest(unittest.TestCase):
    def test_the_peak_is_the_kits_and_kept_on_disk(self):
        module = sound_settings.audio_module('sfx')
        samples = np.zeros((48000, 2), np.float32); samples[30000:31000] = .5
        self.assertEqual(soundtrack.peak_time(samples), module.peak_time(samples))
        with tempfile.TemporaryDirectory() as tmp, patch.object(store, 'DATA_ROOT', Path(tmp)), \
                patch.object(soundtrack, '_PEAKS', {}), patch.object(soundtrack, '_PEAKS_LOADED', False):
            path = Path(tmp) / 'hit.wav'
            module.write_wav(str(path), samples)
            peak = soundtrack._peak(path)
            self.assertAlmostEqual(peak, module.peak_time(samples), delta=.001)
            soundtrack._PEAKS.clear(); soundtrack._PEAKS_LOADED = False   # a new start of the studio
            with patch.object(subprocess, 'run', side_effect=AssertionError('decoded again')):
                self.assertEqual(soundtrack._peak(path), peak)

    def test_a_library_effect_is_the_levelled_file_cloned_into_the_project(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(store, 'DATA_ROOT', Path(tmp) / 'data'):
            root = Path(tmp) / 'lib'; root.mkdir()
            tone(root / '77.wav', .5, 900)
            row = {'mixkit_id': '77', 'name': str(root / '77.wav')}
            folder = Path(tmp) / 'project'; folder.mkdir()
            path, shared = soundtrack._library_copy(folder, row)
            self.assertEqual(shared, sfx_library.leveled_path(row))
            self.assertEqual(path.read_bytes(), shared.read_bytes())
            self.assertEqual([p.name for p in folder.iterdir()], [path.name])   # no part file left
            with patch.object(Path, 'read_bytes', side_effect=AssertionError('hashed again')):
                self.assertEqual(soundtrack._library_copy(folder, row), (path, shared))


class MeasureCacheTest(unittest.TestCase):
    def test_measures_are_parsed_once_and_again_after_the_file_changed(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(audio_level, 'CACHE', Path(tmp) / 'levels.json'):
            sound = Path(tmp) / 'a.wav'; tone(sound, .5, 400)
            key = audio_level._key(sound)
            store.atomic_json(audio_level.CACHE, {key: {'lufs': -20.0, 'peak': -3.0}})
            self.assertEqual(audio_level.measure(sound)['lufs'], -20.0)
            with patch.object(store, 'read_json', side_effect=AssertionError('parsed again')):
                self.assertEqual(audio_level.measure(sound)['lufs'], -20.0)
            store.atomic_json(audio_level.CACHE, {key: {'lufs': -18.5, 'peak': -3.0}})
            self.assertEqual(audio_level.measure(sound)['lufs'], -18.5)


@unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg needed')
class WaveformTest(unittest.TestCase):
    def test_a_short_effect_has_at_most_a_thousand_points_a_second(self):
        with tempfile.TemporaryDirectory() as tmp:
            tone(Path(tmp) / 'fx.wav', 2, 500)
            data = waveforms.read_peaks(Path(tmp) / 'fx.wav', Path(tmp) / 'cache')
            self.assertLessEqual(len(data['peaks']), 2000)
            self.assertEqual(data['samples_per_bin'], 48)
            self.assertAlmostEqual(max(p[1] for p in data['peaks']), .3, delta=.01)


if __name__ == '__main__':
    unittest.main()
