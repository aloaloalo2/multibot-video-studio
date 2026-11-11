"""Switching the channel root stages no migration and never redirects active production."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import app
import store
import workspace_paths


class WorkspacePathsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.old = self.base / 'Old YouTube'
        self.new = self.base / 'New YouTube'
        self.old.mkdir()
        self.new.mkdir()
        self.data = self.base / 'data'
        for key, value in {'YOUTUBE_ROOT': self.old, 'DATA_ROOT': self.data,
                           'PROJECTS_ROOT': self.data / 'projects', 'DISABLED_PATH': self.data / 'disabled.json',
                           'GLOBAL_SETTINGS_PATH': self.data / 'settings.json'}.items():
            p = patch.object(store, key, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.dict(os.environ, {'MULTIBOT_STUDIO_DATA': str(self.data)})
        p.start()
        self.addCleanup(p.stop)

    def test_switch_and_return_preserve_existing_project_and_channel_files(self):
        channel = store.create_channel('Original')
        project = store.create_project(channel['id'], 'Existing episode')
        manifest = store.project_path(project['id']).read_bytes()
        settings = store.update_global_settings({'youtube_root': str(self.new)})
        self.assertEqual(settings['youtube_root'], str(self.new))
        self.assertEqual(store.list_channels(), [])
        self.assertTrue(Path(project['episode_path']).is_dir())
        self.assertEqual(store.project_path(project['id']).read_bytes(), manifest)
        fresh = store.create_channel('New channel')
        next_project = store.create_project(fresh['id'], 'New episode')
        self.assertEqual(Path(next_project['episode_path']).parent, self.new / 'New channel')
        self.assertTrue(store.media_dir(next_project).is_relative_to(self.data))
        import episode_metadata
        self.assertTrue(episode_metadata.path(next_project).is_relative_to(self.new))
        store.update_global_settings({'youtube_root': str(self.old)})
        self.assertEqual(store.list_channels()[0]['id'], channel['id'])
        self.assertEqual(store.list_projects(channel['id'])[0]['id'], project['id'])

    def test_invalid_or_unwritable_root_keeps_memory_and_disk_unchanged(self):
        store.update_global_settings({'export_subfolder': 'Ready'})
        original = store.GLOBAL_SETTINGS_PATH.read_bytes()
        file = self.base / 'file'
        file.write_text('keep')
        channel = self.old / 'Single channel'
        channel.mkdir()
        (channel / store.PLAN_CONFIG).write_text('{}')
        for value in (None, 1, [], '', 'relative/path', 'bad\x00path', str(self.new / 'missing'),
                      str(file), str(store.APP_ROOT), str(self.data), str(channel)):
            with self.subTest(value=value), self.assertRaises(store.StudioError):
                store.update_global_settings({'youtube_root': value})
            self.assertEqual(store.YOUTUBE_ROOT, self.old)
            self.assertEqual(store.GLOBAL_SETTINGS_PATH.read_bytes(), original)
        with patch.object(os, 'access', return_value=False), self.assertRaisesRegex(store.StudioError, 'доступу'):
            store.update_global_settings({'youtube_root': str(self.new)})
        self.assertEqual(store.GLOBAL_SETTINGS_PATH.read_bytes(), original)

    def test_new_process_and_tools_read_saved_root_without_server_or_provider_calls(self):
        store.update_global_settings({'youtube_root': str(self.new), 'export_subfolder': 'Ready'})
        code = "import store; print(store.YOUTUBE_ROOT)"
        run = subprocess.run([sys.executable, '-c', code], cwd=store.APP_ROOT / 'backend',
                             capture_output=True, text=True, check=True)
        self.assertEqual(run.stdout.strip(), str(self.new))
        for name, attribute in [('episode', 'ROOT'), ('pixabay', 'ROOT'), ('razgon_sync', 'YOUTUBE')]:
            spec = importlib.util.spec_from_file_location('workspace_test_' + name, store.APP_ROOT / 'tools' / (name + '.py'))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertEqual(getattr(module, attribute), self.new)
        self.assertEqual((self.new / store.app_rel()).resolve(), store.APP_ROOT)

    def test_missing_saved_drive_does_not_fall_back_to_another_folder(self):
        store.update_global_settings({'youtube_root': str(self.new)})
        self.new.rmdir()
        self.assertEqual(workspace_paths.youtube_root(), self.new)
        self.assertEqual(store.list_channels(), [])

    def test_failed_settings_write_never_switches_runtime_root(self):
        with patch.object(store, 'atomic_json', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                store.update_global_settings({'youtube_root': str(self.new)})
        self.assertEqual(store.YOUTUBE_ROOT, self.old)

    def test_active_jobs_and_other_mutations_block_root_switch_only(self):
        for active, in_flight, voice in [(True, 1, set()), (False, 2, set()), (False, 1, {'voice'})]:
            with self.subTest(active=active, in_flight=in_flight, voice=voice), \
                    patch.object(app, 'IN_FLIGHT', in_flight), patch.object(app.channel_voice_lab, 'ACTIVE', voice), \
                    patch.object(app, 'studio_work_status', return_value={'busy': ['work'] if active else []}):
                with self.assertRaises(store.StudioError) as error:
                    app.update_studio_settings({'youtube_root': str(self.new)})
                self.assertEqual(error.exception.status, 409)
                self.assertEqual(store.YOUTUBE_ROOT, self.old)
                self.assertEqual(app.update_studio_settings({'export_subfolder': 'Ready'})['export_subfolder'], 'Ready')
        with patch.object(app, 'IN_FLIGHT', 1), patch.object(app.channel_voice_lab, 'ACTIVE', set()), \
                patch.object(app, 'studio_work_status', return_value={'busy': []}):
            self.assertEqual(app.update_studio_settings({'youtube_root': str(self.new)})['youtube_root'], str(self.new))

    def test_folder_picker_does_not_apply_the_path_or_create_a_directory(self):
        handler = object.__new__(app.Handler)
        handler.json_response = lambda value, *args: value
        with patch.object(app, 'choose_local_folder', return_value=self.new):
            result = handler.route_mutation('POST', '/api/settings/youtube-root/pick', {})
        self.assertEqual(result, {'path': str(self.new)})
        self.assertEqual(store.YOUTUBE_ROOT, self.old)
        self.assertFalse(store.GLOBAL_SETTINGS_PATH.exists())
        self.assertEqual(list(self.new.iterdir()), [])

    def test_director_and_production_briefs_locate_tools_outside_the_channel_root(self):
        import director
        import production
        store.update_global_settings({'youtube_root': str(self.new)})
        channel = store.create_channel('New channel')
        project = store.create_project(channel['id'], 'New episode')
        with patch.object(director, 'sound_brief', return_value=''), \
                patch.object(production, 'people_rules', return_value={'stock': '', 'rule': '', 'check': ''}):
            brief = director.frames_brief(project)
            self.assertIn(f'{store.app_rel()}/tools/studio.py', brief)
            brief = production.photo_brief(project, {'frames': 1, 'total_frames': 1, 'start': 0, 'end': 1})
            self.assertIn(f'{store.app_rel()}/tools/studio.py', brief)

    def test_director_has_access_to_studio_tools_outside_the_selected_root(self):
        import director
        store.update_global_settings({'youtube_root': str(self.new)})
        with patch.object(director.subprocess, 'Popen', side_effect=OSError('test stop')) as launch:
            with self.assertRaisesRegex(OSError, 'test stop'):
                director.claude(Path('/mock/claude'), 'mock', self.base / 'log', self.base / 'activity', 10)
        command = launch.call_args.args[0]
        directories = [command[i + 1] for i, value in enumerate(command) if value == '--add-dir']
        self.assertIn(str(store.APP_ROOT), directories)
        self.assertIn(str(self.data), directories)
        self.assertEqual(launch.call_args.kwargs['cwd'], self.new)
