import base64
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import store  # noqa: E402
import style_copy  # noqa: E402

ANSWER = {
    "name": "Paper Cutout", "name_uk": "Паперова аплікація", "desc_uk": "Пласкі шари паперу з тінню.",
    "palette": {"sky": ["#9BC8CC", "#7eb3b8", "nope"], "ambient": "#a9c9cf", "key": "#ffd27a", "rim": "#fff", "wall": "#f2b84b"},
    "ink": "#151515", "feature": "#ffffff", "rimWidth": 40,
    "ui": {"card": "#fff6e8", "accent": "#e8453c"},
    "grade": {"contrast": 9, "sat": -1, "vignette": 0.2, "grain": "lots", "bloom": 0},
    "manner": {"wobble": 0, "boil": 0, "outline": None, "flat": True, "glow": False, "fillAlpha": 1, "tones": ["#000000"],
               "shadow": {"x": 6, "y": 99, "color": "#2e2018"}, "lineScale": 1.2, "grayscale": False, "paper": {"color": "#e3cba3", "amount": 0.15}},
}


def picture(size=(2400, 1200)) -> str:
    out = io.BytesIO()
    Image.new("RGB", size, (200, 120, 60)).save(out, format="PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()


class StyleCopyTest(unittest.TestCase):
    def test_answer_becomes_a_checked_razgon_style(self):
        d = style_copy.style_def(ANSWER)
        self.assertEqual(set(d["moods"]), set(style_copy.MOODS))
        day = d["moods"]["day"]
        self.assertEqual(day["sky"], ["#9bc8cc", "#7eb3b8"])          # a bad colour is dropped, the rest lower-cased
        self.assertEqual(day["rim"], "#fff1d6")                       # short hex is not trusted: the default stays
        self.assertEqual(day["grass"], "#4f8a55")                     # a missing colour gets the default
        self.assertEqual(d["rimWidth"], 6)
        self.assertEqual((d["grade"]["contrast"], d["grade"]["sat"], d["grade"]["grain"]), (1.4, 0, 0.04))
        self.assertEqual(d["ui"]["card"], "#fff6e8")
        m = d["manner"]
        self.assertTrue(m["flat"])
        self.assertFalse(m["glow"])
        self.assertNotIn("tones", m)                                  # one tone is not a tone set
        self.assertNotIn("outline", m)
        self.assertEqual(m["shadow"], {"x": 6.0, "y": 12.0, "color": "#2e201855"})
        self.assertEqual(m["paper"], {"color": "#e3cba3", "amount": 0.15})

    def test_empty_answer_gives_a_plain_style_without_manner(self):
        d = style_copy.style_def({})
        self.assertNotIn("manner", d)
        self.assertEqual(len(d["moods"]["night"]["sky"]), 2)
        self.assertEqual(d["name"], "Copied Style")

    def test_picture_is_shrunk_to_a_jpeg(self):
        url = style_copy.picture(picture())
        with Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))) as image:
            self.assertEqual((image.format, max(image.size)), ("JPEG", 1024))
        for bad in ("", "data:image/png;base64,bm90IGFuIGltYWdl", None):
            with self.assertRaises(style_copy.StyleCopyError):
                style_copy.picture(bad)

    def test_create_keeps_the_style_and_remove_drops_it(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(store, "DATA_ROOT", Path(tmp)), \
                patch.object(store, "get_channel_folder", return_value=Path(tmp)), patch.object(style_copy, "ask", return_value=ANSWER):
            style = style_copy.create("c" * 16, picture())
            self.assertRegex(style["id"], r"^custom-[0-9a-f]{10}$")
            self.assertEqual(style["name"], "Паперова аплікація")
            self.assertEqual([s["id"] for s in style_copy.load("c" * 16)], [style["id"]])
            self.assertEqual(style_copy.find("c" * 16, style["id"])["def"]["ink"], "#151515")
            style_copy.remove("c" * 16, style["id"])
            self.assertEqual(style_copy.load("c" * 16), [])
            with self.assertRaises(style_copy.StyleCopyError):
                style_copy.remove("c" * 16, style["id"])
            # a damaged file reads as no styles, not as an error
            style_copy.path("c" * 16).write_text("{not json")
            self.assertEqual(style_copy.load("c" * 16), [])
            style_copy.path("c" * 16).write_text(json.dumps([{"id": "../evil"}]))
            self.assertEqual(style_copy.load("c" * 16), [])


if __name__ == "__main__":
    unittest.main()
