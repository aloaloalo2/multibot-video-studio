import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import frame_progress  # noqa: E402
import store  # noqa: E402


class FrameProgressTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        episode, self.razgon = base / "05 Test", base / "razgon" / "05-test"
        (self.razgon / "story").mkdir(parents=True)
        (self.razgon / "scenes" / "shots").mkdir(parents=True)
        episode.mkdir()
        (episode / "razgon.json").write_text(json.dumps({"project": str(self.razgon)}))
        shots = [{"id": "e01", "start": 0, "end": 5}, {"id": "e02", "start": 5, "end": 8}, {"id": "e03", "start": 8, "end": 12}]
        (self.razgon / "story" / "shots.json").write_text(json.dumps({"shots": shots}))
        frames = [{"number": 1, "start": 0, "end": 5}, {"number": 2, "start": 5, "end": 12}]
        (self.razgon / "story" / "studio_frames.json").write_text(json.dumps({"frames": frames}))
        item = patch.object(store, "load_project", return_value={"id": "p" * 24, "episode_path": str(episode)})
        item.start()
        self.addCleanup(item.stop)
        frame_progress._CACHE.clear()

    def test_a_frame_is_drawn_once_every_shot_it_shows_has_a_scene(self):
        scene = self.razgon / "scenes" / "shots" / "e01_open.js"
        scene.write_text("take('e01', (g, t) => scene(g, t));\ntake(\"e02\", (g, t) => scene(g, t));\n")
        self.assertEqual(frame_progress.drawn("p" * 24), [1])          # frame 2 still lacks e03
        (self.razgon / "scenes" / "shots" / "e03_end.js").write_text("take( 'e03', draw);")
        self.assertEqual(frame_progress.drawn("p" * 24), [1, 2])

    def test_an_episode_without_razgon_has_no_drawn_frames(self):
        with patch.object(store, "load_project", return_value={"id": "p" * 24, "episode_path": self.tmp.name}):
            self.assertEqual(frame_progress.drawn("p" * 24), [])


if __name__ == "__main__":
    unittest.main()
