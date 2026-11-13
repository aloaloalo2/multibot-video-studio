from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parents[2]/'engine')]
import native_review as review
import store


class NativeReviewTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.frames=[{'number':n,'start':n-1,'end':n,'format':'generated_photo','sentences':['test']} for n in (1,2)]
        self.manifest={'width':192,'height':108,'fps':25,'layer_mode':'item','duration':2,'timeline_layers':[]}
        self.files=[]
        for n in (1,2):
            path=self.root/f'pic{n}.png'
            Image.new('RGB',(80,45),'blue').save(path)
            self.files.append(path)
            self.manifest['timeline_layers'].append({'z':n,'clips':[{'id':str(n),'type':'image','source':str(path),'start':n-1,'duration':1}]})
        self.project={'id':'fixture','project_kind':'regular'}
        for stub in [patch.object(store,'project_dir',return_value=self.root),patch.object(store,'load_project_plan',return_value={'frames':self.frames}),
                     patch.object(store,'made_frames',return_value=[1,2]),patch('timeline_manifest.build',return_value=self.manifest),
                     patch('render_cache.renderer_version',return_value='test')]:
            stub.start();self.addCleanup(stub.stop)
        self.renders=[]
        def render(path,window,times):
            self.renders.append(times)
            Image.new('RGB',(240,45),'green').save(path)
        stub=patch.object(review,'render_row',side_effect=render);stub.start();self.addCleanup(stub.stop)

    def test_batches_render_once_and_reopen_only_the_changed_frame(self):
        first=review.batch(self.project,[1,2])
        self.assertTrue(Path(first['sheet']).is_file())
        self.assertEqual(len(self.renders),2)
        self.assertTrue(all(len(set(t))==3 for t in self.renders))
        self.assertEqual(review.batch(self.project,[1,2]),first)
        review.batch(self.project,[1,2],first['ticket'])
        self.assertEqual(review.missing(self.project,self.frames),[])
        Image.new('RGB',(80,45),'red').save(self.files[1])
        self.assertEqual(review.missing(self.project,self.frames),[2])
        with self.assertRaises(store.StudioError):
            review.batch(self.project,[1,2],first['ticket'])
        second=review.batch(self.project,[1,2])
        self.assertEqual(second['frames'],[2])
        review.batch(self.project,[2],second['ticket'])
        self.assertIsNone(review.batch(self.project,[1,2])['sheet'])
        self.assertEqual(len(self.renders),3)

    def test_one_defect_does_not_require_reopening_the_other_row(self):
        sheet=review.batch(self.project,[1,2])
        review.batch(self.project,[2],sheet['ticket'])
        Image.new('RGB',(80,45),'yellow').save(self.files[0])
        self.assertEqual(review.batch(self.project,[1,2])['frames'],[1])
        with self.assertRaises(store.StudioError):
            review.batch(self.project,[1],sheet['ticket'])

    def test_outgoing_join_affects_next_frame_without_reopening_the_finished_one(self):
        original=review.prepare(self.project,self.frames)
        clip=self.manifest['timeline_layers'][0]['clips'][0]
        clip.update(native_duration=1,duration=1.5,join_out={'type':'crossfade','duration':.5,'seam':1})
        joined=review.prepare(self.project,self.frames)
        self.assertEqual(original[1][0],joined[1][0])
        self.assertNotEqual(original[2][0],joined[2][0])
        self.assertEqual(joined[1][1]['timeline_layers'][0]['clips'][0]['duration'],1.5)
        clip['preset']='fade_out'
        self.assertNotEqual(original[1][0],review.prepare(self.project,self.frames)[1][0])
        clip.pop('preset')
        self.manifest['timeline_layers'].insert(0,{'z':0,'clips':[]})
        self.assertEqual(joined[1][0],review.prepare(self.project,self.frames)[1][0])

    def test_no_preapproval_after_missing_stills_or_unplaced_content(self):
        sheet=review.batch(self.project,[1])
        next(review.folder(self.project).glob('1-*.png')).unlink()
        with self.assertRaises(store.StudioError):
            review.batch(self.project,[1],sheet['ticket'])
        with patch.object(store,'made_frames',return_value=[]),self.assertRaises(store.StudioError):
            review.batch(self.project,[1])
