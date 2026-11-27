"""A published film's CapCut renders leave the shared cache at once (27 November 2026: «якщо опублікований ролик,
варто думаю очистити одразу переходи»)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import capcut_cleanup


class CapcutCleanupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        patcher = patch.object(capcut_cleanup.store, 'DATA_ROOT', self.data)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cache = self.data / 'capcut-cache'
        self.cache.mkdir()

    def film(self, pid, used, published=False, ready=None):
        folder = self.data / 'projects' / pid / 'capcut'
        folder.mkdir(parents=True)
        (folder / 'used.txt').write_text(''.join(n + '\n' for n in used))
        if ready:
            (folder / 'ready.json').write_text(json.dumps({'j1': {'url': '/api/capcut/media/' + ready}}))
        if published:
            (self.data / 'projects' / pid / 'published.json').write_text(json.dumps({'at': 1}))

    def file(self, name, size=10):
        (self.cache / name).write_bytes(b'x' * size)

    def test_only_the_published_films_own_files_go(self):
        for name in ('side-a.mp4', 'side-a.none', 'transition-direct-capcut-t.mov', 'transition-direct-capcut-p.mp4',
                     'side-shared.mp4', 'side-other.mp4', 'preview-effect.webm'):
            self.file(name)
        self.film('a' * 24, ['side-a.mp4', 'transition-direct-capcut-t.mov', 'side-shared.mp4', 'side-a.mp4'],
                  published=True, ready='transition-direct-capcut-p.mp4')
        self.film('b' * 24, ['side-shared.mp4', 'side-other.mp4'])
        freed = capcut_cleanup.clear('a' * 24)
        left = sorted(p.name for p in self.cache.iterdir())
        self.assertEqual(left, ['preview-effect.webm', 'side-other.mp4', 'side-shared.mp4'])
        self.assertEqual(freed, 40)
        self.assertFalse((self.data / 'projects' / ('a' * 24) / 'capcut' / 'used.txt').exists())

    def test_a_file_of_another_published_film_is_not_kept(self):
        self.file('side-shared.mp4')
        self.film('a' * 24, ['side-shared.mp4'], published=True)
        self.film('b' * 24, ['side-shared.mp4'], published=True)
        capcut_cleanup.clear('a' * 24)
        self.assertFalse((self.cache / 'side-shared.mp4').exists())


class LedgerTest(unittest.TestCase):
    def test_the_engine_notes_a_projects_files(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'engine'))
        import capcut_fx
        with tempfile.TemporaryDirectory() as folder, patch.object(capcut_fx, 'data_root', return_value=Path(folder)):
            project_file = Path(folder) / 'projects' / ('c' * 24) / 'renders' / 'job.json'
            project_file.parent.mkdir(parents=True)
            capcut_fx._note(project_file, Path(folder) / 'capcut-cache' / 'side-k.mp4')
            capcut_fx._note(Path(folder) / 'elsewhere' / 'still.json', Path('side-z.mp4'))
            ledger = Path(folder) / 'projects' / ('c' * 24) / 'capcut' / 'used.txt'
            self.assertEqual(ledger.read_text(), 'side-k.mp4\n')


if __name__ == '__main__':
    unittest.main()
