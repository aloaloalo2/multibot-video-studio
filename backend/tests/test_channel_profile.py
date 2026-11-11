import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import channel_profile as profile
import store


class ChannelProfileTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);profile.CACHE.clear();profile.TEXT_COUNTS.clear()
        self.project={'id':'p','name':'One','voice_script':{'text':'word '*120}}
        self.path=self.root/'project.json';store.atomic_json(self.path,self.project)
        for item in (patch.object(store,'project_path',return_value=self.path),patch.object(store,'project_dir',return_value=self.root),
                     patch.object(store,'load_project',side_effect=lambda _:copy.deepcopy(self.project))):
            item.start();self.addCleanup(item.stop)
        self.count=Mock(side_effect=lambda text:len(text.split()))

    def test_repeated_profile_reads_reuse_source_and_count_but_script_changes_invalidate(self):
        projects=[{'id':'p','created_at':2}]
        first=profile.samples('c',projects,3,self.count);first[0]['title']='Changed client object'
        again=profile.samples('c',projects,3,self.count)
        self.assertEqual(again[0]['title'],'One');self.assertEqual(self.count.call_count,1)
        self.project['revision']=15;store.atomic_json(self.path,self.project)
        profile.samples('c',projects,3,self.count);self.assertEqual(self.count.call_count,1)
        self.project['voice_script']['text']='new '*180;store.atomic_json(self.path,self.project)
        self.assertEqual(profile.samples('c',projects,3,self.count)[0]['words'],180);self.assertEqual(self.count.call_count,2)

    def test_fallback_timing_file_changes_and_removed_projects_do_not_leave_stale_samples(self):
        self.project.pop('voice_script');store.atomic_json(self.path,self.project)
        timing=self.root/'source-timing.json';store.atomic_json(timing,{'script':'first '*110})
        with patch.object(store,'load_project_narration',side_effect=lambda _:store.read_json(timing)):
            self.assertEqual(profile.samples('c',[{'id':'p'}],3,self.count)[0]['words'],110)
            store.atomic_json(timing,{'script':'second '*190})
            self.assertEqual(profile.samples('c',[{'id':'p'}],3,self.count)[0]['words'],190)
        self.assertEqual(profile.samples('c',[],3,self.count),[])
