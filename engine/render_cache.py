"""Bounded, content-addressed local render cache. User media stays read-only."""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path


def digest_file(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def key_for(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


class RenderCache:
    def __init__(self, root=None, max_bytes=None):
        self.root=Path(root or os.environ.get('MULTIBOT_RENDER_CACHE') or Path.home()/'Library/Caches/MultiBotVideoStudio/render-v2')
        self.max_bytes=int(max_bytes if max_bytes is not None else os.environ.get('MULTIBOT_RENDER_CACHE_BYTES',4*1024**3))
        self.enabled=os.environ.get('MULTIBOT_RENDER_CACHE_ENABLED','1')!='0' and self.max_bytes>0
        self.hits=0;self.misses=0
        self._files={}
        if self.enabled:
            try:self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
            except OSError:self.enabled=False

    @contextlib.contextmanager
    def _lock(self):
        with (self.root/'.lock').open('a+b') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            try:yield
            finally:fcntl.flock(lock,fcntl.LOCK_UN)

    def _entry(self,kind,key):
        if kind not in {'media','chunk','visual','build'} or not re.fullmatch('[0-9a-f]{64}',key):raise ValueError('Invalid cache key')
        return self.root/kind/key

    def source(self,path,_stability_retries=2):
        """Reuse content hashes only while the complete filesystem identity agrees."""
        path=Path(path).resolve();s=path.stat()
        identity=(str(path),s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        if identity in self._files:return self._files[identity]
        token=key_for(identity);value=None
        if self.enabled:
            with sqlite3.connect(self.root/'sources.sqlite',timeout=30) as db:
                db.execute('CREATE TABLE IF NOT EXISTS files (identity TEXT PRIMARY KEY, digest TEXT, used REAL)')
                row=db.execute('SELECT digest FROM files WHERE identity=?',(token,)).fetchone()
                if row:value=row[0]
        if value is None:
            value=digest_file(path)
            # Do not cache a hash computed while the source was changing.
            after=path.stat()
            if (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)!=(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns):
                # Hydration and cache hardlinks can change metadata while a
                # first hash is read. Only retain a hash from a stable read.
                if _stability_retries:return self.source(path,_stability_retries-1)
                raise RuntimeError(f'Media changed during export: {path.name}')
        if self.enabled:
            with sqlite3.connect(self.root/'sources.sqlite',timeout=30) as db:
                db.execute('INSERT OR REPLACE INTO files VALUES (?,?,?)',(token,value,time.time()))
                db.execute('DELETE FROM files WHERE identity IN (SELECT identity FROM files ORDER BY used DESC LIMIT -1 OFFSET 10000)')
        result={'sha256':value,'size':s.st_size,'suffix':path.suffix.lower()}
        self._files[identity]=result
        return result

    def restore(self,kind,key,target):
        if not self.enabled:self.misses+=1;return None
        entry=self._entry(kind,key);target=Path(target)
        if target.exists():raise FileExistsError(target)
        try:
            with self._lock():
                metadata=json.loads((entry/'meta.json').read_text())
                artifact=entry/'data'
                if artifact.stat().st_size!=metadata['size'] or digest_file(artifact)!=metadata['sha256']:raise ValueError('Corrupt cache entry')
                target.parent.mkdir(parents=True,exist_ok=True)
                try:os.link(artifact,target)
                except OSError:
                    if target.exists():raise
                    shutil.copyfile(artifact,target)
                os.utime(entry,None)
            self.hits+=1
            return metadata.get('extra',{})
        except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError):
            target.unlink(missing_ok=True)
            # Corrupt disposable entries never replace user output.
            if entry.exists():
                with self._lock():shutil.rmtree(entry,ignore_errors=True)
            self.misses+=1
            return None

    def publish(self,kind,key,path,extra=None):
        try:self._publish(kind,key,path,extra)
        except OSError:
            # A disposable cache must not restart an otherwise valid export.
            self.enabled=False

    def _publish(self,kind,key,path,extra=None):
        if not self.enabled:return
        path=Path(path);size=path.stat().st_size
        if size>self.max_bytes:return
        entry=self._entry(kind,key);entry.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.write-',dir=entry.parent) as temp:
            stage=Path(temp);artifact=stage/'data'
            try:os.link(path,artifact)
            except OSError:shutil.copyfile(path,artifact)
            metadata={'size':size,'sha256':digest_file(artifact),'extra':extra or {}}
            (stage/'meta.json').write_text(json.dumps(metadata),encoding='utf-8')
            with self._lock():
                if not entry.exists():
                    os.rename(stage,entry)
                    # TemporaryDirectory permits the renamed directory to be absent.
                self._prune_locked()

    def discard(self,kind,key):
        if not self.enabled:return
        with self._lock():shutil.rmtree(self._entry(kind,key),ignore_errors=True)

    def _prune_locked(self):
        entries=[];total=0
        for kind in ('media','chunk','visual','build'):
            folder=self.root/kind
            if not folder.exists():continue
            for entry in folder.iterdir():
                if not re.fullmatch('[0-9a-f]{64}',entry.name):continue
                try:
                    size=(entry/'data').stat().st_size;used=entry.stat().st_mtime
                    entries.append((used,size,entry));total+=size
                except OSError:continue
        for _,size,entry in sorted(entries):
            if total<=self.max_bytes:break
            shutil.rmtree(entry,ignore_errors=True);total-=size


def renderer_version(root):
    root=Path(root);files=[*root.glob('*.py'),root/'gpu_render.swift',
                         root.parent/'frontend/graphic-transitions.json',root.parent/'frontend/visual-effects.json',
                         root.parent/'backend/font_catalog.py',root.parent/'frontend/fonts/catalog.json']
    return key_for([(str(p.relative_to(root.parent)),digest_file(p)) for p in sorted(files) if p.is_file()])


def visual_key(project,project_file,width,height,fps,total,renderer,cache,version):
    layers=[];fonts={}
    for layer in project['timeline_layers']:
        clips=[]
        for original in layer.get('clips',[]):
            if original.get('type',original.get('kind'))=='audio':continue
            clip={k:v for k,v in original.items() if k not in {'id','title','volume','audio_role'}}
            value=renderer.source_value(clip)
            if value:
                source=renderer.resolve_source(value,project_file,'cache media')
                for field in ('source','src','file','path','asset_path','media_path'):
                    if field in clip:clip[field]=cache.source(source)
            if clip.get('text') or clip.get('type',clip.get('kind'))=='text' or clip.get('content_type')=='text':
                font=renderer.first_font(clip.get('font_family','Arial'),clip.get('font_weight',400))
                fonts[str(font)]=cache.source(font)
            clips.append(clip)
        if clips:layers.append({**{k:v for k,v in layer.items() if k not in {'clips','id','title'}},'clips':clips})
    return key_for({'version':version,'width':width,'height':height,'fps':fps,'frames':renderer.frame_index(total,fps),
                    'background':project.get('background','#101114'),'layer_mode':project.get('layer_mode'),
                    'layers':layers,'fonts':fonts,'codec':'hevc','bitrate':2000000})


def prepared_key(scenes,width,height,fps,cache,version):
    normalized=[]
    for scene in scenes:
        layers=[]
        for layer in scene['layers']:
            item=dict(layer)
            if item.get('kind')=='gradient':item['source']='procedural-gradient'
            else:item['source']=cache.source(item['source'])
            layers.append(item)
        normalized.append({'duration_frames':round((scene['end']-scene['start'])*fps),'color':scene['color'],'layers':layers})
    return key_for({'version':version,'width':width,'height':height,'fps':fps,'scenes':normalized,'codec':'hevc','bitrate':2000000})


def scene_key(scene,width,height,fps,renderer,cache,version):
    value=json.loads(json.dumps(scene));fonts={}
    for layer in value.get('layers',[]):
        source=renderer.source_value(layer)
        if source:
            for key in ('source','src','file','path','asset_path','media_path'):
                if key in layer:layer[key]=cache.source(source)
        if layer.get('type')=='text':
            font=renderer.first_font(layer.get('font_family','Arial'),layer.get('font_weight',400))
            fonts[str(font)]=cache.source(font)
    return key_for({'version':version,'scene':value,'width':width,'height':height,'fps':fps,'fonts':fonts})
