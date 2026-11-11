import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import script_drafts as drafts
import store


class ScriptDraftTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.pid = 'a' * 24
        self.project = {'id': self.pid, 'revision': 3, 'voice_script': {'text': 'Accepted voice script.', 'saved_at': 20}}
        self.original = copy.deepcopy(self.project)
        for item in (patch.object(store, 'project_dir', return_value=self.base),
                     patch.object(store, 'load_project', side_effect=lambda pid: copy.deepcopy(self.project)),
                     patch.object(store, 'load_project_narration', return_value=None)):
            item.start();self.addCleanup(item.stop)

    def save(self, text, **patches):
        current = drafts.current(self.pid)
        body = {'text': text, 'expected_version': current['version'], 'base_sha256': current['base_sha256'], 'epoch': current['epoch'], **patches}
        return drafts.save(self.pid, body)

    def test_empty_short_and_full_drafts_are_durable_without_changing_accepted_work(self):
        for text in ('', 'x', 'The edited complete script.\n\nAnother paragraph.'):
            result = self.save(text)
            self.assertEqual(drafts.current(self.pid)['text'], text)
            self.assertEqual(json.loads((drafts.root(self.pid) / 'current.json').read_text())['text'], text)
            self.assertEqual(result['sha256'], drafts.digest(text))
            self.assertEqual(self.project, self.original)

    def test_refreshing_a_draft_is_read_only(self):
        self.save('My working version.')
        files = {path: path.read_bytes() for path in drafts.root(self.pid).rglob('*.json')}
        drafts.current(self.pid);drafts.history(self.pid)
        self.assertEqual({path: path.read_bytes() for path in files}, files)

    def test_conflicting_tabs_cannot_silently_replace_each_other(self):
        first = drafts.current(self.pid)
        self.save('First tab edit.')
        with self.assertRaises(store.StudioError) as caught:
            self.save('Second tab edit.', expected_version=first['version'])
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(drafts.current(self.pid)['text'], 'First tab edit.')

    def test_unknown_acknowledgement_repeats_one_identical_write_safely(self):
        first = drafts.current(self.pid)
        accepted = self.save('One save.')
        files = list(drafts.root(self.pid).rglob('*.json'))
        repeated = self.save('One save.', expected_version=first['version'])
        self.assertEqual(repeated['version'], accepted['version'])
        self.assertEqual(list(drafts.root(self.pid).rglob('*.json')), files)

    def test_reload_can_continue_its_own_unacknowledged_write_without_replaying_older_text(self):
        writer = 'same-browser-tab-123'
        self.save('First edit.', writer_id=writer, client_sequence=1)
        latest = self.save('Newer edit.', expected_version=0, writer_id=writer, client_sequence=2)
        self.assertEqual(latest['text'], 'Newer edit.')
        for expected in (0, latest['version']):
            with self.assertRaises(store.StudioError):
                self.save('First edit.', expected_version=expected, writer_id=writer, client_sequence=1)
        self.assertEqual(drafts.current(self.pid)['text'], 'Newer edit.')

    def test_restore_saves_a_new_working_version_and_preserves_the_replaced_text(self):
        self.save('First edit.')
        self.save('Second edit.')
        previous = next(row for row in drafts.history(self.pid)['versions'] if row['id'] != 'baseline')
        current = drafts.current(self.pid)
        restored = drafts.restore(self.pid, {'version_id': previous['id'], 'expected_version': current['version'], 'base_sha256': current['base_sha256'], 'epoch': current['epoch']})
        self.assertEqual(restored['text'], 'First edit.')
        self.assertEqual(restored['version'], current['version'] + 1)
        self.assertEqual(self.project, self.original)
        texts = [drafts.version(self.pid, row['id'])['text'] for row in drafts.history(self.pid)['versions']]
        self.assertIn('Second edit.', texts)
        self.assertIn('Accepted voice script.', texts)

    def test_new_accepted_script_keeps_old_pending_draft_available_explicitly(self):
        self.save('My unfinished edit.')
        self.project['voice_script']['text'] = 'New accepted script.'
        current = drafts.current(self.pid)
        self.assertTrue(current['stale']);self.assertFalse(current['pending'])
        self.assertEqual(current['text'], 'New accepted script.')
        self.assertEqual(drafts.version(self.pid, 'stale')['text'], 'My unfinished edit.')
        self.assertEqual(drafts.history(self.pid)['versions'][0]['id'], 'stale')

    def test_narration_start_consumes_equal_text_without_a_second_generation(self):
        self.save('The submitted narration script.')
        self.project['voice_script']['text'] = 'The submitted narration script.'
        current = drafts.current(self.pid)
        self.assertFalse(current['pending']);self.assertFalse(current['stale'])
        self.assertEqual(current['text'], self.project['voice_script']['text'])

    def test_restart_rejects_late_edits_from_the_previous_episode_generation(self):
        old = drafts.current(self.pid)
        self.project['restarted_at'] = 50
        with self.assertRaises(store.StudioError) as caught:
            self.save('Old page write.', epoch=old['epoch'], base_sha256=old['base_sha256'])
        self.assertEqual(caught.exception.status, 409)
        self.assertFalse((drafts.root(self.pid) / 'current.json').exists())

    def test_history_is_bounded_and_keeps_the_initial_accepted_script(self):
        with patch.object(drafts, 'MAX_HISTORY', 3):
            for number in range(12):self.save('Draft '+str(number))
            self.assertLessEqual(len(drafts.history(self.pid)['versions']), 4)
            self.assertEqual(drafts.version(self.pid, 'baseline')['text'], self.original['voice_script']['text'])

    def test_failed_head_write_preserves_previous_draft_and_history(self):
        self.save('Saved edit.')
        atomic = store.atomic_json
        def write(path, value):
            if path.name == 'current.json':raise OSError('disk full')
            return atomic(path, value)
        with patch.object(store, 'atomic_json', side_effect=write):
            with self.assertRaises(OSError):self.save('Unacknowledged edit.')
        self.assertEqual(drafts.current(self.pid)['text'], 'Saved edit.')
        self.assertEqual(self.project, self.original)

    def test_invalid_input_and_version_paths_are_rejected(self):
        for text in (None, {}, 'x' * 200001):
            with self.assertRaises(store.StudioError):self.save(text)
        with self.assertRaises(store.StudioError):self.save('Some text.', expected_version=True)
        for value in ('../current', 'a/../../x', None, 'not-a-version'):
            with self.assertRaises(store.StudioError):drafts.version(self.pid, value)


if __name__ == '__main__':unittest.main()
