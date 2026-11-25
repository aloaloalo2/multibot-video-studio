"""The processor export's shortcuts keep its pictures: bounded subpixel canvases, stills prepared once, the scene cache."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import render  # noqa: E402


class ExpressionTest(unittest.TestCase):
    def test_expressions_evaluate_as_ffmpeg_reads_them(self):
        x = render.time_expr([{"time": 0, "x": 100}, {"time": 1, "x": 300}], "x", 0, 1920, "t+0.5", False, "ease_in_out")
        self.assertEqual([render.expr_value(x, t) for t in (0, .5, 1)], [200.0, 300.0, 300.0])
        self.assertAlmostEqual(render.expr_value(x, .25), 100 + 200 * render.easing_value(.75, "ease_in_out"))
        self.assertIsNone(render.expr_value("st(0\\,1)", 0))
        self.assertIsNone(render.expr_value("__import__('os')", 0))

    def test_a_small_moving_layer_gets_a_small_canvas(self):
        x = render.time_expr([{"time": 0, "x": 100}, {"time": 1, "x": 300}], "x", 0, 1920, "t", False)
        self.assertEqual(render.subpixel_canvas(x, "50", "1", 40, 60, 0, 1, 1920, 1080, 25), (98, 48, 244, 64))
        # its corner and size are even: overlay onto a yuv420p frame would round an odd place and shift the colour planes
        self.assertEqual(render.subpixel_canvas("151", "51", "1", 40, 60, 0, 1, 1920, 1080, 25), (148, 48, 46, 66))
        # a layer that cannot be read keeps the whole frame, one never on screen a tiny one
        self.assertEqual(render.subpixel_canvas("st(0\\,t)", "0", "1", 40, 60, 0, 1, 1920, 1080, 25), (0, 0, 1920, 1080))
        self.assertEqual(render.subpixel_canvas("3000+t", "0", "1", 40, 60, 0, 1, 1920, 1080, 25), (0, 0, 2, 2))


def frames(path: Path, width: int, height: int) -> np.ndarray:
    raw = subprocess.check_output([render.FFMPEG, "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
    return np.frombuffer(raw, np.uint8).reshape(-1, height, width, 3).astype(np.int16)


class BoundedCanvasTest(unittest.TestCase):
    def test_a_bounded_canvas_draws_the_same_frames_as_the_whole_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            photo = root / "photo.jpg"
            rng = np.random.default_rng(3)
            Image.fromarray(rng.integers(0, 255, (24, 40, 3), dtype=np.uint8)).resize((800, 480), Image.BICUBIC).save(photo)
            ring = root / "ring.png"
            Image.new("RGBA", (60, 60), (255, 200, 0, 255)).save(ring)
            layers = [
                {"type": "image", "source": str(photo), "start": 0, "duration": 1.2, "position_units": "pixels", "x": 0., "y": 0.,
                 "width": 320, "height": 192, "scale_anchor": "center",
                 "keyframes": [{"time": 0, "scale": 1}, {"time": 1.2, "scale": 1.1}], "easing": "ease_in_out"},
                {"type": "image", "source": str(ring), "start": .2, "duration": 1, "position_units": "pixels", "x": 81., "y": 51.,
                 "width": 40, "height": 40, "scale_anchor": "center",
                 "keyframes": [{"time": 0, "x": 81, "y": 51, "scale": .6, "opacity": 0}, {"time": .5, "x": 95.5, "y": 52.25, "scale": 1, "opacity": 1}]},
            ]
            scene = {"type": "color", "color": "#101114", "duration": 1.2, "layers": layers}
            results = []
            for name, bounded in (("whole", False), ("bounded", True)):
                work = root / name
                work.mkdir()
                out = root / f"{name}.mp4"
                whole = lambda *args, **kwargs: (0, 0, 320, 180)
                with patch.dict(os.environ, {"MULTIBOT_EXPORT_ENCODER": "software"}), \
                        patch.object(render, "subpixel_canvas", render.subpixel_canvas if bounded else whole):
                    render.render_scene(scene, root / "p.json", out, work, 320, 180, 25, 1)
                results.append(frames(out, 320, 180))
            self.assertEqual(results[0].shape, results[1].shape)
            diff = np.abs(results[0] - results[1])
            self.assertLess(float(diff.mean()), .2)
            self.assertLess(float(np.quantile(diff, .999)), 6)


class SceneCacheTest(unittest.TestCase):
    def test_an_export_again_restores_unchanged_scenes(self):
        clips = [dict(type="animation", content_type="shape", color=color, start=start, duration=.5, x=.5, y=.5, width=1., height=1.)
                 for color, start in [("#ff0000", 0), ("#0000ff", .5)]]
        project = dict(width=320, height=180, fps=25, duration=1, timeline_layers=[dict(clips=[clip]) for clip in clips])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "p.json"
            manifest.write_text(json.dumps(project))
            calls = []
            original = render.render_scene
            env = {"MULTIBOT_GPU_EXPORT": "0", "MULTIBOT_RENDER_CACHE": str(root / "cache"), "MULTIBOT_CPU_SCENE_CACHE": "1"}
            with patch.dict(os.environ, env), patch.object(render, "render_scene", side_effect=lambda *a: (calls.append(a[-1]), original(*a))), \
                    patch.object(render, "emit"):
                render.render(manifest, root / "first.mp4")
                self.assertEqual(sorted(calls), [1, 2])
                render.render(manifest, root / "second.mp4")
                self.assertEqual(sorted(calls), [1, 2])   # nothing drawn again
                project["timeline_layers"][1]["clips"][0]["color"] = "#00ff00"
                manifest.write_text(json.dumps(project))
                render.render(manifest, root / "third.mp4")
                self.assertEqual(sorted(calls), [1, 2, 2])   # only the changed scene
            a, b = frames(root / "first.mp4", 320, 180), frames(root / "second.mp4", 320, 180)
            self.assertEqual(a.shape, b.shape)
            self.assertLess(float(np.abs(a - b).mean()), .01)
            self.assertGreater(frames(root / "third.mp4", 320, 180)[-1, 90, 160, 1], 200)


if __name__ == "__main__":
    unittest.main()
