"""An invalid encoded output cannot overwrite an accepted narration."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import languages


class SyncedVoicePublicationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = self.root/'voice.mp3'
        self.staged = self.root/'voice-new.mp3'
        self.target.write_bytes(b'accepted previous narration')
        self.staged.write_bytes(b'candidate encoded narration')

    def test_invalid_probe_preserves_previous_output_and_staged_candidate(self):
        for actual in [None, 0, -1, float('nan'), float('inf')]:
            with self.subTest(actual=actual), patch.object(languages.store, 'media_duration', return_value=actual):
                with self.assertRaisesRegex(RuntimeError, 'перевірити тривалість'):
                    languages.publish_synced_voice(self.staged, self.target, 60)
                self.assertEqual(self.target.read_bytes(), b'accepted previous narration')
                self.assertEqual(self.staged.read_bytes(), b'candidate encoded narration')

    def test_long_or_truncated_encoded_file_does_not_replace_previous_output(self):
        for actual in [61, 59, 60.101, 59.899]:
            with self.subTest(actual=actual), patch.object(languages.store, 'media_duration', return_value=actual):
                with self.assertRaisesRegex(RuntimeError, 'не відповідає ролику'):
                    languages.publish_synced_voice(self.staged, self.target, 60)
                self.assertEqual(self.target.read_bytes(), b'accepted previous narration')
                self.assertTrue(self.staged.exists())

    def test_mp3_padding_is_allowed_and_duration_is_read_from_candidate_before_publish(self):
        def probe(path):
            self.assertEqual(path, self.staged)
            self.assertEqual(self.target.read_bytes(), b'accepted previous narration')
            return 60.048
        with patch.object(languages.store, 'media_duration', side_effect=probe) as checked:
            actual = languages.publish_synced_voice(self.staged, self.target, 60)
        self.assertEqual(actual, 60.048)
        checked.assert_called_once_with(self.staged)
        self.assertEqual(self.target.read_bytes(), b'candidate encoded narration')
        self.assertFalse(self.staged.exists())


if __name__ == '__main__':
    unittest.main()
