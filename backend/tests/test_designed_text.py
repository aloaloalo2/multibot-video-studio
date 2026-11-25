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
        ctx._words, ctx.files = [], []
        return ctx

    def test_text_frame_gets_background_veil_and_timed_words(self):
        assets = [{"id": "a1", "kind": "image", "path": "/nope/photo.png"}]
        frames = [{"number": 4, "clips": [{"kind": "image", "asset_id": "a1", "width": 1, "height": 1}], "group": {"id": "g4"}}]
        ctx = self.ctx(assets, frames)
        planned = {"number": 5, "sentences": ["Врачи признают такое неудобство."],
                   "sentence_timings": [{"number": 1, "text": "Врачи признают такое неудобство.", "start": 10.0, "end": 12.0}]}
        payload = {"kind": "text", "text": "Врачи признают такое неудобство."}
        montage_ops._designed_text(ctx, planned, 5, payload, 10.0, 14.0, None, {"backdrop": "blur"})
        kinds = [a["payload"]["kind"] for a in ctx.actions]
        self.assertEqual(kinds, ["image", "animation"])
        self.assertGreater(ctx.actions[0]["payload"]["blur"], 10)
        self.assertEqual(len(payload["text_words"]), 4)
        self.assertLessEqual(payload["text_words"][0]["start"], .12)
        self.assertIn(payload["word_entrance"]["type"], montage_ops.TEXT_ENTRANCES)
        self.assertEqual(set(ctx.groups.values()), {"Кадр 5"})

    def test_text_with_no_picture_yet_holds_the_frame_from_its_start(self):
        ctx = self.ctx([], [])
        planned = {"number": 5, "sentences": ["Врачи признают такое неудобство."],
                   "start": 10.0, "end": 14.0, "format": "text",
                   "sentence_timings": [{"number": 1, "text": "Врачи признают такое неудобство.", "start": 10.6, "end": 12.0}]}
        ctx.plan = {"frames": [planned]}
        montage_ops.place(ctx, {"frame": 5, "text": True, "backdrop": "blur"})
        field, payload = (action["payload"] for action in ctx.actions)
        self.assertEqual((field["kind"], field["start"], field["duration"]), ("animation", 10.0, 4.0))
        self.assertEqual((field["color"], field["opacity"], field["width"], field["height"]), ("#000000", 1, 1, 1))
        self.assertEqual(set(ctx.groups.values()), {"Кадр 5"})
        self.assertLessEqual(payload["text_words"][0]["start"], .15)              # the text itself still starts with its word
        self.assertGreaterEqual(payload["start"], 10.5)

    def backdrop_of(self, ctx, number, spec=None, start=10.0):
        planned = {"number": number, "sentences": ["Врачи признают такое неудобство."],
                   "sentence_timings": [{"number": 1, "text": "Врачи признают такое неудобство.", "start": start + .5, "end": start + 2}]}
        payload = {"kind": "text", "text": "Врачи признают такое неудобство."}
        montage_ops._designed_text(ctx, planned, number, payload, start, start + 4, None, spec)
        return payload

    def test_backdrops_differ_from_one_text_frame_to_the_next(self):
        """User, 21 November 2026: «для текстових вставок не має бути шаблонності»: the host's video under black 59%,
        a blurred picture, or a grid with noise; the next text frame takes another backdrop and another entrance."""
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            video = Path(root) / "host.mp4"
            video.write_bytes(b"x")
            assets = [{"id": "a1", "kind": "image", "path": "/nope/photo.png"}, {"id": "v", "kind": "video", "path": str(video)}]
            frames = [{"number": n, "clips": [{"kind": "image", "asset_id": "a1", "width": 1, "height": 1}], "group": {"id": f"g{n}"}} for n in (4, 6, 8)]
            ctx = self.ctx(assets, frames)
            ctx.plan = {"timing": {"audio": {"asset_id": "v"}}}
            with mock.patch.object(montage_ops.store, "media_duration", return_value=900.0), \
                    mock.patch.object(montage_ops.store, "media_dir", return_value=Path(root)):
                first = self.backdrop_of(ctx, 5, {"backdrop": "host"})
                host = [a["payload"] for a in ctx.actions]
                self.assertEqual([c["kind"] for c in host], ["video", "animation"])
                self.assertEqual((host[0]["trim_start"], host[0]["volume"], host[1]["opacity"], host[1]["color"]), (10.0, 0, .59, "#000000"))
                self.assertEqual((first["color"], first["word_entrance"]["type"]), ("#ffffff", "letters_fade"))
                ctx.actions = []
                second = self.backdrop_of(ctx, 7, start=20.0)
                self.assertNotEqual(ctx.text_choices[7][0], "host")
                self.assertNotEqual(second["word_entrance"]["type"], "letters_fade")
                ctx.actions = []
                self.backdrop_of(ctx, 9, {"backdrop": "grid"}, start=30.0)
                grid = [a["payload"] for a in ctx.actions]
                self.assertEqual([(c["kind"], c.get("content_type")) for c in grid], [("image", None)])   # the grid alone, no noise
                # the channel's own pattern (channel_design), not one grid shared by every channel
                self.assertEqual(len(list((Path(root) / "text-backdrops").glob("pattern-*-1920x1080.png"))), 1)
        with self.assertRaises(montage_ops.OpError):
            self.backdrop_of(self.ctx([], []), 3, {"backdrop": "rainbow"})

    def test_looks_turn_from_frame_to_frame(self):
        looks = {montage_ops.TEXT_LOOKS[n % len(montage_ops.TEXT_LOOKS)]["veil"] for n in range(5)}
        self.assertGreaterEqual(len(looks), 4)


if __name__ == "__main__":
    unittest.main()


class FrameMotionTest(unittest.TestCase):
    """Every picture and host frame moves (user, 5 November 2026)."""

    def place(self, fmt, aspect, number=7, motion=None):
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
            montage_ops.place(ctx, {"frame": number, "asset_id": "a", **({"motion": motion} if motion else {})})
        return ctx.actions

    def test_vertical_photo_moves_on_its_blurred_copy(self):
        actions = self.place("generated_photo", .75, motion="zoom_in")
        self.assertEqual(len(actions), 3)
        backing, background, photo = (a["payload"] for a in actions)
        self.assertEqual((backing["color"], backing["opacity"], backing["start"], backing["duration"]), ("#000000", 1, 10.0, 6.0))
        self.assertGreater(background["blur"], 10)
        self.assertNotIn("keyframes", background)   # the copy behind stands still
        self.assertGreaterEqual(abs(photo["keyframes"][0]["scale"] - photo["keyframes"][1]["scale"]), .1)

    def test_the_agent_names_the_move(self):
        for number, name in enumerate(("zoom_in", "pan_right", "zoom_out", "pan_left")):
            photo = self.place("stock_photo", 16 / 9, number, motion=name)[-1]["payload"]
            a, b = photo["keyframes"]
            self.assertTrue(abs(a["scale"] - b["scale"]) >= .1 or abs(a.get("x", .5) - b.get("x", .5)) >= .1)
        host = self.place("host", 16 / 9, motion="zoom_in")[-1]["payload"]
        self.assertGreaterEqual(abs(host["keyframes"][0]["scale"] - host["keyframes"][1]["scale"]), .1)

    def test_the_studio_moves_nothing_by_itself(self):
        """User, 8 November 2026: «прибери в студії взагалі можливість самій змінювати рух… це має робити режисер»."""
        for fmt, aspect in (("generated_photo", 16 / 9), ("generated_photo", .75), ("stock_video", 16 / 9), ("host", 16 / 9)):
            for payload in (a["payload"] for a in self.place(fmt, aspect)):
                self.assertNotIn("keyframes", payload)
        self.assertNotIn("motion", montage_ops.OPS)


class BackgroundIsNotThePhotoTest(unittest.TestCase):
    """Accents glue to the photo, never to its blurred copy (user, 6 November 2026)."""

    def test_main_picture_skips_the_blurred_copy(self):
        frame = {"clips": [{"title": "K012 фон", "kind": "image", "asset_id": "a", "width": 1, "height": 1},
                           {"title": "K012 кадр", "kind": "image", "asset_id": "a", "width": 1, "height": 1}]}
        self.assertEqual(montage_ops.main_picture({}, frame)["title"], "K012 кадр")


class AntropovLooksTest(unittest.TestCase):
    """Dim flowing text frames, the first word on its own time (user, 8 November 2026)."""

    def test_dim_text_frame_flows_glows_and_waits_for_the_first_word(self):
        assets = [{"id": "a1", "kind": "image", "path": "/nope/photo.png"}]
        frames = [{"number": 4, "clips": [{"kind": "image", "asset_id": "a1", "width": 1, "height": 1}], "group": {"id": "g4"}}]
        ctx = DesignedTextTest().ctx(assets, frames)
        ctx.text_look = "dim"
        planned = {"number": 5, "sentences": ["Врачи признают такое неудобство."],
                   "sentence_timings": [{"number": 1, "text": "Врачи признают такое неудобство.", "start": 11.5, "end": 13.0}]}
        payload = {"kind": "text", "text": "Врачи признают такое неудобство."}
        montage_ops._designed_text(ctx, planned, 5, payload, 10.0, 14.0, None)
        background, veil, flow = (a["payload"] for a in ctx.actions)
        self.assertEqual(background["visual_effect"], "monochrome")
        self.assertGreaterEqual(veil["opacity"], .75)
        self.assertEqual(flow["content_type"], "gradient")
        self.assertGreater(payload["shadow"]["blur"], 15)
        self.assertAlmostEqual(payload["start"] + payload["text_words"][0]["start"], 11.5, places=3)
        self.assertAlmostEqual(payload["start"] + payload["duration"], 14)
        self.assertEqual(background["start"], 10)
        payload["text"] = montage_ops.display_text.clean(payload["text"])
        montage_ops.store.apply_text_binding(ctx.project,payload,{"text_role":"full_frame","source_text":payload["text"]})


class HeldTailTest(unittest.TestCase):
    def test_a_video_short_of_its_transition_holds_its_last_frame(self):
        import subprocess, tempfile
        import joins
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            clip = root / "host.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=25:duration=1",
                            "-pix_fmt", "yuv420p", str(clip)], check=True)
            import store
            with mock.patch.object(store, "cache_dir", return_value=root / "cache"):
                self.assertEqual(joins.held_source({}, str(clip), .9), str(clip))          # long enough: the file itself
                held = joins.held_source({}, str(clip), 1.6)
                self.assertNotEqual(held, str(clip))
                self.assertGreaterEqual(store.media_duration(Path(held)), 1.6)
                self.assertEqual(joins.held_source({}, str(clip), 1.6), held)                # made once

    def test_a_transition_out_of_a_video_without_tail_ends_on_the_seam(self):
        # user, 25 November 2026: «стоп-кадр відео дивиться дуже дивно і як будто це баг»; «любий кадр можна
        # підтягнути… накласти на ведучого»: the host plays its own last moments, the next frame comes in early
        import subprocess, tempfile
        import joins, store
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            host = root / "host.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=25:duration=2",
                            "-pix_fmt", "yuv420p", str(host)], check=True)
            project = {"id": "p" * 24, "fps": 25, "assets": [{"id": "h", "path": str(host)}],
                       "tracks": [{"id": "l1", "clips": [{"id": "a", "kind": "video", "asset_id": "h", "start": 0.0, "duration": 2.0, "trim_start": 0.0}]},
                                  {"id": "l2", "clips": [{"id": "b", "kind": "image", "start": 2.0, "duration": 3.0,
                                                          "keyframes": [{"time": 0, "scale": 1.0}, {"time": 3.0, "scale": 1.3}]},
                                                         {"id": "c", "kind": "text", "start": 3.0, "duration": 1.0}]}],
                       "scene_groups": [{"id": "g1", "title": "Кадр 1", "clip_ids": ["a"]}, {"id": "g2", "title": "Кадр 2", "clip_ids": ["b", "c"]}],
                       "join_transitions": [{"id": "j", "from_ref": "group:g1", "to_ref": "group:g2", "type": "crossfade", "duration": .4, "seam": 2.0}]}
            self.assertTrue(joins.ends_at_seam(project, project["join_transitions"][0]))
            self.assertEqual(joins.anchor(project)["join_transitions"][0]["anchor"], "end")
            self.assertEqual(joins.window(project["join_transitions"][0]), (1.6, 2.0))
            layers = [{"id": "l1", "clips": [{"id": "a", "type": "video", "source": str(host), "start": 0.0, "duration": 2.0, "trim_start": 0.0, "keyframes": []}]},
                      {"id": "l2", "clips": [{"id": "b", "type": "image", "start": 2.0, "duration": 3.0, "keyframes": [{"time": 0, "scale": 1.0}, {"time": 3.0, "scale": 1.3}]},
                                             {"id": "c", "type": "text", "start": 3.0, "duration": 1.0, "keyframes": []}]}]
            with mock.patch.object(store, "cache_dir", return_value=root / "cache"):
                joins.transport(project, layers)
            out, incoming, later = layers[0]["clips"][0], layers[1]["clips"][0], layers[1]["clips"][1]
            self.assertEqual((out["duration"], out["source"]), (2.0, str(host)))          # the host is not held past its edge
            self.assertEqual(out["join_out"]["seam"], 1.6)
            self.assertAlmostEqual(incoming["start"], 1.6)
            self.assertAlmostEqual(incoming["duration"], 3.4)
            self.assertEqual(incoming["join_in"]["seam"], 1.6)
            # its zoom runs on backwards over the lead and is where it was at the seam
            self.assertAlmostEqual(incoming["keyframes"][0]["scale"], 1.0 - .3 / 3.0 * .4)
            self.assertEqual(incoming["keyframes"][1], {"time": .4, "scale": 1.0})
            self.assertEqual(later["start"], 3.0)                                          # an accent later keeps its time

    def test_a_video_with_a_tail_keeps_the_transition_after_the_seam(self):
        import subprocess, tempfile
        import joins
        with tempfile.TemporaryDirectory() as folder:
            host = Path(folder) / "host.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=25:duration=2.6",
                            "-pix_fmt", "yuv420p", str(host)], check=True)
            project = {"fps": 25, "assets": [{"id": "h", "path": str(host)}],
                       "tracks": [{"id": "l1", "clips": [{"id": "a", "kind": "video", "asset_id": "h", "start": 0.0, "duration": 2.0}]},
                                  {"id": "l2", "clips": [{"id": "b", "kind": "image", "start": 2.0, "duration": 3.0}]}],
                       "scene_groups": [{"id": "g1", "clip_ids": ["a"]}, {"id": "g2", "clip_ids": ["b"]}]}
            join = {"from_ref": "group:g1", "to_ref": "group:g2", "type": "crossfade", "duration": .4, "seam": 2.0}
            self.assertFalse(joins.ends_at_seam(project, join))   # 0.6 s of the host after its edge: it plays through

    def test_an_early_frame_of_video_holds_its_first_picture(self):
        import subprocess, tempfile
        import joins, store
        with tempfile.TemporaryDirectory() as folder:
            clip = Path(folder) / "next.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=25:duration=1",
                            "-pix_fmt", "yuv420p", str(clip)], check=True)
            item = joins.lead({"type": "video", "source": str(clip), "start": 2.0, "duration": 1.0, "trim_start": 0.0}, .4, Path(folder) / "heads")
            self.assertNotEqual(item["source"], str(clip))
            self.assertGreaterEqual(store.media_duration(Path(item["source"])), 1.38)
            self.assertEqual(item["trim_start"], 0.0)
            item = joins.lead({"type": "video", "source": str(clip), "start": 2.0, "duration": .5, "trim_start": .5}, .4, Path(folder) / "heads")
            self.assertEqual((item["source"], round(item["trim_start"], 3)), (str(clip), .1))   # it had the frames

    def test_a_transparent_layer_keeps_its_alpha_through_the_held_tail(self):
        import subprocess, tempfile
        import joins
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            clip = root / "motion.mov"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black@0.0:size=320x180:rate=25:duration=1,format=rgba",
                            "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", str(clip)], check=True)
            import store
            with mock.patch.object(store, "cache_dir", return_value=root / "cache"):
                held = joins.held_source({}, str(clip), 1.6)
            self.assertTrue(held.endswith(".mov"))
            fmt = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=pix_fmt",
                                  "-of", "csv=p=0", held], capture_output=True, text=True).stdout
            self.assertIn("yuva", fmt)
