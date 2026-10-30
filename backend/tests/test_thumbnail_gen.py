import json
import shutil
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
        (base / "What If" / "Еталон стилю" / "Еталон промпт прев'ю.txt").write_text('YouTube thumbnail for "DAY 365".', encoding="utf-8")
        self.project = {"id": "f" * 24, "name": "05 Test", "episode_path": str(self.episode)}
        self.studio = base / "studio"                     # the studio's own project folder
        self.studio.mkdir()
        for item in (patch.object(store, "load_project", return_value=self.project),
                     patch.object(store, "load_project_plan", return_value={"spoken_script": "Your eyes dry out."}),
                     patch.object(thumbnail_gen, "job_path", return_value=base / "job.json"),
                     patch.object(store, "project_dir", return_value=self.studio),
                     patch.object(thumbnail_gen.director, "executable", return_value=Path("claude"))):
            item.start()
            self.addCleanup(item.stop)
        thumbnail_gen.ACTIVE.clear()

    def test_defaults_take_the_first_ab_title_and_the_spoken_script(self):
        self.assertEqual(thumbnail_gen.defaults(self.project["id"])["title"], "05 Test")
        (self.episode / "Метаданные.txt").write_text("ТАЙТЛИ (3 варіанти)\n\nWhat If You Never Blinked?\nЩо, якщо...\n", encoding="utf-8")
        data = thumbnail_gen.defaults(self.project["id"])
        self.assertEqual((data["title"], data["script"], data["preview"]), ("What If You Never Blinked?", "Your eyes dry out.", False))

    def test_claude_gets_the_title_wishes_script_and_the_channels_approved_prompts(self):
        refs = thumbnail_gen.references(self.episode)
        text = thumbnail_gen.brief("What If?", "The script.", "big word DRY", self.episode, refs)
        for part in ('"What If?"', "big word DRY", "The script.", "правий верхній кут порожній", 'thumbnail for "DAY 365"', "Референс кадру 1.png", "тільки самим промптом"):
            self.assertIn(part, text)
        self.assertNotIn("Побажання автора", thumbnail_gen.brief("T", "S", "  ", self.episode, refs))
        drawing = thumbnail_gen.drawing("A neon close-up.", "Превью v2.png")
        self.assertTrue(drawing.startswith("A neon close-up."))
        self.assertIn('"Превью v2.png"', drawing)

    def tools(self, picture=True, answer=None):
        """Claude Code answers with a prompt, Codex saves the picture; each call is recorded."""
        self.calls = []
        def run(command, **kwargs):
            self.calls.append((command, kwargs))
            if command[0] == "claude":
                reply = answer or {"result": "A neon close-up of the frozen hero. " * 8, "total_cost_usd": 0.2}
                return subprocess.CompletedProcess(command, 0, json.dumps(reply), "")
            self.assertIn("-i", command)                      # the channel's style frame is attached
            if picture:
                Image.new("RGB", (16, 9), (0, 0, 255)).save(Path(kwargs["cwd"]) / "Превью v1.png")
            return subprocess.CompletedProcess(command, 0 if picture else 1, "ok", "" if picture else "quota")
        return patch.object(subprocess, "run", side_effect=run)

    def test_a_run_keeps_the_old_thumbnail_and_puts_the_new_one_in_place(self):
        Image.new("RGB", (16, 9), (255, 0, 0)).save(self.episode / "Превью.png")
        thumbnail_gen.ACTIVE.add(self.project["id"])
        with self.tools():
            thumbnail_gen.run(self.project["id"], "T", "S", "")
        (claude, _), (codex, sent) = self.calls
        self.assertIn("--allowedTools", claude)
        self.assertIn(str(self.studio / "preview"), claude)                             # Claude may read the stills there
        self.assertTrue(sent["input"].startswith("A neon close-up of the frozen hero."))   # Codex draws Claude's prompt
        self.assertEqual(thumbnail_gen.state(self.project["id"])["status"], "done")
        kept = self.studio / "preview"                                                  # the studio's own copy
        self.assertEqual(Image.open(kept / "Превью.png").getpixel((0, 0)), (0, 0, 255))
        self.assertEqual(Image.open(kept / "Превью до v1.png").getpixel((0, 0)), (255, 0, 0))
        self.assertTrue((kept / "Лог генерації v1.txt").is_file())
        # the episode folder gets its copy and the prompt, as the channel rules ask
        self.assertEqual(Image.open(self.episode / "Превью.png").getpixel((0, 0)), (0, 0, 255))
        self.assertTrue((self.episode / "Превью" / "Промпт прев'ю v1.txt").read_text(encoding="utf-8").startswith("A neon close-up"))

    def test_the_thumbnail_outlives_the_episode_folder(self):
        Image.new("RGB", (16, 9), (0, 200, 0)).save(self.episode / "Превью.jpg")
        kept = thumbnail_gen.preview(self.project)                                     # copied in on first sight
        self.assertEqual(kept, self.studio / "preview" / "Превью.png")
        shutil.rmtree(self.episode)
        self.assertEqual(thumbnail_gen.preview(self.project), kept)
        self.assertEqual(Image.open(kept).getpixel((0, 0))[1], 200)
        self.assertEqual(thumbnail_gen.defaults(self.project["id"])["title"], "05 Test")
        self.made_frames(2)
        thumbnail_gen.ACTIVE.clear()
        with self.tools():
            thumbnail_gen.run(self.project["id"], "T", "S", "")                           # a new one is made without it
        self.assertEqual(thumbnail_gen.state(self.project["id"])["status"], "done")
        self.assertFalse(self.episode.exists())

    def test_a_run_without_a_picture_fails_and_changes_nothing(self):
        thumbnail_gen.ACTIVE.add(self.project["id"])
        with self.tools(picture=False):
            thumbnail_gen.run(self.project["id"], "T", "S", "")
        result = thumbnail_gen.state(self.project["id"])
        self.assertEqual(result["status"], "failed")
        self.assertIn("quota", result["error"])
        self.assertFalse((self.episode / "Превью.png").exists())
        self.assertFalse((self.studio / "preview" / "Превью.png").exists())

    def test_the_claude_limit_stops_the_run_before_codex(self):
        thumbnail_gen.ACTIVE.add(self.project["id"])
        limit = {"is_error": True, "api_error": "usage_limit_reached", "result": "You've hit your session limit · resets 3pm"}
        with self.tools(answer=limit):
            thumbnail_gen.run(self.project["id"], "T", "S", "")
        self.assertEqual(len(self.calls), 1)
        self.assertIn("оновиться о 15:00", thumbnail_gen.state(self.project["id"])["error"])

    def made_frames(self, count):
        media = Path(self.tmp.name) / "media"
        media.mkdir(exist_ok=True)
        self.project["assets"], clips = [], []
        for number in range(1, count + 1):
            Image.new("RGB", (16, 9), (number * 20, 0, 0)).save(media / f"frame_{number:03d}.png")
            self.project["assets"].append({"id": f"a{number}", "path": str(media / f"frame_{number:03d}.png")})
            clips.append({"kind": "image", "asset_id": f"a{number}", "start": number * 10, "duration": 10, "title": f"Razgon · кадр {number:03d}"})
        clips.append({"kind": "image", "asset_id": "logo", "start": 0, "duration": 99, "title": "Логотип каналу"})
        self.project["tracks"] = [{"clips": clips}]

    def test_the_video_s_own_frames_are_the_style_reference(self):
        self.made_frames(5)
        work = Path(self.tmp.name) / "work"
        work.mkdir()
        stills = thumbnail_gen.frame_stills(self.project, work)
        self.assertEqual([path.name for path in stills], ["Кадр ролику 1.png", "Кадр ролику 2.png", "Кадр ролику 3.png"])
        self.assertEqual([Image.open(path).getpixel((0, 0))[0] for path in stills], [20, 60, 100])   # first, middle, last

    def test_start_needs_a_title_and_two_made_frames(self):
        with self.assertRaises(store.StudioError):
            thumbnail_gen.start(self.project["id"], " ", "S")
        self.made_frames(1)
        with self.assertRaises(store.StudioError) as caught:
            thumbnail_gen.start(self.project["id"], "T", "S")
        self.assertEqual(caught.exception.status, 409)
        self.made_frames(2)


if __name__ == "__main__":
    unittest.main()
