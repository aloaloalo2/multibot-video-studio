import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import store  # noqa: E402


def layer(lid, *clips):
    return {"id": lid, "name": lid, "type": "universal", "z_index": 0,
            "clips": [{"id": cid, "kind": "image", "start": 0, "duration": 1} for cid in clips]}


class LayerOrderTest(unittest.TestCase):
    def test_the_logo_stays_the_top_layer_when_frames_land_after_it(self):
        project = {"tracks": [layer("voice", "v"), layer("frame-10", "f10"), layer("logo", "l"), layer("frame-1", "f1")],
                   "scene_groups": [{"id": "g", "title": "Логотип каналу", "role": "overlay", "clip_ids": ["l"]},
                                    {"id": "s", "title": "Кадр 1", "role": "scene", "clip_ids": ["f1"]}]}
        store.recompute_universal_duration(project)
        self.assertEqual([item["id"] for item in project["tracks"]], ["voice", "frame-10", "frame-1", "logo"])
        self.assertEqual([item["z_index"] for item in project["tracks"]], [0, 1, 2, 3])

    def test_a_project_without_overlays_keeps_its_order(self):
        project = {"tracks": [layer("b", "x"), layer("a", "y")], "scene_groups": []}
        store.recompute_universal_duration(project)
        self.assertEqual([item["id"] for item in project["tracks"]], ["b", "a"])


if __name__ == "__main__":
    unittest.main()
