import unittest
from unittest.mock import patch
import store

class TimedNarrationTest(unittest.TestCase):
    def test_exact_source_is_attached_once(self):
        project={"id":"test", "tracks":[]}
        source={"timing":{"status":"audio_synced","audio":{"sha256":"correct","duration":12}}}
        assets=[{"id":"wrong","kind":"audio","path":"/wrong"},{"id":"voice","kind":"audio","path":"/correct"}]
        with patch.object(store,"discover_assets",return_value=assets), patch.object(store,"audio_fingerprint",side_effect=lambda p:p.name), patch.object(store,"resolve_asset",return_value=assets[1]):
            self.assertTrue(store.attach_timed_narration(project,source))
            self.assertEqual(project["tracks"][0]["clips"][0]["asset_id"],"voice")
            self.assertFalse(store.attach_timed_narration(project,source))
            self.assertEqual(len(project["tracks"]),1)
    def test_missing_source_is_not_substituted(self):
        with patch.object(store,"discover_assets",return_value=[]):
            self.assertFalse(store.attach_timed_narration({"tracks":[]},{"timing":{"status":"audio_synced","audio":{"sha256":"missing","duration":12}}}))
