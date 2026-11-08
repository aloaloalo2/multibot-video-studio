import unittest
from unittest.mock import patch

import test_backend as fixtures
import store


class SoundApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.BackendTest.setUpClass()
        cls.base_url, cls.channel = fixtures.BackendTest.base_url, fixtures.BackendTest.channel

    @classmethod
    def tearDownClass(cls):
        fixtures.BackendTest.tearDownClass()

    request = fixtures.BackendTest.request

    def test_channel_choices_round_trip_and_control_native_sound_generation(self):
        cid = store.channel_id(self.channel)
        sound = {'music': {'enabled': True, 'generate': False}, 'effects': {'enabled': True, 'categories': ['notification']}}
        code, result = self.request('/api/channels/' + cid, 'PATCH', {'settings': {'sound': sound}})
        self.assertEqual(code, 200, result)
        self.assertEqual(result['channel']['settings']['sound'], sound)
        code, data = self.request('/api/sound-effects')
        self.assertEqual((code, len(data['categories'])), (200, 15))
        project = store.create_project(cid, 'Sound fixture')
        pid, layer = project['id'], project['tracks'][0]['id']
        code, result = self.request(f'/api/projects/{pid}/actions', 'POST', {'type': 'add_clip', 'payload': {
            'layer_id': layer, 'kind': 'animation', 'content_type': 'shape', 'duration': 6}})
        self.assertEqual(code, 200, result)
        code, result = self.request(f'/api/projects/{pid}/ops', 'POST', {'ops': [{'op': 'soundtrack', 'music': True,
                                    'cues': [{'name': 'ding', 't': 1}, {'name': 'whoosh', 't': 2}]}]})
        self.assertEqual(code, 200, result)
        saved = store.load_project(pid)
        audio = [c for layer in saved['tracks'] for c in layer['clips'] if c['kind'] == 'audio']
        self.assertEqual(len(audio), 1)
        self.assertIn('ding', audio[0]['title'])
        before = saved['revision']
        code, result = self.request(f'/api/projects/{pid}/ops', 'POST', {'ops': [{'op': 'soundtrack', 'cues': [{'name': 'ding', 't': 1}]}]})
        self.assertEqual(code, 200, result)
        self.assertEqual(store.load_project(pid)['revision'], before)
        code, result = self.request('/api/channels/' + cid, 'PATCH', {'settings': {'sound': {'effects': {'categories': ['bad']}}}})
        self.assertEqual(code, 400)
        self.assertEqual(store.list_channels()[0]['settings']['sound'], sound)

    def test_transitions_get_varied_allowed_sound_in_the_same_undo_step(self):
        cid = store.channel_id(self.channel)
        store.update_channel_settings(cid, {'sound': {'effects': {'categories': ['whoosh', 'devices']}}})
        project = store.create_project(cid, 'Transition sound fixture')
        pid = project['id']
        plan = {'frames': [{'number': n, 'format': 'animation', 'start': (n - 1) * 5, 'end': n * 5} for n in range(1, 4)]}
        with patch.object(store, 'load_project_plan', return_value=plan):
            code, result = self.request(f'/api/projects/{pid}/ops', 'POST', {'ops': [
                {'op': 'animation', 'frame': n, 'background': '#112233', 'clips': [{'kind': 'text', 'text': str(n)}]} for n in range(1, 4)]})
            self.assertEqual(code, 200, result)
            before = store.load_project(pid)['revision']
            code, result = self.request(f'/api/projects/{pid}/ops', 'POST', {'ops': [{'op': 'transitions', 'share': 1, 'pool': ['crossfade']}]})
            self.assertEqual(code, 200, result)
            saved = store.load_project(pid)
            self.assertEqual(saved['revision'], before + 1)
            audio = [c for layer in saved['tracks'] for c in layer['clips'] if c['kind'] == 'audio']
            self.assertEqual([c['start'] for c in audio], [5, 10])
            self.assertEqual(len(saved['scene_groups']), 3)
            self.assertIn('whoosh', audio[0]['title']); self.assertIn('flash', audio[1]['title'])
            code, result = self.request(f'/api/projects/{pid}/actions', 'POST', {'type': 'undo'})
            self.assertEqual(code, 200, result)
            saved = store.load_project(pid)
            self.assertEqual(saved.get('join_transitions', []), [])
            self.assertFalse(any(c['kind'] == 'audio' for layer in saved['tracks'] for c in layer['clips']))


if __name__ == '__main__': unittest.main()
