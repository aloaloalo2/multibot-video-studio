import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import direction_contract as contract


class DirectionContractTest(unittest.TestCase):
    def setUp(self):
        self.plan = {'script_sha256': 'script', 'timing': {'status': 'audio_synced',
            'audio': {'duration': 12.5, 'sha256': 'voice'}, 'sentences': [
                {'start': 0, 'end': 4, 'text': 'The ship accelerates toward the stars.'},
                {'start': 4, 'end': 8, 'text': 'The speed rises on its display.'},
                {'start': 8, 'end': 12, 'text': 'The engine stops near the planet.'}]}}
        self.config = {'music': {'enabled': True, 'generate': True},
                       'sfx': {'enabled': True, 'allowed_names': ['tick', 'pop']}}
        self.words = [{'word': 'The', 'start': 4.0}, {'word': 'speed', 'start': 4.2},
                      {'word': 'rises', 'start': 4.6}, {'word': 'on', 'start': 5.0},
                      {'word': 'its', 'start': 5.2}, {'word': 'display', 'start': 5.7}]
        self.packet = contract.source(self.plan, self.config, self.words)
        self.draft = {'source_signature': self.packet['signature'], 'bible': 'Orbit: the ship accelerates, then brakes.',
            'shots': [{'id': 's1', 'first_sentence': 1, 'last_sentence': 2, 'episode': 'E1', 'set': 'orbit',
                       'scene': 'The ship accelerates while its display counts speed.',
                       'in': {'type': 'fade', 'dur': .5},
                       'cues': [{'sentence': 2, 'word': 'speed', 'name': 'tick', 'gain': -14}]},
                      {'id': 's2', 'first_sentence': 3, 'last_sentence': 3, 'episode': 'E2', 'set': 'planet',
                       'scene': 'The engine stops above the blue planet.', 'in': {'type': 'dip', 'dur': .5}}],
            'music': [{'start': 0, 'end': 12.5, 'mood': 'wonder', 'intensity': .3}]}

    def compile(self):
        return contract.compile_direction(self.draft, self.packet, self.words)

    def test_author_groups_own_meaning_and_original_voice_tail_is_preserved(self):
        before = copy.deepcopy(self.draft)
        result = self.compile()
        self.assertEqual([(s['start'], s['end']) for s in result['shots']['shots']], [(0, 8), (8, 12.5)])
        self.assertEqual(result['beats']['beats'][1]['first_sentence'], 2)  # existing bridge uses zero-based numbers
        self.assertEqual(result['shots']['sfx'][0]['t'], 4.2)
        self.assertEqual(self.draft, before)
        self.assertIn('The speed rises', result['shots']['shots'][0]['line'])

    def test_source_signature_covers_audio_script_timing_words_and_settings(self):
        self.assertNotEqual(contract.source(self.plan, self.config, self.words, project_id='one')['signature'],
                            contract.source(self.plan, self.config, self.words, project_id='two')['signature'])
        for key in ('voice', 'script', 'timing', 'words', 'settings'):
            plan, config, words = copy.deepcopy(self.plan), copy.deepcopy(self.config), copy.deepcopy(self.words)
            if key == 'voice': plan['timing']['audio']['sha256'] = 'other'
            if key == 'script': plan['script_sha256'] = 'other'
            if key == 'timing': plan['timing']['sentences'][1]['start'] = 4.1
            if key == 'words': words[1]['start'] = 4.3
            if key == 'settings': config['sfx']['enabled'] = False
            self.assertNotEqual(contract.source(plan, config, words)['signature'], self.packet['signature'])
        self.draft['source_signature'] = 'stale'
        with self.assertRaisesRegex(ValueError, 'Змінилися'):
            self.compile()

    def test_missing_overlapping_reordered_or_duplicate_shots_cannot_be_accepted(self):
        for patch in ({'first_sentence': 1}, {'first_sentence': 2}, {'last_sentence': 4}, {'id': 's1'}):
            original = copy.deepcopy(self.draft)
            self.draft['shots'][1].update(patch)
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                self.compile()
            self.draft = original

    def test_all_validation_errors_are_returned_together(self):
        self.draft['shots'][0]['scene'] = ''
        self.draft['shots'][1]['set'] = ''
        with self.assertRaises(ValueError) as raised:
            self.compile()
        self.assertIn('Шот 1', str(raised.exception))
        self.assertIn('Шот 2', str(raised.exception))

    def test_disabled_or_unselected_sound_and_new_music_are_rejected(self):
        for value in ({'sfx': {'enabled': False}}, {'sfx': {'enabled': True, 'allowed_names': ['pop']}},
                      {'music': {'enabled': False}}, {'music': {'enabled': True, 'generate': False}}):
            config = {**self.config, **value}
            packet = contract.source(self.plan, config, self.words)
            self.draft['source_signature'] = packet['signature']
            with self.subTest(value=value), self.assertRaises(ValueError):
                contract.compile_direction(self.draft, packet, self.words)

    def test_word_anchors_reject_misses_ambiguity_and_wrong_shots_without_fallback(self):
        for cue in ({'word': 'absent'}, {'word': 'speed', 'offset': 0}, {'word': 'speed', 'occurrence': 2},
                    {'sentence': 3, 'word': None, 'offset': 0}):
            old = copy.deepcopy(self.draft['shots'][0]['cues'][0])
            self.draft['shots'][0]['cues'][0].update(cue)
            with self.subTest(cue=cue), self.assertRaises(ValueError): self.compile()
            self.draft['shots'][0]['cues'][0] = old

    def test_explicit_offset_and_repeated_word_occurrence_are_supported(self):
        cue = self.draft['shots'][0]['cues'][0]
        cue.pop('word'); cue['offset'] = .7
        self.assertEqual(self.compile()['shots']['sfx'][0]['t'], 4.7)
        cue.pop('offset'); cue['word'] = 'speed'; cue['occurrence'] = 2
        self.words.append({'word': 'speed', 'start': 7.5})
        self.assertEqual(self.compile()['shots']['sfx'][0]['t'], 7.5)

    def test_digit_anchor_uses_the_first_word_of_the_spoken_number(self):
        words = [{'word': w, 'start': 4 + i * .3} for i, w in enumerate(['тысяча', 'двести', 'тонн'])]
        cue = self.draft['shots'][0]['cues'][0]
        cue['word'] = '1200'
        result = contract.compile_direction(self.draft, self.packet, words)
        self.assertEqual(result['shots']['sfx'][0]['t'], 4)

    def test_invalid_transition_music_and_nonfinite_values_are_not_silently_coerced(self):
        original = copy.deepcopy(self.draft)
        for value in ('unsupported',):
            self.draft['shots'][0]['in']['type'] = value
            with self.assertRaises(ValueError): self.compile()
        for value in (float('nan'), float('inf'), True, -61, 100):
            self.draft = copy.deepcopy(original)
            self.draft['shots'][0]['cues'][0]['gain'] = value
            with self.subTest(value=value), self.assertRaises(ValueError): self.compile()
        self.draft = original
        self.draft['music'][0]['mood'] = 'unknown'
        with self.assertRaises(ValueError): self.compile()

    def test_compact_packet_contains_the_full_script_once_without_old_project_code(self):
        text = contract.context_text(self.packet)
        for sentence in self.plan['timing']['sentences']:
            self.assertEqual(text.count(sentence['text']), 1)
        self.assertIn('source_signature', text)
        self.assertIn('match', text)
        self.assertNotIn('gen_shots.py', text)
        self.assertNotIn('dump_words.py', text)
