import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

TOOL = Path(__file__).resolve().parents[1] / "sheet_2x2.py"


class SheetTest(unittest.TestCase):
    """One 16:9 sheet becomes four pictures without the white gap on their edges (user, 14 November 2026)."""

    def test_cuts_four_cells_along_the_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            sheet = Path(tmp, "sheet.png")
            im = Image.new("RGB", (1600, 900), "white")
            d = ImageDraw.Draw(im)
            boxes = [(20, 20, 780, 430), (830, 15, 1580, 440), (300, 470, 560, 880), (830, 475, 1585, 885)]
            colours = [(200, 40, 40), (40, 200, 40), (40, 40, 200), (90, 90, 90)]
            for box, colour in zip(boxes, colours):
                d.rectangle(box, fill=colour)
            im.save(sheet)
            subprocess.run([sys.executable, str(TOOL), str(sheet), "--out-dir", tmp, "--names", "a,b,c,-"],
                           check=True, capture_output=True)
            for name, box, colour in zip("abc", boxes, colours):
                out = Image.open(Path(tmp, name + ".png")).convert("RGB")
                self.assertEqual(out.size, (box[2] - box[0] + 1, box[3] - box[1] + 1))
                self.assertEqual(out.getpixel((0, 0)), colour)
                self.assertEqual(out.getpixel((out.width - 1, out.height - 1)), colour)
            self.assertFalse(Path(tmp, "-.png").exists())


if __name__ == "__main__":
    unittest.main()
