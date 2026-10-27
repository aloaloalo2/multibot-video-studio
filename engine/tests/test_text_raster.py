"""Text export must retain complete glyphs, including descenders and accents."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import render
from font_catalog import FONT_FAMILIES


class TextRasterTest(unittest.TestCase):
    def font(self, family, weight, size):
        font = ImageFont.truetype(str(render.first_font(family, weight)), size)
        try:
            font.set_variation_by_axes([weight if b'Weight' in a['name'] else a['default']
                                        for a in font.get_variation_axes()])
        except (OSError, AttributeError):
            pass
        return font

    def test_complete_letters_for_every_studio_font(self):
        # A generous independent reference exposes truncation and accidental
        # font shrinking. Crop to the ink to ignore intentional line leading.
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)/'text.png'
            for family in sorted(FONT_FAMILIES):
                for weight in (400, 500, 700):
                    for text in ('ДЩЦруфйЁ', 'Ágjýj', 'Корицы', 'Чичваркин'):
                        with self.subTest(family=family, weight=weight, text=text):
                            size = 76
                            reference = Image.new('L', (1600, 500))
                            ImageDraw.Draw(reference).text((100, 100), text,
                                font=self.font(family, weight, size), fill=255)
                            render.text_bitmap({'text':text, 'font_family':family,
                                'font_weight':weight, 'font_size':size, 'width':1200,
                                'height':300}, target, 1920, 1080)
                            with Image.open(target) as bitmap:
                                alpha = bitmap.getchannel('A')
                                bounds = alpha.getbbox()
                                self.assertIsNotNone(bounds)
                                self.assertGreater(bounds[0], 0)
                                self.assertGreater(bounds[1], 0)
                                self.assertLess(bounds[2], bitmap.width)
                                self.assertLess(bounds[3], bitmap.height)
                                np.testing.assert_array_equal(np.array(alpha.crop(bounds)),
                                    np.array(reference.crop(reference.getbbox())))

    def test_multiline_descenders_and_alignment_keep_all_ink(self):
        with tempfile.TemporaryDirectory() as temp:
            for align in ('left', 'center', 'right'):
                path = Path(temp)/(align+'.png')
                render.text_bitmap({'text':'Корицы\nдругой ДЩЦруфйЁ',
                    'font_family':'Literata', 'font_weight':500, 'font_size':76,
                    'width':1200, 'height':400, 'text_align':align}, path, 1920, 1080)
                with Image.open(path) as image:
                    bounds=image.getchannel('A').getbbox()
                    self.assertGreater(bounds[0], 0)
                    self.assertGreater(bounds[1], 0)
                    self.assertLess(bounds[2], image.width)
                    self.assertLess(bounds[3], image.height)
                    reference=Image.new('L',(1200,500))
                    draw=ImageDraw.Draw(reference);font=self.font('Literata',500,76)
                    draw.text((100,100),'Корицы',font=font,fill=255)
                    draw.text((100,197),'другой ДЩЦруфйЁ',font=font,fill=255)
                    self.assertEqual(sum(image.getchannel('A').getdata()),sum(reference.getdata()))


if __name__ == '__main__':
    unittest.main()
