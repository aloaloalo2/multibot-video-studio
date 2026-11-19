"""The frame sessions get one line per shared helper instead of the whole helper files."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import helper_index


class HelperIndexTest(unittest.TestCase):
    def test_each_export_gives_its_call_and_the_comment_above(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scenes/channel").mkdir(parents=True)
            (root / "scenes/kit.js").write_text(
                "// ------------- камера\n// filmCam(t, dur, o): повільний наїзд камери\n"
                "export const filmCam = (t, dur, o = {}) => slowPush(t, dur, o);\n"
                "export const FACTS = { a: 1 };\nfunction hidden() {}\n", encoding="utf-8")
            (root / "scenes/channel/ui.js").write_text(
                "// say(g, str, x, y, k, o): рядок тексту з'являється з k\nexport function say(g, str, x, y, k, o = {}) {}\n",
                encoding="utf-8")
            text = helper_index.text(root)
        self.assertIn("scenes/kit.js:\n  filmCam(t, dur, o) · повільний наїзд камери", text)
        self.assertIn("  FACTS", text)
        self.assertIn("  say(g, str, x, y, k, o) · рядок тексту з'являється з k", text)
        self.assertNotIn("hidden", text)

    def test_a_film_without_helpers_gets_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(helper_index.text(Path(tmp)), "")
        self.assertEqual(helper_index.text(None), "")


if __name__ == "__main__":
    unittest.main()
