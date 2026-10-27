"""Cached exports must invalidate on real edits and survive disposable damage."""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from render_cache import RenderCache,key_for,visual_key
import render


class RenderCacheTest(unittest.TestCase):
    def test_cache_write_failure_preserves_export_and_disables_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'video';source.write_bytes(b'valid export')
            cache=RenderCache(root/'cache')
            with patch.object(cache,'_prune_locked',side_effect=OSError('cache is unavailable')):
                cache.publish('visual',key_for('video'),source)
            self.assertFalse(cache.enabled)
            self.assertEqual(source.read_bytes(),b'valid export')

    def test_roundtrip_corruption_eviction_and_live_job_hardlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);cache=RenderCache(root/'cache',max_bytes=10)
            source=root/'source';source.write_bytes(b'first')
            key=key_for('first');cache.publish('media',key,source,{'width':10})
            target=root/'job-copy'
            self.assertEqual(cache.restore('media',key,target),{'width':10})
            self.assertEqual(target.read_bytes(),b'first')
            other=root/'other';other.write_bytes(b'longer!')
            cache.publish('media',key_for('other'),other)
            self.assertFalse((cache.root/'media'/key).exists())
            self.assertEqual(target.read_bytes(),b'first')
            # Corrupt only the cache artifact, never original user media.
            entry=cache.root/'media'/key_for('other')/'data'
            entry.unlink();entry.write_bytes(b'damaged')
            self.assertIsNone(cache.restore('media',key_for('other'),root/'bad-copy'))
            self.assertFalse((root/'bad-copy').exists())
            with self.assertRaises(FileExistsError):cache.restore('media',key,target)

    def test_same_size_and_mtime_source_change_invalidates(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';source.write_bytes(b'abcd')
            cache=RenderCache(root/'cache');first=cache.source(source);stat=source.stat()
            source.write_bytes(b'efgh');os.utime(source,ns=(stat.st_atime_ns,stat.st_mtime_ns))
            self.assertNotEqual(first,cache.source(source))
            self.assertEqual(cache.source(source),RenderCache(root/'cache').source(source))

    def test_visual_cache_preserves_visual_edits_and_can_remix_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);cache=RenderCache(root/'cache');manifest=root/'p.json'
            project={'width':320,'height':180,'fps':25,'layer_mode':'item','timeline_layers':[
                {'clips':[{'type':'text','text':'Корицы','start':0,'duration':1,
                           'font_family':'Literata','font_size':40,'font_weight':500}]},
                {'clips':[{'type':'audio','source':'voice.wav','start':0,'duration':1,'volume':1}]}]}
            def key(p):return visual_key(p,manifest,320,180,25,1,render,cache,'test-version')
            first=key(project)
            project['timeline_layers'][1]['clips'][0]['volume']=.5
            self.assertEqual(first,key(project))
            for field,value in [('text','Другой'),('font_size',42),('font_weight',700),('x',.4)]:
                changed=json.loads(json.dumps(project));changed['timeline_layers'][0]['clips'][0][field]=value
                self.assertNotEqual(first,key(changed))

    def test_source_alias_and_implicit_text_font_are_fingerprinted(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);cache=RenderCache(root/'cache');media=root/'image.png';font=root/'font.ttf'
            media.write_bytes(b'first image');font.write_bytes(b'first font')
            project={'timeline_layers':[{'clips':[{'type':'image','media_path':str(media)},
                {'kind':'text','text':'Test','font_family':'Custom'}]}]}
            def key():return visual_key(project,root/'p.json',320,180,25,1,render,cache,'version')
            with patch.object(render,'first_font',return_value=font):
                first=key();media.write_bytes(b'second image');second=key()
                self.assertNotEqual(first,second)
                font.write_bytes(b'second font');self.assertNotEqual(second,key())


if __name__=='__main__':unittest.main()
