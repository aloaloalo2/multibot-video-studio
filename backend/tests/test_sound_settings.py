import copy
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sound_settings as sound
import soundtrack
import store
import montage_ops


class SoundSettingsTest(unittest.TestCase):
    def test_catalogue_has_15_editing_choices_without_ambience_and_rejects_invalid_choices(self):
        library = sound.audio_module('sfx').LIB
        names = [name for _, _, group in sound.CATEGORIES for name in group]
        self.assertEqual(len(sound.catalog()), 15)
        self.assertLessEqual(set(names), set(library))
        self.assertTrue({"flash", "whoosh", "swish", "blip"}.issubset(names))
        self.assertTrue(set(names).isdisjoint({"city", "wind", "rain", "footstep", "applause"}))
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(sound.allowed_names(sound.normalize()), names)
        for value in [{'music': {'enabled': 'false'}}, {'effects': {'categories': ['missing']}},
                      {'effects': {'categories': ['tick', 'tick']}}, {'effects': []}]:
            with self.subTest(value=value), self.assertRaises(ValueError): sound.normalize(value)
        self.assertEqual(sound.allowed_names(sound.normalize({'effects': {'categories': []}})), [])

    def test_filtering_keeps_saved_cues_and_the_existing_music_file_untouched(self):
        config = {'music': {'file': 'input/music.mp3', 'seed': 3}}
        story = {'sfx': [{'name': 'ding'}, {'name': 'whoosh'}], 'shots': [
            {'sfx': [{'name': 'pop'}], 'amb': {'name': 'wind'}}, {'amb': None}]}
        original = copy.deepcopy(story)
        self.assertEqual(sound.apply_config(config, None), config)
        applied = sound.apply_config(config, {'music': {'generate': False}, 'effects': {'categories': ['notification']}})
        result = sound.filter_story(story, applied)
        self.assertEqual(result['sfx'], [{'name': 'ding'}])
        self.assertEqual(result['shots'][0], {'sfx': []})
        self.assertEqual(story, original)
        self.assertEqual(applied['music']['file'], 'input/music.mp3')
        self.assertFalse(applied['music']['generate'])
        self.assertNotIn('generate', config['music'])

    def test_saved_channel_choices_win_over_the_old_project_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(store, 'get_channel_folder', return_value=Path(tmp)):
            store.atomic_json(Path(tmp) / store.PLAN_CONFIG, {'sound': {'music': {'enabled': False}, 'effects': {'enabled': False}}})
            project = {'id': 'a' * 24, 'channel_id': 'b' * 16, 'settings': {'sound': {'music': {'enabled': True}}}}
            self.assertFalse(sound.for_project(project)['music']['enabled'])
            text = sound.instructions(project, scoped=True)
            self.assertIn('Музика вимкнена', text)
            self.assertIn('наявний звук збережи', text)
            self.assertNotIn('"op":"soundtrack"', text)

    def test_previews_are_real_cached_stereo_audio_without_service_calls(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(store, 'DATA_ROOT', Path(tmp)):
            for row in sound.catalog():
                path = sound.preview(row['id'])
                with wave.open(str(path)) as wav:
                    self.assertEqual((wav.getnchannels(), wav.getframerate()), (2, 48000))
                    self.assertGreater(wav.getnframes(), 100)
                before = path.stat().st_mtime_ns
                self.assertEqual(sound.preview(row['id']).stat().st_mtime_ns, before)
            with self.assertRaises(store.StudioError): sound.preview('../bad')

    def test_mixer_does_not_generate_music_when_only_existing_music_is_allowed(self):
        import numpy as np
        mix = sound.audio_module('mix')
        story = {'duration': 4, 'shots': [{'start': 0, 'end': 4, 'sfx': [{'at': 1, 'name': 'ding'}, {'at': 2, 'name': 'whoosh'}], 'amb': {'name': 'wind'}}]}
        config = sound.apply_config({}, {'music': {'generate': False}, 'effects': {'categories': ['notification']}})
        with patch.object(mix.MUSIC, 'render_score', side_effect=AssertionError('Music generation disabled')), \
             patch.object(mix.SFX, 'make', wraps=mix.SFX.make) as make:
            parts = list(mix.beds('/unused', config, story, 4 * mix.SR, -16, np.zeros(4 * mix.SR)))
            self.assertTrue(parts)
            self.assertEqual([call.args[0] for call in make.call_args_list], ['ding'])
        config['sfx']['enabled'] = False
        self.assertEqual(list(mix.beds('/unused', config, story, 1, -16, np.zeros(1))), [])

    def test_native_soundtrack_skips_disabled_choices_and_reuses_identical_cues(self):
        ctx = SimpleNamespace(project={'id': 'a' * 24, 'tracks': [{'id': 'base', 'clips': [{'start': 0, 'duration': 10, 'title': 'Озвучка'}]}]}, plan=None,
                              actions=[], report=[], asset_for=lambda p: p.name)
        with tempfile.TemporaryDirectory() as tmp, patch.object(store, 'media_dir', return_value=Path(tmp)), \
             patch.object(sound, 'for_project', return_value=sound.normalize({'music': {'enabled': False}, 'effects': {'categories': ['notification']}})):
            soundtrack.place(ctx, {'music': True, 'cues': [{'name': 'ding', 't': 2}, {'name': 'whoosh', 't': 4}]})
            self.assertEqual(len(ctx.actions), 1)
            action = ctx.actions[0]['payload']
            self.assertEqual((action['kind'], action['start']), ('audio', 2))
            self.assertNotIn('group_id', action)
            ctx.project['tracks'][0]['clips'].append(action)
            ctx.actions.clear()
            soundtrack.place(ctx, {'music': True, 'cues': [{'name': 'ding', 't': 2}]})
            self.assertEqual(ctx.actions, [])

    def test_transition_sounds_vary_follow_real_joins_and_disappear_with_a_cut(self):
        frames = [{'number': n, 'start': (n - 1) * 5, 'end': n * 5, 'group': {'id': str(n)}} for n in range(1, 4)]
        joins = [{'from_ref': 'group:1', 'to_ref': 'group:2', 'type': 'crossfade', 'duration': .35},
                 {'from_ref': 'group:2', 'to_ref': 'group:3', 'type': 'slide_left', 'duration': .35}]
        ctx = SimpleNamespace(project={'id': 'a' * 24, 'tracks': [{'id': 'base', 'clips': [{'kind': 'image', 'start': 0, 'duration': 15}]}],
                                       'join_transitions': joins}, frames=frames, plan=None, actions=[], report=[], asset_for=lambda p: p.name)
        choice = {'effects': {'categories': ['whoosh', 'devices']}}
        with tempfile.TemporaryDirectory() as tmp, patch.object(store, 'media_dir', return_value=Path(tmp)), \
             patch.object(sound, 'saved_for_project', return_value=choice):
            soundtrack.transitions(ctx)
            clips = [a['payload'] for a in ctx.actions if a['type'] == 'add_clip']
            self.assertEqual([c['start'] for c in clips], [5, 10])
            self.assertIn('whoosh', clips[0]['title'])
            self.assertIn('flash', clips[1]['title'])
            ctx.project['tracks'][0]['clips'] += [dict(c, id=f'fx-{i}') for i, c in enumerate(clips)]
            ctx.actions.clear(); soundtrack.transitions(ctx)
            self.assertEqual(ctx.actions, [])
            ctx.actions = [{'type': 'set_join_transition', 'payload': {**joins[1], 'type': 'cut'}}]
            soundtrack.transitions(ctx)
            self.assertEqual([a['payload']['clip_id'] for a in ctx.actions if a['type'] == 'delete_clip'], ['fx-1'])


class AccentSideFieldTest(unittest.TestCase):
    def test_rebinding_keeps_the_caption_and_underline_fixed_in_the_side_field(self):
        photo = {'id': 'photo', 'kind': 'image', 'asset_id': 'portrait', 'title': 'K001 кадр', 'start': 0, 'duration': 12,
                 'x': .5, 'y': .5, 'width': 1, 'height': 1, 'scale': 1.25,
                 'keyframes': [{'time': 0, 'scale': 1.25}, {'time': 12, 'scale': 1}]}
        text = {'id': 'label', 'kind': 'text', 'title': 'K001 акцент 1 текст', 'start': 0, 'duration': 12, 'x': .17, 'y': .5}
        line = {'id': 'line', 'kind': 'animation', 'content_type': 'shape', 'title': 'K001 акцент 1 риска', 'start': 0,
                'duration': 12, 'x': .17, 'y': .6, 'width': .17, 'height': .01, 'keyframes': [{'time': 0, 'opacity': 0}, {'time': 10, 'opacity': 1}]}
        ctx = montage_ops.Context.__new__(montage_ops.Context)
        ctx.project = {'width': 1920, 'height': 1080, 'tracks': [{'id': 'base'}]}
        ctx.W, ctx.H, ctx.easing = 1920, 1080, 'ease_in_out'
        ctx.actions, ctx.report = [], []
        ctx.frames = [{'number': 1, 'start': 0, 'end': 12, 'group': {'id': 'g', 'title': 'Кадр 1'}, 'clips': [photo, text, line]}]
        with patch.object(store, 'resolve_asset', return_value={'path': 'portrait.png'}), patch.object(montage_ops, 'media_size', return_value=(480, 728)):
            montage_ops.reglue(ctx, {'frames': [1]})
        steady = next(a['payload']['patch'] for a in ctx.actions if a['type'] == 'update_clip' and a['payload']['clip_id'] == 'line')
        self.assertEqual(steady['x'], .17)
        self.assertFalse(any('x' in p for p in steady['keyframes']))
        appearance = next(a['payload'] for a in ctx.actions if a['type'] == 'add_clip')
        self.assertAlmostEqual(appearance['keyframes'][-1]['x'], .17, places=4)


if __name__ == '__main__': unittest.main()
