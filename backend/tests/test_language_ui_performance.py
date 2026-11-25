import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store
import languages
import eleven_api


class LanguageUIReadsTest(unittest.TestCase):
    def test_voice_switcher_reads_only_ready_metadata_without_overview_or_catalogue(self):
        items={'uk':{'voice':{'made_at':12}},'pl':{'voice':{'made_at':13}},'es':{}}
        with patch.object(store,'load_project',return_value={'id':'p'}), \
             patch.object(languages,'load_state',return_value={'languages':items}), \
             patch.object(languages,'final_voice',return_value=Path('/voice.mp3')), \
             patch.object(languages,'voice_current',side_effect=lambda p,c,v:c=='uk'), \
             patch.object(languages,'overview',side_effect=AssertionError('heavy overview')), \
             patch.object(eleven_api,'catalog',side_effect=AssertionError('network catalogue')):
            result=languages.voice_options('p')
        self.assertEqual([item['code'] for item in result['items']],['uk'])
        self.assertEqual(result['items'][0]['made_at'],12)
        self.assertNotIn('text',result['items'][0])

    def test_one_view_loads_a_project_once_and_sees_a_changed_project(self):
        # the overview asked for the project about twenty times, each re-anchoring the timeline's joins
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'project.json';path.write_text('{}')
            with patch.object(store,'project_path',return_value=path), \
                 patch.object(store,'load_project',side_effect=lambda pid:{'id':pid}) as load:
                with languages.project_reads():
                    first=languages.project_for('p')
                    self.assertIs(languages.project_for('p'),first)
                    self.assertEqual(load.call_count,1)
                    path.write_text('{"changed": true}')
                    languages.project_for('p')
                    self.assertEqual(load.call_count,2)
                languages.project_for('p');languages.project_for('p')
                self.assertEqual(load.call_count,4)

    def test_view_memo_reuses_examples_and_settings_only_inside_a_view(self):
        calls=[]
        compute=lambda:calls.append(1) or len(calls)
        self.assertEqual(languages.view_memo(lambda:('k',),compute),1)
        self.assertEqual(languages.view_memo(lambda:('k',),compute),2)
        with languages.project_reads():
            self.assertEqual(languages.view_memo(lambda:('k',),compute),3)
            self.assertEqual(languages.view_memo(lambda:('k',),compute),3)
            self.assertEqual(languages.view_memo(('other',),compute),4)

    def test_language_check_cache_is_invalidated_by_exact_text(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(languages,'work_dir',return_value=Path(tmp)):
            with patch.object(languages.language_quality,'check',return_value={'version':languages.language_quality.VERSION,'target':'uk','state':'ok'}) as check:
                languages.cached_language_check('p','uk','First text',[])
                languages.cached_language_check('p','uk','First text',[])
                self.assertEqual(check.call_count,1)
                languages.cached_language_check('p','uk','Changed text',[])
                self.assertEqual(check.call_count,2)

    def test_ui_catalogue_deduplicates_background_refresh_and_does_not_wait_for_network(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(store,'DATA_ROOT',Path(tmp)), \
             patch.object(eleven_api.credentials,'vault',return_value=Mock(read=Mock(return_value='test'))), \
             patch.object(eleven_api,'_cache',{}), patch.object(eleven_api,'_refreshing',set()), \
             patch.object(eleven_api.threading,'Thread') as thread, patch.object(eleven_api,'get') as remote:
            first=eleven_api.ui_catalog();second=eleven_api.ui_catalog()
            self.assertEqual(first['models'],second['models'])
            self.assertEqual(thread.call_count,1)
            remote.assert_not_called()

    def test_request_snapshot_reuses_json_but_observes_a_changed_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'data.json';path.write_text('{"a":1}')
            with store.read_snapshot():
                first=store.read_json(path);self.assertIs(first,store.read_json(path))
                path.write_text('{"a":22}')
                self.assertEqual(store.read_json(path)['a'],22)
