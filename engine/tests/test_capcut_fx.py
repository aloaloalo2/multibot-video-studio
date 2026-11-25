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


class NearTest(unittest.TestCase):
    """A seam is drawn from the clips near it, not the whole film."""
    def layers(self, transition=None):
        clip = lambda i, start, dur, **extra: dict(id=i, type="image", start=start, duration=dur, **extra)
        return [dict(id="bg", z=0, clips=[clip("long", 0, 600)]),
                dict(id="a", z=1, clips=[clip("far", 10, 3, transition=transition or {"type": "cut", "duration": 0}),
                                         clip("A", 296, 4), clip("B", 300, 4)]),
                dict(id="c", z=2, clips=[clip("later", 310, 3)])]

    def test_only_clips_reaching_the_window_stay(self):
        near = capcut_fx._near(self.layers(), 300, 300.7)
        self.assertEqual([[c["id"] for c in layer["clips"]] for layer in near], [["long"], ["A", "B"]])

    def test_a_film_with_fades_between_clips_stays_whole(self):
        layers = self.layers({"type": "crossfade", "duration": .5})
        self.assertIs(capcut_fx._near(layers, 300, 300.7), layers)

    def test_layers_keep_their_place_after_the_others_are_dropped(self):
        stripped = capcut_fx._strip([dict(id="x", clips=[dict(id="X", type="image", start=0, duration=1)]),
                                     dict(id="y", clips=[dict(id="Y", type="image", start=0, duration=1)])], set())
        self.assertEqual([layer["z"] for layer in stripped], [0.0, 1.0])


@unittest.skipUnless((capcut_fx.ASSETS / "effects").is_dir(), "the CapCut packages are not installed")
class PreviewTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("MULTIBOT_STUDIO_DATA")
        os.environ["MULTIBOT_STUDIO_DATA"] = self.temp.name

    def tearDown(self):
        if self.old is None:
            os.environ.pop("MULTIBOT_STUDIO_DATA", None)
        else:
            os.environ["MULTIBOT_STUDIO_DATA"] = self.old
        self.temp.cleanup()

    def test_effects_that_change_the_frame_have_a_library_preview(self):
        # «Ковзне тремтіння», «Скляний браслет» and «Зелений CRT» had no loop length and answered 500
        for name in ("capcut_e07", "capcut_e08", "capcut_e12", "capcut_e03"):
            path = capcut_fx.effect_preview(name, 160, 90)
            self.assertGreater(path.stat().st_size, 0, name)

    def test_the_last_frame_of_a_transition_shows_the_incoming_side(self):
        # 0.35 s and 0.7 s at 25 fps from a seam between whole frames: 9 and 18 frames, the last one the incoming side
        work = Path(self.temp.name)
        for colour, name in (("red", "a"), ("blue", "b")):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={colour}:s=320x180:r=25:d=1",
                            "-pix_fmt", "yuv420p", str(work / f"{name}.mp4")], check=True)
        worker = capcut_fx._Worker.get(320, 180)
        entry = capcut_fx.TRANSITIONS["capcut_t09"]
        for frames in (9, 18):
            out = work / f"t-{frames}.mp4"
            worker.run({"codec": "mp4", "mode": "transition", "index": 8, "fps": 25, "frames": frames,
                        "package": str(capcut_fx.package("capcut_transition", entry)), "comp": entry["default_duration"],
                        "a_video": str(work / "a.mp4"), "b_video": str(work / "b.mp4"), "out": str(out),
                        "out_width": 320, "out_height": 180})
            raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(out), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                 capture_output=True).stdout
            self.assertEqual(len(raw), frames * 320 * 180 * 3)
            o = (frames - 1) * 320 * 180 * 3 + (90 * 320 + 160) * 3
            self.assertTrue(raw[o + 2] > 150 and raw[o] < 90, (frames, raw[o:o + 3]))
        self.assertIs(capcut_fx._Worker.get(320, 180), worker)   # one worker serves every transition of a render


if __name__ == "__main__":
    unittest.main()
