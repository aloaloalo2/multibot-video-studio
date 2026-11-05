import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

KIT = Path(__file__).resolve().parents[2] / "razgon-plugin/razgon-2d-studio-plugin/skills/make-2d-video/kit"
sys.path.insert(0, str(KIT / "tools"))
import frame_review as review
from review_dependencies import fingerprints


class ReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.proj = self.root / "projects/test"
        for folder in ("scenes", "story", "input", "assets"):
            (self.proj / folder).mkdir(parents=True)
        (self.root / "engine").mkdir()
        (self.root / "engine/core.js").write_text("export const x = 1;")
        (self.proj / "config.json").write_text('{"fps":25}')
        (self.proj / "story/shots.json").write_text(json.dumps({"shots": [
            {"id": f"s{n}", "start": (n - 1) * 10, "end": n * 10} for n in range(1, 6)]}))
        for n in range(1, 6):
            (self.proj / f"scenes/s{n}.js").write_text(f"take('s{n}', {{}});")

    def hashes(self):
        return fingerprints(self.proj, self.root, review.frames_of(self.proj))

    def test_scene_change_invalidates_only_own_and_adjacent_frames(self):
        before = self.hashes()
        (self.proj / "scenes/s3.js").write_text("take('s3', {fixed:true});")
        after = self.hashes()
        self.assertEqual([n for n in before if before[n] != after[n]], [2, 3, 4])

    def test_shared_helpers_engine_and_assets_invalidate_all(self):
        for path in (self.proj / "scenes/helper.js", self.root / "engine/core.js", self.proj / "assets/a.png"):
            before = self.hashes(); path.write_text("changed"); after = self.hashes()
            self.assertTrue(all(before[n] != after[n] for n in before))

    def test_imported_shot_module_is_also_a_dependency(self):
        (self.proj / "scenes/s1.js").write_text("import './s5.js'; take('s1', {});")
        before = self.hashes()
        (self.proj / "scenes/s5.js").write_text("take('s5', {fixed:true});")
        self.assertNotEqual(before[1], self.hashes()[1])

    def render(self, args, **kwargs):
        self.calls += 1
        out = Path(args[args.index("--dir") + 1]); out.mkdir(exist_ok=True)
        for value in args[args.index("--stills") + 1].split(","):
            Image.new("RGB", (64, 36), (20, 40, 60)).save(out / f"{value}s_{float(value):.2f}.png")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def test_unchanged_sheets_use_no_renderer_and_scoped_review_keeps_status_honest(self):
        self.calls = 0
        args = SimpleNamespace(frames="", scale=.34, all=False)
        with patch.object(review.subprocess, "run", side_effect=self.render), contextlib.redirect_stdout(io.StringIO()):
            review.sheets(self.proj, self.root, args)
            review.mark(self.proj, SimpleNamespace(frames="1-5", verdict="ok", note=""))
            self.assertEqual(review.status(self.proj), 0)
            review.sheets(self.proj, self.root, args)
            self.assertEqual(self.calls, 1)
            (self.proj / "scenes/s3.js").write_text("take('s3', {fixed:true});")
            review.sheets(self.proj, self.root, SimpleNamespace(frames="3", scale=.34, all=False))
            self.assertEqual(review.status(self.proj), 1)  # adjacent frames still need review
            review.sheets(self.proj, self.root, args)
            self.assertEqual(review.status(self.proj), 0)  # identical pixels retain the visual verdict

    def test_deleted_still_forces_render(self):
        self.calls = 0
        args = SimpleNamespace(frames="1", scale=.34, all=False)
        with patch.object(review.subprocess, "run", side_effect=self.render), contextlib.redirect_stdout(io.StringIO()):
            review.sheets(self.proj, self.root, args)
            next((self.proj / "build/review/frames").glob("*.png")).unlink()
            review.sheets(self.proj, self.root, args)
            self.assertEqual(self.calls, 2)


if __name__ == "__main__":
    unittest.main()
