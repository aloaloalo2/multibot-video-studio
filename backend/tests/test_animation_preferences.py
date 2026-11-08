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
