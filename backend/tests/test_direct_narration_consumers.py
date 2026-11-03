"""Direct montage narration stays available without a frame plan."""
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import audio_level
import language_mix
import languages
import store
import thumbnail_gen


class DirectNarrationConsumersTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.original = self.folder / "author-reference.wav"
        self.translated = self.folder / "translated.mp3"
        self.original.write_bytes(b"original")
        self.translated.write_bytes(b"translation")
        self.project = {
            "id": "p", "name": "Episode", "settings": {"plan_mode": "direct"},
            "episode_path": str(self.folder), "duration": 5,
            "assets": [{"id": "voice-id", "name": self.original.name}],
            "tracks": [{"clips": [{"id": "voice", "kind": "audio", "asset_id": "voice-id",
                                     "title": "Uploaded original", "start": 0, "duration": 5}]}],
        }
        self.source = {"script": "The author's script.", "spoken_script": "The actual narration.",
                       "timing": {"audio": {"asset_id": "voice-id", "duration": 5}, "sentences": []}}
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(store, "load_project", return_value=self.project))
        self.stack.enter_context(patch.object(store, "load_project_source", return_value=self.source))
        self.stack.enter_context(patch.object(store, "load_project_plan", side_effect=AssertionError("No frame plan in direct mode")))

    def test_gain_identifies_source_voice_by_id_without_plan_or_special_title(self):
        with patch.object(store, "resolve_asset", return_value={"path": str(self.original)}), \
             patch.object(audio_level, "measure", return_value={"lufs": -22, "peak": -9}) as measure:
            self.assertEqual(audio_level.voice_gains(self.project), {"voice-id": audio_level.gain({"lufs": -22, "peak": -9})})
        measure.assert_called_once_with(self.original)

    def test_mix_replaces_direct_source_voice_instead_of_adding_both_languages(self):
        with patch.object(languages, "load_state", return_value={"languages": {"uk": {"voice": {}}}}), \
             patch.object(languages, "translation_check", return_value={"state": "ok"}), \
             patch.object(languages, "voice_language_check", return_value={"state": "ok"}), \
             patch.object(languages, "voice_current", return_value=True), \
             patch.object(languages, "file_path", return_value=self.translated), \
             patch.object(store, "resolve_asset", side_effect=AssertionError("Original narration must be replaced")):
            result = language_mix.snapshot(self.project, "uk")
        self.assertEqual(len(result["tracks"]), 1)
        self.assertEqual(result["tracks"][0]["source"], str(self.translated))
        self.assertTrue(result["tracks"][0]["voice"])

    def test_thumbnail_uses_direct_transcription_and_pre_analysis_saved_script(self):
        with patch.object(thumbnail_gen, "state", return_value=None), \
             patch.object(thumbnail_gen, "preview", return_value=None), \
             patch.object(thumbnail_gen, "versions", return_value=[]), \
             patch.object(store, "picture_count", return_value=0):
            self.assertEqual(thumbnail_gen.defaults("p")["script"], "The actual narration.")
            self.source.clear()
            self.project["voice_script"] = {"text": "Saved script before recognition."}
            self.assertEqual(thumbnail_gen.defaults("p")["script"], "Saved script before recognition.")


if __name__ == "__main__":
    unittest.main()
