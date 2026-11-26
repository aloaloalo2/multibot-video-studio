import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import live_montage
import montage_ops
import planner


def clip(cid, kind, start, duration, **more):
    return {"id": cid, "kind": kind, "start": start, "duration": duration, "x": .5, "y": .5, "scale": 1, "keyframes": [], **more}


class HostInsetTest(unittest.TestCase):
    """The host frame moves inside his speech; the neighbours' pictures take the half seconds (26 November 2026)."""
    def context(self):
        clips = [clip("p_bg", "animation", 0, 4, frame_background=True), clip("p_txt", "text", 2, 2), clip("p_img", "image", 0, 4, keyframes=[{"time": 0, "scale": 1}, {"time": 4, "scale": 1.1}]),
                 clip("h_bg", "animation", 4, 4), clip("h_vid", "video", 4, 4, trim_start=.4),
                 clip("a_img", "image", 8, 4), clip("a_txt", "text", 9, 2)]
        project = {"fps": 25, "assets": [], "tracks": [{"id": "t", "clips": clips}],
                   "scene_groups": [{"id": "g1", "title": "Кадр 1", "clip_ids": ["p_bg", "p_img", "p_txt"]},
                                    {"id": "g2", "title": "Кадр 2", "clip_ids": ["h_bg", "h_vid"]},
                                    {"id": "g3", "title": "Кадр 3", "clip_ids": ["a_img", "a_txt"]}],
                   "join_transitions": [{"id": "j", "from_ref": "group:g1", "to_ref": "group:g2", "type": "crossfade", "duration": .35}]}
        plan = {"frames": [{"number": 1, "format": "generated_photo", "start": 0, "end": 4, "sentence_timings": [{"start": 0, "end": 3.9}]},
                           {"number": 2, "format": "host", "start": 4, "end": 8, "sentence_timings": [{"start": 4.02, "end": 7.98}]},
                           {"number": 3, "format": "animation", "start": 8, "end": 12, "sentence_timings": [{"start": 8, "end": 12}]}]}
        return SimpleNamespace(project=project, plan=plan, frames=montage_ops.frame_groups(project, plan), actions=[], report=[])

    def test_host_moves_inside_his_speech_and_neighbours_take_the_edges(self):
        ctx = self.context()
        live_montage.host_inset(ctx, {})
        moves = {a["payload"]["clip_id"]: a["payload"]["start"] for a in ctx.actions if a["type"] == "move_clip"}
        trims = {a["payload"]["clip_id"]: a["payload"] for a in ctx.actions if a["type"] == "trim_clip"}
        self.assertEqual(moves["h_vid"], 4.52)
        self.assertEqual((trims["h_vid"]["trim_start"], trims["h_vid"]["duration"]), (.92, 2.96))
        self.assertEqual(trims["p_img"]["duration"], 4.52)                   # the picture before him lasts longer
        self.assertEqual((moves["a_img"], trims["a_img"]["duration"]), (7.48, 4.52))   # the one after starts earlier
        self.assertNotIn("a_txt", moves)                                     # a caption keeps its time
        self.assertEqual(trims["p_txt"]["duration"], 2.52)                  # the text held to the frame's end holds to the new one
        keyframes = next(a["payload"]["patch"]["keyframes"] for a in ctx.actions if a["type"] == "update_clip" and a["payload"]["clip_id"] == "p_img")
        self.assertEqual(keyframes[-1]["time"], montage_ops.end_time(4.52))   # its move stretches over the longer time
        self.assertTrue(any(a["type"] == "set_join_transition" for a in ctx.actions))   # set again at the end of the batch
        frames = ctx.new_plan["frames"]
        self.assertEqual([(f["start"], f["end"]) for f in frames], [(0, 4.52), (4.52, 7.48), (7.48, 12)])
        self.assertEqual(frames[1]["host_inset"], planner.HOST_INSET)

    def test_plan_edges_agree_with_the_planner(self):
        times = planner.aligned_times([["a"], ["b"], ["c"]], [{"start": 0, "end": 3.9}, {"start": 4, "end": 8}, {"start": 8, "end": 12}], 12, None, [0, .5, 0])
        self.assertEqual(times, [(0.0, 4.5), (4.5, 7.5), (7.5, 12)])
        short = planner.aligned_times([["a"], ["b"], ["c"]], [{"start": 0, "end": 3.9}, {"start": 4, "end": 6}, {"start": 6, "end": 9}], 9, None, [0, .5, 0])
        self.assertAlmostEqual(short[1][1] - short[1][0], planner.HOST_MIN_VISIBLE)   # a short phrase keeps 1.5 s on screen


class StandsStillTest(unittest.TestCase):
    """A frame where nothing moves the picture gets the camera; one that moves is left (26 November 2026, frame 71)."""

    def test_still_photo_under_motion_code_counts_as_standing(self):
        frame = {"number": 71, "clips": [
            {"kind": "animation", "title": "K071 чорний фон", "keyframes": []},
            {"kind": "image", "title": "K071 кадр", "keyframes": []},
            {"kind": "animation", "content_type": "code", "title": "K071 моушн", "keyframes": []}]}
        self.assertTrue(live_montage.stands_still(frame))

    def test_a_zoom_a_video_or_a_razgon_block_moves_the_frame(self):
        zoom = {"kind": "image", "keyframes": [{"time": 0, "scale": 1.02}, {"time": 5, "scale": 1.1}]}
        self.assertFalse(live_montage.stands_still({"clips": [zoom]}))
        self.assertFalse(live_montage.stands_still({"clips": [{"kind": "video", "keyframes": []}]}))
        self.assertFalse(live_montage.stands_still({"clips": [{"kind": "animation", "title": "Razgon · кадр 004"}]}))
        fade = {"kind": "image", "keyframes": [{"time": 0, "opacity": 0}, {"time": 1, "opacity": 1}]}
        self.assertTrue(live_montage.stands_still({"clips": [fade]}))
