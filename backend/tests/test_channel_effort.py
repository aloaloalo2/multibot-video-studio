import unittest
from pathlib import Path
from unittest.mock import patch
import store
import production
import agent_view

class ChannelEffortTest(unittest.TestCase):
    def test_saved_effort_and_high_default(self):
        project={"channel_id":"channel"}
        with patch.object(store,"get_channel_folder",return_value=Path('/tmp')):
            for value in ['low','medium','high','xhigh']:
                with patch.object(store,'read_json',return_value={'claude_effort':value}):
                    self.assertEqual(store.channel_effort(project),value)
            with patch.object(store,'read_json',return_value={}):
                self.assertEqual(store.channel_effort(project),'high')
            for value in ['wrong',False,{}]:
                with self.assertRaises(store.StudioError):
                    store.validate_settings({'weights':{'stock_photo':100},'claude_effort':value})

    def test_universal_brief_exposes_both_asset_modes(self):
        with patch.object(store,'get_channel_folder',return_value=Path('/tmp')):
            for enabled,expected in [(True,'PNG-предмети'),(False,'малюй кодом')]:
                with patch.object(store,'read_json',return_value={'animation':{'assets':enabled}}):
                    self.assertIn(expected,production.mixed_assets_step({'channel_id':'channel'}))

    def test_active_recognition_and_direction_are_reported_to_sidebar(self):
        with patch.object(store,'project_dir',return_value=Path('/tmp')),patch.object(store,'listed_project',return_value={'id':'project','name':'Project','channel_id':'channel'}),patch.object(store,'list_channels',return_value=[{'id':'channel','name':'Channel'}]):
            active=agent_view.studio_status([],lambda pid:{'розпізнавання озвучки':'running','режисура':'queued'},{'project'})
            self.assertEqual(active['active_channels'],['channel'])
            self.assertEqual({task['kind'] for task in active['activities']},{'розпізнавання озвучки','режисура'})
            done=agent_view.studio_status([],lambda pid:{'режисура':'done'},{'project'})
            self.assertEqual(done['activities'],[])
            self.assertEqual(done['active_channels'],[])
