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
