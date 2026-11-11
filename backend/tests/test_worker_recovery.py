"""Launch and storage failures must release every workflow slot without provider work."""
import contextlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import analysis_jobs
import app
import director
import episode_ideas as ideas
import languages
import production
import project_narration as narration
import store
import thumbnail_gen
import agent_runtime
import razgon_sound


class WorkerRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.base = Path(self.stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        youtube, data = self.base / 'youtube', self.base / 'data'
        youtube.mkdir()
        for key, value in {'YOUTUBE_ROOT': youtube, 'DATA_ROOT': data, 'PROJECTS_ROOT': data / 'projects',
                           'DISABLED_PATH': data / 'disabled.json', 'GLOBAL_SETTINGS_PATH': data / 'settings.json'}.items():
            self.stack.enter_context(patch.object(store, key, value))
        self.stack.enter_context(patch.object(app, 'JOBS_ROOT', data / 'jobs'))
        for module, key, value in [(director, 'ACTIVE', set()), (production, 'ACTIVE', set()),
                                   (thumbnail_gen, 'ACTIVE', set()), (ideas, 'ACTIVE', {}),
                                   (analysis_jobs, 'ACTIVE_JOBS', set()), (analysis_jobs, 'ACTIVE_PROJECTS', {}),
                                   (narration, 'ACTIVE', set()), (narration, 'HEYGEN_QUEUE', []),
                                   (narration.lab, 'NARRATIONS', {}), (languages, 'ACTIVE', set()),
                                   (languages, 'CANCEL', set())]:
            self.stack.enter_context(patch.object(module, key, value))
        self.stack.enter_context(patch.object(director, 'executable', return_value=Path('/mock/claude')))
        self.cid = store.create_channel('Test')['id']
        self.project = store.create_project(self.cid, 'Test episode')
        self.pid = self.project['id']
        self.folder = store.project_dir(self.pid)

    def prepare_production(self):
        self.project['production_request'] = {'id': 'request', 'frames': 1, 'status': 'requested'}
        store.save_project(self.project)

    def thumbnail_start(self):
        executable = self.base / 'codex'
        executable.touch()
        with patch.object(thumbnail_gen, 'CODEX', executable), \
                patch.object(store, 'picture_count', return_value=4), \
                patch('idea_reference.thumbnail_reference', return_value=(None, None)):
            return thumbnail_gen.start(self.pid, 'Title', 'Script')

    def narration_spec(self):
        return ({'provider': 'heygen', 'speed': 1}, {}, [], {'provider': 'heygen', 'total': 0})

    def language_start(self):
        with patch.object(languages, 'key', return_value='mock'), \
                patch.object(languages, 'source', return_value={'script': 'Full script.'}), \
                patch.object(languages, 'thumbnail_options', return_value={'add_flag': False}):
            return languages.start(self.pid, 'translate', 'de')

    def test_thread_failure_releases_director_and_frame_jobs(self):
        with patch.object(director.threading, 'Thread', side_effect=RuntimeError('No thread')):
            with self.assertRaises(RuntimeError):
                director.start(self.pid)
            self.assertNotIn(self.pid, director.ACTIVE)
            self.assertEqual(director.state(self.pid)['status'], 'failed')
            self.prepare_production()
            with self.assertRaises(RuntimeError):
                production.start(self.pid)
            self.assertNotIn(self.pid, production.ACTIVE)
            self.assertEqual(store.load_project(self.pid)['production_request']['status'], 'failed')

    def test_thread_failure_releases_thumbnail_and_translation_jobs(self):
        with patch.object(thumbnail_gen.threading, 'Thread', side_effect=RuntimeError('No thread')):
            with self.assertRaises(RuntimeError):
                self.thumbnail_start()
            self.assertNotIn(self.pid, thumbnail_gen.ACTIVE)
            self.assertEqual(thumbnail_gen.state(self.pid)['status'], 'failed')
            with self.assertRaises(RuntimeError):
                self.language_start()
            self.assertFalse(languages.busy(self.pid))
            self.assertEqual(languages.load_state(self.pid)['jobs']['de|voice']['status'], 'failed')

    def test_thread_failure_releases_writing_and_topic_jobs(self):
        for action in ['openings', 'ideas']:
            data = {'id': action, 'context': {}, 'attempt_day': ideas.today(),
                    **({'project_id': self.pid, 'selected_index': 0} if action == 'openings' else {})}
            with patch.object(ideas, 'Thread', side_effect=RuntimeError('No thread')):
                with self.assertRaises(RuntimeError):
                    ideas.launch(self.cid, data, action)
            self.assertEqual(ideas.ACTIVE, {})
            self.assertEqual(data['status'], 'failed')
            if action == 'ideas':
                self.assertEqual(ideas.catalog(self.cid)['status'], 'failed')

    def test_failed_initial_write_does_not_reserve_director_thumbnail_or_language(self):
        with patch.object(store, 'atomic_json', side_effect=OSError('Disk full')):
            for launch in [lambda: director.start(self.pid), self.thumbnail_start, self.language_start]:
                with self.subTest(launch=launch), self.assertRaises(OSError):
                    launch()
                self.assertNotIn(self.pid, director.ACTIVE)
                self.assertNotIn(self.pid, thumbnail_gen.ACTIVE)
                self.assertFalse(languages.busy(self.pid))

    def test_failed_initial_narration_write_leaves_no_orphan_in_heygen_queue(self):
        with patch.object(narration, 'spec', return_value=self.narration_spec()), \
                patch.object(store, 'atomic_json', side_effect=OSError('Disk full')):
            with self.assertRaises(OSError):
                narration.start(self.project, 'A complete sentence.')
        self.assertEqual(narration.HEYGEN_QUEUE, [])
        self.assertFalse(narration.ACTIVE)
        self.assertEqual(narration.lab.NARRATIONS, {})

    def test_analysis_thread_and_pointer_write_failures_release_their_own_slot(self):
        asset = {'id': 'voice', 'kind': 'audio', 'name': 'Voice', 'path': 'voice.wav'}
        with patch.object(store, 'resolve_asset', return_value=asset), \
                patch.object(analysis_jobs.threading, 'Thread', side_effect=RuntimeError('No thread')):
            with self.assertRaises(RuntimeError):
                analysis_jobs.start(self.project, 'voice', app.save_job, app.load_job)
        self.assertFalse(analysis_jobs.ACTIVE_JOBS)
        self.assertEqual(analysis_jobs.ACTIVE_PROJECTS, {})
        self.assertEqual(analysis_jobs.latest(self.pid, app.load_job)['job']['status'], 'failed')
        save = store.atomic_json
        def fail_pointer(path, data):
            if path.name == 'analysis-state.json':
                raise OSError('Disk full')
            save(path, data)
        with patch.object(store, 'resolve_asset', return_value=asset), patch.object(store, 'atomic_json', side_effect=fail_pointer):
            with self.assertRaises(OSError):
                analysis_jobs.start(self.project, 'voice', app.save_job, app.load_job)
        self.assertFalse(analysis_jobs.ACTIVE_JOBS)
        self.assertEqual(analysis_jobs.ACTIVE_PROJECTS, {})

    def active_analysis(self):
        job = {'id': 'job', 'project_id': self.pid, 'source_asset_id': 'voice'}
        analysis_jobs.ACTIVE_JOBS.add(job['id'])
        analysis_jobs.ACTIVE_PROJECTS[job['id']] = self.pid
        return job

    def test_analysis_directory_failure_is_terminal_and_releases_the_queue(self):
        (self.folder / 'analysis').write_text('Cannot create a directory here')
        job = self.active_analysis()
        saved = []
        analysis_jobs.worker(job, 'Full script.', lambda value: saved.append(dict(value)))
        self.assertEqual(saved[-1]['status'], 'failed')
        self.assertFalse(analysis_jobs.ACTIVE_JOBS)
        self.assertFalse(analysis_jobs.ACTIVE_PROJECTS)

    def test_analysis_final_write_failure_also_releases_the_queue(self):
        job = self.active_analysis()
        with self.assertRaises(OSError):
            analysis_jobs.worker(job, 'Full script.', lambda value: (_ for _ in ()).throw(OSError('Disk full')))
        self.assertFalse(analysis_jobs.ACTIVE_JOBS)
        self.assertFalse(analysis_jobs.ACTIVE_PROJECTS)

    def test_unexpected_model_result_fails_instead_of_retaining_running_status(self):
        director.ACTIVE.add(self.pid)
        with patch.object(director, 'brief', side_effect=ValueError('Malformed state')):
            director.run(self.pid, Path('/mock/claude'))
        self.assertEqual(store.read_json(director.state_path(self.pid))['status'], 'failed')
        self.assertFalse(director.ACTIVE)
        key = languages.job_key(self.pid, 'de', 'voice')
        languages.ACTIVE.add(key)
        job = {'key': key, 'slot': 'de|voice', 'kind': 'translate', 'code': 'de', 'status': 'running'}
        with patch.dict(languages.WORK, {'translate': lambda *args: (_ for _ in ()).throw(KeyError('Missing result'))}):
            languages.worker(self.pid, 'translate', 'de', None, job)
        self.assertEqual(job['status'], 'failed')
        self.assertFalse(languages.ACTIVE)

    def test_agent_thread_failure_closes_its_guard_and_clears_the_queued_state(self):
        from unittest.mock import Mock
        guard=Mock()
        with patch.object(agent_runtime,'JOBS',{}), patch.object(agent_runtime,'active',return_value=None), \
                patch.object(agent_runtime,'acquire_project_guard',return_value=guard), \
                patch.object(agent_runtime.agent_openrouter.credentials,'vault') as vault, \
                patch.object(agent_runtime.agent_storage,'add_message'), \
                patch.object(agent_runtime.agent_storage,'get_settings',return_value={'reasoning_effort':'auto'}), \
                patch.object(agent_runtime.threading,'Thread',side_effect=RuntimeError('No thread')):
            vault.return_value.configured.return_value=True
            with self.assertRaises(RuntimeError):
                agent_runtime.start(self.pid,'Do the requested edit',{'export_active':lambda pid:False})
            self.assertEqual(agent_runtime.JOBS[self.pid]['status'],'failed')
        guard.close.assert_called_once()

    def test_sound_start_failure_never_reserves_a_project_forever(self):
        for disk_failure in (False,True):
            with self.subTest(disk_failure=disk_failure), patch.object(razgon_sound,'ACTIVE',set()), \
                    patch.object(razgon_sound,'AGAIN',set()), patch.object(razgon_sound,'due',return_value={'project':'mock'}), \
                    patch.object(razgon_sound.threading,'Thread',side_effect=RuntimeError('No thread')):
                with contextlib.ExitStack() as faults:
                    if disk_failure:faults.enter_context(patch.object(store,'atomic_json',side_effect=OSError('Disk full')))
                    with self.assertRaises((RuntimeError,OSError)):
                        razgon_sound.start(self.pid,'test')
                self.assertFalse(razgon_sound.ACTIVE)
                self.assertFalse(razgon_sound.AGAIN)

    def test_voice_sample_launch_failure_releases_the_channel(self):
        lab=narration.lab
        with patch.object(lab,'ACTIVE',set()), patch.object(lab,'effective_reference',return_value={'sha256':'mock'}), \
                patch.object(lab.languages.language_quality,'require'), \
                patch.object(lab.threading,'Thread',side_effect=RuntimeError('No thread')):
            with self.assertRaises(RuntimeError):
                lab.start(self.cid,{'provider':'heygen','text':'Full sample text.','heygen_voice_id':'voice'},'sample-request-12345')
            self.assertFalse(lab.ACTIVE)
            self.assertEqual(store.read_json(lab.folder(self.cid)/'job.json')['status'],'failed')

    def test_status_keeps_owned_workers_busy_during_terminal_receipt_publication(self):
        director.ACTIVE.add(self.pid)
        store.atomic_json(director.state_path(self.pid),{'status':'done','create_video':True})
        self.assertEqual(app.project_jobs(self.pid)['режисура'],'running')
        director.ACTIVE.clear()
        self.assertEqual(app.project_jobs(self.pid)['режисура'],'done')

    def test_director_to_frames_handoff_holds_the_restart_gate(self):
        import threading,work_guard
        observations=[]
        def handoff(pid):
            def probe():
                acquired=work_guard.MUTEX.acquire(timeout=.05)
                observations.append(acquired)
                if acquired:work_guard.MUTEX.release()
            observer=threading.Thread(target=probe)
            observer.start();observer.join(2)
            self.assertFalse(observer.is_alive())
        director.ACTIVE.add(self.pid)
        store.atomic_json(director.state_path(self.pid),{'status':'done','create_video':True})
        with patch.object(director,'_run'),patch.object(production,'start_from_plan',side_effect=handoff) as start:
            director.run(self.pid,Path('/mock/claude'))
        start.assert_called_once_with(self.pid)
        self.assertEqual(observations,[False])
