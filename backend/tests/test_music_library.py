"""The music library: the channel's ticked tracks laid by the film's moments (user, 26 November 2026)."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.tests import test_backend as support  # noqa: F401  (sys.path)
import music_library
import store


class MusicLibraryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patches = [patch.object(store, 'DATA_ROOT', self.root), patch.object(store, 'project_dir', lambda pid: self.root / 'projects' / pid)]
        for p in self.patches:
            p.start()
        files = self.root / 'music-library' / 'files'
        files.mkdir(parents=True)
        rows = []
        for n, (cat, freq) in enumerate([('спокійна', 220), ('спокійна', 330), ('драйвова', 440), ('сумна', 550)]):
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'sine=f={freq}:d=20', '-ac', '2', '-ar', '48000', str(files / f't{n}abcdef.mp3')], check=True)
            rows.append({'id': f't{n}abcdef', 'title': f'T{n}', 'artist': 'A', 'category': cat, 'file': f'files/t{n}abcdef.mp3', 'seconds': 20, 'lufs': -20})
        (self.root / 'music-library' / 'catalog.json').write_text(json.dumps(rows))
        self.project = {'id': 'p' * 24, 'channel_id': 'c1'}
        (self.root / 'projects' / self.project['id']).mkdir(parents=True)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_only_ticked_tracks_without_voice(self):
        sound = {'music': {'tracks': ['t0abcdef', 't2abcdef', 'missing']}}
        self.assertEqual([r['id'] for r in music_library.selected(sound)], ['t0abcdef', 't2abcdef'])
        music_library.mark_vocals('t2abcdef', True)
        self.assertEqual([r['id'] for r in music_library.selected(sound)], ['t0abcdef'])

    def test_a_track_never_starts_over_inside_its_stretch(self):
        plan = {'frames': [{'start': float(i * 10), 'end': float(i * 10 + 10), 'music': 'спокійна' if i == 0 else ''} for i in range(4)]}
        segments = music_library.lay_out(self.project, plan, 40.0, music_library.catalog())
        tracks = [s['track'] for s in segments]
        self.assertNotEqual(tracks[0], tracks[2])   # each test track is 20 s: the third frame needs the next one
        self.assertTrue(all(s['from'] + (s['end'] - s['start']) <= 20 + 1e-6 for s in segments))

    def test_tracks_with_a_voice_leave_the_library(self):
        music_library.mark_vocals('t1abcdef', True)
        self.assertEqual(music_library.remove_vocal_tracks(), ['T1'])
        self.assertEqual([r['id'] for r in music_library.catalog()], ['t0abcdef', 't2abcdef', 't3abcdef'])
        self.assertFalse((self.root / 'music-library' / 'files' / 't1abcdef.mp3').exists())
        self.assertTrue((self.root / 'music-library' / 'files' / 't0abcdef.mp3').exists())

    def test_the_directors_marks_choose_tracks_levels_and_silence(self):
        plan = {'frames': [{'start': 0, 'end': 10, 'music': 'спокійна'}, {'start': 10, 'end': 20, 'music': 'тихіше'},
                           {'start': 20, 'end': 30, 'music': 'драйвова'}, {'start': 30, 'end': 40, 'music': 'тиша'},
                           {'start': 40, 'end': 50}]}
        tracks = music_library.catalog()
        seg = music_library.lay_out(self.project, plan, 50.0, tracks)
        self.assertEqual(seg[0]['track'], seg[1]['track'])          # one category, one track
        self.assertEqual(seg[1]['level'], music_library.LEVELS['тихіше'])
        self.assertNotEqual(seg[2]['track'], seg[1]['track'])       # a new category, a new track
        self.assertEqual(next(t for t in tracks if t['id'] == seg[2]['track'])['category'], 'драйвова')
        self.assertEqual(seg[3]['level'], 0.0)                      # no music there
        self.assertEqual(seg[4]['level'], 1.0)
        out = self.root / 'bed.flac'
        music_library.render(seg, 50.0, out)
        import numpy as np
        raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(out), '-f', 'f32le', '-ac', '1', '-ar', '48000', '-'], capture_output=True, check=True).stdout
        x = np.frombuffer(raw, '<f4')
        rms = lambda a, b: float(np.sqrt(np.mean(x[int(a * 48000):int(b * 48000)] ** 2)))
        self.assertLess(rms(33, 37), rms(23, 27) / 20)              # quiet in the silent stretch
        self.assertLess(rms(13, 17), rms(3, 7) * .8)                # «тихіше» is lower
        self.assertGreater(rms(43, 47), rms(33, 37) * 20)           # the music comes back

    def test_a_film_without_marks_uses_tracks_the_channel_did_not_just_play(self):
        tracks = music_library.catalog()
        first = music_library.lay_out(self.project, None, 120.0, tracks)
        music_library.remember(self.project, first)
        other = {'id': 'q' * 24, 'channel_id': 'c1'}
        (self.root / 'projects' / other['id']).mkdir(parents=True)
        second = music_library.lay_out(other, None, 120.0, tracks)
        self.assertNotEqual(first[0]['track'], second[0]['track'])
        self.assertEqual(music_library.credits(self.project), ['T' + first[0]['track'][1] + ', A'])
