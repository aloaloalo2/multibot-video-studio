"""Fresh channel permissions reach modern, legacy and export mixers without changing sources."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import razgon_bridge as bridge


class SoundPolicyTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / 'projects/film'
        for path in ('story', 'input', 'build'):
            (self.root / path).mkdir(parents=True)
        self.config = {'fps': 25, 'voiceover': 'input/voice.wav', 'music': {'enabled': True}, 'sfx': {'enabled': True}}
        self.story = {'duration': 2, 'sfx': [{'name': 'ding', 't': .5}, {'name': 'pop', 't': 1}],
                      'shots': [{'start': 0, 'end': 2, 'amb': {'name': 'wind'}, 'sfx': [{'name': 'ding', 'at': .7}]}]}
        bridge.write_json(self.root/'config.json', self.config)
        bridge.write_json(self.root/'story/shots.json', self.story)
        bridge.write_json(self.root/'story/studio_frames.json', {'project_id': 'p', 'studio_url': 'http://fixture'})
        self.choice = {'music': {'enabled': False}, 'effects': {'enabled': False}, 'library': {'enabled': False}}
        studio = Mock()
        studio.project.return_value = {'id': 'p', 'channel_id': 'c', 'project_kind': 'animated'}
        studio.call.side_effect = lambda *args: {'channels': [{'id': 'c', 'settings': {'sound': self.choice}}]}
        p = patch.object(bridge, 'Studio', return_value=studio)
        p.start(); self.addCleanup(p.stop)

    def assert_sources_untouched(self):
        self.assertEqual(bridge.read_json(self.root/'config.json'), self.config)
        self.assertEqual(bridge.read_json(self.root/'story/shots.json'), self.story)
        self.assertEqual(list((self.root/'build/studio').glob('sound-inputs-*')), [])

    def test_fresh_choices_override_old_config_and_filter_global_and_shot_cues(self):
        cfg, story = bridge.sound_inputs(self.root)
        self.assertFalse(cfg['music']['enabled'])
        self.assertEqual(story['sfx'], [])
        self.assertEqual(story['shots'][0]['sfx'], [])
        self.assertNotIn('amb', story['shots'][0])
        self.choice = {'music': {'enabled': True, 'generate': False}, 'effects': {'categories': ['notification']}}
        cfg, story = bridge.sound_inputs(self.root)
        self.assertFalse(cfg['music']['enabled'])  # an old mixer must not generate a missing music file
        self.assertEqual(story['sfx'], [{'name': 'ding', 't': .5}])
        self.assertEqual(story['shots'][0]['sfx'], [{'name': 'ding', 'at': .7}])
        self.assertEqual(bridge.read_json(self.root/'story/shots.json'), self.story)

    def test_snapshot_keeps_existing_file_paths_and_cleans_up_after_failure(self):
        cfg = {**self.config, 'music': {'enabled': True, 'generate': False, 'file': 'input/song.wav'}}
        before = copy.deepcopy(cfg)
        with self.assertRaisesRegex(RuntimeError, 'simulated mixer failure'):
            with bridge.sound_workspace(self.root, cfg, self.story) as prepared:
                self.assertTrue(bridge.read_json(prepared/'config.json')['music']['file'].endswith('/input/song.wav'))
                self.assertEqual(bridge.read_json(prepared/'config.json')['voiceover'], str((self.root/'input/voice.wav').resolve()))
                self.assertEqual(bridge.read_json(prepared/'story/shots.json'), self.story)
                raise RuntimeError('simulated mixer failure')
        self.assertEqual(cfg, before)
        self.assert_sources_untouched()

    def test_export_policy_supports_legacy_links_without_a_studio_url(self):
        bridge.write_json(self.root/'story/studio_frames.json', {'project_id': 'p'})
        with patch.object(bridge, 'Studio', side_effect=AssertionError('No guessed server address')):
            # A standalone legacy link retains its own config; a Studio export supplies saved channel choices.
            cfg, story = bridge.sound_inputs(self.root)
            self.assertTrue(cfg['music']['enabled'])
            cfg, story = bridge.sound_inputs(self.root, {'sound': self.choice, 'animated': True})
            self.assertFalse(cfg['music']['enabled'])
            self.assertEqual(story['sfx'], [])

    def test_legacy_mixer_receives_disabled_settings_and_filtered_story(self):
        import numpy as np
        audio = bridge.STUDIO_BACKEND.parent/'razgon-plugin/razgon-2d-studio-plugin/skills/make-2d-video/kit/audio'
        with patch.object(sys, 'path', [str(audio), *sys.path]):
            seen = []
            def main():
                prepared = Path(sys.argv[sys.argv.index('--project')+1])
                seen.append(prepared)
                self.assertFalse(bridge.read_json(prepared/'config.json')['music']['enabled'])
                self.assertEqual(bridge.read_json(prepared/'story/shots.json')['sfx'], [])
                mixer.write_wav(prepared/'build/mix_raw.wav', np.zeros((48000,2), np.float32))
            mixer = SimpleNamespace(main=main, write_wav=Mock(), subprocess=SimpleNamespace(run=Mock()),
                                    load_any=lambda path: np.zeros((48000,2), np.float32))
            self.assertIsNone(bridge._bed_from_whole_mix(self.root, mixer))
        self.assertEqual(len(seen), 1)
        self.assertFalse(seen[0].exists())
        self.assert_sources_untouched()

    def test_export_mixer_reads_fresh_permissions_instead_of_source_config(self):
        seen = []
        def run(command, **kwargs):
            if 'audio/mix.py' in command:
                prepared = Path(command[command.index('--project')+1])
                seen.append(prepared)
                self.assertNotEqual(prepared, self.root)
                self.assertFalse(bridge.read_json(prepared/'config.json')['music']['enabled'])
                self.assertEqual(bridge.read_json(prepared/'story/shots.json')['sfx'], [])
        with patch.object(bridge, 'video_frame_count', return_value=50), \
             patch.object(bridge, 'video_encoder', return_value=('-c:v', 'copy')), \
             patch.object(bridge.subprocess, 'run', side_effect=run):
            bridge.glue(self.root, {'fps': 25, 'frames': [{'start': 0, 'end': 2}]}, self.config,
                        [self.root/'build/frame.mp4'], None, self.root/'out/video.mp4')
        self.assertEqual(len(seen), 1)
        self.assertFalse(seen[0].exists())
        self.assert_sources_untouched()


if __name__ == '__main__':
    unittest.main()
