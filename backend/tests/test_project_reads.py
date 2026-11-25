import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import project_reads
import store


class ProjectReadsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.old = store.YOUTUBE_ROOT, store.DATA_ROOT, store.PROJECTS_ROOT
        store.YOUTUBE_ROOT, store.DATA_ROOT = root / "youtube", root / "data"
        store.PROJECTS_ROOT = store.DATA_ROOT / "projects"
        channel = store.YOUTUBE_ROOT / "Channel"
        channel.mkdir(parents=True)
        (channel / "video-plan.json").write_text("{}")
        self.project = store.create_project(store.channel_id(channel), "Episode")
        self.pid = self.project["id"]
        self.video = root / "clip.mp4"
        self.video.write_bytes(b"0" * 10)
        project_reads.install()

    def tearDown(self):
        project_reads.uninstall()
        store.YOUTUBE_ROOT, store.DATA_ROOT, store.PROJECTS_ROOT = self.old
        self.temp.cleanup()

    def counted(self):
        original = project_reads._ORIGINAL
        calls = []
        def read(pid):
            calls.append(pid)
            return original(pid)
        return calls, patch.object(project_reads, "_ORIGINAL", read)

    def test_an_unchanged_project_is_read_once_and_each_reader_gets_its_own_copy(self):
        calls, reading = self.counted()
        with reading:
            first = store.load_project(self.pid)
            first["name"] = "changed by a caller"
            first["tracks"].append({"id": "mine"})
            second = store.load_project(self.pid)
        self.assertEqual(calls, [self.pid])
        self.assertEqual(second["name"], "Episode")
        self.assertNotIn({"id": "mine"}, second["tracks"])
        self.assertIsNot(second, store.load_project(self.pid))

    def test_a_saved_project_is_read_again(self):
        calls, reading = self.counted()
        with reading:
            project = store.load_project(self.pid)
            project["name"] = "Renamed"
            store.save_project(project)
            self.assertEqual(store.load_project(self.pid)["name"], "Renamed")
        self.assertEqual(len(calls), 2)

    def test_a_changed_video_or_channel_setting_reads_the_project_again(self):
        project = store.load_project(self.pid)
        project.setdefault("assets", []).append({"id": "v1", "kind": "video", "path": str(self.video)})
        store.save_project(project)
        calls, reading = self.counted()
        with reading:
            store.load_project(self.pid)
            store.load_project(self.pid)
            self.assertEqual(len(calls), 1)
            self.video.write_bytes(b"1" * 20)   # another file in the same place: its length at the seams may differ
            store.load_project(self.pid)
            self.assertEqual(len(calls), 2)
            settings = store.DATA_ROOT / "channels" / project["channel_id"] / "settings.json"
            settings.parent.mkdir(parents=True, exist_ok=True)
            settings.write_text('{"logo": {"enabled": false}}')
            store.load_project(self.pid)
            self.assertEqual(len(calls), 3)

    def test_a_deleted_project_is_not_served_from_the_cache(self):
        store.load_project(self.pid)
        project = store.read_json(store.project_path(self.pid))
        project["deleted_at"] = 1
        store.atomic_json(store.project_path(self.pid), project)
        with self.assertRaises(store.StudioError):
            store.load_project(self.pid)

    def test_uninstall_restores_the_plain_read(self):
        project_reads.uninstall()
        self.assertIsNot(store.load_project, project_reads.load_project)
        project_reads.install()
        self.assertIs(store.load_project, project_reads.load_project)


class ListedTest(ProjectReadsTest):
    def test_listed_reads_the_saved_fields_and_refuses_what_load_project_refuses(self):
        self.assertEqual(app.listed(self.pid)["name"], "Episode")
        with self.assertRaises(store.StudioError) as missing:
            app.listed("0" * 24)
        self.assertEqual(missing.exception.status, 404)
        (store.project_path(self.pid)).unlink()
        with self.assertRaises(store.StudioError) as broken:
            app.listed(self.pid)
        self.assertEqual(broken.exception.status, 500)


class StartupTest(unittest.TestCase):
    def test_startup_tasks_run_in_order_and_one_failure_does_not_stop_the_rest(self):
        done = []
        def failing():
            done.append("failing")
            raise RuntimeError("broken")
        with patch("traceback.print_exc"):
            app.run_startup([lambda: done.append("first"), failing, lambda: done.append("last")])
        self.assertEqual(done, ["first", "failing", "last"])
        self.assertTrue(app.STARTUP_STATE["done"])

    def test_migrations_come_first_and_every_former_start_up_task_is_queued(self):
        self.assertIs(app.STARTUP_TASKS[0], app.migrate_at_start)
        names = {getattr(task, "__name__", "") for task in app.STARTUP_TASKS}
        for expected in ("reset_interrupted", "restore_hidden_projects", "resume_retimes", "razgon_kit_at_start", "update_all",
                         "keep_sounds", "backfill_all", "refresh_all", "warm", "warm_project_cache", "start_automation",
                         "start_edits_queue"):
            self.assertIn(expected, names)
        order = [getattr(task, "__name__", "") for task in app.STARTUP_TASKS]
        self.assertLess(order.index("reset_interrupted"), order.index("start_edits_queue"))

    def test_a_restart_waits_while_the_projects_are_migrated_after_a_start(self):
        with patch.dict(app.STARTUP_STATE, current="migrate_at_start"), \
             patch.object(app.agent_view, "studio_status", return_value={"busy": [], "activities": [], "active_channels": []}):
            busy = app.studio_work_status([])["busy"]
        self.assertIn("перенесення службових файлів після запуску", busy)
        self.assertEqual(app.busy_words(busy), "Зараз працює перенесення файлів після запуску")


if __name__ == "__main__":
    unittest.main()
