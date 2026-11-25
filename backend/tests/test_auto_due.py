import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import auto_pipeline
import published
import store


class AutoDueTest(unittest.TestCase):
    """The step the channel's automation takes shows as coming, not as a button (user, 21 November 2026: «висить кнопка
    опублікувати… а потім… запускається… вводить в оману»), and a finished run wakes the automation at once."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        patch.object(store, 'project_dir', return_value=self.root).start()
        patch.object(published, 'publishing', return_value=None).start()
        self.addCleanup(patch.stopall)

    def project(self, finished=200.0):
        return {'id': 'p', 'production_request': {'id': 'r1', 'status': 'done', 'finished_at': finished}}

    def test_export_is_due_after_frames_and_publish_after_export(self):
        since = {'auto_export': 100.0, 'auto_publish': 100.0}
        self.assertEqual(auto_pipeline.due(self.project(), {}, 0, since), 'export')
        self.assertEqual(auto_pipeline.due(self.project(), {}, 300.0, since), 'publish')
        store.atomic_json(self.root / 'auto-publish.json', {'export_at': 300.0})
        self.assertIsNone(auto_pipeline.due(self.project(), {}, 300.0, since))

    def test_nothing_is_due_for_runs_before_the_box_went_on(self):
        self.assertIsNone(auto_pipeline.due(self.project(finished=50.0), {}, 0, {'auto_export': 100.0, 'auto_publish': None}))
        self.assertIsNone(auto_pipeline.due(self.project(), {}, 0, {'auto_export': None, 'auto_publish': None}))

    def test_kick_wakes_the_loop(self):
        auto_pipeline.WAKE.clear()
        auto_pipeline.kick()
        self.assertTrue(auto_pipeline.WAKE.is_set())


class TickTest(unittest.TestCase):
    """A round reads the episodes through the list's cache and loads a whole project only to export it."""

    def test_only_the_episode_to_export_is_loaded(self):
        import json
        root = Path(tempfile.mkdtemp())
        for pid, finished in (("a", 200.0), ("b", 50.0)):
            (root / "projects" / pid).mkdir(parents=True)
            (root / "projects" / pid / "project.json").write_text(json.dumps(
                {"id": pid, "channel_id": "c", "name": pid, "production_request": {"id": "r" + pid, "status": "done", "finished_at": finished}}))
        started, loaded = [], []
        with patch.object(store, "DATA_ROOT", root), patch.object(store, "PROJECTS_ROOT", root / "projects"), \
             patch.object(store, "project_dir", side_effect=lambda pid: root / "projects" / pid), \
             patch.object(store, "list_channels", return_value=[{"id": "c"}]), \
             patch.object(store, "get_channel_folder", return_value=root), \
             patch.object(store, "read_channel_settings", return_value={"auto_export": True}), \
             patch.object(store, "upgrade_legacy_project", side_effect=lambda data: data), \
             patch.object(store, "load_project", side_effect=lambda pid: loaded.append(pid) or {"id": pid, "production_request": {"id": "r" + pid}}), \
             patch.object(store, "plan_readiness", return_value={"export_ready": True}), \
             patch.object(auto_pipeline, "_busy", return_value=False), \
             patch.object(auto_pipeline.time, "time", return_value=100.0):
            store.atomic_json(root / auto_pipeline.STATE, {"c": {"auto_export": 100.0}})
            done = auto_pipeline.tick(lambda project, confirmed, bitrate: started.append(project["id"]), lambda pid: None)
        self.assertEqual(done, ["export a"])
        self.assertEqual(loaded, ["a"])
        self.assertEqual(started, ["a"])


if __name__ == '__main__':
    unittest.main()
