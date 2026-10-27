import unittest
import sys
from pathlib import Path

from PIL import ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import font_catalog
import graphics


class FontCatalogTests(unittest.TestCase):
    def test_available_fonts_are_valid_for_editor_and_export(self):
        self.assertEqual(len(font_catalog.CATALOG), 40)
        self.assertEqual(len(font_catalog.FONT_FILES), 40)
        for entry in font_catalog.CATALOG:
            family = entry['family']
            self.assertEqual(graphics.validate({'font_family': family})['font_family'], family)
            self.assertTrue((font_catalog.FONT_ROOT / entry['license']).is_file())
            for weight in (400, 700):
                face = ImageFont.truetype(str(font_catalog.font_path(family, weight)), 32)
                self.assertGreater(face.getlength('Київ Ёжик Grüße'), 0)


if __name__ == '__main__':
    unittest.main()
