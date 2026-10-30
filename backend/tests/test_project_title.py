import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import store  # noqa: E402

META = "ТАЙТЛИ (3 варіанти для A/B-тесту)\n\nWhat If You Spent a Year in Space?\nЩо, якщо провести рік у космосі?\n\n=====\nОПИС\n"


class ProjectTitleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.episode = Path(self.tmp.name) / "04 A Year in Space"
        self.episode.mkdir()

    def test_the_project_follows_the_first_title_once_it_is_written(self):
        project = {"name": "04 A Year in Space", "episode_path": str(self.episode)}
        self.assertFalse(store.follow_title(project))                       # no titles yet
        (self.episode / "Метаданные.txt").write_text(META, encoding="utf-8")
        self.assertEqual(store.episode_title(self.episode), "What If You Spent a Year in Space?")
        self.assertTrue(store.follow_title(project))
        self.assertEqual(project["name"], "What If You Spent a Year in Space?")

    def test_a_name_the_author_chose_stays(self):
        (self.episode / "Метаданные.txt").write_text(META, encoding="utf-8")
        project = {"name": "Космос, мій варіант", "episode_path": str(self.episode)}
        self.assertFalse(store.follow_title(project))
        self.assertEqual(project["name"], "Космос, мій варіант")


if __name__ == "__main__":
    unittest.main()
