"""Immutable versions of each language's thumbnail, including legacy single-file previews."""
from __future__ import annotations
import fcntl
import hashlib
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from PIL import Image
import store

LOCK=threading.RLock()
VERSION=re.compile(r'v([1-9][0-9]*)\.png')


def folder(pid: str, code: str) -> Path:
    if not re.fullmatch('[a-z]{2}',code):raise store.StudioError('Невідома мова',400)
    return store.project_dir(pid)/'languages'/code


def manifest(pid: str, code: str) -> dict:
    return store.read_json(folder(pid,code)/'thumbnails.json',{}) or {}


def current_file(pid: str, code: str) -> Path | None:
    work=folder(pid,code);current=manifest(pid,code).get('current','')
    if VERSION.fullmatch(current) and (work/'thumbnails'/current).is_file():return work/'thumbnails'/current
    legacy=work/'thumbnail.png'
    return legacy if legacy.is_file() else None


def versions(pid: str, code: str) -> list[dict]:
    work=folder(pid,code);data=manifest(pid,code);result=[]
    for item in data.get('versions',[]):
        name=item.get('name','')
        if not VERSION.fullmatch(name):continue
        path=work/'thumbnails'/name
        if path.is_file():result.append({**item,'current':name==data.get('current'),'stamp':path.stat().st_mtime_ns})
    if not result and (work/'thumbnail.png').is_file():
        stat=(work/'thumbnail.png').stat()
        result=[{'name':'v1.png','number':1,'current':True,'time':stat.st_mtime,'stamp':stat.st_mtime_ns,'legacy':True}]
    return sorted(result,key=lambda x:x['number'],reverse=True)


def version_file(pid: str, code: str, name: str) -> Path:
    if not VERSION.fullmatch(name):raise store.StudioError('Прев’ю не знайдено',404)
    work=folder(pid,code);path=work/'thumbnails'/name
    if path.is_file():return path
    if name=='v1.png' and not manifest(pid,code) and (work/'thumbnail.png').is_file():return work/'thumbnail.png'
    raise store.StudioError('Прев’ю не знайдено',404)


def validate(path: Path) -> None:
    with Image.open(path) as image:
        if image.format!='PNG':raise store.StudioError('Результат прев’ю має бути PNG.',400)
        image.verify()


def _copy(source: Path, target: Path) -> None:
    temp=target.with_name(target.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        shutil.copy2(source,temp);temp.replace(target)
    finally:temp.unlink(missing_ok=True)


def publish(pid: str, code: str, source: Path, metadata: dict | None = None, prompt: str = '') -> dict:
    validate(source)
    work=folder(pid,code);work.mkdir(parents=True,exist_ok=True)
    metadata=dict(metadata or {})
    with LOCK,(work/'thumbnails.lock').open('a+') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        data=manifest(pid,code);items=data.setdefault('versions',[]);archive=work/'thumbnails';archive.mkdir(exist_ok=True)
        # Retrying publication of the same completed job must not create another version.
        if metadata.get('job_started') is not None:
            old=next((x for x in items if x.get('job_started')==metadata['job_started']),None)
            if old:return old
        legacy=work/'thumbnail.png'
        if not items and legacy.is_file():
            validate(legacy);_copy(legacy,archive/'v1.png')
            items.append({'name':'v1.png','number':1,'time':legacy.stat().st_mtime,
                          'sha256':hashlib.sha256(legacy.read_bytes()).hexdigest(),'legacy':True})
        number=max((x['number'] for x in items),default=0)+1
        while (archive/f'v{number}.png').exists():number+=1
        name=f'v{number}.png';_copy(source,archive/name)
        item={**metadata,'name':name,'number':number,'time':time.time(),
              'sha256':hashlib.sha256((archive/name).read_bytes()).hexdigest()}
        if prompt:(archive/f'v{number}.prompt.txt').write_text(prompt,encoding='utf-8')
        items.append(item);data['current']=name
        # This pointer publishes the complete validated version atomically.
        store.atomic_json(work/'thumbnails.json',data)
        _copy(archive/name,legacy)
        return item


def choose(pid: str, code: str, name: str) -> None:
    source=version_file(pid,code,name);work=folder(pid,code)
    with LOCK,(work/'thumbnails.lock').open('a+') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        data=manifest(pid,code)
        if not data:return  # the sole legacy v1 is already selected
        if not any(x.get('name')==name for x in data.get('versions',[])):
            raise store.StudioError('Прев’ю не знайдено',404)
        data['current']=name;store.atomic_json(work/'thumbnails.json',data)
        _copy(source,work/'thumbnail.png')
