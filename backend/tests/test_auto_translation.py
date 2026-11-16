import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import episode_automation as automation


class AutoTranslationTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        for target, value in (("project_dir", self.dir),):
            p = patch.object(automation.store, target, return_value=value); p.start(); self.addCleanup(p.stop)
        p = patch.object(automation.store, "load_project", return_value={"id": "p", "voice_script": {"text": "Текст."}})
        p.start(); self.addCleanup(p.stop)

    def channel(self, **flags):
        p = patch.object(automation, "settings", return_value=flags); p.start(); self.addCleanup(p.stop)

    def test_the_voiced_script_goes_to_every_language_once(self):
        self.channel(auto_translation=True)
        import language_defaults, languages
        import episode_pause
        synced = {"timing": {"status": "audio_synced", "audio": {"sha256": "a"}}, "spoken_script": "Текст."}
        with patch.object(language_defaults, "apply"), patch.object(episode_pause, "paused", return_value=None), \
             patch.object(languages, "load_state", return_value={"languages": {"de": {}, "fr": {}}}), \
             patch.object(automation.store, "load_project_plan", return_value=synced), \
             patch.object(languages, "start") as start:
            automation.translate_all("p", {"script": "Текст."})
            automation.translate_all("p", {"script": "Текст."})   # a repeated event buys nothing twice
        self.assertEqual([c.args for c in start.call_args_list], [("p", "translate", "de"), ("p", "translate", "fr")])

    def test_a_plan_estimated_from_the_script_waits_for_the_voice(self):
        self.channel(auto_translation=True)
        import episode_pause, language_defaults, languages
        with patch.object(language_defaults, "apply"), patch.object(episode_pause, "paused", return_value=None), \
             patch.object(automation.store, "load_project_plan", return_value={"timing": {"status": "script_estimate"}, "spoken_script": "Текст."}), \
             patch.object(languages, "start") as start:
            automation.translate_all("p", {"script": "Текст."})
        start.assert_not_called()

    def test_off_by_default(self):
        self.channel()
        import languages
        with patch.object(languages, "start") as start:
            automation.translate_all("p", {"script": "Текст."})
            automation.after_translation("p", "de", {"kind": "translate", "status": "done"})
        start.assert_not_called()

    def test_a_done_translation_goes_on_to_its_voice(self):
        self.channel(auto_translation_voice=True)
        import episode_pause, languages
        with patch.object(episode_pause, "paused", return_value=None), \
             patch.object(languages, "read_text", return_value="Text."), patch.object(languages, "start") as start:
            automation.after_translation("p", "de", {"kind": "translate", "status": "failed"})
            automation.after_translation("p", "de", {"kind": "translate", "status": "done"})
        start.assert_called_once_with("p", "voice", "de")


if __name__ == "__main__":
    unittest.main()
