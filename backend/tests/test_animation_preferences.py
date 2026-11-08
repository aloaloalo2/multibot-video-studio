import unittest
import inspect
from unittest.mock import patch
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import animation_preferences as pref
import production
import director

class AnimationPreferencesTest(unittest.TestCase):
    def test_real_people_preference_applies_to_both_animation_formats_and_asset_modes(self):
        for people in ['real','real_older','stickman']:
            for enabled in [True,False]:
                with patch.object(pref.store,'get_channel_folder',return_value=Path('/tmp/channel')),patch.object(pref.store,'read_json',return_value={'people_style':people,'animation':{'assets':enabled}}):
                    for planning in [True,False]:
                        for kind in ['regular','animated']:
                            text=pref.instructions({'channel_id':'test','project_kind':kind},planning=planning)
                            self.assertIn('композиційний центр',text)
                            self.assertIn('Спокійний показ для читання допустимий',text)
                            self.assertIn('Повторно перевіряй тільки змінені',text)
                            self.assertEqual('Стікмени, дудли й мультяшні ведучі заборонені' in text,kind=='regular')

    def test_universal_brief_does_not_require_pointless_continuous_motion(self):
        self.assertNotIn('жодної секунди без руху',inspect.getsource(production.photo_brief))
        self.assertNotIn('Кадр без руху є помилкою',production.PHOTO_STYLE_WISH)
        self.assertIn('читабельну спокійну фазу',production.PHOTO_STYLE_WISH)
        self.assertLess(len(production.QUALITY),3000)

    def test_both_agents_get_the_same_two_format_png_requirement(self):
        project={'channel_id':'test'}
        with patch.object(pref.store,'get_channel_folder',return_value=Path('/tmp/channel')),patch.object(pref.store,'read_json',return_value={'animation':{'assets':True}}):
            text=pref.instructions(project,planning=True)
            self.assertIn('обов’язкова',text)
            self.assertIn('animation',text);self.assertIn('razgon_2d',text)
            self.assertIn('лише запиши',text)
            self.assertIn('kind=image',production.mixed_assets_step(project))
        with patch.object(pref.store,'get_channel_folder',return_value=Path('/tmp/channel')),patch.object(pref.store,'read_json',return_value={'animation':{'assets':False}}):
            self.assertIn('вимкнені',production.mixed_assets_step(project))

    def test_stable_readable_text_rules_reach_both_asset_modes(self):
        for enabled in [True,False]:
            with patch.object(pref.store,'get_channel_folder',return_value=Path('/tmp/channel')),patch.object(pref.store,'read_json',return_value={'animation':{'assets':enabled}}):
                for planning in [True,False]:
                    brief=pref.instructions({'channel_id':'test'},planning=planning)
                    self.assertIn('Заголовки закріплюй',brief)
                    self.assertIn('разом із цим предметом',brief)
                    self.assertIn('Тінь або сяйво не додавай',brief)
