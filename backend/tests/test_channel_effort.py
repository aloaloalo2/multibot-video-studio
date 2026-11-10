import unittest
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import store
import production
import agent_view

class ChannelEffortTest(unittest.TestCase):
    def test_model_setting_persists_without_overwriting_other_choices(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            store.atomic_json(folder/store.PLAN_CONFIG, {'weights': {'stock_photo': 100}, 'claude_effort': 'xhigh'})
            with patch.object(store, 'get_channel_folder', return_value=folder), \
                    patch.object(store, 'channel_record', side_effect=lambda f: store.read_json(f/store.PLAN_CONFIG, {})):
                saved = store.update_channel_settings('channel', {'director_model': 'claude-fable-5-2'})
                self.assertEqual(saved['director_model'], 'claude-fable-5-2')
                self.assertEqual(saved['claude_effort'], 'xhigh')
                self.assertEqual(store.channel_director_model({'channel_id': 'channel'}), 'claude-fable-5-2')
                self.assertEqual(store.channel_effort({'channel_id': 'channel'}), 'xhigh')

    def test_director_model_is_saved_validated_and_channel_scoped(self):
        project = {"channel_id": "channel"}
        with patch.object(store, "get_channel_folder", return_value=Path('/tmp')) as folder:
            for model in store.DIRECTOR_MODELS:
                settings = {'weights': {'stock_photo': 100}, 'director_model': model}
                self.assertEqual(store.validate_settings(settings)['director_model'], model)
                with patch.object(store, 'read_json', return_value=settings):
                    self.assertEqual(store.channel_director_model(project), model)
            folder.assert_called_with('channel', include_disabled=True)
            for invalid in ['wrong', False, {}, None]:
                with self.assertRaises(store.StudioError):
                    store.validate_settings({'weights': {'stock_photo': 100}, 'director_model': invalid})
                with patch.object(store, 'read_json', return_value={'director_model': invalid}):
                    self.assertEqual(store.channel_director_model(project), store.DEFAULT_DIRECTOR_MODEL)
            with patch.object(store, 'read_json', return_value={}):
                self.assertEqual(store.channel_director_model(project), store.DEFAULT_DIRECTOR_MODEL)
        self.assertEqual(store.channel_director_model({}), store.DEFAULT_DIRECTOR_MODEL)

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
            for enabled,expected in [(True,'PNG асети'),(False,'малюй кодом')]:
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
