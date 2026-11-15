import base64
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import channel_hero
import store


class ChannelHeroTest(unittest.TestCase):
    def test_reference_is_channel_scoped_normalized_and_snapshot_is_optional(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(store, 'DATA_ROOT', Path(temp)), patch.object(store, 'get_channel_folder'):
            raw=io.BytesIO()
            Image.new('RGB',(2400,1200),'red').save(raw,format='JPEG')
            saved=channel_hero.save('c'*16,base64.b64encode(raw.getvalue()).decode())
            self.assertIn('/thumbnail-hero?v=',saved['url'])
            with Image.open(channel_hero.path('c'*16)) as image:
                self.assertEqual(image.size,(1600,800))
            project={'channel_id':'c'*16}
            work=Path(temp)/'job';work.mkdir()
            reference,rules=channel_hero.prepare(project,work)
            self.assertEqual(reference.read_bytes(),channel_hero.path('c'*16).read_bytes())
            self.assertIn('Preserve their identity',rules)
            reference,rules=channel_hero.prepare(project,work,False)
            self.assertIsNone(reference)
            self.assertIn('do not include the channel host',rules)
            self.assertEqual(channel_hero.prepare({'channel_id':'d'*16},work),(None,''))
            channel_hero.remove('c'*16)
            self.assertIsNone(channel_hero.info('c'*16))
            for invalid in ('broken',base64.b64encode(b'not a picture').decode()):
                with self.assertRaises(store.StudioError):channel_hero.save('c'*16,invalid)
            with self.assertRaises(store.StudioError):channel_hero.prepare(project,work,'false')


class HeroEverywhereTest(unittest.TestCase):
    """user, 15 November 2026: the hero for pictures and animations too, any photo shape, and a new pose every time"""

    def test_a_tall_photo_is_kept_whole_and_every_use_draws_the_hero_anew(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(store, 'DATA_ROOT', Path(temp)), patch.object(store, 'get_channel_folder'):
            raw = io.BytesIO()
            Image.new('RGB', (900, 1600), 'blue').save(raw, format='PNG')
            channel_hero.save('c' * 16, base64.b64encode(raw.getvalue()).decode())
            with Image.open(channel_hero.path('c' * 16)) as image:
                self.assertEqual(image.size, (900, 1600))          # not cropped to a square
            work = Path(temp) / 'job'; work.mkdir()
            _, rules = channel_hero.prepare({'channel_id': 'c' * 16}, work)
            self.assertIn('never a copy, cutout or paste', rules)
            self.assertIn('fresh camera angle', rules)
            rule = channel_hero.production_rule({'channel_id': 'c' * 16})
            self.assertIn(f'--ref "{channel_hero.path("c" * 16)}"', rule)
            self.assertIn('Щоразу інша поза, ракурс, емоція', rule)
            self.assertEqual(channel_hero.production_rule({'channel_id': 'd' * 16}), '')
