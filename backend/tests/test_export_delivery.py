import errno
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import export_delivery


class ExportDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'staging.mp4'
        self.source.write_bytes(b'complete video' * 1024)
        self.destination = self.root / 'final.mp4'

    def other_volume(self):
        original = Path.stat
        def stat(path, *args, **kwargs):
            if path == self.source:
                return SimpleNamespace(st_dev=original(path).st_dev + 1)
            return original(path, *args, **kwargs)
        return patch.object(Path, 'stat', stat)

    def test_same_volume_publishes_a_complete_file_without_replacing_source(self):
        with export_delivery.prepared(self.source, self.destination) as ready:
            self.assertEqual(ready, self.source)
            export_delivery.publish(ready, self.destination)
        self.assertEqual(self.destination.read_bytes(), self.source.read_bytes())

    def test_external_volume_copies_locally_before_publishing_and_cleans_temporary_file(self):
        with self.other_volume(), export_delivery.prepared(self.source, self.destination) as ready:
            self.assertNotEqual(ready, self.source)
            self.assertEqual(ready.read_bytes(), self.source.read_bytes())
            self.assertFalse(self.destination.exists())
            export_delivery.publish(ready, self.destination)
        self.assertEqual(self.destination.read_bytes(), self.source.read_bytes())
        self.assertEqual(list(self.root.glob('*.partial')), [])

    def test_a_filename_created_during_render_is_never_overwritten(self):
        self.destination.write_bytes(b'author file')
        with self.assertRaisesRegex(RuntimeError, 'вже існує'):
            export_delivery.publish(self.source, self.destination)
        self.assertEqual(self.destination.read_bytes(), b'author file')

    def test_filesystems_without_hardlinks_use_an_exclusive_reservation(self):
        with patch.object(export_delivery.os, 'link', side_effect=OSError(errno.EPERM, 'Unsupported')):
            export_delivery.publish(self.source, self.destination)
        self.assertEqual(self.destination.read_bytes(), b'complete video' * 1024)
        self.assertFalse(self.source.exists())

    def test_external_copy_cancel_or_failure_never_publishes_partial_video(self):
        with self.other_volume():
            with self.assertRaises(InterruptedError):
                with export_delivery.prepared(self.source, self.destination, lambda: True):
                    self.fail('Cancelled copy reached publication')
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.root.glob('*.partial')), [])
        with self.other_volume(), patch.object(export_delivery.os, 'fsync', side_effect=OSError('Disk full')):
            with self.assertRaises(OSError):
                with export_delivery.prepared(self.source, self.destination):
                    self.fail('Failed copy reached publication')
        self.assertTrue(self.source.is_file())
        self.assertEqual(list(self.root.glob('*.partial')), [])

    def test_failed_rename_removes_only_its_empty_reservation(self):
        with patch.object(export_delivery.os, 'link', side_effect=OSError(errno.EPERM, 'Unsupported')), \
                patch.object(export_delivery.os, 'replace', side_effect=OSError('Disk full')):
            with self.assertRaises(OSError):
                export_delivery.publish(self.source, self.destination)
        self.assertFalse(self.destination.exists())
        self.assertTrue(self.source.is_file())
