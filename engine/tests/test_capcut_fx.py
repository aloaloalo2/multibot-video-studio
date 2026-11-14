"""A CapCut transition, an overlay effect and a picture-changing effect in a real render (needs backend/data/capcut)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE))
import capcut_fx


@unittest.skipUnless((capcut_fx.ASSETS / "transitions").is_dir(), "the CapCut packages are not installed")
class CapcutRenderTest(unittest.TestCase):
    def test_transition_overlay_and_content_effect_render(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            Image.new("RGB", (640, 360), (200, 60, 40)).save(work / "a.png")
            Image.new("RGB", (640, 360), (40, 80, 200)).save(work / "b.png")
            def img(i, src, start, dur):
                return dict(id=i, type="image", source=str(work / src), start=start, duration=dur, trim_start=0, x=.5, y=.5,
                            width=1, height=1, scale=1, opacity=1, keyframes=[], easing="linear", volume=0)
            manifest = dict(width=640, height=360, fps=25, duration=3, layer_mode="item", timeline_layers=[
                dict(id="a", z=0, clips=[img("A", "a.png", 0, 2)]), dict(id="b", z=1, clips=[img("B", "b.png", 1.5, 1.5)]),
                dict(id="t", z=1.5, clips=[dict(id="T", type="animation", content_type="capcut_transition", capcut_type="capcut_t09",
                                              start=1.5, duration=.5, capcut_a_drop=["B"], capcut_b_drop=["A"])]),
                dict(id="n", z=2, clips=[dict(id="N", type="animation", content_type="capcut_effect", capcut_effect="capcut_e03", start=0, duration=1)]),
                dict(id="c", z=3, clips=[dict(id="C", type="animation", content_type="capcut_effect", capcut_effect="capcut_e12", start=2.5, duration=.5)])])
            (work / "m.json").write_text(json.dumps(manifest))
            env = {**os.environ, "MULTIBOT_RENDER_CACHE": str(work / "cache")}
            result = subprocess.run([sys.executable, str(ENGINE / "render.py"), str(work / "m.json"), str(work / "out.mp4")],
                                    capture_output=True, text=True, env=env, timeout=600)
            self.assertEqual(result.returncode, 0, result.stdout[-800:] + result.stderr[-800:])
            raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(work / "out.mp4"), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                 capture_output=True).stdout
            def pixel(t, x=320, y=180):
                o = round(t * 25) * 640 * 360 * 3 + (y * 640 + x) * 3
                return raw[o], raw[o + 1], raw[o + 2]
            r, g, b = pixel(1.2)
            self.assertTrue(r > 150 and b < 90, (r, g, b))          # A before the seam
            r, g, b = pixel(1.8)
            self.assertTrue(b > 150 and r < 90, (r, g, b))          # «Збільшення центру»: B stands in the middle near the end
            r, g, b = pixel(1.8, 20, 20)
            self.assertTrue(r > 150 and b < 90, (r, g, b))          # and A is still around it
            r, g, b = pixel(2.8)
            self.assertTrue(g > r and g > b, (r, g, b))             # the green CRT over B


if __name__ == "__main__":
    unittest.main()
