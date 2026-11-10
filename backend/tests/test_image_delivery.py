import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from PIL import Image, PngImagePlugin

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import image_delivery


def png_chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))


def marked_png(path):
    info = PngImagePlugin.PngInfo()
    info.add_text('Author', 'OpenAI metadata')
    info.add_itxt('XML:com.adobe.xmp', '<xmp>metadata</xmp>')
    Image.new('RGBA', (16, 9), (20, 40, 60, 128)).save(path, pnginfo=info, icc_profile=b'test-profile')
    raw = path.read_bytes()
    path.write_bytes(raw[:33] + png_chunk(b'caBX', b'c2pa.test') + png_chunk(b'eXIf', b'Exif test') + raw[33:])


class ImageDeliveryTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source, self.target = self.root/'source.png', self.root/'export.png'
        marked_png(self.source)

    def test_metadata_is_removed_with_identical_pixels_colours_and_original(self):
        raw = self.source.read_bytes()
        image_delivery.copy_png(self.source, self.target)
        clean = self.target.read_bytes()
        self.assertEqual(self.source.read_bytes(), raw)
        for marker in (b'caBX', b'eXIf', b'tEXt', b'iTXt', b'c2pa', b'OpenAI'):
            self.assertNotIn(marker, clean)
        with Image.open(self.source) as original, Image.open(self.target) as delivered:
            self.assertEqual(original.tobytes(), delivered.tobytes())
            self.assertEqual(original.info['icc_profile'], delivered.info['icc_profile'])
        self.assertEqual(self.source.stat().st_mtime_ns, self.target.stat().st_mtime_ns)
        self.assertEqual(clean, image_delivery.clean_png(clean))
        # Encoded compressed pixels are copied, not decoded/recompressed.
        at = raw.index(b'IDAT') - 4
        end = at + 12 + struct.unpack_from('>I', raw, at)[0]
        self.assertIn(raw[at:end], clean)

    def test_palette_and_transparency_survive(self):
        image = Image.new('P', (2, 2), 1)
        image.putpalette([0, 0, 0, 10, 20, 30] + [0] * 762)
        image.save(self.source, transparency=0)
        image_delivery.copy_png(self.source, self.target)
        with Image.open(self.source) as a, Image.open(self.target) as b:
            self.assertEqual(a.convert('RGBA').tobytes(), b.convert('RGBA').tobytes())

    def test_invalid_or_failed_copy_keeps_previous_output_and_no_temporary_file(self):
        self.target.write_bytes(b'previous')
        for bad in (b'not png', self.source.read_bytes()[:-3]):
            with self.subTest(bad=bad[:10]), self.assertRaises(OSError):
                image_delivery.clean_png(bad)
        with patch.object(Path, 'replace', side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError):
                image_delivery.copy_png(self.source, self.target)
        self.assertEqual(self.target.read_bytes(), b'previous')
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['export.png', 'source.png'])
        with self.assertRaises(OSError):
            image_delivery.copy_png(self.source, self.source)

    def test_translation_delivery_cleans_only_image_and_keeps_selected_original(self):
        import languages
        folder = self.root/'language'
        with patch.object(languages, 'episode_dir', return_value=folder), \
             patch.object(languages.language_thumbnails, 'current_file', return_value=self.source), \
             patch.object(languages, 'work_dir', return_value=self.root):
            raw = self.source.read_bytes()
            languages.copy_out({'id': 'p'}, 'pl', 'thumbnail')
            self.assertEqual((folder/"Прев'ю Polski.png").read_bytes(), image_delivery.clean_png(raw))
            self.assertEqual(self.source.read_bytes(), raw)
            (self.root/'voice.mp3').write_bytes(b'unchanged audio')
            languages.copy_out({'id': 'p'}, 'pl', 'voice')
            self.assertEqual((folder/'Озвучка Polski.mp3').read_bytes(), b'unchanged audio')
