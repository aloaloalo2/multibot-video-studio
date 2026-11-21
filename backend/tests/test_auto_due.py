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


if __name__ == '__main__':
    unittest.main()
