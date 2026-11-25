import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import asset_motion
import channel_design
import montage_ops
import native_animation

PROJECT = {"id": "film-a", "width": 1920, "height": 1080}


def at(points, prop, t):
    return montage_ops.keyframe_value({"keyframes": points, "easing": "linear"}, prop, t)


def kit(seed):
    return lambda project: channel_design.generate(seed)


class RecipeTest(unittest.TestCase):
    def test_every_channel_moves_its_own_way(self):
        styles = []
        for seed in ("channel-1:a", "channel-2:b", "channel-3:c"):
            with patch.object(channel_design, "for_project", kit(seed)):
                styles.append(asset_motion.style(PROJECT))
        keys = ("enter_length", "overshoot", "float_px", "float_period", "drift_angle", "side")
        self.assertEqual(len({tuple(s[k] for k in keys) for s in styles}), 3)
        with patch.object(channel_design, "for_project", kit("channel-1:a")):
            again = asset_motion.style(PROJECT)
            other_film = asset_motion.style({**PROJECT, "id": "film-b"})
        self.assertEqual(again, styles[0])                    # the same channel and film: the same motion
        self.assertNotEqual(other_film["float_px"], again["float_px"])   # another film of the channel: a little shifted
        self.assertEqual(other_film["enters"], again["enters"])          # ... in the same family

    def test_a_group_comes_in_one_after_another_and_spec_overrides(self):
        made = [asset_motion.recipe(PROJECT, 7, i) for i in range(3)]
        self.assertEqual(len({m["enter"] for m in made}), 1)
        self.assertEqual([m["delay"] for m in made], sorted(m["delay"] for m in made))
        self.assertGreater(made[2]["delay"], made[0]["delay"])
        self.assertEqual(asset_motion.recipe(PROJECT, 7, 0, "drop")["enter"], "drop")
        self.assertEqual(asset_motion.recipe(PROJECT, 7, 0, {"life": "pulse", "side": "above"})["life"], "pulse")
        with self.assertRaises(ValueError):
            asset_motion.recipe(PROJECT, 7, 0, {"enter": "spin"})


class KeyframesTest(unittest.TestCase):
    def build(self, enter, life, duration=6.0, appear=1.0, latest=None, x=.6, y=.45, w=.15, h=.2, exit="hold"):
        made = {"enter": enter, "life": life, "exit": exit, "side": "left", "delay": 0, "phase": .7}
        return asset_motion.keyframes(PROJECT, made, duration=duration, at=appear, latest=latest, x=x, y=y, width=w, height=h)

    def test_hidden_until_its_word_then_comes_in_and_keeps_moving_to_the_end(self):
        for enter in asset_motion.ENTERS:
            for life in asset_motion.LIVES:
                points = self.build(enter, life)
                with self.subTest(enter=enter, life=life):
                    self.assertEqual(points[0]["time"], 0.0)
                    self.assertEqual(points[-1]["time"], 6.0)
                    self.assertEqual(at(points, "opacity", .9), 0.0)
                    self.assertAlmostEqual(at(points, "opacity", 2.5), 1.0, places=3)
                    self.assertLessEqual(len(points), asset_motion.MAX_POINTS + 2)
                    # still moving in the last half second: never frozen before the seam
                    moved = sum(abs(at(points, p, 6.0) - at(points, p, 5.5)) * (1920 if p == "x" else 1080 if p == "y" else 500)
                                for p in ("x", "y", "scale"))
                    self.assertGreater(moved, .3)
                    # settled near its place after the entrance (the life is a few pixels)
                    self.assertLess(abs(at(points, "x", 3) - .6) * 1920, 40)
                    self.assertLess(abs(at(points, "y", 3) - .45) * 1080, 40)

    def test_no_entrance_in_the_frames_last_second_and_sub_pixel_values(self):
        points = self.build("pop", "float", duration=4.0, appear=3.6, latest=3.0)
        first = next(p["time"] for p in points if p["opacity"] > 0)
        self.assertLessEqual(first, 3.0 + asset_motion.STEP + 1e-6)
        xs = [p["x"] * 1920 for p in points]
        self.assertTrue(any(abs(v - round(v)) > .01 for v in xs))   # positions on fractions of a pixel

    def test_no_jolt_between_keyframes_after_the_entrance(self):
        points = self.build("slide", "float", duration=10.0, appear=.5)
        settled = [p for p in points if p["time"] > 1.6]
        for a, b in zip(settled, settled[1:]):
            speed = math.hypot((b["x"] - a["x"]) * 1920, (b["y"] - a["y"]) * 1080) / (b["time"] - a["time"])
            self.assertLess(speed, 25)   # px a second: a calm life

    def test_a_prop_near_the_edge_never_drifts_out(self):
        for life in asset_motion.LIVES:
            points = self.build("fade", life, duration=40.0, appear=.3, x=.93, y=.9, w=.12, h=.18)
            for t in [k / 4 for k in range(8, 160)]:
                x, y, s = at(points, "x", t), at(points, "y", t), at(points, "scale", t)
                with self.subTest(life=life, t=t):
                    self.assertLessEqual(x + .06 * s, 1.0 + .02)   # was 1.0 - .03 at rest: never pushed further out
                    self.assertLessEqual(y + .09 * s, 1.0 + .02)

    def test_long_clips_stay_under_the_engines_keyframe_limit(self):
        self.assertLessEqual(len(self.build("drop", "pulse", duration=90.0)), asset_motion.MAX_POINTS + 2)

    def test_out_leaves_by_the_clip_end(self):
        points = self.build("rise", "float", exit="out")
        self.assertEqual(points[-1]["opacity"], 0.0)


class EnlivenTest(unittest.TestCase):
    def test_a_static_png_gets_the_channels_life_and_keeps_its_fade(self):
        part = {"kind": "image", "start": .5, "duration": 7.5, "x": .3, "y": .5, "width": .2, "height": .25,
                "keyframes": [{"time": 0, "opacity": 0}, {"time": .35, "opacity": 1}]}
        note = asset_motion.enliven(PROJECT, part, 8.0, 4, 0)
        self.assertIn("живе", note)
        self.assertEqual(part["easing"], "linear")
        self.assertAlmostEqual(at(part["keyframes"], "opacity", .1), .1 / .35, places=2)
        self.assertEqual(at(part["keyframes"], "opacity", 5), 1.0)
        end = part["keyframes"][-1]
        self.assertEqual(end["time"], 7.5)
        self.assertNotEqual((at(part["keyframes"], "x", 7.5), at(part["keyframes"], "y", 7.5)),
                            (at(part["keyframes"], "x", 7.0), at(part["keyframes"], "y", 7.0)))

    def test_a_late_png_comes_in_before_the_last_second(self):
        part = {"kind": "image", "start": 7.6, "duration": .4, "x": .5, "y": .5, "width": .1, "height": .1,
                "keyframes": [{"time": 0, "opacity": 0}, {"time": .3, "opacity": 1}]}
        asset_motion.enliven(PROJECT, part, 8.0, 4, 0)
        self.assertLessEqual(part["start"], 7.0 + 1e-6)
        self.assertAlmostEqual(part["start"] + part["duration"], 8.0, places=3)

    def test_still_backdrop_and_moving_layers_are_left_alone(self):
        still = {"kind": "image", "start": 0, "duration": 5, "motion": "still", "keyframes": []}
        backdrop = {"kind": "image", "start": 0, "duration": 5, "width": 1, "height": 1, "keyframes": []}
        moving = {"kind": "image", "start": 0, "duration": 5, "width": .2, "height": .2,
                  "keyframes": [{"time": 0, "x": .2}, {"time": 4.8, "x": .4}]}
        for part in (still, backdrop, moving):
            before = dict(part, keyframes=list(part["keyframes"]))
            before.pop("motion", None)
            asset_motion.enliven(PROJECT, part, 5.0, 2, 0)
            self.assertEqual(part, before)

    def test_motion_gives_the_whole_recipe_on_its_word(self):
        part = {"kind": "image", "start": 0, "duration": 6, "x": .5, "y": .5, "width": .2, "height": .2,
                "motion": {"enter": "drop", "life": "pulse"}}
        asset_motion.enliven(PROJECT, part, 6.0, 2, 0, word_at=2.0)
        self.assertNotIn("motion", part)
        self.assertEqual(at(part["keyframes"], "opacity", 1.9), 0.0)
        self.assertLess(at(part["keyframes"], "y", 2.05), .5)   # falls in from above
        self.assertGreater(at(part["keyframes"], "opacity", 3), .99)


class ClusterTest(unittest.TestCase):
    def parts(self):
        gut = {"kind": "image", "title": "кишечник", "start": 0, "duration": 9, "x": .68, "y": .34, "width": .25, "height": .5}
        germ = {"kind": "image", "title": "бактерії", "start": 5.2, "duration": 3.8, "x": .7, "y": .3, "width": .09, "height": .11,
                "keyframes": [{"time": 0, "opacity": 0}, {"time": .3, "opacity": 1}]}
        contour = {"kind": "image", "title": "контур", "start": 5.7, "duration": 3.3, "x": .5, "y": .5, "width": 1, "height": 1,
                   "keyframes": [{"time": 0, "opacity": 0}, {"time": .35, "opacity": 1}]}
        stomach = {"kind": "image", "title": "шлунок", "start": 0, "duration": 9, "x": .25, "y": .4, "width": .2, "height": .5}
        label = {"kind": "text", "text": "бактерии", "start": 5, "duration": 4, "x": .4, "y": .2, "width": .15, "height": .08}
        return [gut, germ, contour, stomach, label]

    def test_props_under_one_drawing_move_as_one(self):
        parts = self.parts()
        inks = {0: (0, 0, 1, 1), 1: (0, 0, 1, 1), 2: (.55, .1, .8, .6), 3: (0, 0, 1, 1)}
        notes = asset_motion.enliven_frame(PROJECT, parts, 9.0, 46, inks=inks)
        gut, germ, contour, stomach, label = parts
        self.assertEqual(len(notes), 4)
        for t in (6.2, 7.0, 8.0, 8.99):   # frame seconds: the contour, the germs and the gut share one offset
            offsets = [(at(p["keyframes"], "x", t - p["start"]) - p["x"], at(p["keyframes"], "y", t - p["start"]) - p["y"])
                       for p in (gut, germ, contour)]
            for dx, dy in offsets[1:]:
                self.assertAlmostEqual(dx * 1920, offsets[0][0] * 1920, delta=.35)
                self.assertAlmostEqual(dy * 1080, offsets[0][1] * 1080, delta=.35)
        self.assertNotIn("keyframes", label)                 # the text stays put
        self.assertGreater(len(stomach["keyframes"]), 4)       # the stomach lives on its own

    def test_a_group_with_its_own_motion_lives_after_it_and_unknown_ink_is_never_moved(self):
        parts = self.parts()
        parts[0]["keyframes"] = [{"time": 0, "scale": .97}, {"time": 3.6, "scale": 1.0}]
        asset_motion.enliven_frame(PROJECT, parts, 9.0, 46, inks={2: (.55, .1, .8, .6)})
        gut = parts[0]
        self.assertAlmostEqual(at(gut["keyframes"], "scale", 1.8), .97 + .03 * .5, places=3)   # its own zoom kept
        self.assertAlmostEqual(at(gut["keyframes"], "x", 3.0), .68, places=5)                  # no life before it ends
        self.assertNotAlmostEqual(at(gut["keyframes"], "y", 8.0), .34, places=4)
        parts = self.parts()
        asset_motion.enliven_frame(PROJECT, parts, 9.0, 46)
        self.assertEqual(parts[2]["keyframes"], self.parts()[2]["keyframes"])   # unknown ink: never moved


class NativeAnimationHookTest(unittest.TestCase):
    def test_png_layers_of_an_animation_frame_live_and_shapes_are_untouched(self):
        ctx = SimpleNamespace(project={"id": "test", "fps": 25, "assets": [{"id": "png", "kind": "image"}], "tracks": [{"id": "base", "clips": []}]},
                              plan={"frames": [{"number": 3, "format": "animation", "start": 10.0, "end": 16.0}]},
                              frames=[], groups={}, actions=[], report=[])
        shape = {"kind": "animation", "content_type": "shape", "width": 1, "height": 1, "keyframes": [{"time": 0, "x": .5}]}
        png = {"kind": "animation", "content_type": "image", "asset_id": "png", "start": 1, "duration": 5, "x": .3, "y": .4,
               "width": .2, "height": .2, "keyframes": [{"time": 0, "opacity": 0}, {"time": .35, "opacity": 1}]}
        dropped = dict(png, motion="drop", x=.7)
        native_animation.place(ctx, {"frame": 3, "clips": [shape, png, dropped]})
        layers = [a["payload"] for a in ctx.actions]
        self.assertEqual(layers[1]["keyframes"], [{"time": 0, "x": .5}])
        for layer in layers[2:]:
            self.assertEqual(layer["easing"], "linear")
            self.assertGreater(len(layer["keyframes"]), 4)
            self.assertNotIn("motion", layer)
            self.assertNotIn("_png", layer)
        self.assertTrue(any("PNG" in line or "живе" in line or "рух" in line for line in ctx.report))


class AccentPictureTest(unittest.TestCase):
    def test_an_accent_picture_is_one_living_clip_glued_to_its_photo(self):
        photo = {"start": 20.0, "duration": 6.0, "x": .5, "y": .5, "scale": 1.0, "easing": "ease_in_out",
                 "keyframes": [{"time": 0, "scale": 1.0}, {"time": 6, "scale": 1.12}]}

        class Pic:   # a full-frame photo zooming in (montage_ops.Picture, without its asset file)
            clip, W, H, cw, ch, duration = photo, 1920.0, 1080.0, 1920.0, 1080.0, 6.0
            state = montage_ops.Picture.state
            to_frame = montage_ops.Picture.to_frame
            to_photo = montage_ops.Picture.to_photo

        ctx = SimpleNamespace(project={**PROJECT, "tracks": [{"id": "l"}]}, W=1920.0, H=1080.0, actions=[], easing="ease_in_out")
        ctx.prefix = lambda frame: "K005"
        ctx.add = lambda frame, picture, title, payload: montage_ops.Context.add(ctx, frame, picture, title, payload)
        frame = {"number": 5, "start": 20.0, "end": 26.0, "group": {"id": "g5"}}
        asset_motion.accent(ctx, frame, Pic(), "0 картинка", {"kind": "image", "asset_id": "a"}, (1400, 300), (240, 240), 5.7, 6.0, {})
        self.assertEqual(len(ctx.actions), 1)    # no separate entrance clip
        clip = ctx.actions[0]["payload"]
        self.assertEqual(clip["easing"], "linear")
        self.assertTrue(asset_motion.is_living(clip))
        first = next(k["time"] for k in clip["keyframes"] if k["opacity"] > 0)
        self.assertLessEqual(first, 5.0 + asset_motion.STEP + 1e-6)   # asked at 5.7 s of a 6 s frame: moved out of the last second
        # it rides the zoom: at the end it is farther from the centre than at the start (plus a little parallax)
        self.assertGreater(at(clip["keyframes"], "x", 6.0), at(clip["keyframes"], "x", 5.5))
        self.assertGreater(at(clip["keyframes"], "scale", 6.0), 1.0)
        # glued again (montage_ops.reglue): the same place and the same moment of appearance, no entrance clip
        patch_ = asset_motion.reglued(ctx, frame, Pic(), {**clip, "id": "c", "title": "K005 акцент 0 картинка"})
        self.assertEqual(patch_["easing"], "linear")
        again = next(k["time"] for k in patch_["keyframes"] if k["opacity"] > 0)
        self.assertAlmostEqual(again, first, delta=2 * asset_motion.STEP)
        self.assertAlmostEqual(at(patch_["keyframes"], "x", 3.0), at(clip["keyframes"], "x", 3.0), delta=2 / 1920)


if __name__ == "__main__":
    unittest.main()
