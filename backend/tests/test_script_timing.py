import copy
import unittest

import direction_contract as contract
import planner
import script_timing


SCRIPT = "Первое предложение про звёзды. Второе предложение длиннее первого и рассказывает больше. Третье короткое."
SETTINGS = {"weights": {"stock_photo": 1}, "max_sentences_per_scene": 4}


class EstimateTest(unittest.TestCase):
    def test_sentences_and_words_follow_the_script_at_the_channel_pace(self):
        timed = script_timing.estimate(SCRIPT, 0.08)
        self.assertEqual([s["text"] for s in timed["sentences"]], planner.split_sentences(SCRIPT))
        spans = [s["end"] - s["start"] for s in timed["sentences"]]
        self.assertGreater(spans[1], spans[0])   # a longer sentence sounds longer
        self.assertTrue(all(b["start"] >= a["end"] for a, b in zip(timed["sentences"], timed["sentences"][1:])))
        self.assertAlmostEqual(timed["duration"], script_timing.letters(SCRIPT) * 0.08, places=2)
        self.assertEqual(len(timed["words"]), len(SCRIPT.split()))
        self.assertTrue(all(w["end"] > w["start"] for w in timed["words"]))

    def test_an_estimated_plan_passes_the_checks_the_director_needs(self):
        timed = script_timing.estimate(SCRIPT, 0.08)
        plan = planner.build_plan(SCRIPT, SETTINGS, "Канал", timed["duration"], None, timed["sentences"])
        plan["timing"].update(status=script_timing.ESTIMATE, audio={"duration": timed["duration"], "estimated": True})
        planner.validate_synced_plan(plan, timed["duration"])
        self.assertTrue(script_timing.estimated(plan))


class KeepFramesTest(unittest.TestCase):
    def test_the_directors_groups_move_onto_the_real_voice(self):
        timed = script_timing.estimate(SCRIPT, 0.08)
        estimated = planner.build_plan(SCRIPT, SETTINGS, "Канал", timed["duration"], None, timed["sentences"])
        texts = planner.split_sentences(SCRIPT)
        rows = estimated["timing"]["sentences"]
        estimated["frames"] = [
            {"number": 1, "start": 0, "end": rows[2]["start"], "sentences": texts[:2], "sentence_timings": rows[:2],
             "format": "stock_photo", "visual": "небо"},
            {"number": 2, "start": rows[2]["start"], "end": timed["duration"], "sentences": texts[2:],
             "sentence_timings": rows[2:], "format": "stock_photo"}]
        estimated["frame_source"] = planner.DIRECTOR_FRAME_SOURCE
        estimated["timing"]["status"] = script_timing.ESTIMATE
        real = [{"text": texts[0], "start": 0.3, "end": 2.0}, {"text": texts[1], "start": 2.4, "end": 7.9},
                {"text": texts[2], "start": 8.3, "end": 9.5}]
        synced = planner.build_plan(SCRIPT, SETTINGS, "Канал", 10.0, None, real)
        synced["timing"]["audio"] = {"duration": 10.0}
        kept = planner.keep_director_frames(synced, estimated)
        self.assertEqual([f["sentences"] for f in kept["frames"]], [texts[:2], texts[2:]])
        self.assertEqual(kept["frames"][0]["visual"], "небо")
        self.assertEqual(kept["frames"][1]["start"], 8.3)
        self.assertNotIn("director_stale", kept)


class RetimeTest(unittest.TestCase):
    def packet(self, rows, duration):
        return {"signature": "new" if duration == 20 else "old", "duration": duration,
                "sentences": [{"number": i, **r} for i, r in enumerate(rows, 1)]}

    def test_cues_and_music_move_with_their_sentences(self):
        old = self.packet([{"text": "Один два три.", "start": 0, "end": 4}, {"text": "Четыре пять.", "start": 5, "end": 9}], 10)
        new = self.packet([{"text": "Один два три.", "start": 0.5, "end": 9}, {"text": "Четыре пять.", "start": 10, "end": 19}], 20)
        draft = {"source_signature": "old", "bible": "b",
                 "shots": [{"first_sentence": 1, "last_sentence": 2, "cues": [{"sentence": 2, "offset": 2.0, "name": "x"}]}],
                 "music": [{"start": 0, "end": 5, "mood": "calm"}, {"start": 5, "end": 10, "mood": "epic"}]}
        moved = contract.retimed(copy.deepcopy(draft), old, new)
        self.assertEqual(moved["source_signature"], "new")
        self.assertAlmostEqual(moved["shots"][0]["cues"][0]["offset"], 4.5)   # sentence 2 sounds 9 s instead of 4
        self.assertEqual(moved["music"][0]["start"], 0.0)
        self.assertEqual(moved["music"][0]["end"], moved["music"][1]["start"])
        self.assertAlmostEqual(moved["music"][1]["start"], 10.0)   # the second part still starts with sentence 2
        self.assertEqual(moved["music"][1]["end"], 20)
        self.assertEqual(draft["music"][0]["end"], 5)   # the saved draft is left alone

    def test_a_music_part_squeezed_to_nothing_joins_the_one_before(self):
        old = self.packet([{"text": "Один.", "start": 0, "end": 4}, {"text": "Два.", "start": 5, "end": 9}], 10)
        new = self.packet([{"text": "Один.", "start": 0, "end": 9}, {"text": "Два.", "start": 10, "end": 19}], 20)
        draft = {"source_signature": "old", "shots": [],
                 "music": [{"start": 0, "end": 9.5, "mood": "calm"}, {"start": 9.5, "end": 10, "mood": "epic"},
                           {"start": 10, "end": 10, "mood": "sad"}]}
        music = contract.retimed(draft, old, new)["music"]
        self.assertTrue(all(b["start"] == a["end"] for a, b in zip(music, music[1:])))
        self.assertTrue(all(m["end"] - m["start"] >= .05 for m in music))
        self.assertEqual(music[-1]["end"], 20)

    def test_a_moved_word_cue_past_its_sentence_keeps_the_sentence(self):
        packet = self.packet([{"text": "Один два три.", "start": 1, "end": 3}], 20)
        cue = {"sentence": 1, "word": "три"}
        words = [{"word": "Один", "start": 1.0}, {"word": "два", "start": 1.5}, {"word": "три", "start": 3.05}]
        with self.assertRaises(ValueError):
            contract.cue_time(cue, packet, words)
        self.assertEqual(contract.cue_time(cue, packet, words, lenient=True), 2.0)

    def test_other_sentences_need_a_new_direction(self):
        old = self.packet([{"text": "Один.", "start": 0, "end": 1}], 10)
        new = self.packet([{"text": "Другой.", "start": 0, "end": 1}], 20)
        with self.assertRaises(ValueError):
            contract.retimed({"shots": []}, old, new)


if __name__ == "__main__":
    unittest.main()


class EarlyKitTest(unittest.TestCase):
    def run_kit(self, estimated, needed=True):
        from unittest.mock import patch
        import director
        import production
        import production_kit
        plan = {"timing": {"status": script_timing.ESTIMATE if estimated else "audio_synced"},
                "frames": [{"number": n} for n in range(1, 13)]}
        data = {"effort": "high", "model": "claude-opus-5-5"}
        with patch.object(director.store, "load_project", return_value={"id": "p"}), \
             patch.object(director.store, "load_project_plan", return_value=plan), \
             patch.object(director.store, "project_dir", return_value=__import__("pathlib").Path("/tmp")), \
             patch.object(director, "animated", return_value=True), \
             patch.object(director, "save"), \
             patch.object(production_kit, "needed", return_value=needed), \
             patch.object(production_kit, "seed"), patch.object(production_kit, "record_cost"), \
             patch.object(production_kit, "ready", return_value=True), \
             patch.object(production, "kit_brief", return_value="kit"), \
             patch.object(director, "claude", return_value=(0, {"total_cost_usd": 1.5})) as claude:
            director.early_kit("p", "cli", data)
        return claude, data

    def test_the_kit_follows_a_direction_on_the_script(self):
        claude, data = self.run_kit(True)
        claude.assert_called_once()
        self.assertEqual(data["kit"], "ready")
        self.assertNotIn("stage", data)

    def test_a_direction_on_the_voice_leaves_the_kit_to_production(self):
        claude, data = self.run_kit(False)
        claude.assert_not_called()
        claude, data = self.run_kit(True, needed=False)
        claude.assert_not_called()


class RetimeSoonTest(unittest.TestCase):
    def test_the_move_runs_in_its_own_thread_and_starts_the_frames_after_it(self):
        import threading
        import time
        from unittest.mock import patch
        import director
        import production
        done = threading.Event()

        def retime(pid):
            with director.store.LOCK:   # the move may need the studio's lock (its subprocess posts to the studio)
                return True
        with patch.object(director, "workspace_estimated", return_value=True), \
             patch.object(director.store, "load_project_plan", return_value={"timing": {"status": "audio_synced"}}), \
             patch.object(director.store, "load_project", return_value={"id": "p"}), \
             patch.object(director, "animated", return_value=True), \
             patch.object(director, "retime", side_effect=retime), \
             patch.object(production, "start_from_plan", side_effect=lambda pid: done.set()) as frames:
            with director.store.LOCK:   # a caller holding the lock returns at once instead of waiting for the move
                began = time.monotonic()
                self.assertTrue(director.retime_soon("p", create_video=True))
                self.assertLess(time.monotonic() - began, 1)
            self.assertTrue(done.wait(5))
        frames.assert_called_once_with("p")

    def test_nothing_to_move_runs_nothing(self):
        from unittest.mock import patch
        import director
        with patch.object(director, "workspace_estimated", return_value=False):
            self.assertFalse(director.retime_soon("p"))


class PhotoChannelWorkspaceTest(unittest.TestCase):
    def test_a_photo_channels_workspace_takes_the_real_voice_then_the_frames(self):
        import threading
        from unittest.mock import patch
        import director
        import production
        done = threading.Event()
        with patch.object(director, "workspace_estimated", return_value=True), \
             patch.object(director.store, "load_project_plan", return_value={"timing": {"status": "audio_synced"}}), \
             patch.object(director.store, "load_project", return_value={"id": "p"}), \
             patch.object(director, "animated", return_value=False), \
             patch.object(director, "retime") as retime, \
             patch.object(director, "refresh_workspace", return_value=True) as refresh, \
             patch.object(production, "start_from_plan", side_effect=lambda pid: done.set()):
            self.assertTrue(director.retime_soon("p", create_video=True))
            self.assertTrue(done.wait(5))
        refresh.assert_called_once_with("p")
        retime.assert_not_called()   # a photo channel has no direction to move
