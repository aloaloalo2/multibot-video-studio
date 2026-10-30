import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import store  # noqa: E402
import thumbnail_gen  # noqa: E402


class ThumbnailTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.episode = base / "What If" / "05 Test"
        self.episode.mkdir(parents=True)
        (base / "What If" / "Еталон стилю").mkdir()
        Image.new("RGB", (32, 18)).save(base / "What If" / "Еталон стилю" / "Референс кадру 1.png")
        self.project = {"id": "f" * 24, "name": "05 Test", "episode_path": str(self.episode)}
        for item in (patch.object(store, "load_project", return_value=self.project),
                     patch.object(store, "load_project_plan", return_value={"spoken_script": "Your eyes dry out."}),
                     patch.object(thumbnail_gen, "job_path", return_value=base / "job.json")):
            item.start()
            self.addCleanup(item.stop)
        thumbnail_gen.ACTIVE.clear()

    def test_defaults_take_the_first_ab_title_and_the_spoken_script(self):
        self.assertEqual(thumbnail_gen.defaults(self.project["id"])["title"], "05 Test")
        (self.episode / "Метаданные.txt").write_text("ТАЙТЛИ (3 варіанти)\n\nWhat If You Never Blinked?\nЩо, якщо...\n", encoding="utf-8")
        data = thumbnail_gen.defaults(self.project["id"])
        self.assertEqual((data["title"], data["script"], data["preview"]), ("What If You Never Blinked?", "Your eyes dry out.", False))

    def test_prompt_carries_title_wishes_script_and_the_free_corners(self):
        text = thumbnail_gen.prompt("What If?", "The script.", "big word DRY", [Path("a.png")], "Превью v2.png")
        for part in ('"What If?"', "big word DRY", "The script.", "top-right corner empty", '"Превью v2.png"', "Промпт прев'ю v2.txt", "attached reference frame"):
            self.assertIn(part, text)
        self.assertNotIn("wishes", thumbnail_gen.prompt("T", "S", "  ", [], "Превью v1.png"))

    def test_a_run_keeps_the_old_thumbnail_and_puts_the_new_one_in_place(self):
        Image.new("RGB", (16, 9), (255, 0, 0)).save(self.episode / "Превью.png")
        def codex(command, **kwargs):
            self.assertIn("-i", command)                      # the channel's style frame is attached
            Image.new("RGB", (16, 9), (0, 0, 255)).save(Path(kwargs["cwd"]) / "Превью v1.png")
            return subprocess.CompletedProcess(command, 0, "ok", "")
        thumbnail_gen.ACTIVE.add(self.project["id"])
        with patch.object(subprocess, "run", side_effect=codex):
            thumbnail_gen.run(self.project["id"], "T", "S", "")
        self.assertEqual(thumbnail_gen.state(self.project["id"])["status"], "done")
        work = self.episode / "Превью"
        self.assertEqual(Image.open(self.episode / "Превью.png").getpixel((0, 0)), (0, 0, 255))
        self.assertEqual(Image.open(work / "Превью до v1.png").getpixel((0, 0)), (255, 0, 0))
        self.assertTrue((work / "Лог генерації v1.txt").is_file())

    def test_a_run_without_a_picture_fails_and_changes_nothing(self):
        thumbnail_gen.ACTIVE.add(self.project["id"])
        with patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "quota")):
            thumbnail_gen.run(self.project["id"], "T", "S", "")
        result = thumbnail_gen.state(self.project["id"])
        self.assertEqual(result["status"], "failed")
        self.assertIn("quota", result["error"])
        self.assertFalse((self.episode / "Превью.png").exists())

    def test_start_needs_a_title_and_an_episode_folder(self):
        with self.assertRaises(store.StudioError):
            thumbnail_gen.start(self.project["id"], " ", "S")
        self.project["episode_path"] = str(self.episode / "missing")
        with self.assertRaises(store.StudioError):
            thumbnail_gen.start(self.project["id"], "T", "S")


if __name__ == "__main__":
    unittest.main()
