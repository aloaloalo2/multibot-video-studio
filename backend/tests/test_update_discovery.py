"""The downloaded Mac updater finds the intended installation without a folder picker."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class UpdateDiscoveryTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.home=self.base/'home';self.home.mkdir()
        self.source=(Path(__file__).resolve().parents[2]/'Оновити студію.command').read_text()
        self.namespace={'__name__':'discovery_fixture'}
        block=self.source.split("<<'FIND_STUDIO'\n",1)[1].split('\nFIND_STUDIO\n',1)[0]
        exec(compile(block,'updater-discovery','exec'),self.namespace)
        self.origins={};self.pids='';self.cwds={};self.indexed='';self.commands=[]
        self.namespace['capture']=self.capture
        home=patch.object(Path,'home',return_value=self.home);home.start();self.addCleanup(home.stop)

    def studio(self,name,official=True):
        root=self.base/name;(root/'backend').mkdir(parents=True);(root/'.git').mkdir()
        (root/'backend/app.py').write_text('# fixture')
        self.origins[str(root.resolve())]='https://github.com/aloaloalo2/multibot-video-studio.git' if official else 'https://example.test/other.git'
        return root.resolve()

    def capture(self,args):
        self.commands.append(args)
        if args[0]=='git':return self.origins.get(args[2],'')+'\n'
        if args[0]=='mdfind':return self.indexed
        if args[0]=='lsof':return self.pids if '-tiTCP:8770' in args else self.cwds.get(args[args.index('-p')+1],'')
        raise AssertionError('Unexpected discovery command: '+repr(args))

    def registered(self,root):
        config=self.home/'Library/Application Support/VideoKey Studio/config.json'
        config.parent.mkdir(parents=True,exist_ok=True)
        config.write_text(json.dumps({'command':str(root/'Запустить студию.command')}))

    def test_running_studio_wins_over_registered_and_downloaded_copies(self):
        active=self.studio('Потрібна студія з пробілами');other=self.studio('Old copy')
        self.registered(other);self.pids='42\n42\n';self.cwds['42']='p42\nn'+str(active)+'\n'
        self.assertEqual(self.namespace['find_root'](other),active)
        self.assertFalse(any(command[0]=='mdfind' for command in self.commands))
        self.assertNotIn('choose folder',self.source)

    def test_registered_launcher_finds_a_closed_studio(self):
        installed=self.studio('Installed');self.registered(installed)
        self.assertEqual(self.namespace['find_root'](self.base/'Downloads'),installed)
        self.assertFalse(any(command[0]=='mdfind' for command in self.commands))

    def test_a_single_indexed_copy_is_found_without_recursive_file_scanning(self):
        installed=self.studio('Custom location');self.indexed=str(installed/'Запустить студию.command')+'\n'
        self.assertEqual(self.namespace['find_root'](self.base/'Downloads'),installed)
        self.assertTrue(any(command[0]=='mdfind' for command in self.commands))
        self.assertLess(len(self.commands),10)

    def test_multiple_closed_copies_require_opening_the_intended_studio(self):
        copies=[self.studio('First'),self.studio('Second')]
        self.indexed='\n'.join(str(root/'Запустить студию.command') for root in copies)
        with self.assertRaisesRegex(SystemExit,'Відкрийте потрібну студію'):
            self.namespace['find_root'](self.base/'Downloads')
        self.assertTrue(all((root/'backend/app.py').read_text()=='# fixture' for root in copies))

    def test_unknown_repositories_and_invalid_process_ids_are_ignored(self):
        other=self.studio('Unrelated repo',official=False)
        self.pids='not-a-pid\n';self.indexed=str(other/'Запустить студию.command')
        self.assertIsNone(self.namespace['official_root'](other))
        with self.assertRaisesRegex(SystemExit,'Спочатку відкрийте студію'):
            self.namespace['find_root'](self.base/'Downloads')
        self.assertFalse(any('-p' in command for command in self.commands))

    def test_adjacent_checkout_and_git_worktrees_are_supported(self):
        installed=self.studio('Beside the helper');(installed/'.git').rmdir();(installed/'.git').write_text('gitdir: fixture')
        self.assertEqual(self.namespace['find_root'](installed),installed)
