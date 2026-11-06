import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import store


class ChannelOrderTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.channels = [{"id": name, "name": name} for name in ["a", "b", "c"]]
        for item in (patch.object(store, "DATA_ROOT", root),
                     patch.object(store, "channel_folders", side_effect=lambda: self.channels),
                     patch.object(store, "channel_record", side_effect=lambda record: dict(record))):
            item.start()
            self.addCleanup(item.stop)

    def ids(self):
        return [channel["id"] for channel in store.list_channels()]

    def test_saved_order_survives_new_reads(self):
        self.assertEqual(self.ids(), ["a", "b", "c"])
        store.reorder_channels(["c", "a", "b"])
        self.assertEqual(self.ids(), ["c", "a", "b"])
        self.assertEqual(store.read_json(store.DATA_ROOT / "channel-order.json"), ["c", "a", "b"])

    def test_new_channels_append_and_removed_channels_are_ignored(self):
        store.reorder_channels(["c", "a", "b"])
        self.channels[:] = [{"id": name, "name": name} for name in ["a", "c", "d"]]
        self.assertEqual(self.ids(), ["c", "a", "d"])

    def test_invalid_or_stale_order_does_not_replace_saved_order(self):
        store.reorder_channels(["c", "a", "b"])
        for ids in (["a", "a", "c"], ["a", "b"], ["a", "b", "unknown"], "abc", [1, 2, 3]):
            with self.subTest(ids=ids), self.assertRaises(store.StudioError):
                store.reorder_channels(ids)
            self.assertEqual(self.ids(), ["c", "a", "b"])
