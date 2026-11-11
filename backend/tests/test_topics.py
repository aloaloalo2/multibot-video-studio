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
            with mock.patch.object(store, "YOUTUBE_ROOT", root / "YOUTUBE"), mock.patch.object(store, "PROJECTS_ROOT", projects), mock.patch.object(store, "DATA_ROOT", root / "data"):
                store.create_project(store.channel_id(channel), "Чому небо синє")
                path = topics.path(channel)
                text = path.read_text(encoding="utf-8")
                self.assertIn("Що буде, якщо Місяць зникне\n", text)
                self.assertIn("Чому небо синє\n", text)
                path.write_text(text + "Моя тема на потім\n", encoding="utf-8")
                self.assertEqual(topics.update(channel), [])
                text = path.read_text(encoding="utf-8")
                self.assertEqual(text.count("Чому небо синє"), 1)
                self.assertIn("Моя тема на потім", text)

    def test_migration_merges_internal_and_manual_legacy_topics_with_exact_backup(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(store, "DATA_ROOT", Path(tmp) / "data"), mock.patch.object(topics, "titles", return_value=["Новий випуск"]):
            channel = Path(tmp) / "Канал"
            channel.mkdir()
            legacy = channel / topics.FILE
            original = "# Моя примітка\r\nРучна тема\r\nСпільна тема\r\n".encode()
            legacy.write_bytes(original)
            target = topics.path(channel)
            store.atomic_text(target, "# Технічна історія\nВнутрішня тема\nСпільна тема\n")
            self.assertEqual(topics.history(channel), ["Внутрішня тема", "Спільна тема", "Ручна тема", "Новий випуск"])
            self.assertFalse(legacy.exists())
            backups = list(target.parent.glob("technical-history/*/" + topics.FILE))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), original)
            self.assertEqual(topics.update(channel), [])
            self.assertEqual(len(topics.history(channel)), 4)

    def test_failed_write_keeps_original_file(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(store, "DATA_ROOT", Path(tmp) / "data"), mock.patch.object(topics, "titles", return_value=[]):
            channel = Path(tmp) / "Канал"
            channel.mkdir()
            legacy = channel / topics.FILE
            legacy.write_text("Моя тема\n", encoding="utf-8")
            with mock.patch.object(store, "atomic_text", side_effect=OSError("Full disk")), self.assertRaises(OSError):
                topics.history(channel)
            self.assertEqual(legacy.read_text(), "Моя тема\n")

    def test_writer_reads_manual_topics_and_separates_channels(self):
        import episode_ideas
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(store, "DATA_ROOT", Path(tmp) / "data"), mock.patch.object(topics, "titles", return_value=[]):
            channel = Path(tmp) / "Канал"
            other = Path(tmp) / "Інший канал"
            channel.mkdir()
            other.mkdir()
            store.atomic_text(topics.path(channel), "# Comment\nРучна тема без проєкту\n")
            store.atomic_text(topics.path(other), "Інша історія\n")
            with mock.patch.object(store, "get_channel_folder", return_value=channel), mock.patch.object(store, "list_projects", return_value=[]), mock.patch.object(episode_ideas, "recent_scripts", return_value=[]), mock.patch.object(episode_ideas.author_rules, "for_channel", return_value={}), mock.patch.object(store, "read_channel_settings", return_value={}):
                ctx = episode_ideas.context(store.channel_id(channel))
            self.assertEqual(ctx['previous_titles'], ["Ручна тема без проєкту"])
            with self.assertRaises(ValueError):
                episode_ideas.validate_titles({'ideas': [{'title': "Ручна тема без проєкту"}] * 5}, ctx)
            self.assertEqual(topics.history(other), ["Інша історія"])


if __name__ == "__main__":
    unittest.main()
