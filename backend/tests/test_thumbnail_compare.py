from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import thumbnail_compare as comparison
import store


class ThumbnailComparisonTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        p=patch.object(store,'project_dir',return_value=self.root);p.start();self.addCleanup(p.stop)

    def test_each_clone_keeps_its_own_source_after_reference_changes(self):
        source=self.root/'source.jpg';source.write_bytes(b'first reference')
        comparison.record('p','Превью v1.png',reference={'id':'first','title':'First'},image=source)
        first=comparison.describe('p','Превью v1.png')
        source.write_bytes(b'second reference')
        comparison.record('p','Превью v2.png',reference={'id':'second','title':'Second'},image=source)
        self.assertEqual(comparison.describe('p','Превью v1.png'),first)
        self.assertNotEqual(first['url'],comparison.describe('p','Превью v2.png')['url'])
        comparison.record('p','Превью v3.png',reference={'id':'second'},image=source)
        self.assertEqual(len(list((self.root/'preview/comparison').glob('*.jpg'))),2)
        with patch.object(store,'load_project'):
            self.assertEqual(comparison.source('p',first['url'].split('/')[-1]).read_bytes(),b'first reference')

    def test_edits_keep_exact_base_including_archived_cover(self):
        comparison.record('p','Превью v4.png',base='Превью до v4.png')
        self.assertEqual(comparison.describe('p','Превью v4.png'),{'kind':'edit','base':'Превью до v4.png'})

    def test_missing_or_invalid_sources_do_not_fabricate_a_comparison(self):
        self.assertIsNone(comparison.describe('p','Превью v1.png'))
        with patch.object(store,'load_project'):
            for name in ('../source.jpg','secret.jpg','0'*64+'.jpg'):
                with self.assertRaises(store.StudioError):comparison.source('p',name)
        with self.assertRaises(store.StudioError):comparison.record('p','../../outside.png',base='Превью v1.png')
