import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import published
import store


def tag(folder, names):
    data = plistlib.dumps(names, fmt=plistlib.FMT_BINARY).hex()
    subprocess.run(['xattr', '-wx', 'com.apple.metadata:_kMDItemUserTags', data, str(folder)], check=True)


class PublishedTest(unittest.TestCase):
    """The blue Finder tag marks an episode as published, and the mark stays without the folder (16 November 2026)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.folder = root / 'episode'; self.folder.mkdir()
        self.project = root / 'project'; self.project.mkdir()
        patcher = patch.object(store, 'project_dir', return_value=self.project); patcher.start(); self.addCleanup(patcher.stop)
        published._SEEN.clear()

    def test_blue_in_any_language_marks_it_and_the_mark_stays(self):
        item = {'id': 'p', 'episode_path': str(self.folder)}
        self.assertIsNone(published.check(item))
        tag(self.folder, ['Бузковий\n3'])
        self.assertIsNone(published.check(item))           # another colour is not a publication
        tag(self.folder, ['Синій\n4'])
        self.assertTrue(published.check(item)['at'])
        self.folder.rmdir()                                 # the folder is gone, the mark is not
        self.assertTrue(published.check(item)['at'])


if __name__ == '__main__':
    unittest.main()


class FinderInfoColourTest(PublishedTest):
    def test_the_old_finder_colour_counts_too(self):
        info = bytearray(32); info[9] = 4 << 1   # Finder's colour 4 (blue) in the FinderInfo flags
        subprocess.run(['xattr', '-wx', 'com.apple.FinderInfo', info.hex(), str(self.folder)], check=True)
        self.assertTrue(published.check({'id': 'p', 'episode_path': str(self.folder)})['at'])


class CancelTest(unittest.TestCase):
    """«Скасувати» takes an episode out of the queue and marks a running one (20 November 2026)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.project = root / 'project'; self.project.mkdir()
        patches = [patch.object(store, 'project_dir', return_value=self.project),
                   patch.object(store, 'load_project', return_value={'id': 'a' * 24}),
                   patch.object(store, 'DATA_ROOT', root), patch.object(store, 'PROJECTS_ROOT', root / 'projects')]
        for pid in ('a' * 24, 'b' * 24):
            (root / 'projects' / pid).mkdir(parents=True); (root / 'projects' / pid / 'project.json').write_text('{}')
        for p in patches:
            p.start(); self.addCleanup(p.stop)

    def test_a_queued_episode_leaves_the_queue_and_the_card_is_free_again(self):
        pid = 'a' * 24
        store.atomic_json(published.queue_path(), [{'project': pid}, {'project': 'b' * 24}])
        result = published.cancel(pid)
        self.assertTrue(result['was_queued'])
        self.assertEqual([row['project'] for row in published.queue()], ['b' * 24])
        self.assertIsNone(published.publishing({'id': pid}))

    def test_a_running_publication_is_marked_for_the_session(self):
        pid = 'a' * 24
        store.atomic_json(self.project / 'publishing.json', {'at': 1, 'step': 'Відео у формі'})
        self.assertTrue(published.cancel(pid)['was_publishing'])
        self.assertTrue(store.read_json(self.project / 'publishing.json', {})['cancelled'])
        self.assertIsNone(published.publishing({'id': pid}))

    def test_a_deleted_project_leaves_the_queue_by_itself(self):
        import shutil
        store.atomic_json(published.queue_path(), [{'project': 'a' * 24}, {'project': 'b' * 24}])
        shutil.rmtree(store.PROJECTS_ROOT / ('b' * 24))
        self.assertEqual([row['project'] for row in published.queue()], ['a' * 24])
        self.assertEqual(len(store.read_json(published.queue_path(), [])), 1)
