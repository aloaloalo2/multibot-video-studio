"""The film's shared kit and the channel library (user, 15 November 2026)."""
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import production_kit as kit
import store


class KitTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.film = self.root / 'film'; (self.film / 'scenes' / 'shots').mkdir(parents=True); (self.film / 'story').mkdir()
        for name in ('cast.js', 'assets.js', 'lib.js'):
            (self.film / 'scenes' / name).write_text('// shared\n')
        (self.film / 'scenes' / 'lib_c11.js').write_text('// own\n')
        self.project = {'id': 'p', 'channel_id': 'c', 'name': 'Film'}
        patches = [patch.object(kit, 'razgon', lambda project: self.film), patch.object(store, 'DATA_ROOT', self.root / 'data')]
        for p in patches:
            p.start(); self.addCleanup(p.stop)

    def writable(self, path):
        return bool(os.stat(path).st_mode & stat.S_IWUSR)

    def test_lock_makes_only_shared_files_read_only_and_unlock_restores_them(self):
        kit.lock(self.project)
        self.assertFalse(self.writable(self.film / 'scenes' / 'cast.js'))
        self.assertTrue(self.writable(self.film / 'scenes' / 'lib_c11.js'))
        kit.unlock(self.project)
        self.assertTrue(self.writable(self.film / 'scenes' / 'cast.js'))

    def test_ready_kit_tells_sessions_which_files_are_read_only(self):
        self.assertEqual(kit.chunk_note(self.project), '')
        (self.film / kit.KIT_FILE).write_text(json.dumps({'ready': True}))
        note = kit.chunk_note(self.project)
        self.assertIn('scenes/cast.js', note)
        self.assertIn('scenes/lib_<перший кадр партії>.js', note)

    def test_kit_is_needed_only_for_many_razgon_frames_and_once(self):
        plan = {'frames': [{'number': n, 'format': 'razgon_2d'} for n in range(1, 21)]}
        with patch.object(store, 'load_project_plan', lambda pid: plan):
            self.assertTrue(kit.needed(self.project, list(range(1, 21))))
            self.assertFalse(kit.needed(self.project, list(range(1, 6))))
            (self.film / kit.KIT_FILE).write_text(json.dumps({'ready': True}))
            self.assertFalse(kit.needed(self.project, list(range(1, 21))))

    def test_library_is_seeded_into_the_film_and_takes_back_what_the_film_added(self):
        library = kit.library_dir(self.project); library.mkdir(parents=True)
        (library / 'people.js').write_text('// v1\n')
        self.assertEqual(kit.seed(self.project), ['people.js'])
        channel = self.film / 'scenes' / 'channel'
        (channel / 'people.js').write_text('// v2\n')
        (channel / 'price_tag.js').write_text('// new\n')
        self.assertEqual(sorted(kit.harvest(self.project)), ['people.js', 'price_tag.js'])
        self.assertEqual((library / 'people.js').read_text(), '// v2\n')
        self.assertEqual([p.read_text() for p in (library / 'history').rglob('people.js')], ['// v1\n'])
        self.assertEqual(kit.harvest(self.project), [])


if __name__ == '__main__':
    unittest.main()
