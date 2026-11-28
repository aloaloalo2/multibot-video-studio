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


class ListenerTest(unittest.TestCase):
    """A waiting script whose session is gone, or a reused pid, is no listener (20 November 2026)."""

    def run_ps(self, rows):
        def fake(cmd, **kw):
            pid = int(cmd[-1])
            return subprocess.CompletedProcess(cmd, 0, stdout=rows.get(pid, ''), stderr='')
        return patch.object(subprocess, 'run', side_effect=fake)

    def test_alive_session_orphan_and_reused_pid(self):
        wait = 'python3 VideoKey Studio/tools/youtube_publish.py wait'
        with self.run_ps({10: f'20 {wait}', 20: '30 /bin/zsh -c ...'}):
            self.assertTrue(published.waiting_script(10))
        with self.run_ps({10: f'20 {wait}', 20: '1 /bin/zsh -c ...'}), patch('os.kill') as kill:
            self.assertFalse(published.waiting_script(10))
            kill.assert_called_once()
        with self.run_ps({10: '20 /usr/bin/some-other-app'}):
            self.assertFalse(published.waiting_script(10))


class OpenSessionTest(unittest.TestCase):
    """Cancelled and sent again within minutes: a new Claude session opens (20 November 2026)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for pid in ('a' * 24, 'b' * 24):
            (root / 'projects' / pid).mkdir(parents=True); (root / 'projects' / pid / 'project.json').write_text('{}')
        patches = [patch.object(store, 'DATA_ROOT', root), patch.object(store, 'PROJECTS_ROOT', root / 'projects'),
                   patch.object(store, 'project_dir', side_effect=lambda pid: root / 'projects' / pid),
                   patch.object(store, 'load_project', side_effect=lambda pid: {'id': pid, 'channel_id': 'c'}),
                   patch.object(published, 'listener', return_value=False),
                   patch.object(published, 'open_claude', return_value=True)]
        for p in patches:
            p.start(); self.addCleanup(p.stop)

    def test_a_lone_episode_opens_a_session_even_right_after_another(self):
        self.assertTrue(published.enqueue('a' * 24)['open_session'])
        published.cancel('a' * 24)
        self.assertTrue(published.enqueue('a' * 24)['open_session'])
        self.assertFalse(published.enqueue('b' * 24)['open_session'])   # two waiting: the one just opened takes both


class BetweenEpisodesTest(OpenSessionTest):
    """The publishing session has just run `done … && stop` and starts `wait` two seconds later: no second session opens
    in that gap (28 November 2026), and one opens once the pause is over and nobody took the queue."""

    def test_no_new_session_right_after_a_publication(self):
        import json, os, time
        done = store.PROJECTS_ROOT / ('b' * 24) / 'published.json'
        done.write_text(json.dumps({'at': time.time(), 'source': 'youtube_publish'}))
        self.assertFalse(published.enqueue('a' * 24)['open_session'])
        rows = published.queue(); rows[0]['at'] = time.time() - 600
        store.atomic_json(published.queue_path(), rows)
        self.assertFalse(published.ensure_session())
        old = time.time() - published.BETWEEN_SECONDS - 5
        os.utime(done, (old, old))
        self.assertTrue(published.ensure_session())

    def test_a_blue_tag_mark_is_not_a_session(self):
        import json, time
        (store.PROJECTS_ROOT / ('b' * 24) / 'published.json').write_text(json.dumps({'at': time.time(), 'source': 'finder-blue-tag'}))
        self.assertTrue(published.enqueue('a' * 24)['open_session'])
