import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import still


class StillWindowTest(unittest.TestCase):
    """A still's CapCut window never outlives the still: an export started later from the same process drew every
    CapCut seam outside it as a plain cut (26 November 2026)."""
    def test_window_is_set_while_drawing_and_restored_after(self):
        seen = {}
        def fake(*args, **kwargs):
            os.environ["STUDIO_CAPCUT_WINDOW"] = "1,5"
            seen["during"] = os.environ.get("STUDIO_CAPCUT_WINDOW")
            raise RuntimeError("boom")
        os.environ.pop("STUDIO_CAPCUT_WINDOW", None)
        with patch.object(still, "_still", side_effect=fake), self.assertRaises(RuntimeError):
            still.still(Path("p.json"), 3.0, Path("o.png"))
        self.assertEqual(seen["during"], "1,5")
        self.assertNotIn("STUDIO_CAPCUT_WINDOW", os.environ)


if __name__ == "__main__":
    unittest.main()
