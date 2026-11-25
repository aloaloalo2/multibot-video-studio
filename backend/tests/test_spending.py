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


    def test_a_host_video_counts_in_the_panel_and_its_channel_after_the_project_is_deleted(self):
        # the host's HeyGen videos reached only the project cards (user, 25 November 2026: «сюди не записується нічого
        # на рахунок Хейгена»); now the panel and the channel's settings count them, deleted projects too
        project = self.root / "projects" / "p1"
        (project / "project.json").write_text(json.dumps({"id": "p1", "channel_id": "c1"}))
        frames = project / "heygen-frames"
        frames.mkdir()
        (frames / "f1.json").write_text(json.dumps({"state": "completed", "video_id": "v1", "usd_per_minute": 1.2,
                                                    "submitted_at": time.time(), "identity": {"start": 0, "end": 30}}))
        (self.root / spending.VIDEO_BACKFILLED).write_text("done")
        self.assertAlmostEqual(spending.summary()["services"]["heygen"]["day"], 0.6)
        spending.project_channels()
        shutil.rmtree(project)
        spending._CACHE.clear()
        channel = spending.channel_summary("c1")
        self.assertAlmostEqual(channel["services"]["heygen"]["month"], 0.6)
        self.assertEqual(spending.channel_summary("other")["total"]["month"], 0)

    def test_a_channel_voice_sample_is_a_charge_of_the_channel(self):
        spending.charge("heygen", 0.05, "voice-sample-x", "voice_sample", "channel:c1")
        spending.charge("heygen", 0.05, "voice-sample-x", "voice_sample", "channel:c1")   # the same sample counts once
        self.assertAlmostEqual(spending.channel_summary("c1")["services"]["heygen"]["day"], 0.05)
        self.assertAlmostEqual(spending.summary()["services"]["heygen"]["day"], 0.05)

    def test_older_videos_are_written_once_with_their_times(self):
        project = self.root / "projects" / "p1"
        (project / "project.json").write_text(json.dumps({"id": "p1", "channel_id": "c1"}))
        frames = project / "heygen-frames"
        frames.mkdir()
        (frames / "f1.json").write_text(json.dumps({"state": "submitted", "video_id": "v2", "usd_per_minute": 0.6,
                                                    "identity": {"start": 0, "end": 60}}))
        spending.backfill_videos()
        spending.backfill_videos()
        lines = [json.loads(l) for l in (self.root / spending.LEDGER).read_text().splitlines() if l.strip()]
        self.assertEqual([(l["provider"], l["identity"], l["amount"]) for l in lines], [("heygen", "video:v2", 0.6)])


if __name__ == "__main__":
    unittest.main()
