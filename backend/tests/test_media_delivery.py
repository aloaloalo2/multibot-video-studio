import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import media_delivery as media
import store

class MediaDeliveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.project_file=self.root/'project.json'
        self.project_file.write_text('{}')
        self.path_patch=patch.object(store,'project_path',return_value=self.project_file)
        self.path_patch.start();self.addCleanup(self.path_patch.stop)
        media._PROJECTS.clear()

    def test_preview_burst_reads_project_once_but_validates_each_file(self):
        project={'id':'p'}
        with patch.object(store,'load_project',return_value=project) as load, \
             patch.object(store,'resolve_asset',side_effect=lambda p,aid:{'id':aid}) as resolve:
            for i in range(40):self.assertEqual(media.resolve('p',str(i))[1]['id'],str(i))
            self.assertEqual(load.call_count,1)
            self.assertEqual(resolve.call_count,40)

    def test_timeline_edit_and_deletion_invalidate_cached_project(self):
        with patch.object(store,'load_project',return_value={'revision':1}) as load, \
             patch.object(store,'resolve_asset',return_value={'id':'a'}):
            self.assertEqual(media.resolve('p','a')[0]['revision'],1)
            self.project_file.write_text('{"revision":2}')
            load.return_value={'revision':2}
            self.assertEqual(media.resolve('p','a')[0]['revision'],2)
            self.project_file.write_text('{"deleted_at":123}')
            load.side_effect=store.StudioError('Deleted',404)
            with self.assertRaises(store.StudioError):media.resolve('p','a')

    def test_new_channel_logo_refreshes_derived_metadata_without_timeline_edit(self):
        def asset(project,aid):
            if aid not in project['assets']:raise store.StudioError('Missing',404)
            return {'id':aid}
        with patch.object(store,'load_project',side_effect=[{'assets':['old']},{'assets':['new']}]) as load, \
             patch.object(store,'resolve_asset',side_effect=asset):
            media.resolve('p','old')
            self.assertEqual(media.resolve('p','new')[1]['id'],'new')
            self.assertEqual(load.call_count,2)

    def test_cached_metadata_does_not_bypass_file_access_validation(self):
        with patch.object(store,'load_project',return_value={'id':'p'}), \
             patch.object(store,'resolve_asset',return_value={'id':'a'}) as resolve:
            media.resolve('p','a')
            resolve.side_effect=store.StudioError('Outside allowed directory',403)
            with self.assertRaises(store.StudioError) as error:media.resolve('p','a')
            self.assertEqual(error.exception.status,403)
