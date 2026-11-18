"""The limits panel's spending: one studio-wide journal that outlives deleted projects (18 November 2026)."""
import json
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import project_costs
import spending
import store


class SpendingTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        for item in (patch.object(store, "DATA_ROOT", self.root), patch.object(store, "PROJECTS_ROOT", self.root / "projects"),
                     patch.object(spending, "openrouter", return_value={"day": 0.5, "week": 1.0, "month": 2.0})):
            item.start()
            self.addCleanup(item.stop)
        spending._CACHE.clear()
        (self.root / "projects" / "p1").mkdir(parents=True)
        (self.root / spending.BACKFILLED).write_text("done")

    def test_a_charge_counts_after_its_project_is_deleted_and_only_once(self):
        project = self.root / "projects" / "p1"
        project_costs.record_at(project, "heygen", 0.25, identity="take-1", category="narration")
        project_costs.record_at(project, "heygen", 0.25, identity="take-1", category="narration")   # the same take again
        shutil.rmtree(project)
        result = spending.summary()
        self.assertEqual(result["services"]["heygen"]["day"], 0.25)
        self.assertEqual(result["total"]["day"], 0.75)   # OpenRouter's 0.5 from its account

    def test_older_receipts_are_brought_in_once(self):
        (self.root / spending.BACKFILLED).unlink()
        receipts = self.root / "projects" / "p1" / "narration" / "receipts"
        receipts.mkdir(parents=True)
        (receipts / "narration-a.json").write_text(json.dumps({"identity": "narration-a", "provider": "heygen", "amount": 0.4, "created_at": time.time()}))
        self.assertEqual(spending.summary()["services"]["heygen"]["month"], 0.4)
        spending._CACHE.clear()
        self.assertEqual(spending.summary()["services"]["heygen"]["month"], 0.4)
        self.assertTrue((self.root / spending.BACKFILLED).exists())


if __name__ == "__main__":
    unittest.main()
