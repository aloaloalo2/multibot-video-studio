import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import store


class EpisodeStoreTest(unittest.TestCase):
    def test_pictures_go_to_the_episode_folder_and_frame_renders_stay_in_the_studio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channel = root / "YOUTUBE" / "Канал"
            channel.mkdir(parents=True)
            (channel / store.PLAN_CONFIG).write_text("{}", encoding="utf-8")
            with mock.patch.object(store, "YOUTUBE_ROOT", root / "YOUTUBE"), mock.patch.object(store, "PROJECTS_ROOT", root / "projects"), \
                    mock.patch.object(store, "asset_record", side_effect=lambda path, pid, source="local": {"id": path.name, "path": str(path)}):
                project = store.create_project(store.channel_id(channel), "Випуск")
                episode = Path(project["episode_path"])
                picture, render = root / "морква.png", root / "frame_001.mp4"
                picture.write_bytes(b"png"); render.write_bytes(b"mp4")
                with mock.patch.object(store, "media_kind", return_value="image"):
                    first = store.import_asset_file(project, picture)
                    second = store.import_asset_file(project, render)
                self.assertEqual(Path(first["path"]).parent, episode / "VideoKey" / "Матеріали")   # goes with the folder
                self.assertEqual(Path(second["path"]).parent, store.project_dir(project["id"]) / "media")   # the studio's cache
                # deleting the episode in the studio takes the VideoKey folder, the author's files stay
                (episode / "Сценарій.txt").write_text("текст", encoding="utf-8")
                store.delete_project(project["id"])
                self.assertFalse((episode / "VideoKey").exists())
                self.assertTrue((episode / "Сценарій.txt").exists())


    def test_a_deleted_episode_folder_hides_the_project_and_its_data_goes_after_the_grace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channel = root / "YOUTUBE" / "Канал"
            channel.mkdir(parents=True)
            (channel / store.PLAN_CONFIG).write_text("{}", encoding="utf-8")
            with mock.patch.object(store, "YOUTUBE_ROOT", root / "YOUTUBE"), mock.patch.object(store, "PROJECTS_ROOT", root / "projects"):
                gone, renamed, working = (store.create_project(store.channel_id(channel), name) for name in ("Готовий", "Перейменований", "В роботі"))
                for project in (gone, renamed, working):
                    Path(project["episode_path"]).rmdir()
                self.assertEqual(store.sweep_orphans(busy={working["id"]}, now=1000), [])
                self.assertEqual([p["name"] for p in store.list_projects()], ["В роботі"])   # the others leave the list at once
                Path(renamed["episode_path"]).mkdir()                                     # the folder comes back
                self.assertEqual(store.sweep_orphans(busy={working["id"]}, now=1000 + store.ORPHAN_GRACE), [gone["id"]])
                self.assertFalse((root / "projects" / gone["id"]).exists())
                self.assertEqual(sorted(p["name"] for p in store.list_projects()), ["В роботі", "Перейменований"])
                (root / "YOUTUBE" / "Канал").rename(root / "YOUTUBE" / "Відключений")   # a disk away deletes nothing
                self.assertEqual(store.sweep_orphans(now=10 ** 9), [])


if __name__ == "__main__":
    unittest.main()
