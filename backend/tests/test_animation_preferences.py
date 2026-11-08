import unittest
from unittest.mock import patch
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import animation_preferences as pref
import production
import director

class AnimationPreferencesTest(unittest.TestCase):
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
