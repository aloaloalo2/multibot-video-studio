"""Every film its own score, inside its channel's own music (user, 26 November 2026)."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.tests import test_backend as support  # noqa: F401  (sys.path)
import sound_settings
import soundtrack
import store


class MusicPickTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patches = [patch.object(store, 'DATA_ROOT', self.root), patch.object(store, 'project_dir', lambda pid: self.root / 'projects' / pid)]
        for p in self.patches:
            p.start()
        self.module = sound_settings.audio_module('music')

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def pick(self, pid, channel='c1'):
        (self.root / 'projects' / pid).mkdir(parents=True, exist_ok=True)
        return soundtrack.music_pick({'id': pid, 'channel_id': channel}, self.module)

    def test_films_of_a_channel_vary_inside_its_kit_and_never_repeat_the_last(self):
        kit = soundtrack.music_kit('c1', self.module)
        picks = [self.pick(f'{n:024d}') for n in range(6)]
        for pick in picks:
            self.assertIn(pick['style'], kit['styles'])
            self.assertIn(pick['mood'], kit['moods'])
            self.assertIn(pick['key'], kit['keys'])
        for a, b in zip(picks, picks[1:]):
            self.assertNotEqual((a['style'], a['mood']), (b['style'], b['mood']))
        self.assertEqual(len({p['seed'] for p in picks}), 6)
        self.assertEqual(self.pick(f'{0:024d}'), picks[0])   # laid again, the same score

    def test_another_channel_leads_with_another_sound(self):
        first = soundtrack.music_kit('c1', self.module)
        second = soundtrack.music_kit('c2', self.module)
        self.assertNotEqual(first['styles'][0], second['styles'][0])
        self.assertFalse(set(first['styles']) & set(second['styles']))

    def test_the_intensity_has_a_peak_and_stays_under_the_voice(self):
        arc = soundtrack.music_arc(16, 1234)
        self.assertTrue(all(.22 <= x <= .42 for x in arc))
        top = arc.index(max(arc))
        self.assertTrue(4 <= top <= 14)
        self.assertNotEqual(arc, soundtrack.music_arc(16, 99))
