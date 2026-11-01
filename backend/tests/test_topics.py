import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import store
import topics


class TopicsTest(unittest.TestCase):
    def test_titles_are_appended_once_and_hand_lines_stay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channel = root / "YOUTUBE" / "Канал"
            old = channel / "Старий випуск"
            old.mkdir(parents=True)
            (channel / store.PLAN_CONFIG).write_text("{}", encoding="utf-8")
            (old / "Метаданные.txt").write_text("ТАЙТЛ\nЩо буде, якщо Місяць зникне\n", encoding="utf-8")
            projects = root / "projects"
            with mock.patch.object(store, "YOUTUBE_ROOT", root / "YOUTUBE"), mock.patch.object(store, "PROJECTS_ROOT", projects):
                store.create_project(store.channel_id(channel), "Чому небо синє")
                path = channel / topics.FILE
                text = path.read_text(encoding="utf-8")
                self.assertIn("Що буде, якщо Місяць зникне\n", text)
                self.assertIn("Чому небо синє\n", text)
                path.write_text(text + "Моя тема на потім\n", encoding="utf-8")
                self.assertEqual(topics.update(channel), [])
                text = path.read_text(encoding="utf-8")
                self.assertEqual(text.count("Чому небо синє"), 1)
                self.assertIn("Моя тема на потім", text)


if __name__ == "__main__":
    unittest.main()
