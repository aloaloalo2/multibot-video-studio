import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import razgon_sync


class RazgonHomeTest(unittest.TestCase):
    def test_the_working_copy_moves_into_the_studio_and_links_follow(self):
        with tempfile.TemporaryDirectory() as tmp:
            youtube = Path(tmp)
            old, studio = youtube / "What If" / "razgon-2d-studio", youtube / "VideoKey Studio"
            (old / "projects" / "film").mkdir(parents=True)
            (old / "render.mjs").write_text("//", encoding="utf-8")
            studio.mkdir()
            episode = youtube / "What If" / "Епізод 1"
            episode.mkdir()
            (episode / "razgon.json").write_text(json.dumps({"razgon_root": str(old), "project": str(old / "projects" / "film"), "fps": 25}))
            (youtube / "What If" / "AGENTS.md").write_text("Анімація в What If/razgon-2d-studio/projects.", encoding="utf-8")
            new = studio / "razgon-2d-studio"
            self.assertTrue(razgon_sync.move_home(old, new, youtube))
            self.assertFalse(old.exists())
            self.assertTrue((new / "projects" / "film").is_dir())
            link = json.loads((episode / "razgon.json").read_text())
            self.assertEqual((link["razgon_root"], link["project"], link["fps"]), (str(new), str(new / "projects" / "film"), 25))
            self.assertIn("VideoKey Studio/razgon-2d-studio/projects", (youtube / "What If" / "AGENTS.md").read_text(encoding="utf-8"))
            self.assertFalse(razgon_sync.move_home(old, new, youtube))   # once only


if __name__ == "__main__":
    unittest.main()
