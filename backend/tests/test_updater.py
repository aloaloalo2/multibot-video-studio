import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from updater import Updater, UpdateError, update_at_start
import app
import store


class UpdateTest(unittest.TestCase):
    def git(self, root, *args):
        return subprocess.run(['git', '-c', 'user.name=Studio test', '-c', 'user.email=test@localhost', *args], cwd=root, check=True, capture_output=True)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.remote, self.author, self.install = root/'remote.git', root/'author', root/'install'
        self.git(root, 'init', '--bare', '--initial-branch=main', str(self.remote))
        self.author.mkdir()
        self.git(self.author, 'init', '-b', 'main')
        (self.author/'.gitignore').write_text('backend/data/\n')
        (self.author/'app.txt').write_text('first')
        self.git(self.author, 'add', '.')
        self.git(self.author, 'commit', '-m', 'first')
        self.git(self.author, 'remote', 'add', 'origin', str(self.remote))
        self.git(self.author, 'push', '-u', 'origin', 'main')
        self.git(root, 'clone', str(self.remote), str(self.install))
        self.updater = Updater(self.install)
        self.data = self.install/'backend'/'data'/'project.txt'
        self.data.parent.mkdir(parents=True)
        self.data.write_text('my project')

    def tearDown(self):
        self.temp.cleanup()

    def publish(self, content='second'):
        (self.author/'app.txt').write_text(content)
        self.git(self.author, 'add', 'app.txt')
        self.git(self.author, 'commit', '-m', 'update')
        self.git(self.author, 'push')

    def test_update_preserves_local_projects(self):
        self.publish()
        self.assertEqual(self.updater.refresh()['status'], 'available')
        self.updater.apply()
        self.assertEqual((self.install/'app.txt').read_text(), 'second')
        self.assertEqual(self.data.read_text(), 'my project')
        self.assertEqual(self.updater.refresh()['status'], 'current')

    def test_startup_updates_before_the_app_is_launched(self):
        self.publish()
        self.assertEqual(update_at_start(self.install), 'updated')
        self.assertEqual((self.install/'app.txt').read_text(), 'second')
        self.assertEqual(self.data.read_text(), 'my project')

    def test_local_changes_are_never_overwritten(self):
        self.publish()
        (self.install/'app.txt').write_text('local changes')
        self.assertEqual(self.updater.refresh()['status'], 'local_changes')
        with self.assertRaises(UpdateError): self.updater.apply()
        self.assertEqual((self.install/'app.txt').read_text(), 'local changes')

    def test_remote_cannot_replace_project_data(self):
        folder = self.author/'backend'/'data'
        folder.mkdir(parents=True)
        (folder/'project.txt').write_text('remote')
        self.git(self.author, 'add', '-f', 'backend/data/project.txt')
        self.git(self.author, 'commit', '-m', 'unsafe')
        self.git(self.author, 'push')
        self.assertEqual(self.updater.refresh()['status'], 'unsafe_update')
        with self.assertRaises(UpdateError): self.updater.apply()
        self.assertEqual(self.data.read_text(), 'my project')

    def test_update_does_not_interrupt_an_export_or_audio_analysis(self):
        with patch.dict(app.ACTIVE_EXPORTS, {'test': {}}, clear=True), patch.object(app.UPDATE_MANAGER, 'apply') as apply:
            with self.assertRaises(store.StudioError): app.begin_update()
            apply.assert_not_called()
        with patch.dict(app.ACTIVE_EXPORTS, {}, clear=True), patch.object(app.analysis_jobs, 'ACTIVE_JOBS', {'test'}), patch.object(app.UPDATE_MANAGER, 'apply') as apply:
            with self.assertRaises(store.StudioError): app.begin_update()
            apply.assert_not_called()


if __name__ == '__main__':
    unittest.main()
