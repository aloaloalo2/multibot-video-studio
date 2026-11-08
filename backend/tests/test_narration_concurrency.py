import contextlib
import sys
import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import channel_voice_lab as lab
import project_narration as narration
import store

Thread = threading.Thread


class NarrationConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.cid = '1' * 16
        self.projects = {pid: {'id': pid, 'channel_id': self.cid, 'assets': []} for pid in ['a' * 24, 'b' * 24]}
        self.settings = lab.validated({'provider': 'heygen', 'heygen_voice_id': 'saved-voice', 'heygen_model': 'heygen-voice-1'})
        self.workers = []
        self.release = threading.Event()
        duration = store.media_duration
        patches = [patch.object(store, 'DATA_ROOT', self.root),
                   patch.object(store, 'project_dir', side_effect=self.project_dir),
                   patch.object(store, 'load_project', side_effect=lambda pid: self.projects[pid]),
                   patch.object(store, 'get_channel_folder', return_value=self.root),
                   patch.object(store, 'media_duration', side_effect=lambda path: duration(path) if Path(path).suffix=='.flac' else 1),
                   patch.object(store, 'import_asset_file', side_effect=self.import_audio),
                   patch.object(narration.languages, 'run', side_effect=self.assemble),
                   patch.object(lab, 'snapshot', side_effect=lambda cid: {'settings': self.settings.copy(), 'reference': {'sha256': 'reference', 'approved': True}}),
                   patch.object(narration, 'ACTIVE', set()), patch.object(lab, 'ACTIVE', set()),
                   patch.object(lab, 'NARRATIONS', {}), patch.object(lab, '_AUDIO_USERS', {}),
                   patch.object(narration.threading, 'Thread', side_effect=self.worker)]
        for item in patches:
            self.stack.enter_context(item)

    def assemble(self, command, *args):
        # Real silence lets the local closing-pause code decode the assembled fixture.
        with wave.open(str(command[-1]),'wb') as audio:
            audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(8000)
            audio.writeframes(b'\0\0'*8000)

    def tearDown(self):
        self.release.set()
        for worker in self.workers:
            worker.join(5)
        try:
            self.assertFalse(any(worker.is_alive() for worker in self.workers))
            self.assertEqual(lab._AUDIO_USERS, {})
        finally:
            self.stack.close()

    def project_dir(self, pid):
        folder = self.root / pid
        folder.mkdir(exist_ok=True)
        return folder

    def import_audio(self, project, path, kind):
        asset = {'id': project['id'], 'path': str(path), 'duration': 1}
        project['assets'].append(asset)
        return asset

    def worker(self, **kwargs):
        worker = Thread(**kwargs)
        self.workers.append(worker)
        return worker

    def wait_for_users(self, path, count):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with lab._AUDIO_LOCK:
                users = lab._AUDIO_USERS.get(path, {}).get('users', 0)
            if users >= count:
                return
            self.release.wait(.005)
        self.fail('Concurrent worker never reached the shared audio cache')

    def finished(self):
        for worker in self.workers:
            worker.join(5)
            self.assertFalse(worker.is_alive())
        return [store.read_json(narration.root(pid) / 'job.json') for pid in self.projects]

    def test_two_projects_of_one_channel_reach_heygen_together_with_isolated_settings(self):
        both = threading.Barrier(2)
        def synthesize(settings):
            both.wait(5)
            self.assertTrue(self.release.wait(5))
            return settings['text'].encode()
        with patch.object(lab.heygen_voice, 'synthesize', side_effect=synthesize) as paid:
            first, second = self.projects.values()
            narration.start(first, 'First project sentence.')
            self.settings['heygen_expressiveness'] = .8
            narration.start(second, 'Second project sentence.')
            self.assertEqual(set(lab.NARRATIONS), set(self.projects))
            self.assertEqual(lab.ACTIVE, set())
            self.release.set()
            jobs = self.finished()
        self.assertEqual([job['status'] for job in jobs], ['done', 'done'])
        self.assertEqual([job['render_settings']['heygen_expressiveness'] for job in jobs], [.5, .8])
        self.assertEqual(paid.call_count, 2)
        self.assertEqual(lab.NARRATIONS, {})
        for pid, text in zip(self.projects, ['First project sentence.', 'Second project sentence.']):
            entries = store.read_json(narration.root(pid) / 'phrases.json')
            self.assertEqual((narration.root(pid) / (entries[0]['key'] + '.mp3')).read_bytes(), text.encode())

    def test_identical_concurrent_phrases_share_one_take_and_one_project_charge(self):
        entered = threading.Event()
        def synthesize(settings):
            entered.set()
            self.assertTrue(self.release.wait(5))
            return b'shared take'
        text = 'The same sentence in both projects.'
        source = lab.original_path({**self.settings, 'text': text}, {})
        with patch.object(lab.heygen_voice, 'synthesize', side_effect=synthesize) as paid:
            first, second = self.projects.values()
            narration.start(first, text)
            self.assertTrue(entered.wait(5))
            narration.start(second, text)
            self.wait_for_users(source, 3)  # producer, nested cache writer, waiting project
            self.release.set()
            jobs = self.finished()
        self.assertEqual([job['status'] for job in jobs], ['done', 'done'])
        paid.assert_called_once()
        amounts = [sum(row['amount'] for row in store.read_json(self.project_dir(pid) / 'project-costs.json')['events'].values()) for pid in self.projects]
        self.assertAlmostEqual(sum(amounts), len(text) * 30 / 1_000_000)
        self.assertEqual(sum(amount > 0 for amount in amounts), 1)

    def test_waiting_duplicate_does_not_repeat_a_failed_provider_call(self):
        entered = threading.Event()
        def fail(settings):
            entered.set()
            self.assertTrue(self.release.wait(5))
            raise RuntimeError('Provider refused')
        text = 'The same sentence in both projects.'
        source = lab.original_path({**self.settings, 'text': text}, {})
        with patch.object(lab.heygen_voice, 'synthesize', side_effect=fail) as paid:
            first, second = self.projects.values()
            narration.start(first, text)
            self.assertTrue(entered.wait(5))
            narration.start(second, text)
            self.wait_for_users(source, 3)
            self.release.set()
            jobs = self.finished()
        paid.assert_called_once()
        self.assertEqual([job['status'] for job in jobs], ['failed', 'failed'])
        self.assertEqual([job['error'] for job in jobs], ['Provider refused', 'Provider refused'])
        self.assertEqual(lab.NARRATIONS, {})

    def test_cancel_and_completion_release_only_their_project_and_keep_reference_protected(self):
        entered = threading.Barrier(3)
        first_release = threading.Event()
        def synthesize(settings):
            entered.wait(5)
            self.assertTrue((first_release if settings['text'].startswith('First') else self.release).wait(5))
            return b'audio'
        with patch.object(lab.heygen_voice, 'synthesize', side_effect=synthesize):
            first, second = self.projects.values()
            narration.start(first, 'First project sentence.')
            narration.start(second, 'Second project sentence.')
            entered.wait(5)
            with self.assertRaises(store.StudioError):
                narration.start(first, 'Repeated click sentence.')
            narration.cancel(first['id'])
            first_release.set()
            self.workers[0].join(5)
            self.assertEqual(narration.snapshot(first['id'])['job']['status'], 'cancelled')
            self.assertEqual(set(lab.NARRATIONS), {second['id']})
            self.assertTrue(lab.in_use(self.cid))
            with self.assertRaises(store.StudioError):
                lab.remove(self.cid)
            self.release.set()
            jobs = self.finished()
        self.assertEqual([job['status'] for job in jobs], ['cancelled', 'done'])
        self.assertFalse(lab.in_use(self.cid))

    def test_worker_start_failure_releases_project_and_channel_reservation(self):
        project = next(iter(self.projects.values()))
        with patch.object(narration.threading, 'Thread', side_effect=RuntimeError('No worker')):
            with self.assertRaisesRegex(RuntimeError, 'No worker'):
                narration.start(project, 'A complete sentence.')
        self.assertFalse(narration.ACTIVE)
        self.assertFalse(lab.in_use(self.cid))
        self.assertEqual(narration.snapshot(project['id'])['job']['status'], 'failed')

    def test_elevenlabs_and_fish_also_synthesize_different_projects_in_parallel(self):
        for provider in ['elevenlabs', 'fishaudio']:
            with self.subTest(provider=provider):
                self.settings = lab.validated({'provider': provider, 'noise_cleanup': False})
                both = threading.Barrier(2)
                def synthesize(*args, **kwargs):
                    both.wait(5)
                    return b'audio'
                with patch.object(lab, 'prepared_source', return_value=self.root / 'reference.mp3'), \
                     patch.object(lab, 'clone', return_value=('secret', 'voice')), \
                     patch.object(lab, 'fish_reference', return_value={'audio': b'ref', 'text': 'Reference.'}), \
                     patch.object(lab.languages, 'key', return_value='secret'), \
                     patch.object(lab.eleven_api, 'balance', return_value={'credit_usd_rate': .00022}), \
                     patch.object(lab, 'synthesis', side_effect=synthesize) as eleven, \
                     patch.object(lab.languages, 'request', side_effect=synthesize) as fish:
                    first, second = self.projects.values()
                    narration.start(first, 'First ' + provider + ' project sentence.')
                    narration.start(second, 'Second ' + provider + ' project sentence.')
                    jobs = self.finished()
                self.assertEqual([job['status'] for job in jobs], ['done', 'done'])
                self.assertEqual((eleven if provider == 'elevenlabs' else fish).call_count, 2)

    def test_channel_sample_and_project_share_cached_audio_without_a_second_charge(self):
        text = 'The same sentence in the sample and project.'
        settings = {**self.settings, 'text': text}
        ref = lab.effective_reference(self.cid, settings)
        source = lab.original_path(settings, ref)
        entered = threading.Event()
        def synthesize(settings):
            entered.set()
            self.assertTrue(self.release.wait(5))
            return b'shared take'
        sample = {'status': 'running', 'fingerprint': lab.fingerprint(settings, ref), 'estimate': lab.estimate(settings)}
        with patch.object(lab.heygen_voice, 'synthesize', side_effect=synthesize) as paid:
            narration.start(next(iter(self.projects.values())), text)
            self.assertTrue(entered.wait(5))
            lab.ACTIVE.add(self.cid)
            worker = self.worker(target=lab.run, args=(self.cid, settings, ref, sample), daemon=True)
            worker.start()
            self.wait_for_users(source, 3)
            self.release.set()
            for worker in self.workers:
                worker.join(5)
        paid.assert_called_once()
        self.assertEqual(sample['status'], 'done')
        self.assertEqual(sample['estimate']['amount'], 0)
        self.assertFalse(lab.in_use(self.cid))


if __name__ == '__main__':
    unittest.main()
