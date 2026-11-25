"""A picture an agent leaves in the episode folder is copied into the studio's media; the episode folder holds only
the author's files (user, 25 November 2026: «папка кадри… сміття технічне»)."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import montage_ops
import store


class AdoptedMediaTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.episode, self.studio = root / "episode", root / "studio" / "p1"
        (self.episode / "кадри").mkdir(parents=True)
        self.studio.mkdir(parents=True)
        self.picture = self.episode / "кадри" / "frame.png"
        self.picture.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 64)
        patcher = mock.patch.object(store, "project_dir", lambda pid: self.studio)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.ctx = montage_ops.Context.__new__(montage_ops.Context)
        self.ctx.project = {"id": "p1", "episode_path": str(self.episode), "assets": []}
        self.ctx.files = []

    def tearDown(self):
        self.temp.cleanup()

    def test_a_picture_in_the_episode_folder_is_copied_into_studio_media(self):
        self.ctx.asset_for(self.picture)
        copy = self.ctx.files[0]
        self.assertTrue(store.under(copy, self.studio / "media"))
        self.assertEqual(copy.read_bytes(), self.picture.read_bytes())
        self.assertTrue(self.picture.is_file())   # the author's folder is never changed by the studio

    def test_the_same_picture_placed_twice_reuses_one_copy(self):
        self.ctx.asset_for(self.picture)
        self.ctx.asset_for(self.picture)
        self.assertEqual(len(self.ctx.files), 1)
        self.assertEqual(len(list((self.studio / "media" / "adopted").glob("*.png"))), 1)

    def test_a_file_outside_the_episode_and_studio_is_left_for_the_batch_to_refuse(self):
        outside = Path(self.temp.name) / "elsewhere.png"
        outside.write_bytes(b"\x89PNG\r\n\x1a\n")
        self.ctx.asset_for(outside)
        self.assertEqual(self.ctx.files, [outside.resolve()])


if __name__ == "__main__":
    unittest.main()
