"""Full-frame text frames stand as one centred block (user, 25 November 2026, Andromeda frame 40: «текстові вставки
мають бути побудовані з розумом… розкидано як небуть без ідеї»)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import montage_ops  # noqa: E402


def text(cid, x, y, h, rows, title="K040 кадр"):
    words = [{"text": f"w{r}", "x": .5, "y": (r + .5) / rows, "width": .3, "height": .8 / rows, "start": 0} for r in range(rows)]
    return {"id": cid, "kind": "text", "title": title, "x": x, "y": y, "width": .6, "height": h, "text_role": "full_frame", "text_words": words}


def frame(*clips, plan_format="text"):
    background = {"id": "bg", "kind": "image", "title": "K040 фон", "x": .5, "y": .5, "width": 1, "height": 1}
    return {"group": {"id": "g", "title": "Кадр 40"}, "number": 40, "plan": {"format": plan_format}, "clips": [background, *clips]}


class ComposeTest(unittest.TestCase):
    def test_off_centre_block_and_detached_line_become_one_centred_block(self):
        main, tail = text("a", .385, .40, .5, 5), text("b", .385, .72, .13, 1, "K040 галактики")
        moves = dict((c["id"], ch) for c, ch in montage_ops.text_layout_changes(frame(main, tail)))
        for clip in (main, tail):
            self.assertAlmostEqual(montage_ops._letters_centre({**clip, **moves[clip["id"]]}), .5, places=4)
        tops = {}
        for clip in (main, tail):
            moved = {**clip, **moves[clip["id"]]}
            tops[clip["id"]] = montage_ops._text_extent(moved)
        block_top, block_bottom = tops["a"][0], tops["b"][1]
        self.assertAlmostEqual((block_top + block_bottom) / 2, .5, places=3)
        gap = tops["b"][0] - tops["a"][1]
        self.assertAlmostEqual(gap, montage_ops.TEXT_GAP * max(tops["a"][2], tops["b"][2]), places=4)

    def test_words_off_the_middle_of_their_box_are_centred_by_their_letters(self):
        main = text("a", .5, .5, .4, 1)
        main["text_words"][0].update(x=.3, width=.4)
        (clip, changes), = montage_ops.text_layout_changes(frame(main))
        self.assertAlmostEqual(changes["x"], .5 + .2 * .6, places=4)

    def test_highlight_over_some_words_moves_with_them(self):
        main = text("a", .45, .5, .4, 3)
        over = text("b", .45, .5, .4, 3, "K040 акцент фрази")
        over["text_words"] = over["text_words"][1:]
        over["text_words"][0].update(x=.7, width=.2)
        moves = dict((c["id"], ch) for c, ch in montage_ops.text_layout_changes(frame(main, over)))
        self.assertAlmostEqual(moves["a"]["x"] - .45, moves["b"]["x"] - .45, places=6)

    def test_the_coloured_end_line_takes_the_main_size_and_line_spacing(self):
        main = text("a", .385, .40, .5, 5)
        main["font_size"] = 62
        tail = text("b", .385, .75, .13, 1, "K040 галактики")
        tail.update(font_size=66, text=" ".join(w["text"] for w in tail["text_words"]))
        moves = dict((c["id"], ch) for c, ch in montage_ops.text_layout_changes(frame(main, tail)))
        self.assertEqual(moves["b"]["font_size"], 62)
        a, b = montage_ops._text_extent({**main, **moves["a"]}), montage_ops._text_extent({**tail, **moves["b"]})
        self.assertAlmostEqual(b[0] - a[1], 62 * .05 / 1080, places=4)

    def test_centred_frame_and_highlight_over_its_words_stay(self):
        main = text("a", .5, .5, .4, 3)
        over = text("b", .5, .5, .4, 3, "K040 акцент фрази")
        self.assertEqual(montage_ops.text_layout_changes(frame(main, over)), [])

    def test_text_beside_a_picture_is_the_directors_composition(self):
        main = text("a", .3, .5, .4, 3)
        photo = {"id": "p", "kind": "image", "title": "K040 фото", "x": .75, "y": .5, "width": .4, "height": .6}
        self.assertEqual(montage_ops.text_layout_changes(frame(main, photo)), [])
        code = {"id": "c", "kind": "animation", "content_type": "code", "title": "K040 моушн", "x": .5, "y": .5, "width": 1, "height": 1}
        self.assertEqual(montage_ops.text_layout_changes(frame(main, code)), [])

    def test_photo_frames_are_not_touched(self):
        label = text("a", .3, .8, .1, 1)
        label["text_role"] = None
        self.assertEqual(montage_ops.text_layout_changes(frame(label, plan_format="photo")), [])


if __name__ == "__main__":
    unittest.main()


class LineBreakTest(unittest.TestCase):
    """Lines break by sense (user, 25 November 2026: «дуже дивно чому текст так дивно розташований»)."""

    def lines(self, text, limit=967):
        import typography
        words = text.split()
        sizes = [len(w) * 32.0 for w in words]
        cuts = typography.breaks(words, sizes, 16.0, limit)
        return [" ".join(words[a:b]) for a, b in zip([0] + cuts, cuts + [len(words)])]

    def test_no_line_ends_on_a_preposition_and_numbers_stay_whole(self):
        for line in self.lines("Одна мигающая звезда на одной пластинке закрыла спор, который тянулся десятилетиями"):
            self.assertNotIn(line.split()[-1], {"на", "в", "с", "который"})
        joined = self.lines("Андромеда приближается к нам со скоростью сто десять километров в секунду")
        self.assertFalse(any(line.endswith("сто") for line in joined))

    def test_lines_are_about_one_length(self):
        lines = self.lines("Получается, глаз ловит свет, который был в пути дольше, чем существует всё человечество")
        widths = [len(line) for line in lines]
        self.assertLess(max(widths) - min(widths), 16)


class HeadlineDesignTest(unittest.TestCase):
    """A lead-in and a key phrase become a designed headline (user, 25 November 2026: «в 100 раз крутіші»)."""

    def test_key_phrase_is_large_accent_with_a_growing_line_under_it(self):
        lead = text("a", .385, .40, .5, 5)
        lead.update(font_size=62, start=10.0, text=" ".join(w["text"] for w in lead["text_words"]))
        key = text("b", .385, .75, .13, 1, "K040 галактики")
        key.update(font_size=66, start=10.0, color="#5ff2e8", text="w0")
        key["text_words"][0]["start"] = 6.0
        f = frame(lead, key)
        f.update(start=10.0, end=19.0)
        actions = montage_ops.text_design_changes(f, "#ff00aa")
        updates = {a["payload"]["clip_id"]: a["payload"]["changes"] for a in actions if a["type"] == "update_clip"}
        self.assertLess(updates["a"]["font_size"], updates["b"]["font_size"])
        self.assertEqual(updates["b"]["color"], "#5ff2e8")
        line = next(a["payload"] for a in actions if a["type"] == "add_clip")
        self.assertTrue(line["title"].endswith("лінія"))
        self.assertGreater(line["y"], updates["b"]["y"])
        appear = line["keyframes"][0]["time"]
        self.assertAlmostEqual(appear, 6.15, places=2)   # on the key word, from its clip start
        self.assertLessEqual(appear + 10.0, 19.0 - montage_ops.LAST_QUIET)
        self.assertGreaterEqual(min(k["scale"] for k in line["keyframes"]), .05)
        # designed once: a second pass leaves the frame alone
        f["clips"].append({"id": "l", "kind": "animation", "content_type": "shape", "title": "K040 лінія", "width": .3, "height": .01})
        self.assertEqual(montage_ops.text_design_changes(f, "#ff00aa"), [])
