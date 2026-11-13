import copy
import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sfx_library
import sound_settings
import store
import test_backend as fixtures


class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        with wave.open(str(self.root / '123.wav'), 'wb') as out:
            out.setnchannels(1); out.setsampwidth(2); out.setframerate(48000)
            out.writeframes(b'\x01\x00' * 24000)
        (self.root / 'catalog.json').write_text(json.dumps([{
            'mixkit_id': '123', 'label': 'Поява', 'category': 'appearance',
            'duration_seconds': .5, 'license': 'Mixkit Sound Effects Free License'}]))
        patcher = patch.object(sfx_library, 'ROOT', self.root)
        patcher.start(); self.addCleanup(patcher.stop)
        self.name = sfx_library.catalog()[0]['name']

    def test_category_controls_brief_and_mixer_allowlist_without_touching_story(self):
        sound = sound_settings.normalize({'effects': {'categories': ['appearance']}})
        self.assertIn(self.name, sound_settings.apply_config({}, sound, animated=True)['sfx']['allowed_names'])
        self.assertNotIn(self.name, sound_settings.apply_config({}, sound)['sfx']['allowed_names'])
        self.assertIn(self.name, sfx_library.instructions(sound))
        sound['effects']['enabled'] = False
        self.assertEqual(sfx_library.allowed(sound), [])
        story = {'sfx': [{'name': self.name, 't': 1}], 'shots': [
            {'start': 0, 'sfx': [{'name': self.name, 'at': 2}, {'name': 'pop', 'at': 3}]}]}
        original = copy.deepcopy(story)
        bed = sfx_library.without_library(story)
        self.assertEqual(bed['sfx'], [])
        self.assertEqual(bed['shots'][0]['sfx'], [{'name': 'pop', 'at': 3}])
        self.assertEqual(story, original)

    def test_automatic_story_handoff_uses_absolute_shot_time_and_original_file(self):
        from unittest.mock import Mock
        studio = Mock(); studio.project.return_value = {'revision': 7}
        count = sfx_library.place(studio, 'p', {'shots': [{'start': 12, 'sfx': [
            {'name': self.name, 'at': .25, 'gain': -12}]}]})
        self.assertEqual(count, 1)
        body = studio.call.call_args.args[2]
        self.assertEqual(body['expected_revision'], 7)
        self.assertEqual(body['ops'][0]['cues'], [{'name': self.name, 't': 12.25, 'dur': .5, 'gain': -12}])

    def test_individual_selection_controls_director_and_both_mixer_paths(self):
        import soundtrack
        from types import SimpleNamespace
        # Explicit library selection is independent of synthesized accent categories.
        selected = sound_settings.normalize({'effects': {'enabled': False}, 'library': {'enabled': True, 'ids': ['123', '999']}})
        self.assertEqual(sfx_library.allowed(selected), [self.name])
        config = sound_settings.apply_config({}, selected, animated=True)
        self.assertTrue(config['sfx']['enabled'])
        self.assertEqual(config['sfx']['allowed_names'], [self.name])
        self.assertIn(self.name, sfx_library.instructions(selected))
        self.assertEqual(sound_settings.apply_config({}, selected)['sfx']['allowed_names'], [])
        for choice in [{'enabled': False, 'ids': ['123']}, {'enabled': True, 'ids': []}, {'enabled': True, 'ids': ['999']}]:
            sound = sound_settings.normalize({'effects': {'enabled': False}, 'library': choice})
            self.assertEqual(sfx_library.allowed(sound), [])
            self.assertNotIn(self.name, sfx_library.instructions(sound))
            config = sound_settings.apply_config({}, sound, animated=True)
            self.assertFalse(config['sfx']['enabled'])
            self.assertEqual(sound_settings.filter_story({'sfx': [{'name': self.name}]}, config)['sfx'], [])
            ctx = SimpleNamespace(project={'id': 'a'*24, 'tracks': [{'id': 'base', 'clips': [{'duration': 5}]}]}, plan=None,
                                  actions=[], report=[])
            with patch.object(sound_settings, 'for_project', return_value=sound), \
                 patch.object(store, 'project_animated', return_value=True), \
                 patch.object(store, 'media_dir', return_value=self.root), \
                 patch.object(sound_settings, 'audio_module', side_effect=AssertionError('No synthesis')):
                soundtrack.place(ctx, {'cues': [{'name': self.name, 't': 1, 'dur': .5}]})
            self.assertEqual(ctx.actions, [])


class LibraryApiTest(LibraryTest):
    @classmethod
    def setUpClass(cls):
        fixtures.BackendTest.setUpClass()
        cls.base_url, cls.channel = fixtures.BackendTest.base_url, fixtures.BackendTest.channel

    @classmethod
    def tearDownClass(cls):
        fixtures.BackendTest.tearDownClass()

    request = fixtures.BackendTest.request

    def test_file_selection_round_trips_and_empty_list_blocks_future_placement(self):
        cid = store.channel_id(self.channel)
        code, result = self.request('/api/channels/'+cid, 'PATCH', {'settings': {'sound': {
            'library': {'enabled': True, 'ids': ['123', '999']}}}})
        self.assertEqual(code, 200, result)
        self.assertEqual(result['channel']['settings']['sound']['library'], {'enabled': True, 'ids': ['123', '999']})
        code, result = self.request('/api/channels/'+cid, 'PATCH', {'settings': {'sound': {'library': {'ids': []}}}})
        self.assertEqual(code, 200, result)
        self.assertEqual(result['channel']['settings']['sound']['library'], {'enabled': True, 'ids': []})
        self.assertEqual(sfx_library.allowed(sound_settings.for_project({'channel_id': cid})), [])
        code, result = self.request('/api/sound-effects')
        self.assertEqual(code, 200)
        self.assertTrue(result['library_selection'])

    def test_original_preview_and_separate_timeline_clip_reuse_and_disabled_choices(self):
        import sound_settings
        store.atomic_json(store.channel_settings_path(self.channel), {'weights': {'stock_photo': 100}, 'sound': {'effects': {'categories': ['appearance']}}})
        code, data = self.request('/api/sound-effects')
        self.assertEqual((code, len(data['library'])), (200, 1))
        import urllib.request
        with urllib.request.urlopen(self.base_url + data['library'][0]['preview_url']) as result:
            self.assertEqual(result.read(), (self.root / '123.wav').read_bytes())
        project = store.create_project(store.channel_id(self.channel), 'SFX test')
        pid = project['id']
        self.request(f'/api/projects/{pid}/actions', 'POST', {'type': 'add_clip', 'payload': {
            'layer_id': project['tracks'][0]['id'], 'kind': 'animation', 'content_type': 'shape', 'duration': 6}})
        body = {'ops': [{'op': 'soundtrack', 'cues': [{'name': self.name, 't': 1.25, 'dur': .5, 'gain': -12}]}]}
        with patch.object(store, 'project_animated', return_value=True), patch.object(sound_settings, 'audio_module', side_effect=AssertionError('No synthesis')):
            code, result = self.request(f'/api/projects/{pid}/ops', 'POST', body)
            self.assertEqual(code, 200, result)
            saved = store.load_project(pid)
            audio = [(layer, clip) for layer in saved['tracks'] for clip in layer['clips'] if clip['kind'] == 'audio']
            self.assertEqual(len(audio), 1)
            layer, clip = audio[0]
            self.assertTrue(all(c['kind'] == 'audio' for c in layer['clips']))
            self.assertTrue(clip['title'].startswith('Звук ролика · SFX · '))
            self.assertEqual((clip['start'], clip['duration']), (1.25, .5))
            self.assertAlmostEqual(clip['volume'], .12 * 10 ** (-4 / 20))
            asset = store.resolve_asset(saved, clip['asset_id'])
            self.assertEqual(Path(asset['path']).read_bytes(), (self.root / '123.wav').read_bytes())
            revision = saved['revision']
            code, result = self.request(f'/api/projects/{pid}/ops', 'POST', body)
            self.assertEqual(code, 200, result)
            self.assertEqual(store.load_project(pid)['revision'], revision)
            store.update_channel_settings(store.channel_id(self.channel), {'sound': {'effects': {'enabled': False}}})
            body['ops'][0]['cues'][0]['t'] = 3
            self.request(f'/api/projects/{pid}/ops', 'POST', body)
            self.assertEqual(store.load_project(pid)['revision'], revision)
