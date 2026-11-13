import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CHECK = Path(__file__).resolve().parents[2] / 'razgon-plugin/razgon-2d-studio-plugin/skills/make-2d-video/kit/tools/direction_check.py'


class DirectionSoundPolicyTest(unittest.TestCase):
    def check(self, sound, cues=None):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'story').mkdir()
            (root/'config.json').write_text(json.dumps({'sfx': sound}))
            (root/'story/shots.json').write_text(json.dumps({'duration': 120, 'sfx': cues or [], 'shots': [
                {'id': 'shot1', 'episode': 'opening', 'start': 0, 'end': 120, 'scene': 'The presenter explains changes using objects', 'set': 'room'}]}))
            return subprocess.run([sys.executable, str(CHECK), '--project', str(root)], capture_output=True, text=True)

    def test_disabled_sound_and_empty_allowlist_do_not_demand_effects_or_ambience(self):
        for sound in ({'enabled': False}, {'enabled': True, 'allowed_names': []}):
            result = self.check(sound, [{'name': '/not-installed.wav', 't': 999}])
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertNotIn('No sound effects', result.stdout)
            self.assertNotIn('most shots need an amb bed', result.stdout)
            self.assertNotIn('Sound files missing', result.stdout)

    def test_curated_effects_do_not_require_forbidden_ambient_beds(self):
        result = self.check({'enabled': True, 'allowed_names': ['tick']})
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn('No sound effects', result.stdout)
        self.assertNotIn('most shots need an amb bed', result.stdout)
        # Legacy standalone films without a channel allowlist retain their original guidance.
        self.assertIn('most shots need an amb bed', self.check({}).stdout)

    def test_only_allowed_cues_are_checked_but_invalid_selected_timing_still_fails(self):
        sound = {'enabled': True, 'allowed_names': ['tick']}
        result = self.check(sound, [{'name': '/not-installed.wav', 't': 999}])
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        result = self.check(sound, [{'name': 'tick', 't': 999}])
        self.assertEqual(result.returncode, 1)
        self.assertIn('sound cues lie outside', result.stdout)


if __name__ == '__main__':
    unittest.main()
