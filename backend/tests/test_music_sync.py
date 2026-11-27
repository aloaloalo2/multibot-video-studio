"""The channels' music library reaches every Mac from its repository (27 November 2026: «на інш пк нема музики»)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import music_sync

REMOTE = [{'id': 'aaa', 'file': 'files/aaa.mp3', 'title': 'A', 'artist': 'X', 'category': 'спокійна', 'license': 'L'},
          {'id': 'bbb', 'file': 'files/bbb.mp3', 'title': 'B', 'artist': 'Y', 'category': 'темна', 'license': 'L'},
          {'id': 'evil', 'file': '../outside.mp3'}]


class MusicSyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'music-library'
        patcher = patch.object(music_sync.music_library, 'root', return_value=self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        self.asked = []

    def get(self, url):
        self.asked.append(url)
        name = url[len(music_sync.RAW):]
        if name == 'catalog.json':
            return json.dumps(REMOTE).encode()
        if name.startswith('analysis/'):
            return b'{"bpm": 100}'
        return b'mp3:' + name.encode()

    def test_downloads_missing_tracks_and_keeps_local_rows(self):
        (self.root / 'files').mkdir(parents=True)
        (self.root / 'files' / 'aaa.mp3').write_bytes(b'mine')
        local = [{'id': 'aaa', 'file': 'files/aaa.mp3', 'title': 'A', 'vocals': True}]
        (self.root / 'catalog.json').write_text(json.dumps(local))
        added = music_sync.sync(get=self.get)
        self.assertEqual(added, 1)
        self.assertEqual((self.root / 'files' / 'aaa.mp3').read_bytes(), b'mine')
        self.assertEqual((self.root / 'files' / 'bbb.mp3').read_bytes(), b'mp3:files/bbb.mp3')
        self.assertTrue((self.root / 'analysis' / 'bbb.json').is_file())
        self.assertFalse((Path(self.tmp.name) / 'outside.mp3').exists())
        rows = json.loads((self.root / 'catalog.json').read_text())
        self.assertEqual([r['id'] for r in rows], ['aaa', 'bbb'])
        self.assertTrue(rows[0]['vocals'])   # this Mac's own mark stays
        self.assertEqual(music_sync.sync(get=self.get), 0)   # a second start downloads nothing

    def test_offline_start_leaves_the_library_alone(self):
        def offline(url):
            raise OSError('no network')
        with patch.object(music_sync, '_get', offline):
            music_sync.run()
        self.assertIn('no network', music_sync.STATE['error'])
        self.assertFalse(self.root.exists())


if __name__ == '__main__':
    unittest.main()
