import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import montage_ops


class DesignedTextTest(unittest.TestCase):
    """A text frame gets a blurred picture, a veil and words with the voice (user, 5 November 2026)."""

    def ctx(self, assets, frames):
        ctx = montage_ops.Context.__new__(montage_ops.Context)
        ctx.project = {"id": "p", "assets": assets, "tracks": [{"id": "layer-1"}], "font_family": "Golos"}
        ctx.W, ctx.H, ctx.frames, ctx.actions, ctx.groups, ctx.report, ctx.easing = 1920.0, 1080.0, frames, [], {}, [], "ease_in_out"
        ctx._words = []
        return ctx

    def test_text_frame_gets_background_veil_and_timed_words(self):
        assets = [{"id": "a1", "kind": "image", "path": "/nope/photo.png"}]
        frames = [{"number": 4, "clips": [{"kind": "image", "asset_id": "a1", "width": 1, "height": 1}], "group": {"id": "g4"}}]
        ctx = self.ctx(assets, frames)
        planned = {"number": 5, "sentences": ["Врачи признают такое неудобство."],
                   "sentence_timings": [{"number": 1, "text": "Врачи признают такое неудобство.", "start": 10.0, "end": 12.0}]}
        payload = {"kind": "text", "text": "Врачи признают такое неудобство."}
        montage_ops._designed_text(ctx, planned, 5, payload, 10.0, 14.0, None)
        kinds = [a["payload"]["kind"] for a in ctx.actions]
        self.assertEqual(kinds, ["image", "animation"])
        self.assertGreater(ctx.actions[0]["payload"]["blur"], 10)
        self.assertEqual(len(payload["text_words"]), 4)
        self.assertLessEqual(payload["text_words"][0]["start"], .12)
        self.assertIn(payload["word_entrance"]["type"], montage_ops.ENTRANCES)
        self.assertEqual(set(ctx.groups.values()), {"Кадр 5"})

    def test_looks_turn_from_frame_to_frame(self):
        looks = {montage_ops.TEXT_LOOKS[n % len(montage_ops.TEXT_LOOKS)]["veil"] for n in range(5)}
        self.assertGreaterEqual(len(looks), 4)


if __name__ == "__main__":
    unittest.main()


class FrameMotionTest(unittest.TestCase):
    """Every picture and host frame moves (user, 5 November 2026)."""

    def place(self, fmt, aspect, number=7):
        import tempfile
        from PIL import Image
        folder = tempfile.mkdtemp()
        path = Path(folder) / "p.png"
        Image.new("RGB", (int(400 * aspect), 400)).save(path)
        kind = "image" if fmt != "host" else "video"
        ctx = DesignedTextTest.ctx(DesignedTextTest(), [{"id": "a", "kind": kind, "path": str(path)}], [])
        ctx.plan = {"frames": [{"number": number, "start": 10.0, "end": 16.0, "format": fmt, "sentences": ["x"]}]}
        ctx.project["fps"] = 25
        with mock.patch.object(montage_ops.store, "media_duration", return_value=60.0):
            montage_ops.place(ctx, {"frame": number, "asset_id": "a"})
        return ctx.actions

    def test_vertical_photo_moves_on_its_blurred_copy(self):
        actions = self.place("generated_photo", .75)
        self.assertEqual(len(actions), 2)
        background, photo = (a["payload"] for a in actions)
        self.assertGreater(background["blur"], 10)
        self.assertGreaterEqual(abs(photo["keyframes"][0]["scale"] - photo["keyframes"][1]["scale"]), .1)

    def test_wide_photo_drifts_or_zooms_and_host_zooms(self):
        for number in range(4):
            photo = self.place("stock_photo", 16 / 9, number)[-1]["payload"]
            a, b = photo["keyframes"]
            self.assertTrue(abs(a["scale"] - b["scale"]) >= .1 or abs(a.get("x", .5) - b.get("x", .5)) >= .1)
        host = self.place("host", 16 / 9)[-1]["payload"]
        self.assertGreaterEqual(abs(host["keyframes"][0]["scale"] - host["keyframes"][1]["scale"]), .1)


class AccentPopTest(unittest.TestCase):
    """Accents spring in and pulse once, following the photo's glued scale (user, 5 November 2026)."""

    def test_pop_follows_the_glued_scale(self):
        points = [{"time": 0.0, "x": .5, "scale": 1.0, "opacity": 0}, {"time": 2.0, "opacity": 0}, {"time": 2.29, "opacity": 1}, {"time": 8.0, "scale": 1.2}]
        out = montage_ops.pop(points, 2.04, 8.0)
        scales = {round(p["time"], 2): p["scale"] for p in out if "scale" in p}
        self.assertLess(scales[2.0], .7)
        self.assertGreater(scales[2.2], 1.1)
        self.assertAlmostEqual(scales[8.0], 1.2)
        self.assertTrue(any(abs(t - 3.49) < .01 for t in scales))   # the pulse a second later
