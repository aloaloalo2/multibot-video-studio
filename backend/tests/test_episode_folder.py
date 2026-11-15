import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import episode_folder  # noqa: E402
import store  # noqa: E402


class EpisodeFolderTest(unittest.TestCase):
    """user, 15 November 2026: «зміна імені проекта… змінить назву папки? я думаю варто так зробити»"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name).resolve()
        self.old = store.YOUTUBE_ROOT, store.DATA_ROOT, store.PROJECTS_ROOT
        store.YOUTUBE_ROOT, store.DATA_ROOT = root / "youtube", root / "data"
        store.PROJECTS_ROOT = store.DATA_ROOT / "projects"
        self.channel = store.YOUTUBE_ROOT / "Канал"
        self.channel.mkdir(parents=True)
        (self.channel / "video-plan.json").write_text("{}")
        self.project = store.create_project(store.channel_id(self.channel), "Старий випуск")
        self.pid = self.project["id"]
        self.episode = Path(self.project["episode_path"])
        picture = self.episode / "кадр.png"
        picture.write_bytes(b"png")
        data = json.loads(store.project_path(self.pid).read_text())
        data["assets"] = [{"id": "a1", "name": "кадр.png", "path": str(picture)}]
        store.atomic_json(store.project_path(self.pid), data)
        # a Razgon project linked to the episode, and a JSON file that escapes its Cyrillic
        self.razgon = root / "razgon" / "projects" / "slug"
        (self.razgon / "story").mkdir(parents=True)
        (self.razgon / "story" / "studio_frames.json").write_text(json.dumps({"episode": str(self.episode)}))
        store.atomic_json(store.project_dir(self.pid) / "razgon-link.json", {"project": str(self.razgon)})
        # another episode whose name starts the same way stays as it is
        self.other = self.channel / (self.episode.name + " 2")
        self.other.mkdir()
        (store.project_dir(self.pid) / "note.txt").write_text(f"{self.other}/a.png\n", encoding="utf-8")

    def tearDown(self):
        store.YOUTUBE_ROOT, store.DATA_ROOT, store.PROJECTS_ROOT = self.old
        self.temp.cleanup()

    def rename(self, name):
        store.apply_action(self.pid, "rename_project", {"name": name}, store.load_project(self.pid)["revision"])
        with patch("language_mix.refresh_later"):
            return episode_folder.follow(self.pid)

    def test_the_folder_and_every_path_of_the_project_follow_the_new_name(self):
        result = self.rename("Новий: випуск 2")
        new = self.channel / "Новий випуск 2"
        self.assertTrue(result["moved"])
        self.assertTrue(new.is_dir())
        self.assertFalse(self.episode.exists())
        project = store.load_project(self.pid)
        self.assertEqual(project["episode_path"], str(new))
        self.assertEqual(project["assets"][0]["path"], str(new / "кадр.png"))
        self.assertTrue(Path(project["assets"][0]["path"]).is_file())
        frames = json.loads((self.razgon / "story" / "studio_frames.json").read_text())
        self.assertEqual(frames["episode"], str(new))
        self.assertEqual((store.project_dir(self.pid) / "note.txt").read_text(encoding="utf-8"), f"{self.other}/a.png\n")

    def test_a_taken_name_keeps_the_old_folder_and_says_why(self):
        (self.channel / "Зайнято").mkdir()
        result = self.rename("Зайнято")
        self.assertFalse(result["moved"])
        self.assertIn("вже є", result["note"])
        self.assertTrue(self.episode.is_dir())
        self.assertEqual(store.load_project(self.pid)["name"], "Зайнято")

    def test_a_missing_folder_only_changes_the_name(self):
        import shutil
        shutil.rmtree(self.episode)
        result = self.rename("Інша назва")
        self.assertFalse(result["moved"])
        self.assertFalse((self.channel / "Інша назва").exists())

    def test_folder_names_stay_valid(self):
        self.assertEqual(episode_folder.folder_name(" .Що: далі/потім?. "), "Що далі потім?")


if __name__ == "__main__":
    unittest.main()
