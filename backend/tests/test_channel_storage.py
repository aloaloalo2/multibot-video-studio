import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import store
import technical_files


class ChannelStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.youtube = self.base / 'external-drive' / 'YouTube'
        self.youtube.mkdir(parents=True)
        self.data = self.base / 'studio' / 'data'
        self.patches = [patch.object(store, 'YOUTUBE_ROOT', self.youtube),
                        patch.object(store, 'DATA_ROOT', self.data),
                        patch.object(store, 'DISABLED_PATH', self.data / 'disabled.json')]
        for p in self.patches:
            p.start()
        self.folder = self.youtube / 'Ду'
        self.folder.mkdir()
        self.legacy = self.folder / store.PLAN_CONFIG
        self.settings = {'weights': {'animation': 100}, 'script_wishes': 'Зберегти все',
                         'auto_narration': True, 'auto_montage': False, 'future_option': {'a': 1}}

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def write_legacy(self):
        raw = json.dumps(self.settings, ensure_ascii=False, indent=1).encode()
        self.legacy.write_bytes(raw)
        return raw

    def test_new_channel_is_discovered_with_completely_empty_user_folder(self):
        record = store.create_channel('Новий')
        folder = self.youtube / 'Новий'
        self.assertEqual(list(folder.iterdir()), [])
        self.assertTrue(store.channel_settings_path(folder).is_file())
        self.assertEqual(store.get_channel_folder(record['id']), folder)
        self.assertEqual(store.create_channel('Новий')['id'], record['id'])

    def test_legacy_read_is_compatible_and_has_no_write_side_effect(self):
        self.write_legacy()
        self.assertEqual(store.read_channel_settings(self.folder), self.settings)
        self.assertFalse(self.data.exists())

    def test_migration_preserves_identity_every_setting_and_exact_backup(self):
        original = self.write_legacy()
        cid = store.channel_id(self.folder)
        self.assertEqual(technical_files.migrate_channel(self.folder), [str(self.legacy)])
        self.assertEqual(store.get_channel_folder(cid), self.folder)
        self.assertEqual(store.channel_record(self.folder)['settings'], self.settings)
        self.assertEqual(list(self.folder.iterdir()), [])
        saved = list(store.channel_settings_path(self.folder).parent.glob('technical-history/*/video-plan.json'))
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].read_bytes(), original)
        self.assertEqual(technical_files.migrate_channel(self.folder), [])

    def test_newer_internal_settings_remain_authoritative(self):
        original = self.write_legacy()
        newer = {**self.settings, 'script_wishes': 'Нове побажання'}
        store.atomic_json(store.channel_settings_path(self.folder), newer)
        technical_files.migrate_channel(self.folder)
        self.assertEqual(store.read_channel_settings(self.folder), newer)
        self.assertEqual(next(store.channel_settings_path(self.folder).parent.glob('technical-history/*/video-plan.json')).read_bytes(), original)

    def test_invalid_sources_are_never_deleted_or_replaced(self):
        for raw in (b'{broken', b'[]', b'null'):
            self.legacy.write_bytes(raw)
            with self.assertRaises((ValueError, store.StudioError)):
                technical_files.migrate_channel(self.folder)
            self.assertEqual(self.legacy.read_bytes(), raw)
            self.assertFalse(store.channel_settings_path(self.folder).exists())
        self.write_legacy()
        store.atomic_json(store.channel_settings_path(self.folder), [])
        with self.assertRaises(store.StudioError):
            technical_files.migrate_channel(self.folder)
        self.assertTrue(self.legacy.exists())

    def test_failed_backup_or_save_keeps_legacy_readable(self):
        original = self.write_legacy()
        for owner, method in ((technical_files.shutil, 'copy2'), (store, 'atomic_json')):
            with patch.object(owner, method, side_effect=OSError('Full disk')), self.assertRaises(OSError):
                technical_files.migrate_channel(self.folder)
            self.assertEqual(self.legacy.read_bytes(), original)
            self.assertEqual(store.read_channel_settings(self.folder), self.settings)

    def test_disabled_channels_migrate_without_becoming_enabled(self):
        self.write_legacy()
        cid = store.channel_id(self.folder)
        store.disable_channel(cid)
        result = technical_files.migrate_channels()
        self.assertIn(cid, result)
        self.assertEqual(store.channel_folders(), [])
        self.assertEqual(store.get_channel_folder(cid, include_disabled=True), self.folder)
        self.assertFalse(self.legacy.exists())

    def test_settings_save_and_readd_never_recreate_external_json(self):
        self.write_legacy()
        record = store.add_channel(self.folder)
        saved = store.update_channel_settings(record['id'], {'thumbnail_wishes': 'Побажання'})
        self.assertEqual(saved['settings']['thumbnail_wishes'], 'Побажання')
        self.assertEqual(saved['settings']['future_option'], {'a': 1})
        self.assertEqual(list(self.folder.iterdir()), [])
        self.assertEqual(store.add_channel(self.folder)['id'], record['id'])
        with self.assertRaises(store.StudioError):
            store.validated_youtube_root(str(self.folder))

    def test_imported_rules_are_internal_and_old_rules_remain_readable(self):
        old = self.folder / 'AGENTS.md'
        old.write_text('Old rules')
        self.assertEqual(store.channel_rules_source(self.folder), old)
        new = store.channel_settings_path(self.folder).with_name('channel-rules.md')
        store.atomic_text(new, 'Imported rules')
        self.assertEqual(store.channel_rules_source(self.folder), new)
