"""Every window that asks for the script's length starts from the author's last number (user, 27 November 2026:
«кількість слів запоминалась… навіть якщо я проект удалюю»)."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import episode_ideas  # noqa: E402
import store  # noqa: E402


class ScriptWordsTest(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(store, "DATA_ROOT", Path(self.work.name))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.work.cleanup()

    def test_the_last_number_wins_over_the_average(self):
        samples = [{"words": 1000}, {"words": 3000}]
        self.assertEqual(episode_ideas.recommended_length("c1", samples)["target_words"], 2000)
        episode_ideas.remember_words("c1", 2600)
        self.assertEqual(episode_ideas.recommended_length("c1", samples)["target_words"], 2600)

    def test_a_channel_without_its_own_number_takes_the_latest_of_any(self):
        episode_ideas.remember_words("c1", 1800)
        self.assertEqual(episode_ideas.last_words("c2"), 1800)
        episode_ideas.remember_words("c2", 3200)
        self.assertEqual(episode_ideas.last_words("c1"), 1800)
        self.assertEqual(episode_ideas.last_words("c2"), 3200)

    def test_a_number_out_of_range_is_not_kept(self):
        episode_ideas.remember_words("c1", 50)
        episode_ideas.remember_words("c1", "2000")
        self.assertIsNone(episode_ideas.last_words("c1"))

    def test_it_lives_apart_from_the_projects(self):
        episode_ideas.remember_words("c1", 2400)
        self.assertTrue((Path(self.work.name) / "channels" / "c1" / "script-words.json").is_file())
        self.assertFalse((Path(self.work.name) / "projects").exists())


if __name__ == "__main__":
    unittest.main()
