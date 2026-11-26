import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import director_plan  # noqa: E402
import planner  # noqa: E402
import store  # noqa: E402

SCRIPT = " ".join(f"Sentence number {word} talks about one simple thing here." for word in
                  ("one", "two", "three", "four", "five", "six", "seven", "eight"))
CHANNEL = {"id": "c" * 16, "settings": {"weights": {"stock_photo": 50, "text": 50}, "max_sentences_per_scene": 3}}
PROJECT = {"id": "a" * 24, "channel_id": "c" * 16}


def frames(*spec):
    return [{"sentences": numbers, "format": kind, "idea": "a picture"} for numbers, kind in spec]


class DirectorPlanTest(unittest.TestCase):
    def setUp(self):
        alignment = [{"text": text, "start": i * 2 + .1, "end": i * 2 + 1.9} for i, text in enumerate(planner.split_sentences(SCRIPT))]
        self.plan = planner.build_plan(SCRIPT, planner.effective_settings(CHANNEL["settings"]), "Test", duration=16.5, alignment=alignment)
        self.plan["timing"]["audio"] = {"duration": 16.5}   # the Studio adds the voice it measured
        self.saved = []
        for item in (patch.object(store, "load_project", return_value=PROJECT),
                     patch.object(store, "load_project_plan", side_effect=lambda pid: self.plan),
                     patch.object(store, "list_channels", return_value=[CHANNEL]),
                     patch.object(store, "attach_plan", side_effect=lambda pid, plan: self.saved.append(plan))):
            item.start()
            self.addCleanup(item.stop)

    def test_the_director_reads_numbered_sentences_and_the_channel_shares(self):
        data = director_plan.sentences(PROJECT["id"])
        self.assertEqual([item["number"] for item in data["sentences"]], list(range(1, 9)))
        self.assertEqual(data["shares"], {"stock_photo": 50.0, "text": 50.0})
        self.assertNotIn("max_sentences", data)

    def test_karl_requires_first_host_and_no_adjacent_hosts(self):
        channel={**CHANNEL,"name":"Karl Brenners Werkstatt","settings":{**CHANNEL["settings"],"weights":{"host":50,"stock_photo":50}}}
        with patch.object(store,"list_channels",return_value=[channel]):
            self.assertEqual(director_plan.sentences(PROJECT["id"])["opening"],[{"number":1,"format":"host"}])
            result=director_plan.apply(PROJECT["id"],frames(([1,2],"host"),([3,4],"host"),([5,6],"stock_photo"),([7,8],"stock_photo")),dry_run=True)
            self.assertTrue(any("двох кадрах поспіль" in x for x in result["problems"]))

    def test_the_closing_frames_are_checked_and_shown_to_the_director(self):
        # «Кінець ролика» (user, 26 November 2026): the last frame must be a text frame
        channel = {**CHANNEL, "settings": {**CHANNEL["settings"], "closing_sequence": ["auto", "auto", "text"]}}
        with patch.object(store, "list_channels", return_value=[channel]):
            self.assertEqual(director_plan.sentences(PROJECT["id"])["closing"], [{"from_end": 1, "format": "text"}])
            bad = director_plan.apply(PROJECT["id"], frames(([1, 2], "text"), ([3, 4], "stock_photo"), ([5, 6], "text"), ([7, 8], "stock_photo")), dry_run=True)
            self.assertTrue(any("за кінцем ролика" in p for p in bad["problems"]))
            good = director_plan.apply(PROJECT["id"], frames(([1, 2], "stock_photo"), ([3, 4], "text"), ([5, 6], "stock_photo"), ([7, 8], "text")), dry_run=True)
            self.assertFalse([p for p in good.get("problems", []) if "за кінцем ролика" in p])

    def test_the_channels_closing_wins_over_the_host_last_rule(self):
        # Астрофізика UA closes on another format; the director stopped between the two rules (26 November 2026)
        settings = {**CHANNEL["settings"], "weights": {"host": 50, "stock_photo": 50}}
        hosts_last = {**CHANNEL, "settings": settings}
        photo_last = {**CHANNEL, "settings": {**settings, "closing_sequence": ["auto", "auto", "stock_photo"]}}
        plan = frames(([1, 2], "host"), ([3, 4], "stock_photo"), ([5, 6], "host"), ([7, 8], "stock_photo"))
        with patch.object(store, "list_channels", return_value=[hosts_last]):
            self.assertTrue(any("Останній кадр ролику має бути з ведучим" in p for p in director_plan.apply(PROJECT["id"], plan, dry_run=True)["problems"]))
            self.assertTrue(director_plan.sentences(PROJECT["id"])["host_rules"]["last_frame"])
        with patch.object(store, "list_channels", return_value=[photo_last]):
            self.assertFalse(any("Останній кадр ролику має бути з ведучим" in p for p in director_plan.apply(PROJECT["id"], plan, dry_run=True)["problems"]))
            self.assertFalse(director_plan.sentences(PROJECT["id"])["host_rules"]["last_frame"])

    def test_a_plan_needs_the_voice(self):
        self.plan = None
        with self.assertRaises(store.StudioError):
            director_plan.sentences(PROJECT["id"])

    def test_automatic_formats_are_chosen_freely_while_fixed_share_is_checked(self):
        channel = {'id': PROJECT['channel_id'], 'settings': {
            'weights': {'text': 50, 'generated_photo': 25, 'animation': 25},
            'weights_auto': ['generated_photo', 'animation']}}
        with patch.object(store, 'list_channels', return_value=[channel]):
            info = director_plan.sentences(PROJECT['id'])
            self.assertEqual(info['auto_formats'], ['animation', 'generated_photo'])
            good = frames(([1, 2], 'text'), ([3, 4], 'generated_photo'),
                          ([5, 6], 'text'), ([7, 8], 'generated_photo'))
            self.assertTrue(director_plan.apply(PROJECT['id'], good, dry_run=True)['ok'])
            wrong = frames(([1, 2], 'text'), ([3, 4, 5, 6], 'generated_photo'),
                           ([7, 8], 'animation'))
            self.assertFalse(director_plan.apply(PROJECT['id'], wrong, dry_run=True)['ok'])

    def test_frames_are_checked_before_they_are_saved(self):
        def problems(*spec):
            result = director_plan.apply(PROJECT["id"], frames(*spec), dry_run=True)
            self.assertFalse(result["ok"])
            return " ".join(result["problems"])
        # one continuous scene stays one frame however many sentences it has (21 November 2026): no limit is checked
        long = director_plan.apply(PROJECT["id"], frames(([1, 2, 3, 4], "text"), ([5, 6, 7, 8], "stock_photo")), dry_run=True)
        self.assertFalse([p for p in long.get("problems", []) if "речень, а в кадрі" in p])
        self.assertIn("підряд від 3", problems(([1, 2], "text"), ([4, 5, 6], "stock_photo"), ([7, 8], "text")))
        self.assertIn("не використовує", problems(([1, 2], "host"), ([3, 4, 5], "text"), ([6, 7, 8], "stock_photo")))
        self.assertIn("1–6", problems(([1, 2, 3], "text"), ([4, 5, 6], "stock_photo")))
        self.assertIn("Текстова сцена", problems(([1, 2, 3], "text"), ([4, 5, 6], "text"), ([7, 8], "stock_photo")))
        self.assertIn("поспіль", problems(*[([n], "text") for n in range(1, 7)], ([7], "stock_photo"), ([8], "stock_photo")))
        self.assertEqual(self.saved, [])

    def test_good_frames_become_the_plan_with_times_from_the_voice(self):
        good = frames(([1, 2], "text"), ([3, 4], "stock_photo"), ([5, 6], "text"), ([7, 8], "stock_photo"))
        self.assertTrue(director_plan.apply(PROJECT["id"], good, dry_run=True)["ok"])
        self.assertEqual(self.saved, [])
        self.assertTrue(director_plan.apply(PROJECT["id"], good)["ok"])
        plan = self.saved[-1]
        self.assertEqual(plan["frame_source"], planner.DIRECTOR_FRAME_SOURCE)
        self.assertEqual([frame["format"] for frame in plan["frames"]], ["text", "stock_photo", "text", "stock_photo"])
        self.assertEqual(plan["frames"][0]["visual"], "a picture")
        self.assertEqual(plan["frames"][1]["start"], plan["frames"][1]["sentence_timings"][0]["start"])
        self.assertEqual(plan["frames"][-1]["end"], 16.5)
        # a later recognition of the same sentences keeps the director's frames and their ideas
        kept = planner.keep_director_frames(self.plan, plan)
        self.assertEqual([frame.get("visual") for frame in kept["frames"]], ["a picture"] * 4)


    def test_an_episode_with_its_own_shares_is_held_to_them(self):
        own = dict(PROJECT, plan_weights={"stock_photo": 100, "text": 0})
        with patch.object(store, "load_project", return_value=own):
            self.assertEqual(director_plan.sentences(own["id"])["shares"], {"stock_photo": 100.0})
            good = frames(([1, 2], "stock_photo"), ([3, 4], "stock_photo"), ([5, 6], "stock_photo"), ([7, 8], "stock_photo"))
            self.assertTrue(director_plan.apply(own["id"], good, dry_run=True)["ok"])

    def test_a_plan_waiting_for_the_director_keeps_waiting_through_a_rebuild(self):
        stale = dict(self.plan, director_stale=True)
        rebuilt = planner.keep_director_frames(dict(self.plan), stale)
        self.assertTrue(rebuilt.get("director_stale"))

if __name__ == "__main__":
    unittest.main()


class OpeningSequenceTest(unittest.TestCase):
    def test_the_first_three_frames_follow_the_channel_and_a_named_first_frame_beats_the_host(self):
        import director_plan
        host = {"weights": {"razgon_2d": 83, "host": 15, "text": 2}, "host_even_distribution": True}
        self.assertEqual(director_plan.opening(host), ["host"])                                   # all «Авто»: the host opens
        self.assertEqual(director_plan.opening({**host, "opening_sequence": ["auto", "auto", "auto"]}), ["host"])
        self.assertEqual(director_plan.opening({**host, "opening_sequence": ["razgon_2d", "host", "auto"]}), ["razgon_2d", "host"])
        self.assertEqual(director_plan.opening({**host, "opening_sequence": ["auto", "text", "auto"]}), ["host", "text"])
        plain = {"weights": {"stock_photo": 100}}
        self.assertEqual(director_plan.opening(plain), [])
        self.assertEqual(director_plan.opening({**plain, "first_clip_format": "stock_photo", "first_clip_count": 2}), ["stock_photo"] * 2)
        self.assertEqual(director_plan.opening({**plain, "first_clip_format": "stock_photo", "first_clip_count": 2,
                                                "opening_sequence": ["auto", "stock_photo", "auto"]}), [None, "stock_photo"])


class ContinuousSceneTest(unittest.TestCase):
    def test_an_idea_that_goes_on_from_the_frame_before_is_seen(self):
        import director_plan
        for idea in ("Та сама геометрія після зіткнення", "той самий кадр ближче", "Продовження руху камери"):
            self.assertTrue(director_plan.CONTINUES.match(idea), idea)
        for idea in ("Камера відходить від двох скупчень", "Нова сцена: телескоп Евклід", "Самі галактики"):
            self.assertFalse(director_plan.CONTINUES.match(idea), idea)


class ClosingSequenceTest(unittest.TestCase):
    """«Кінець ролика»: the formats of the last frames, the last one last (user, 26 November 2026)."""

    def test_the_last_frames_follow_the_channel(self):
        import director_plan
        plain = {"weights": {"stock_photo": 60, "text": 40}}
        self.assertEqual(director_plan.closing(plain), [])
        self.assertEqual(director_plan.closing({**plain, "closing_sequence": ["auto", "auto", "auto"]}), [])
        self.assertEqual(director_plan.closing({**plain, "closing_sequence": ["auto", "auto", "text"]}), ["text"])
        self.assertEqual(director_plan.closing({**plain, "closing_sequence": ["text", "auto", "stock_photo"]}), ["text", None, "stock_photo"])

