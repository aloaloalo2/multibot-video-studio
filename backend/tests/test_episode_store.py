import json
import subprocess
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


    def test_a_project_stays_in_the_studio_when_its_episode_folder_is_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channel = root / "YOUTUBE" / "Канал"
            channel.mkdir(parents=True)
            (channel / store.PLAN_CONFIG).write_text("{}", encoding="utf-8")
            with mock.patch.object(store, "YOUTUBE_ROOT", root / "YOUTUBE"), mock.patch.object(store, "PROJECTS_ROOT", root / "projects"):
                project = store.create_project(store.channel_id(channel), "Готовий")
                Path(project["episode_path"]).rmdir()
                self.assertEqual([p["name"] for p in store.list_projects()], ["Готовий"])
                # a project an earlier version hid for its missing folder is listed again and loses the mark
                hidden = store.load_project(project["id"]); hidden["episode_gone_at"] = 1000; store.save_project(hidden)
                self.assertEqual([p["name"] for p in store.list_projects()], ["Готовий"])
                self.assertEqual(store.restore_hidden_projects(), [project["id"]])
                self.assertNotIn("episode_gone_at", store.load_project(project["id"]))

    def test_a_deleted_episode_keeps_its_razgon_link_and_its_sound(self):
        import keep, shutil
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channel = root / "YOUTUBE" / "Канал"
            channel.mkdir(parents=True)
            (channel / store.PLAN_CONFIG).write_text("{}", encoding="utf-8")
            with mock.patch.object(store, "YOUTUBE_ROOT", root / "YOUTUBE"), mock.patch.object(store, "PROJECTS_ROOT", root / "projects"):
                project = store.create_project(store.channel_id(channel), "Анімація")
                episode = Path(project["episode_path"])
                razgon = root / "razgon" / "projects" / "film"
                razgon.mkdir(parents=True)
                (episode / "razgon.json").write_text(json.dumps({"razgon_root": str(razgon.parents[1]), "project": str(razgon)}))
                self.assertEqual(store.razgon_link(project)["project"], str(razgon))      # read once: kept in the studio
                voice = episode / "voice.wav"
                subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", "sine=d=1", str(voice)], check=True)
                project = store.load_project(project["id"])
                project["assets"] = [{"id": "a" * 20, "kind": "audio", "path": str(voice)}]
                project["tracks"][0]["clips"] = [{"id": "c1", "kind": "audio", "asset_id": "a" * 20, "start": 0, "duration": 1}]
                store.save_project(project)
                self.assertEqual(keep.keep_project(project["id"]), 1)
                shutil.rmtree(episode)                                                 # the author deletes the folder
                self.assertEqual(store.razgon_link(project)["project"], str(razgon))
                kept = store.resolve_asset(project, "a" * 20)
                self.assertTrue(kept["kept"] and kept["path"].endswith(".m4a") and Path(kept["path"]).is_file())


if __name__ == "__main__":
    unittest.main()
