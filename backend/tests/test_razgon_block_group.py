"""A Razgon frame block is in its frame group from the moment it is added (user, 25 November 2026: «Кожен кадр має
працювати окремо»): no moment when the editor shows it as a loose row."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import store


def project():
    return {"id": "x", "tracks": [{"id": "l1", "type": "universal", "clips": []}], "scene_groups": [], "fps": 25}


def block(number):
    return {"layer_id": "l1", "kind": "animation", "content_type": "shape", "start": 0, "duration": 2,
            "title": f"Razgon · кадр {number:03d}", "opacity": 1, "color": "#000000"}


class RazgonBlockGroupTest(unittest.TestCase):
    def test_a_new_block_gets_its_own_frame_group_at_once(self):
        p = project()
        store.apply_universal_action(p, "add_clip", block(30))
        self.assertEqual([(g["title"], len(g["clip_ids"])) for g in p["scene_groups"]], [("Кадр 30", 1)])

    def test_a_block_joins_an_existing_frame_group(self):
        p = project()
        p["scene_groups"].append({"id": "g", "title": "Кадр 31", "clip_ids": [], "role": "scene"})
        store.apply_universal_action(p, "add_clip", block(31))
        self.assertEqual(len(p["scene_groups"]), 1)
        self.assertEqual(len(p["scene_groups"][0]["clip_ids"]), 1)

    def test_an_explicit_group_wins(self):
        p = project()
        p["scene_groups"].append({"id": "g", "title": "Кадр 99", "clip_ids": [], "role": "scene"})
        store.apply_universal_action(p, "add_clip", {**block(32), "group_id": "g"})
        self.assertEqual([(g["title"], len(g["clip_ids"])) for g in p["scene_groups"]], [("Кадр 99", 1)])


if __name__ == "__main__":
    unittest.main()


class BackgroundCodeUnderTextTest(unittest.TestCase):
    """A motion code that fills the frame is its background and lies under the frame's words (user, 25 November 2026:
    «124 текстовая вставка просто исчезла»)."""

    def test_under_text_puts_the_clip_below_the_frames_words(self):
        p = {"id": "x", "fps": 25, "tracks": [
            {"id": "l0", "type": "universal", "clips": [{"id": "bg", "kind": "animation", "content_type": "shape", "start": 0, "duration": 5, "title": "K001 чорний фон"}]},
            {"id": "l1", "type": "universal", "clips": [{"id": "tx", "kind": "text", "start": 0, "duration": 5, "title": "K001 кадр", "text": "a"}]}],
             "scene_groups": [{"id": "g", "title": "Кадр 1", "clip_ids": ["bg", "tx"], "role": "scene"}]}
        store.apply_universal_action(p, "add_clip", {"layer_id": "l0", "group_id": "g", "under_text": True, "kind": "animation",
                                                     "content_type": "code", "code": "function draw(){}", "start": 0, "duration": 5, "title": "K001 моушн фон"})
        self.assertEqual([t["clips"][0]["title"] for t in p["tracks"]], ["K001 чорний фон", "K001 моушн фон", "K001 кадр"])
