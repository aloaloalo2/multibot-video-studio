import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store,logo_layer,channel_branding

class LiveLogoTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.channel=self.root/'channel';self.channel.mkdir()
        self.cid='c'*16;self.pid='a'*24
        for stub in (patch.object(store,'DATA_ROOT',self.root/'data'),patch.object(store,'PROJECTS_ROOT',self.root/'data/projects'),patch.object(store,'get_channel_folder',return_value=self.channel)):
            stub.start();self.addCleanup(stub.stop)
        store.PROJECTS_ROOT.joinpath(self.pid).mkdir(parents=True)
        self.logo=channel_branding.logo_path(self.cid);self.logo.parent.mkdir(parents=True)
        Image.new('RGBA',(100,100),'red').save(self.logo)
        store.atomic_json(self.channel/store.PLAN_CONFIG,{'logo':{'position':'top-left','margin':0,'size':10}})
        self.project={'id':self.pid,'channel_id':self.cid,'episode_path':str(self.channel),'revision':3,'created_at':1000000000000,'schema_version':2,'layer_mode':'item',
            'duration':10,'width':320,'height':180,'assets':[], 'tracks':[{'id':'film','clips':[{'id':'frame','kind':'video','start':0,'duration':10}]}]}
        store.save_project(self.project)

    def test_current_source_is_used_without_rewriting_project_or_export_snapshot(self):
        original=store.project_path(self.pid).read_bytes()
        first=store.load_project(self.pid);clip=logo_layer.clips(first)[0][1]
        asset=store.resolve_asset(first,clip['asset_id']);old_path=Path(asset['path']);old_bytes=old_path.read_bytes()
        Image.new('RGBA',(100,100),'blue').save(self.logo)
        second=store.load_project(self.pid);new_clip=logo_layer.clips(second)[0][1]
        new_path=Path(store.resolve_asset(second,new_clip['asset_id'])['path'])
        self.assertNotEqual(first['branding_version'],second['branding_version'])
        self.assertNotEqual(old_path,new_path)
        self.assertEqual(old_path.read_bytes(),old_bytes)
        self.assertEqual(store.project_path(self.pid).read_bytes(),original)
        self.assertEqual(first['revision'],second['revision'])
        self.assertEqual(clip['id'],new_clip['id'])
        with Image.open(new_path) as image:self.assertEqual(image.getpixel((2,2)),(0,0,255,255))
        self.assertEqual(len(logo_layer.clips(store.load_project(self.pid))),1)

    def test_legacy_channel_logo_plate_relinks_but_another_plate_survives(self):
        old=self.root/'channel_logo.png';Image.new('RGBA',(320,180),'red').save(old)
        self.project['assets']=[{'id':'old','path':str(old),'source':'local'}]
        self.project['tracks'].extend([
            {'id':'legacy','clips':[{'id':'oldclip','asset_id':'old','title':'Плашка каналу','kind':'image','start':0,'duration':10}]},
            {'id':'other','clips':[{'id':'otherclip','title':'Плашка каналу','kind':'image','start':0,'duration':10}]}])
        store.save_project(self.project)
        current=store.load_project(self.pid)
        self.assertEqual(len(logo_layer.clips(current)),1)
        self.assertEqual(logo_layer.clips(current)[0][1]['id'],'oldclip')
        self.assertIn('otherclip',[c['id'] for t in current['tracks'] for c in t['clips']])
        store.save_project(current)
        off={'logo':{'enabled':False}};store.atomic_json(self.channel/store.PLAN_CONFIG,off)
        disabled=store.load_project(self.pid)
        self.assertFalse(logo_layer.clips(disabled))
        self.assertIn('otherclip',[c['id'] for t in disabled['tracks'] for c in t['clips']])
        self.assertEqual(len(disabled['tracks']),2)

    def test_new_placement_and_frame_size_get_distinct_snapshots(self):
        one=store.load_project(self.pid)
        store.atomic_json(self.channel/store.PLAN_CONFIG,{'logo':{'position':'bottom-right','margin':0,'size':10}})
        two=store.load_project(self.pid)
        asset=store.resolve_asset(two,logo_layer.clips(two)[0][1]['asset_id'])
        self.assertNotEqual(one['branding_version'],two['branding_version'])
        with Image.open(asset['path']) as image:
            self.assertEqual(image.getpixel((2,2))[3],0)
            self.assertEqual(image.getpixel((318,178))[:3],(255,0,0))
        three=logo_layer.bind({**self.project,'width':640})
        self.assertNotEqual(two['branding_version'],three['branding_version'])

    def test_import_collision_copy_is_removed_and_the_managed_clip_identity_survives(self):
        current = store.load_project(self.pid)
        managed_id = logo_layer.clips(current)[0][1]['id']
        copied = self.root/'channel_logo-4f90ed3f.png'
        copied.write_bytes(self.logo.read_bytes())
        current['assets'].append({'id':'copy','path':str(copied),'source':'local'})
        current['tracks'].insert(0, {'id':'copied-plate','clips':[
            {'id':'duplicate','asset_id':'copy','title':'Плашка каналу','kind':'image','start':0,'duration':10}]})
        current['scene_groups'].append({'id':'copied-group','role':'overlay','clip_ids':['duplicate']})
        store.save_project(current)
        saved = store.project_path(self.pid).read_bytes()
        resolved = store.load_project(self.pid)
        self.assertEqual([c['id'] for _,c in logo_layer.clips(resolved)], [managed_id])
        self.assertNotIn('duplicate', [c['id'] for t in resolved['tracks'] for c in t['clips']])
        self.assertFalse(any('duplicate' in group['clip_ids'] for group in resolved['scene_groups']))
        self.assertEqual(store.project_path(self.pid).read_bytes(), saved)
        self.assertEqual(resolved['revision'], current['revision'])
        self.assertTrue(copied.is_file())
        store.atomic_json(self.channel/store.PLAN_CONFIG, {'logo':{'enabled':False}})
        disabled = store.load_project(self.pid)
        self.assertFalse(logo_layer.clips(disabled))

    def test_unrelated_name_plate_with_similar_filename_is_preserved(self):
        self.project['assets'].append({'id':'portrait','path':str(self.root/'channel_logo-portrait.png'),'source':'local'})
        self.project['tracks'].append({'id':'portrait-layer','clips':[
            {'id':'portrait','asset_id':'portrait','title':'Плашка каналу','kind':'image','start':0,'duration':10}]})
        store.save_project(self.project)
        resolved = store.load_project(self.pid)
        self.assertIn('portrait', [c['id'] for t in resolved['tracks'] for c in t['clips']])

    def test_both_frame_briefs_reserve_logo_space_and_assign_branding_to_studio(self):
        import production
        project = {**self.project, 'name':'Branding test'}
        request = {'frames':3,'total_frames':10,'start':0,'end':30}
        with patch.object(production.channel_branding,'reserved_zone',return_value='reserved corner'), \
             patch.object(production.director,'channel_settings',return_value={}):
            for brief in (production.brief, production.photo_brief):
                text = brief(project, request)
                self.assertIn('Логотип і плашку каналу додає сама студія.', text)
                self.assertIn('не імпортуй копій', text)
                self.assertIn('reserved corner', text)

if __name__=='__main__':unittest.main()
