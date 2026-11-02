import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import store


class LayerEyeTest(unittest.TestCase):
    def test_a_picture_row_switches_off_and_on_a_sound_row_has_no_eye(self):
        project = {"tracks": [{"id": "l1", "type": "universal", "clips": [{"id": "c1", "kind": "image"}]},
                              {"id": "l2", "type": "universal", "clips": [{"id": "a", "kind": "audio"}]}]}
        store.apply_universal_action(project, "set_layer_hidden", {"layer_id": "l1", "hidden": True})
        self.assertTrue(project["tracks"][0]["hidden"])
        store.apply_universal_action(project, "set_layer_hidden", {"layer_id": "l1", "hidden": False})
        self.assertNotIn("hidden", project["tracks"][0])
        with self.assertRaises(store.StudioError):
            store.apply_universal_action(project, "set_layer_hidden", {"layer_id": "l2", "hidden": True})


if __name__ == "__main__":
    unittest.main()
