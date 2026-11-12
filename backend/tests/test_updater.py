import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'engine' / 'tests'))
from updater import Updater, UpdateError, update_at_start
import preview_js
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

    def backup(self):
        folder=Path(self.updater.state['backup'])
        return folder,json.loads((folder/'manifest.json').read_text())

    def test_local_changes_are_saved_before_the_official_update(self):
        self.publish()
        (self.install/'app.txt').write_text('local changes')
        self.assertEqual(self.updater.refresh()['status'], 'available')
        self.updater.apply()
        self.assertEqual((self.install/'app.txt').read_text(), 'second')
        folder,backup=self.backup()
        self.assertEqual(self.git(self.install,'show',backup['stash']+':app.txt').stdout,b'local changes')
        self.assertEqual(backup['status'],'updated')
        self.assertEqual(self.data.read_text(),'my project')

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

    def test_unrelated_stray_files_stay_in_place_without_blocking_updates(self):
        (self.install/'app.txt').write_text('local changes')
        self.assertEqual(self.updater.refresh()['status'], 'current')   # nothing new on GitHub: no notice
        self.publish()
        for n in range(9):
            (self.install/f'copy {n}.txt').write_text('stray')
        state = self.updater.refresh()
        self.assertEqual(state['status'], 'available')
        public = self.updater.public_state()
        self.assertNotIn('revision', public)
        self.updater.apply()
        for n in range(9):self.assertEqual((self.install/f'copy {n}.txt').read_text(),'stray')

    def test_an_ignored_file_the_update_would_replace_is_backed_up(self):
        (self.author/'new.txt').write_text('remote')
        self.git(self.author, 'add', 'new.txt')
        self.git(self.author, 'commit', '-m', 'new file')
        self.git(self.author, 'push')
        self.git(self.install, 'fetch')
        (self.install/'.git'/'info'/'exclude').write_text('new.txt\n')   # an untracked file Git does not list
        (self.install/'new.txt').write_text('mine')
        self.assertEqual(self.updater.refresh()['status'],'available')
        self.updater.apply()
        folder,backup=self.backup()
        self.assertEqual((folder/'files/new.txt').read_text(),'mine')
        self.assertEqual((self.install/'new.txt').read_text(),'remote')

    def test_local_commits_remain_reachable_after_updating_main(self):
        self.publish()
        (self.install/'app.txt').write_text('my edit')
        self.git(self.install, 'commit', '-am', 'local edit')
        before=self.git(self.install,'rev-parse','HEAD').stdout.decode().strip()
        self.assertEqual(self.updater.refresh()['status'], 'available')
        self.updater.apply()
        folder,backup=self.backup()
        self.assertEqual(backup['head'],before)
        self.assertEqual(self.git(self.install,'show',backup['head']+':app.txt').stdout,b'my edit')
        self.assertEqual((self.install/'app.txt').read_text(),'second')

    def test_staged_and_unstaged_versions_are_both_preserved(self):
        self.publish()
        (self.install/'app.txt').write_text('staged edition')
        self.git(self.install,'add','app.txt')
        (self.install/'app.txt').write_text('latest working edition')
        self.updater.refresh();self.updater.apply()
        folder,backup=self.backup()
        self.assertEqual(self.git(self.install,'show',backup['stash']+':app.txt').stdout,b'latest working edition')
        self.assertEqual(self.git(self.install,'show',backup['stash']+'^2:app.txt').stdout,b'staged edition')

    def test_a_failed_build_restores_local_branch_index_working_text_and_collisions(self):
        (self.author/'new.txt').write_text('new official file')
        self.git(self.author,'add','new.txt')
        self.publish()
        self.git(self.install,'checkout','-b','agent-work')
        (self.install/'app.txt').write_text('staged edit');self.git(self.install,'add','app.txt')
        (self.install/'app.txt').write_text('working edit')
        (self.install/'new.txt').write_text('local file')
        (self.install/'unrelated.txt').write_text('stay here')
        before=self.git(self.install,'rev-parse','HEAD').stdout
        main=self.git(self.install,'rev-parse','main').stdout
        index=self.git(self.install,'diff','--cached','--binary').stdout
        work=self.git(self.install,'diff','--binary').stdout
        self.updater.refresh()
        with patch.object(Updater,'starts',return_value='Missing dependency'),self.assertRaises(UpdateError):self.updater.apply()
        self.assertEqual(self.git(self.install,'branch','--show-current').stdout.strip(),b'agent-work')
        self.assertEqual(self.git(self.install,'rev-parse','HEAD').stdout,before)
        self.assertEqual(self.git(self.install,'rev-parse','main').stdout,main)
        self.assertEqual(self.git(self.install,'diff','--cached','--binary').stdout,index)
        self.assertEqual(self.git(self.install,'diff','--binary').stdout,work)
        self.assertEqual((self.install/'new.txt').read_text(),'local file')
        self.assertEqual((self.install/'unrelated.txt').read_text(),'stay here')
        self.assertEqual(self.data.read_text(),'my project')
        self.assertEqual(self.backup()[1]['status'],'restored')

    def test_untracked_symlink_parent_never_modifies_the_external_folder(self):
        outside=Path(self.temp.name)/'outside';outside.mkdir();(outside/'helper.py').write_text('external original')
        (self.install/'plugins').symlink_to(outside,target_is_directory=True)
        (self.author/'plugins').mkdir();(self.author/'plugins/helper.py').write_text('official helper')
        self.git(self.author,'add','plugins/helper.py')
        self.publish();self.updater.refresh();self.updater.apply()
        folder,backup=self.backup()
        self.assertEqual((outside/'helper.py').read_text(),'external original')
        self.assertFalse((self.install/'plugins').is_symlink())
        self.assertEqual((self.install/'plugins/helper.py').read_text(),'official helper')
        self.assertTrue((folder/'files/plugins').is_symlink())

    def test_ignored_directory_collision_is_preserved_as_a_directory(self):
        (self.install/'new.txt').mkdir();(self.install/'new.txt/local.bin').write_bytes(b'local bytes')
        (self.install/'.git/info/exclude').write_text('new.txt/\n')
        (self.author/'new.txt').write_text('official file');self.git(self.author,'add','new.txt');self.publish()
        self.updater.refresh();self.updater.apply();folder,backup=self.backup()
        self.assertEqual((folder/'files/new.txt/local.bin').read_bytes(),b'local bytes')
        self.assertEqual((self.install/'new.txt').read_text(),'official file')

    def test_backup_failure_leaves_the_original_installation_in_place(self):
        self.publish();self.updater.refresh();(self.install/'app.txt').write_text('local source')
        with patch('updater.UpdateBackup',side_effect=OSError('disk full')),self.assertRaises(UpdateError):self.updater.apply()
        self.assertEqual((self.install/'app.txt').read_text(),'local source')
        self.assertEqual(self.data.read_text(),'my project')

    def test_credentials_cannot_be_replaced_by_an_update(self):
        (self.install/'.env').write_text('local secret')
        (self.author/'.env').write_text('new file')
        self.git(self.author,'add','-f','.env');self.publish()
        self.assertEqual(self.updater.refresh()['status'],'unsafe_update')
        with self.assertRaises(UpdateError):self.updater.apply()
        self.assertEqual((self.install/'.env').read_text(),'local secret')

    def test_the_same_version_can_be_retried_after_its_missing_dependency_is_fixed(self):
        self.publish();self.updater.refresh()
        with patch.object(Updater,'starts',return_value='ModuleNotFoundError'),self.assertRaises(UpdateError):self.updater.apply()
        self.assertEqual(self.updater.refresh()['status'],'update_failed')
        with patch.object(Updater,'starts',return_value=None):self.updater.apply()
        self.assertEqual((self.install/'app.txt').read_text(),'second')

    def test_detached_installation_can_follow_main(self):
        self.git(self.install,'checkout','--detach');self.publish()
        self.updater.refresh();self.updater.apply()
        self.assertEqual(self.git(self.install,'branch','--show-current').stdout.strip(),b'main')
        self.assertIsNone(self.backup()[1]['branch'])

    def run_mac_recovery(self, *, busy=False, broken=False):
        repository=Path(__file__).resolve().parents[2]
        (self.author/'backend').mkdir(exist_ok=True);(self.author/'tools').mkdir()
        (self.author/'backend/app.py').write_text('# previous working application\n')
        (self.author/'tools/studio_restart.py').write_text('''import json,os,sys
from pathlib import Path
root=Path(sys.argv[sys.argv.index('--root')+1]) if '--root' in sys.argv else Path(__file__).resolve().parents[1]
with open(os.environ['VIDEOKEY_BOOTSTRAP_TEST_LOG'],'a') as output:
 output.write(json.dumps({'stop':'--stop-only' in sys.argv,'text':(root/'app.txt').read_text()})+'\\n')
if '--stop-only' in sys.argv and os.environ.get('VIDEOKEY_BOOTSTRAP_TEST_BUSY'):sys.exit(1)
''')
        self.git(self.author,'add','backend/app.py','tools/studio_restart.py')
        self.git(self.author,'commit','-m','previous application');self.git(self.author,'push')
        self.git(self.install,'pull','--ff-only')
        for name in ('backend/updater.py','backend/update_backup.py'):
            shutil.copyfile(repository/name,self.author/name)
        if broken:(self.author/'backend/app.py').write_text('import deliberately_missing_bootstrap_fixture\n')
        self.git(self.author,'add','backend');self.publish()
        (self.install/'app.txt').write_text('local edits')
        launcher=(repository/'Оновити студію.command').read_text()
        discovery=launcher.split("<<'FIND_STUDIO'\n",1)[1].split('\nFIND_STUDIO\n',1)[0]
        code=launcher.split("<<'PY'\n",1)[1].split('\nPY\n',1)[0]
        prelude='''import subprocess
import sys
original_run=subprocess.run
def run(arguments,*args,**kwargs):
 if arguments[:4]==['git','remote','get-url','origin'] or arguments[:2]==['git','-C']:
  return subprocess.CompletedProcess(arguments,0,stdout=b'https://github.com/aloaloalo2/multibot-video-studio.git\\n',stderr=b'')
 if arguments[0]=='lsof':
  output=b'42\\n' if '-tiTCP:8770' in arguments else b'p42\\nn'+sys.argv[1].encode()+b'\\n'
  return subprocess.CompletedProcess(arguments,0,stdout=output,stderr=b'')
 return original_run(arguments,*args,**kwargs)
subprocess.run=run
'''
        prelude+='\nnamespace={"__name__":"discovery_fixture"}\nexec('+repr(discovery)+',namespace)\nsys.argv[1]=str(namespace["find_root"]("/Downloads"))\n'
        log=Path(self.temp.name)/'recovery-events.jsonl'
        result=subprocess.run([sys.executable,'-c',prelude+'\nexec('+repr(code)+')',str(self.install)],
            capture_output=True,text=True,timeout=30,env={**os.environ,'VIDEOKEY_BOOTSTRAP_TEST_LOG':str(log),
                'VIDEOKEY_BOOTSTRAP_TEST_BUSY':'1' if busy else ''})
        return result,[json.loads(line) for line in log.read_text().splitlines()]

    def test_mac_recovery_replaces_an_old_blocked_updater_and_restarts_only_after_success(self):
        result,events=self.run_mac_recovery()
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(events,[{'stop':True,'text':'local edits'},{'stop':False,'text':'second'}])
        self.assertEqual((self.install/'app.txt').read_text(),'second')
        self.assertEqual(self.data.read_text(),'my project')
        manifest=next(self.install.glob('.git/studio-update-backups/*/manifest.json'))
        self.assertEqual(json.loads(manifest.read_text())['status'],'updated')

    def test_mac_recovery_does_not_change_a_busy_installation(self):
        result,events=self.run_mac_recovery(busy=True)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(events,[{'stop':True,'text':'local edits'}])
        self.assertEqual((self.install/'app.txt').read_text(),'local edits')
        self.assertFalse((self.install/'backend/update_backup.py').exists())

    def test_mac_recovery_restarts_the_previous_version_when_the_update_cannot_load(self):
        result,events=self.run_mac_recovery(broken=True)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(events,[{'stop':True,'text':'local edits'},{'stop':False,'text':'local edits'}])
        self.assertEqual((self.install/'app.txt').read_text(),'local edits')
        self.assertEqual(self.data.read_text(),'my project')

    def test_an_agent_branch_can_update_to_main_without_manual_merging(self):
        self.git(self.install, 'checkout', '-b', 'agent-work')
        self.assertEqual(self.updater.refresh()['status'], 'current')
        self.publish()
        self.assertEqual(self.updater.refresh()['status'], 'available')
        self.git(self.install, 'push', '-u', 'origin', 'agent-work')
        self.assertEqual(self.updater.refresh()['status'], 'available')
        self.updater.apply()
        self.assertEqual(self.git(self.install,'branch','--show-current').stdout.strip(),b'main')
        self.assertEqual((self.install/'app.txt').read_text(),'second')
        self.assertEqual(self.updater.refresh()['status'], 'current')

    @unittest.skipUnless(shutil.which('node'), 'node required')
    def test_the_page_explains_each_blocked_update(self):
        states = [{'status': 'local_changes', 'files': ['<b>.txt', 'a.txt'], 'more': 3}, {'status': 'diverged'},
                  {'status': 'unsafe_update', 'files': ['new.txt']}, {'status': 'other_branch', 'branch': 'agent-work'},
                  {'status': 'available'}, {'status': 'current'}, {'status': 'offline'}, {'status': 'not_configured'}]
        esc = "const esc=value=>String(value??'').replace(/[&<>\"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[char]));"
        html = preview_js.run(['updateReasonHtml'], f"console.log(JSON.stringify({json.dumps(states)}.map(updateReasonHtml)))", esc)
        self.assertEqual(html[:2],['',''])
        self.assertIn('new.txt', html[2])
        self.assertEqual(html[3],'')
        self.assertEqual(html[4:], ['', '', '', ''])   # no notice when nothing is blocked

    def test_a_version_that_does_not_load_is_taken_back(self):
        self.publish()
        self.updater.refresh()
        with patch.object(Updater, 'starts', return_value='ModuleNotFoundError: No module named new_package'):
            with self.assertRaises(UpdateError):
                self.updater.apply()
        self.assertEqual((self.install/'app.txt').read_text(), 'first')          # still the version that works
        self.assertEqual(self.updater.public_state()['status'], 'update_failed')
        self.assertIn('new_package', self.updater.public_state()['error'])
        self.assertEqual(self.updater.refresh()['status'], 'update_failed')     # not offered again
        self.publish('third')                                                   # a newer version is offered
        self.assertEqual(self.updater.refresh()['status'], 'available')
        self.updater.apply()
        self.assertEqual((self.install/'app.txt').read_text(), 'third')

    def test_update_waits_for_the_agents(self):
        with patch.dict(app.ACTIVE_EXPORTS, {}, clear=True), patch.object(app.analysis_jobs, 'ACTIVE_JOBS', set()), \
                patch.object(app.agent_view, 'studio_status', return_value={'busy': ['створення кадрів: Горбунов / 23']}), \
                patch.object(app.UPDATE_MANAGER, 'apply') as apply:
            with self.assertRaises(store.StudioError) as busy: app.begin_update()
            apply.assert_not_called()
        self.assertEqual(str(busy.exception), 'Зараз працює агент кадрів')   # short, no episode or id

    def test_a_busy_update_waits_on_the_server_and_starts_after_the_work(self):
        busy = ['режисура: What If / X (abc)']
        with patch.dict(app.ACTIVE_EXPORTS, {}, clear=True), patch.object(app.analysis_jobs, 'ACTIVE_JOBS', set()), \
                patch.object(app.agent_view, 'studio_status', side_effect=lambda *a: {'busy': list(busy)}), \
                patch.object(app.time, 'sleep'), patch.object(app.UPDATE_MANAGER, 'apply') as apply, \
                patch.object(app.threading, 'Timer'), patch.object(app.threading, 'Thread') as thread:
            try:
                app.UPDATE_QUEUED = None
                app.queue_update('Зараз працює режисер')
                self.assertEqual(app.UPDATE_QUEUED, 'Зараз працює режисер')   # what GET /api/update reports after a reload
                busy.clear()                                                    # the director ends
                thread.call_args.kwargs['target']()
                apply.assert_called_once()
                self.assertIsNone(app.UPDATE_QUEUED)
            finally:
                app.UPDATE_RESTARTING = False
                app.UPDATE_QUEUED = None

    def test_an_export_takes_only_the_window_s_qualities(self):
        with self.assertRaises(store.StudioError) as wrong:
            app.start_export({"id": "a" * 24, "width": 1920, "height": 1080, "fps": 25}, True, 3_000_000)
        self.assertEqual(wrong.exception.status, 400)

    def test_update_does_not_interrupt_an_export_or_audio_analysis(self):
        with patch.dict(app.ACTIVE_EXPORTS, {'test': {}}, clear=True), patch.object(app.UPDATE_MANAGER, 'apply') as apply:
            with self.assertRaises(store.StudioError): app.begin_update()
            apply.assert_not_called()
        with patch.dict(app.ACTIVE_EXPORTS, {}, clear=True), patch.object(app.analysis_jobs, 'ACTIVE_JOBS', {'test'}), patch.object(app.UPDATE_MANAGER, 'apply') as apply:
            with self.assertRaises(store.StudioError): app.begin_update()
            apply.assert_not_called()


if __name__ == '__main__':
    unittest.main()
