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
    def test_library_selection_is_portable_strict_and_preserved_by_partial_updates(self):
        choice = {'enabled': False, 'ids': ['123', '999999999']}
        normalized = sound.normalize({'library': choice})
        self.assertEqual(normalized['library'], choice)
        normalized['library']['ids'].append('456')
        self.assertEqual(choice['ids'], ['123', '999999999'])
        self.assertNotIn('library', sound.normalize())
        self.assertEqual(sound.merge({'library': choice}, {'effects': {'enabled': False}})['library'], choice)
        self.assertEqual(sound.merge({'library': choice}, {'library': {'enabled': True}})['library'],
                         {'enabled': True, 'ids': choice['ids']})
        for library in [None, [], {'enabled': 'false'}, {'ids': None}, {'ids': [123]},
                        {'ids': ['../123']}, {'ids': ['123', '123']}, {'unknown': True}]:
            with self.subTest(library=library), self.assertRaises(ValueError):
                sound.normalize({'library': library})

    def test_transition_choices_are_separate_and_have_3_distinct_decodable_designs(self):
        import numpy as np
        import hashlib
        module = sound.audio_module('sfx')
        choice = sound.normalize({'effects': {'enabled': False}, 'transitions': {'enabled': True, 'styles': ['air', 'snap']}})
        self.assertEqual(sound.allowed_names(choice), [])
        self.assertEqual(sound.transition_names(choice), ['tr_air', 'tr_snap'])
        self.assertFalse(sound.normalize({'effects': {'categories': ['whoosh']}})['transitions']['enabled'])
        self.assertEqual(sound.apply_config({}, choice)['sfx']['allowed_names'], ['tr_air', 'tr_snap'])
        self.assertEqual(sound.apply_config({}, choice, animated=True)['sfx']['allowed_names'], [])
        self.assertFalse(sound.apply_config({}, choice, animated=True)['sfx']['enabled'])
        hashes = set()
        for row in sound.transition_catalog():
            if row['source_group'] != 'studio':
                continue   # CapCut's are files of the SFX library (test_transition_capcut), not synthesized
            data = module.make(row['name'])
            self.assertEqual(data.shape[1], 2)
            self.assertTrue(np.isfinite(data).all())
            self.assertGreater(float(np.sqrt(np.mean(data ** 2))), .001)
            self.assertLessEqual(float(np.abs(data).max()), .95)
            hashes.add(hashlib.sha256(data.tobytes()).hexdigest())
        self.assertEqual(len(hashes), 3)
        self.assertEqual(sound.normalize({'transitions': {'enabled': True, 'styles': ['air', 'camera', 'snap']}})['transitions']['styles'], ['air', 'snap'])
        for transitions in [{'enabled': 'true'}, {'styles': ['missing']}, {'styles': ['air', 'air']}]:
            with self.subTest(transitions=transitions), self.assertRaises(ValueError):
                sound.normalize({'transitions': transitions})

    def test_catalogue_has_20_motion_choices_without_ambience_and_rejects_invalid_choices(self):
        library = sound.audio_module('sfx').LIB
        names = [name for _, _, group in sound.CATEGORIES for name in group]
        self.assertEqual(len(sound.catalog()), 20)
        self.assertLessEqual(set(names), set(library))
        self.assertTrue({"flash", "whoosh", "swish", "ratchet", "spin", "swoosh_in", "scramble"}.issubset(names))
        self.assertTrue(set(names).isdisjoint({"city", "wind", "rain", "footstep", "applause", "ding", "powerup"}))
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(sound.allowed_names(sound.normalize()), names)
        for value in [{'music': {'enabled': 'false'}}, {'effects': {'categories': ['missing']}},
                      {'effects': {'categories': ['tick', 'tick']}}, {'effects': []}]:
            with self.subTest(value=value), self.assertRaises(ValueError): sound.normalize(value)
        self.assertEqual(sound.allowed_names(sound.normalize({'effects': {'categories': []}})), [])

    def test_filtering_keeps_saved_cues_and_the_existing_music_file_untouched(self):
        config = {'music': {'file': 'input/music.mp3', 'seed': 3}}
        story = {'sfx': [{'name': 'lock_in'}, {'name': 'whoosh'}], 'shots': [
            {'sfx': [{'name': 'pop'}], 'amb': {'name': 'wind'}}, {'amb': None}]}
        original = copy.deepcopy(story)
        self.assertEqual(sound.apply_config(config, None), config)
        applied = sound.apply_config(config, {'music': {'generate': False}, 'effects': {'categories': ['lock'], 'version': 2}})
        result = sound.filter_story(story, applied)
        self.assertEqual(result['sfx'], [{'name': 'lock_in'}])
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
        story = {'duration': 4, 'shots': [{'start': 0, 'end': 4, 'sfx': [{'at': 1, 'name': 'lock_in'}, {'at': 2, 'name': 'whoosh'}], 'amb': {'name': 'wind'}}]}
        config = sound.apply_config({}, {'music': {'generate': False}, 'effects': {'categories': ['lock'], 'version': 2}})
        with patch.object(mix.MUSIC, 'render_score', side_effect=AssertionError('Music generation disabled')), \
             patch.object(mix.SFX, 'make', wraps=mix.SFX.make) as make:
            parts = list(mix.beds('/unused', config, story, 4 * mix.SR, -16, np.zeros(4 * mix.SR)))
            self.assertTrue(parts)
            self.assertEqual({call.args[0] for call in make.call_args_list}, {'lock_in'})
        config['sfx']['enabled'] = False
        self.assertEqual(list(mix.beds('/unused', config, story, 1, -16, np.zeros(1))), [])

    def test_native_soundtrack_skips_disabled_choices_and_reuses_identical_cues(self):
        ctx = SimpleNamespace(project={'id': 'a' * 24, 'tracks': [{'id': 'base', 'clips': [{'start': 0, 'duration': 10, 'title': 'Озвучка'}]}]}, plan=None,
                              actions=[], report=[], asset_for=lambda p: p.name)
        with tempfile.TemporaryDirectory() as tmp, patch.object(store, 'media_dir', return_value=Path(tmp)), \
             patch.object(sound, 'for_project', return_value=sound.normalize({'music': {'enabled': False}, 'effects': {'categories': ['lock'], 'version': 2}})):
            soundtrack.place(ctx, {'music': True, 'cues': [{'name': 'lock_in', 't': 2}, {'name': 'whoosh', 't': 4}]})
            self.assertEqual(len(ctx.actions), 1)
            action = ctx.actions[0]['payload']
            # the loudest moment of the sound lands on its time (21 November 2026), so the clip starts a little before it
            self.assertEqual(action['kind'], 'audio'); self.assertTrue(1.5 <= action['start'] <= 2)
            self.assertNotIn('group_id', action)
            ctx.project['tracks'][0]['clips'].append(action)
            ctx.actions.clear()
            soundtrack.place(ctx, {'music': True, 'cues': [{'name': 'lock_in', 't': 2}]})
            self.assertEqual(ctx.actions, [])

    def test_transition_sounds_vary_follow_real_joins_and_disappear_with_a_cut(self):
        frames = [{'number': n, 'start': (n - 1) * 5, 'end': n * 5, 'group': {'id': str(n)}} for n in range(1, 4)]
        joins = [{'from_ref': 'group:1', 'to_ref': 'group:2', 'type': 'crossfade', 'duration': .35},
                 {'from_ref': 'group:2', 'to_ref': 'group:3', 'type': 'slide_left', 'duration': .35}]
        ctx = SimpleNamespace(project={'id': 'a' * 24, 'tracks': [{'id': 'base', 'clips': [{'kind': 'image', 'start': 0, 'duration': 15}]}],
                                       'join_transitions': joins}, frames=frames, plan=None, actions=[], report=[], asset_for=lambda p: p.name)
        choice = {'effects': {'enabled': False}, 'transitions': {'enabled': True, 'styles': ['air', 'snap']}}
        with tempfile.TemporaryDirectory() as tmp, patch.object(store, 'media_dir', return_value=Path(tmp)), \
             patch.object(sound, 'saved_for_project', return_value=choice):
            soundtrack.transitions(ctx, {'sound_frames': [2, 3]})
            clips = [a['payload'] for a in ctx.actions if a['type'] == 'add_clip']
            self.assertTrue(all(abs(c['start'] - seam) < .5 for c, seam in zip(clips, [5, 10])))   # peak on the transition's middle
            # a dissolve sounds soft (a soft sound of the studio when the channel chose none), a slide whooshes
            self.assertEqual(sound.sound_character(clips[0]['title'].split(' · ')[-1]), 'soft')
            self.assertIn('tr_air', clips[1]['title'])
            ctx.project['tracks'][0]['clips'] += [dict(c, id=f'fx-{i}') for i, c in enumerate(clips)]
            ctx.actions.clear(); soundtrack.transitions(ctx, {'sound_frames': [2, 3]})
            self.assertEqual(ctx.actions, [])
            ctx.actions = [{'type': 'set_join_transition', 'payload': {**joins[1], 'type': 'cut'}}]
            soundtrack.transitions(ctx, {'sound_frames': [2, 3]})
            self.assertEqual([a['payload']['clip_id'] for a in ctx.actions if a['type'] == 'delete_clip'], ['fx-1'])

    def test_a_transition_sounds_like_what_it_does(self):
        self.assertEqual(sound.transition_character('capcut_t24'), 'glitch')
        self.assertEqual(sound.transition_character('crossfade'), 'soft')
        chosen = ['tr_air', 'tr_cc7021300953584257026', 'tr_cc7685955880517355521']
        self.assertEqual(sound.sounds_for('glitch', chosen), ['tr_cc7021300953584257026'])
        self.assertNotIn('tr_cc7021300953584257026', sound.sounds_for('soft', chosen))   # a dissolve never glitches
        self.assertTrue(all(sound.sound_character(n) == 'flash' for n in sound.sounds_for('flash', chosen)))   # from the studio

    def test_a_batch_before_a_host_frame_sets_the_transition_into_the_host(self):
        # the host's frames are made by the studio, never in an agent's batch: the seam into the host belongs to the batch
        # of the frame before it (user, 25 November 2026: «якщо хайген аватар, то in переход має бути обов'язковий»)
        frames = [{'number': n, 'start': (n - 1) * 5, 'end': n * 5, 'group': {'id': str(n)}, 'clips': [],
                   'plan': {'format': 'host' if n == 3 else 'razgon_2d'}} for n in range(1, 5)]
        ctx = SimpleNamespace(project={'id': 'a' * 24, 'fps': 25, 'tracks': [], 'join_transitions': []}, frames=frames,
                              plan=None, actions=[], report=[], asset_for=lambda p: p.name)
        with patch.object(montage_ops, 'channel_transitions', return_value={'allowed': ['crossfade']}), \
             patch.object(soundtrack, 'transitions'), patch.object(soundtrack, 'typing'):
            montage_ops.transitions(ctx, {'frames': [2]})
        seams = {(a['payload']['from_ref'], a['payload']['to_ref']) for a in ctx.actions if a['type'] == 'set_join_transition'}
        self.assertIn(('group:2', 'group:3'), seams)

    def test_the_host_sounds_only_where_he_goes_out_and_a_cut_never(self):
        frames = [{'number': n, 'start': (n - 1) * 5, 'end': n * 5, 'group': {'id': str(n)},
                   'plan': {'format': 'host' if n == 2 else 'razgon_2d'}} for n in range(1, 5)]
        joins = [{'from_ref': 'group:1', 'to_ref': 'group:2', 'type': 'crossfade', 'duration': .35},
                 {'from_ref': 'group:2', 'to_ref': 'group:3', 'type': 'crossfade', 'duration': .35}]   # 3 → 4 is a cut
        ctx = SimpleNamespace(project={'id': 'a' * 24, 'tracks': [{'id': 'base', 'clips': [{'kind': 'image', 'start': 0, 'duration': 20}]}],
                                       'join_transitions': joins}, frames=frames, plan=None, actions=[], report=[], asset_for=lambda p: p.name)
        with tempfile.TemporaryDirectory() as tmp, patch.object(store, 'media_dir', return_value=Path(tmp)), \
             patch.object(sound, 'saved_for_project', return_value={'transitions': {'enabled': False}}):
            soundtrack.transitions(ctx)
        cues = [a['payload'] for a in ctx.actions if a['type'] == 'add_clip']
        # where the host goes out his transition sounds; where he comes in, none; a cut never (user, 25 November 2026:
        # «для хейгена лише для аута. Для іна не став звуковий ефект»; «там, де дійсно переход»)
        self.assertEqual([c['title'].split(' · ')[1] for c in cues], ['2 → 3'])
        self.assertLess(abs(cues[0]['start'] - 10), .5)

    def test_a_transition_sound_peaks_on_the_transition_hit(self):
        # user, 25 November 2026: «звук підставляється неточно, не в той момент переходу… то лівіше, то правіше»: a 1.4 s
        # transition put its sound's peak 0.35 s after the seam, not on the transition
        frames = [{'number': n, 'start': (n - 1) * 5, 'end': n * 5, 'group': {'id': str(n)}, 'plan': {'format': 'razgon_2d'}} for n in (1, 2)]
        joins = [{'from_ref': 'group:1', 'to_ref': 'group:2', 'type': 'crossfade', 'duration': 1.4}]
        ctx = SimpleNamespace(project={'id': 'a' * 24, 'tracks': [{'id': 'base', 'clips': [{'kind': 'image', 'start': 0, 'duration': 10}]}],
                                       'join_transitions': joins}, frames=frames, plan=None, actions=[], report=[], asset_for=lambda p: p.name)
        with tempfile.TemporaryDirectory() as tmp, patch.object(store, 'media_dir', return_value=Path(tmp)), \
             patch.object(sound, 'saved_for_project', return_value={'transitions': {'enabled': False}}):
            soundtrack.transitions(ctx)
            cue = next(a['payload'] for a in ctx.actions if a['type'] == 'add_clip')
            path = next(Path(tmp).rglob('*.wav'))
            # the transition is laid with its hit on the seam, and the sound peaks there
            self.assertLess(abs(cue['start'] + soundtrack._peak(path) - 5.0), .03)   # within the 50 ms window the peak is measured in

    def test_a_transition_sounds_by_what_it_shows(self):
        # watched, not named: the white burst «Спотворення прискорення» is a flash, «Райдужний фільтр» a soft wash
        self.assertEqual(sound.transition_character('capcut_t13'), 'flash')
        self.assertEqual(sound.transition_character('capcut_t34'), 'soft')
        self.assertEqual(sound.transition_character('capcut_t24'), 'glitch')
        self.assertEqual(sound.transition_character('capcut_t15'), 'motion')

    def test_a_text_frame_going_out_sounds_only_with_a_real_transition(self):
        # user, 25 November 2026: «озвучку переходів ставити там, де дійсно переход» (a cut out of a text frame has none)
        frames = [{'number': n, 'start': (n - 1) * 5, 'end': n * 5, 'group': {'id': str(n)},
                   'plan': {'format': 'text' if n == 3 else 'stock_photo'}} for n in range(1, 5)]
        ctx = SimpleNamespace(project={'id': 'a' * 24, 'tracks': [{'id': 'base', 'clips': [{'kind': 'image', 'start': 0, 'duration': 20}]}],
                                       'join_transitions': []}, frames=frames, plan=None, actions=[], report=[], asset_for=lambda p: p.name)
        with tempfile.TemporaryDirectory() as tmp, patch.object(store, 'media_dir', return_value=Path(tmp)), \
             patch.object(sound, 'saved_for_project', return_value={'transitions': {'enabled': False}}):
            soundtrack.transitions(ctx)
            self.assertEqual([a for a in ctx.actions if a['type'] == 'add_clip'], [])   # a cut: no sound
            ctx.project['join_transitions'] = [{'from_ref': 'group:3', 'to_ref': 'group:4', 'type': 'crossfade', 'duration': .35}]
            ctx.actions = []
            soundtrack.transitions(ctx)
        cues = [a['payload'] for a in ctx.actions if a['type'] == 'add_clip']
        self.assertEqual([c['title'].split(' · ')[1] for c in cues], ['3 → 4'])

    def test_animated_films_get_no_transition_sound_and_every_transition_of_a_film_has_its_own(self):
        ctx = SimpleNamespace(project={'project_kind': 'animated'}, actions=[], report=[])
        with patch.object(sound, 'saved_for_project', side_effect=AssertionError('Animated must not use this setting')):
            soundtrack.transitions(ctx)
        self.assertEqual(ctx.actions, [])
        ctx = SimpleNamespace(project={'id': 'a'*24, 'project_kind': 'regular', 'tracks': [{'id': 'base', 'clips': [
            {'kind': 'image', 'start': 0, 'duration': 60}]}], 'join_transitions': [
            {'from_ref': f'group:{n}', 'to_ref': f'group:{n+1}', 'type': 'crossfade', 'duration': .35} for n in range(1, 6)]},
            frames=[{'number': n, 'start': (n-1)*10, 'end': n*10, 'group': {'id': str(n)}} for n in range(1, 7)],
            plan=None, actions=[], report=[], asset_for=lambda p: p.name)
        with tempfile.TemporaryDirectory() as tmp, patch.object(store, 'media_dir', return_value=Path(tmp)), \
             patch.object(sound, 'saved_for_project', return_value={'transitions': {'enabled': True}}):
            soundtrack.transitions(ctx)
            cues = [a['payload'] for a in ctx.actions if a['type'] == 'add_clip']
            self.assertEqual(len(cues), 5)   # every transition has its sound, gentle ones too
            self.assertEqual(len({c['title'].split(' · ')[-1] for c in cues}), 1)   # one kind of transition, one sound
            ctx.actions.clear()
            ctx.project['join_transitions'][2]['type'] = 'slide_left'
            soundtrack.transitions(ctx)
            cues = [a['payload'] for a in ctx.actions if a['type'] == 'add_clip']
            names = {c['title'].split(' · ')[1]: c['title'].split(' · ')[-1] for c in cues}
            self.assertNotEqual(names['3 → 4'], names['1 → 2'])   # another kind, another sound


    def test_typed_text_gets_the_typing_sound_only_when_the_channel_allows_it(self):
        typed = {'id': 't1', 'kind': 'text', 'start': 5.0, 'duration': 6.0, 'word_entrance': {'type': 'letters_fade'},
                 'text_words': [{'text': w, 'start': s} for w, s in [('Ми', .2), ('склали', .6), ('карту', 1.1), ('невидимого', 3.9)]]}
        popped = {'id': 't2', 'kind': 'text', 'start': 11.0, 'duration': 4.0, 'word_entrance': {'type': 'pop'},
                  'text_words': [{'text': 'Слово', 'start': .1}]}
        frames = [{'number': 2, 'start': 5, 'end': 11, 'group': {'id': '2'}, 'clips': [typed]},
                  {'number': 3, 'start': 11, 'end': 15, 'group': {'id': '3'}, 'clips': [popped]}]
        ctx = SimpleNamespace(project={'id': 'a' * 24, 'tracks': [{'id': 'base', 'clips': [{'kind': 'image', 'start': 0, 'duration': 15}, typed, popped]}],
                                       'join_transitions': []}, frames=frames, plan=None, actions=[], report=[], asset_for=lambda p: p.name)
        on = {'effects': {'enabled': True, 'categories': ['typing'], 'version': sound.EFFECTS_VERSION}}
        with tempfile.TemporaryDirectory() as tmp, patch.object(store, 'media_dir', return_value=Path(tmp)), \
             patch.object(sound, 'saved_for_project', return_value=on), patch.object(soundtrack.sfx_library, 'catalog', return_value=[]):
            soundtrack.typing(ctx)
            cues = [a['payload'] for a in ctx.actions if a['type'] == 'add_clip']
            # from the first letter, the sounds one after another for as long as the words keep coming (each whole), then
            # again with the next run of words, a little after the first letter; a popped word is not typed and stays
            # silent (user, 26 November 2026: «Коли по буквах появляється, тоді да. Але трошки з затримкою»)
            self.assertEqual([c['start'] for c in cues], [5.4, 6.2, 9.1])
            self.assertTrue(all(c['title'].startswith(soundtrack.TYPING_PREFIX + 'K002') for c in cues))
            self.assertTrue(all(c['duration'] >= .5 for c in cues))   # played whole, never cut to a word
            ctx.project['tracks'][0]['clips'] += [dict(c, id=f'ty-{i}') for i, c in enumerate(cues)]
            ctx.actions.clear(); soundtrack.typing(ctx)
            self.assertEqual(ctx.actions, [])
        off = {'effects': {'enabled': True, 'categories': ['click'], 'version': sound.EFFECTS_VERSION}}
        with patch.object(sound, 'saved_for_project', return_value=off), patch.object(soundtrack.sfx_library, 'catalog', return_value=[]):
            soundtrack.typing(ctx)
        self.assertEqual(sorted(a['payload']['clip_id'] for a in ctx.actions if a['type'] == 'delete_clip'), ['ty-0', 'ty-1', 'ty-2'])


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


class TransitionSoundSyncTest(unittest.TestCase):
    """A transition added, changed or removed brings its sounds along by itself (user, 25 November 2026: «щоб
    автоматично ставилось там, де дійсно переход»)."""

    def test_join_edits_start_a_sound_pass_and_other_edits_do_not(self):
        import app
        self.assertTrue(app.changes_joins({"type": "set_join_transition", "payload": {}}))
        self.assertTrue(app.changes_joins({"type": "batch", "payload": {"actions": [{"type": "update_clip"}, {"type": "set_join_transition"}]}}))
        self.assertTrue(app.changes_joins({"type": "undo"}))
        self.assertFalse(app.changes_joins({"type": "update_clip", "payload": {}}))
        self.assertFalse(app.changes_joins({"type": "batch", "payload": {"actions": [{"type": "add_clip"}]}}))

    def test_several_edits_in_a_row_make_one_pass(self):
        import app
        calls = []
        with patch.object(app, "active_export", return_value=None), \
             patch.object(app.montage_ops, "run", side_effect=lambda pid, ops: calls.append((pid, ops))):
            for _ in range(3):
                app.sync_transition_sounds("p" * 24, delay=.05)
            import time
            time.sleep(1.0)
        self.assertEqual(calls, [("p" * 24, [{"op": "transition_sounds"}, {"op": "typing_sounds"}, {"op": "drawing_sounds"}])])


class WritingAndAppearanceSoundsTest(unittest.TestCase):
    POOL = [('a', 3.88), ('b', 2.4), ('c', 2.21), ('d', 0.75)]

    def test_long_writing_gets_different_sounds_one_after_another_for_its_whole_length(self):
        used = {}
        sounds, last = soundtrack.chain(self.POOL, 10.0, 7.0, used)
        names = [n for n, _, _ in sounds]
        self.assertTrue(all(a != b for a, b in zip(names, names[1:])))          # never the same twice in a row
        self.assertEqual([round(t, 2) for _, t, _ in sounds][0], 10.0)
        for (_, t, d), (_, t2, _) in zip(sounds, sounds[1:]):
            self.assertAlmostEqual(t + d, t2, places=3)                          # back to back, no overlap
        end = sounds[-1][1] + sounds[-1][2]
        self.assertLess(abs(end - 17.0), 0.8)                                    # as long as the writing
        short, _ = soundtrack.chain(self.POOL, 0.0, 0.8, {})
        self.assertEqual([n for n, _, _ in short], ['d'])                        # a short writing, a short sound

    def test_writing_runs_split_where_the_words_pause(self):
        words = [{'start': 0.2}, {'start': 0.6}, {'start': 1.1, 'end': 1.5}, {'start': 3.9}]
        self.assertEqual(soundtrack.writing_runs(words, 5.0), [(5.2, 6.5), (8.9, 8.9 + soundtrack.LAST_WORD)])

    def test_motion_code_writes_only_the_words_of_its_own_text(self):
        clip = {'code': "ctx.fillText('Милкомеда', 0, 0); label('Milky Way')",
                'code_words': [{'text': 'Астрономы', 'start': .3}, {'text': 'Милкомеда,', 'start': 4.8}, {'text': 'и', 'start': 8.8}]}
        self.assertEqual([w['text'] for w in soundtrack.written_words(clip)], ['Милкомеда,'])
        self.assertEqual(soundtrack.written_words({'code': 'draw()', 'code_words': clip['code_words']}), [])

    def test_appearances_in_razgon_frames_sound_on_their_moment_spaced_and_varied(self):
        block = {'id': 'r', 'kind': 'animation', 'title': 'Razgon · кадр 004', 'start': 10.0, 'duration': 10.0}
        frames = [{'number': 4, 'start': 10.0, 'end': 20.0, 'clips': [block]},
                  {'number': 5, 'start': 20.0, 'end': 25.0, 'clips': [{'id': 'p', 'kind': 'image', 'title': 'K005 кадр', 'start': 20, 'duration': 5}]}]
        ctx = SimpleNamespace(project={'id': 'a' * 24, 'tracks': [{'id': 'base', 'clips': [block]}]}, frames=frames, actions=[], report=[])
        events = [{'t': 11.0, 'kind': 'text'}, {'t': 11.5, 'kind': 'text'}, {'t': 13.0, 'kind': 'picture'},
                  {'t': 14.5, 'kind': 'text'}, {'t': 16.0, 'kind': 'write', 'dur': 3.0}, {'t': 22.0, 'kind': 'text'}]
        pools = {'text': [('pop', .5), ('glint', 1.1)], 'picture': [('whoosh', .8)], 'write': self.POOL}
        laid = {}
        with patch.object(sound, 'saved_for_project', return_value={}), patch.object(soundtrack, 'appear_pools', return_value=pools), \
                patch.object(soundtrack, 'place', side_effect=lambda c, spec, **k: laid.update(spec=spec, flags=k)), \
                patch.object(soundtrack.sfx_library, 'find', return_value=None), patch.object(store, 'project_animated', return_value=False):
            soundtrack.appear(ctx, {'events': events})
        cues = laid['spec']['cues']
        self.assertEqual(laid['flags'], {'appear': True})
        plain = [(c['t'], c['name']) for c in cues if not c.get('from_start')]
        # 11.5 is too close to 11.0; 22.0 is outside the Razgon frames
        self.assertEqual(plain, [(11.0, 'glint'), (13.0, 'whoosh'), (14.5, 'pop')])
        writing = [c for c in cues if c.get('from_start')]
        self.assertEqual(writing[0]['t'], 16.0 + soundtrack.KEYS_DELAY)   # the keys a moment after the first letter
        self.assertLessEqual(writing[-1]['t'] + writing[-1]['dur'], 19.9)

