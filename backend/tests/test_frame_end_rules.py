"""Three rules of a frame's end (user, 25 November 2026)."""
import unittest

from backend.tests import test_backend as support  # noqa: F401  (paths and a temporary studio)
import joins  # noqa: E402
import montage_ops  # noqa: E402


def project(text_out: bool):
    out = {"id": "a", "kind": "text" if text_out else "image", "title": "K004 кадр" if text_out else "K004 кадр", "start": 0.0, "duration": 5.0}
    if text_out:
        out["text_role"] = "full_frame"
    nxt = {"id": "b", "kind": "image", "title": "K005 кадр", "start": 5.0, "duration": 5.0}
    return {"fps": 25, "tracks": [{"id": "t", "clips": [out, nxt]}],
            "scene_groups": [{"id": "g4", "title": "Кадр 4", "clip_ids": ["a"]}, {"id": "g5", "title": "Кадр 5", "clip_ids": ["b"]}],
            "join_transitions": []}


class FrameEndRulesTest(unittest.TestCase):
    def test_a_transition_out_of_a_text_frame_starts_on_the_seam(self):
        # «текстова вставка має закінчитись аж там, де починається наступне речення»
        join = {"from_ref": "group:g4", "to_ref": "group:g5", "type": "capcut_t38", "duration": .7, "seam": 5.0}
        self.assertEqual(joins.lead_seconds(project(True), join), 0.0)
        self.assertGreater(joins.lead_seconds(project(False), join), 0.0)   # elsewhere the hit lands on the seam

    def test_multi_line_frame_text_counts_as_a_text_frame(self):
        p = project(False)
        p["tracks"][0]["clips"][0].update(kind="text", title="K004 кадр 2", text_role="caption")
        join = {"from_ref": "group:g4", "to_ref": "group:g5", "type": "capcut_t38", "duration": .7, "seam": 5.0}
        self.assertEqual(joins.lead_seconds(p, join), 0.0)

    def test_nothing_comes_in_during_a_frames_last_second(self):
        # «за секунду до кінця кадра нічого не може появлятися»
        frame = {"start": 10.0, "end": 16.0}
        self.assertEqual(montage_ops._quiet_end(frame, 10.0, 5.7), 5.0)
        self.assertEqual(montage_ops._quiet_end(frame, 10.0, 2.0), 2.0)
        self.assertEqual(montage_ops._quiet_end({"start": 0, "end": .5}, 0.0, .3), 0.0)

    def test_slice_and_pan_is_kept_for_the_way_out(self):
        self.assertIn("capcut_t30", montage_ops.OUT_ONLY)


if __name__ == "__main__":
    unittest.main()


class LeadScaleTest(unittest.TestCase):
    """28 November 2026: an accent growing from 0.46 led in 0.6 s early ran its scale back to −1.96 and the export
    failed with «scale keyframe must be at least 0.05»."""

    def test_a_scale_run_back_stops_at_the_least_the_engine_takes(self):
        import joins
        clip = {"start": 698.36, "duration": 13.46, "scale": 1, "keyframes": [
            {"time": 0, "scale": .4635, "opacity": 0}, {"time": .04, "scale": .6249, "opacity": .32}]}
        joins.lead(clip, .6)
        self.assertEqual(clip["keyframes"][0]["scale"], joins.MIN_SCALE)
        self.assertEqual(clip["keyframes"][0]["opacity"], 0)
        self.assertAlmostEqual(clip["start"], 697.76)
