"""Three export stills per finished Studio frame. A visual verdict belongs to the exact sheet the agent opened."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading

from PIL import Image, ImageDraw

import store

LOCK = threading.RLock()


def prepare(project, frames):
    """Keep render order and every visual layer that can appear within each selected frame."""
    import timeline_manifest
    import render
    from render_cache import RenderCache, renderer_version, visual_key
    content = timeline_manifest.build(project, visual_only=True, include_transitions=False)
    manifest = copy.deepcopy(content)
    # Display the finished join, but keep its envelope and neighbouring tails out
    # of the content approval identity. The export manifest still includes joins.
    import joins
    joins.transport(project, manifest['timeline_layers'])
    fps = manifest['fps']
    root = store.project_dir(project['id'])
    cache = RenderCache(root / 'render-cache')
    version = renderer_version(store.APP_ROOT / 'engine')
    result = {}
    for frame in frames:
        first, end = (render.frame_index(frame[k], fps) for k in ('start', 'end'))
        if first >= end:
            raise store.StudioError('Кадр закороткий для перевірки.')
        def local_layers(source):
            result=[]
            for layer in sorted(source, key=lambda row: row['z']):
                clips=[c for c in layer['clips'] if render.frame_index(c['start'],fps)<end
                       and render.frame_index(c['start']+c['duration'],fps)>first]
                if clips:
                    result.append({'z':len(result),'clips':clips})
            return result
        layers=local_layers(manifest['timeline_layers'])
        signature_layers=local_layers(content['timeline_layers'])
        if not layers:
            raise store.StudioError(f"Кадр {frame['number']} ще порожній.")
        window = {**manifest, 'duration': end/fps, 'timeline_layers': layers}
        moments = [min(end-1, first+int((end-first)*part))/fps for part in (.05,.5,.95)]
        picture = visual_key({**window, 'timeline_layers':signature_layers}, root/'project.json', window['width'], window['height'], fps,
                             end/fps, render, cache, version)
        key = digest([picture, moments, frame.get('sentences'), frame.get('visual'), frame.get('scene')])
        result[frame['number']] = (key, window, moments)
    return result


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def folder(project):
    return store.project_dir(project['id']) / 'frame-review'


def approved(root, n, key):
    entry = store.read_json(root/f'{n}-ok.json', {}) or {}
    return entry.get('source') == key and (root/f'{n}-{key}.png').is_file()


def missing(project, frames):
    root = folder(project)
    if not root.is_dir():
        return [f['number'] for f in frames]
    return [n for n,(key,_,_) in prepare(project, frames).items() if not approved(root,n,key)]


def render_row(target, window, moments):
    from still import still
    with tempfile.TemporaryDirectory(dir=target.parent) as temp:
        work = Path(temp)
        manifest = work/'manifest.json'
        store.atomic_json(manifest, window)
        width = min(window['width'], 400)
        height = max(1, round(width*window['height']/window['width']))
        row = Image.new('RGB', (3*width, height))
        for i, moment in enumerate(moments):
            image = work/'moment.png'
            still(manifest, moment, image)
            with Image.open(image) as original:
                row.paste(original.resize((width,height), Image.Resampling.LANCZOS), (i*width,0))
        row.save(work/'row.png')
        os.replace(work/'row.png',target)


def batch(project, numbers, ticket=None):
    if not isinstance(numbers,list) or not 1 <= len(numbers) <= 5 or any(type(n) is not int for n in numbers) or len(set(numbers)) != len(numbers):
        raise store.StudioError('Вкажіть від одного до п’яти різних номерів кадрів.')
    with LOCK:
        plan = store.load_project_plan(project['id']) or {}
        wanted = set(numbers)
        frames = [f for f in plan.get('frames',[]) if f['number'] in wanted]
        if len(frames) != len(numbers) or any(f.get('format')=='razgon_2d' for f in frames) or store.project_animated(project):
            raise store.StudioError('Оберіть кадри таймлайна Studio. Для кадрів Razgon відкрийте аркуш Razgon.')
        if not wanted <= set(store.made_frames(project,plan)):
            raise store.StudioError('Спершу поставте готові кадри на таймлайн.',409)
        root = folder(project)
        root.mkdir(parents=True,exist_ok=True)
        current = prepare(project,frames)
        if ticket is not None:
            import re
            if not isinstance(ticket,str) or not re.fullmatch('[a-f0-9]{64}', ticket):
                raise store.StudioError('Невірний ідентифікатор аркуша.')
            record = store.read_json(root/f'sheet-{ticket}.json',{}) or {}
            listed = record.get('frames') or []
            if digest(listed) != ticket or not (root/f'sheet-{ticket}.png').is_file():
                raise store.StudioError('Аркуш не знайдено. Підготуйте його знову.',409)
            sources = dict(listed)
            for n,(key,_,_) in current.items():
                if sources.get(n) != key or not (root/f'{n}-{key}.png').is_file():
                    raise store.StudioError('Кадр змінився. Відкрийте актуальний аркуш.',409)
            for n,(key,_,_) in current.items():
                store.atomic_json(root/f'{n}-ok.json', {'source':key})
            return {'approved':numbers}
        rows = []
        for n,(key,window,moments) in current.items():
            if approved(root,n,key):
                continue
            path = root/f'{n}-{key}.png'
            if not path.exists():
                render_row(path,window,moments)
            rows.append([n,key])
        if not rows:
            return {'frames':[], 'sheet':None}
        token = digest(rows)
        sheet = root/f'sheet-{token}.png'
        if not sheet.exists():
            with Image.open(root/f'{rows[0][0]}-{rows[0][1]}.png') as row:
                width, height = row.size
            contact = Image.new('RGB',(width,len(rows)*(height+22)),'#141418')
            pen = ImageDraw.Draw(contact)
            for i,(n,key) in enumerate(rows):
                y = i*(height+22)
                pen.text((6,y+3),f'#{n}',fill='white')
                with Image.open(root/f'{n}-{key}.png') as row:
                    contact.paste(row,(0,y+22))
            temp = sheet.with_suffix('.tmp')
            contact.save(temp,format='PNG')
            os.replace(temp,sheet)
        store.atomic_json(root/f'sheet-{token}.json',{'frames':rows})
        return {'sheet':str(sheet),'frames':[n for n,_ in rows],'ticket':token}
