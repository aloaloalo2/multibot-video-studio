"""Each channel's own design kit (user, 25 November 2026: «кожен канал має свою унікальність»)."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.tests import test_backend as support  # noqa: F401
import channel_design  # noqa: E402
import store  # noqa: E402


class ChannelDesignTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        patcher = patch.object(store, "DATA_ROOT", Path(temp.name)); patcher.start(); self.addCleanup(patcher.stop)
        settings = patch.object(store, "read_channel_settings", return_value={}); settings.start(); self.addCleanup(settings.stop)
        folder = patch.object(store, "get_channel_folder", return_value=Path(temp.name)); folder.start(); self.addCleanup(folder.stop)

    def test_two_channels_never_share_a_kit_and_a_channel_keeps_its_own(self):
        a, b = channel_design.kit("aaa"), channel_design.kit("bbb")
        self.assertNotEqual(a["seed"], b["seed"])
        self.assertNotEqual(a["text_looks"], b["text_looks"])
        self.assertNotEqual(a["pattern"], b["pattern"])
        self.assertEqual(channel_design.kit("aaa"), a)          # kept from film to film
        # another computer: no saved kit, a fresh random seed, another design
        channel_design.path_for("aaa").unlink()
        self.assertNotEqual(channel_design.kit("aaa")["seed"], a["seed"])

    def test_films_of_one_channel_are_related_but_never_the_same(self):
        one, two = {"id": "p1", "channel_id": "ccc"}, {"id": "p2", "channel_id": "ccc"}
        self.assertEqual(channel_design.text_look(one, 3), channel_design.text_look(one, 3))   # stable in a film
        self.assertNotEqual(channel_design.text_look(one, 3), channel_design.text_look(two, 3))
        self.assertNotEqual(channel_design.pattern(one), channel_design.pattern(two))
        self.assertEqual(channel_design.pattern(one)["kind"], channel_design.pattern(two)["kind"])   # the channel's pattern
        self.assertNotEqual(channel_design.text_look(one, 3), channel_design.text_look(one, 4))      # neighbours differ

    def test_the_brief_names_the_channels_own_colours(self):
        project = {"id": "p1", "channel_id": "ddd"}
        kit = channel_design.for_project(project)
        self.assertIn(kit["palette"]["accent"], channel_design.brief(project))


if __name__ == "__main__":
    unittest.main()
