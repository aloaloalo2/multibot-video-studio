"""CapCut's whooshes, shutters and glitches among the transition sounds (user, 25 November 2026: «ці SFX капкати…
скопіюй і в звуки переходів… звук вух або звук затвору камери»)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sound_settings


@unittest.skipUnless(sound_settings.capcut_transitions(), "CapCut trending sounds are not on this Mac")
class CapcutTransitionSounds(unittest.TestCase):
    def test_they_are_offered_after_the_studios_own_and_chosen_by_key(self):
        catalog = sound_settings.transition_catalog()
        studio = [row for row in catalog if row['source_group'] == 'studio']
        capcut = [row for row in catalog if row['source_group'] == 'capcut']
        self.assertEqual([row['id'] for row in studio], [key for key, _ in sound_settings.TRANSITIONS])
        self.assertTrue(capcut and all(row['name'] == 'tr_' + row['id'] and row['preview_url'] for row in capcut))
        self.assertLess(catalog.index(studio[-1]), catalog.index(capcut[0]))
        key = capcut[0]['id']
        sound = {'transitions': {'enabled': True, 'styles': ['air', key]}}
        self.assertEqual(sound_settings.transition_names(sound), ['tr_air', 'tr_' + key])
        self.assertEqual(sound_settings.transition_names({'transitions': {'enabled': False, 'styles': [key]}}), [])

    def test_only_seam_sounds_were_chosen(self):
        labels = [row['label'] for row in sound_settings.capcut_transitions().values()]
        for unwanted in ('Павич', 'Кумедний', 'Діти кричать', 'Друк на клавіатурі'):
            self.assertFalse(any(unwanted in label for label in labels), unwanted)


if __name__ == '__main__':
    unittest.main()
