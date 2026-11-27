"""A text frame is never dead (user, 27 November 2026, Astéroïde 37 and 86: «текстовий кадр появився, і там на протязі
секунди просто пусто… це вважається вже… як брак»): the words said before the shown text come first, and only what
comes on after the transition into the frame counts («воно появилося одразу після переходу… як будто воно там було»)."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import montage_ops  # noqa: E402
import motion_code  # noqa: E402

SPOKEN = [("Pour", 0.0), ("se", .12), ("brûler,", .3), ("il", 1.0), ("faut", 1.08), ("à", 1.26), ("la", 1.36), ("fois", 1.42),
          ("des", 1.64), ("particules", 1.8), ("rapides", 2.26)]


def text_clip(words, start=10.0, title="K037 кадр"):
    return {"id": "t", "kind": "text", "title": title, "text": " ".join(w for w, _ in words), "start": start, "duration": 6,
            "x": .5, "y": .5, "width": .9, "height": .7, "font_size": 84, "font_weight": 700, "font_family": "Roboto Condensed",
            "color": "#eaf7f3", "text_role": "full_frame", "adapted": True,
            "text_words": [{"text": w, "start": s, "x": .5, "y": .5, "width": .1, "height": .15} for w, s in words]}


def frame(*clips):
    background = {"id": "bg", "kind": "image", "title": "K037 фон", "start": 10.0, "duration": 6, "x": .5, "y": .5, "width": 1, "height": 1}
    return {"group": {"id": "g", "title": "Кадр 37"}, "number": 37, "start": 10.0, "end": 16.0,
            "plan": {"format": "text", "sentences": ["x"]}, "clips": [background, *clips]}


class Ctx:
    W, H = 1920, 1080

    def __init__(self, clips):
        self.project = {"fps": 25, "tracks": [{"id": "L", "clips": list(clips)}], "join_transitions": []}


class LeadInTest(unittest.TestCase):
    def lead(self, fr):
        ctx = Ctx(fr["clips"])
        with mock.patch.object(montage_ops, "_timed_tokens", return_value=[(w, 10.0 + s) for w, s in SPOKEN]):
            return montage_ops.lead_in_actions(ctx, fr)

    def test_an_excerpt_later_in_the_sentence_gets_the_words_said_before_it(self):
        shown = text_clip([("des", 1.64), ("particules", 1.8), ("rapides", 2.26)])
        actions = self.lead(frame(shown))
        add = actions[0]["payload"]
        self.assertEqual(add["text"], "Pour se brûler, il faut à la fois")
        self.assertEqual(add["start"], 10.0)
        self.assertEqual([w["start"] for w in add["text_words"]][:3], [0.0, .12, .3])
        # a frame of the studio's own layers: the lead-in stands above the text for the whole frame, the text moves down
        self.assertAlmostEqual(add["start"] + add["duration"], 16.0)
        self.assertEqual(actions[1]["payload"]["clip_id"], "t")
        self.assertGreater(actions[1]["payload"]["changes"]["y"], .5)
        self.assertLess(add["y"], .5)

    def test_beside_the_directors_code_it_fades_out_before_the_text_comes(self):
        shown = text_clip([("des", 1.64), ("particules", 1.8), ("rapides", 2.26)])
        code = {"id": "c", "kind": "animation", "content_type": "code", "title": "K037 моушн", "start": 10.0, "duration": 6,
                "x": .5, "y": .5, "width": 1, "height": 1}
        actions = self.lead(frame(shown, code))
        self.assertEqual(len(actions), 1)
        add = actions[0]["payload"]
        self.assertAlmostEqual(add["start"] + add["duration"], 11.64)
        self.assertEqual(add["keyframes"][-1]["opacity"], 0.0)
        # its last word is up before the fade, and the fade is over when «des» comes in: never one text over the other
        self.assertGreater(add["keyframes"][0]["time"], 1.42)
        self.assertLessEqual(add["keyframes"][-1]["time"], 1.64)

    def test_text_that_starts_with_the_voice_needs_nothing(self):
        self.assertEqual(self.lead(frame(text_clip(SPOKEN))), [])

    def test_a_frame_with_a_lead_in_already_is_left(self):
        shown = text_clip([("des", 1.64)])
        lead = text_clip([("Pour", 0.0)], title="K037 підводка")
        lead["id"] = "l"
        self.assertEqual(self.lead(frame(shown, lead)), [])


class DeadFrameTest(unittest.TestCase):
    def looks(self, shares, thumbs=None):
        steps = list(motion_code.ONSET_STEPS[:len(shares)])
        return {"steps": steps, "shares": shares, "thumbs": thumbs or [[0] * 4 for _ in shares]}

    def test_a_drawing_that_came_in_under_the_transition_is_no_appearance(self):
        # Astéroïde 86: the planet faded in from 0.25 s under a 0.5 s transition, then stood
        look = self.looks([0, 0, .002, .004, .004, .004, .004], [[0] * 4, [0] * 4, [30] * 4, [60] * 4, [60] * 4, [60] * 4, [60] * 4])
        with mock.patch.object(motion_code, "looks", return_value=look):
            self.assertIsNone(motion_code.appears({}, {}, .5 + montage_ops.SETTLE))
            self.assertEqual(motion_code.appears({}, {}, 0), .4)

    def test_something_growing_or_moving_after_the_transition_is(self):
        look = self.looks([0, 0, 0, 0, .003, .004], [[0] * 4, [0] * 4, [0] * 4, [0] * 4, [40] * 4, [60] * 4])
        with mock.patch.object(motion_code, "looks", return_value=look):
            self.assertEqual(motion_code.appears({}, {}, .5), .8)
        moving = self.looks([.08] * 4, [[10, 0, 0, 0], [10, 0, 0, 0], [0, 10, 0, 40], [0, 0, 60, 0]])
        with mock.patch.object(motion_code, "looks", return_value=moving):
            self.assertEqual(motion_code.appears({}, {}, .3), .4)

    def test_a_drift_too_slow_to_see_is_a_still_picture(self):
        # Andromeda 118: two galaxies, one or two grey levels of change in three seconds
        slow = self.looks([.079] * 6, [[100, 100], [101, 100], [101, 101], [102, 101], [102, 102], [101, 102]])
        with mock.patch.object(motion_code, "looks", return_value=slow):
            self.assertIsNone(motion_code.appears({}, {}, .7))

    def test_words_of_a_full_frame_text_count_under_the_transition_too(self):
        fr = frame(text_clip([("rien", 0.0), ("à", .48), ("voir", 1.48)]))
        self.assertEqual(montage_ops.first_shown({"join_transitions": []}, fr, .7), .7)

    def test_background_veil_and_texture_alone_are_dead(self):
        veil = {"id": "v", "kind": "animation", "content_type": "shape", "title": "K037 тінь", "start": 10.0, "duration": 6,
                "x": .5, "y": .5, "width": 1, "height": 1}
        noise = {"id": "n", "kind": "animation", "content_type": "capcut_effect", "title": "CapCut", "start": 10.0, "duration": 6,
                 "x": .5, "y": .5, "width": 1, "height": 1}
        self.assertIsNone(montage_ops.first_shown({"join_transitions": []}, frame(veil, noise), .5))

    def test_incoming_reads_the_transition_into_the_frame(self):
        project = {"join_transitions": [{"from_ref": "group:x", "to_ref": "group:g", "duration": .5}]}
        self.assertEqual(montage_ops.incoming(project, frame()), .5)


if __name__ == "__main__":
    unittest.main()
