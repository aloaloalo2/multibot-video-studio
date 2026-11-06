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
