"""Immutable local comparison sources, independent of paid image generation."""
import hashlib
import re
import shutil

import store

VERSION = re.compile(r'Превью (?:до )?v[1-9][0-9]*\.png')


def folder(pid):
    return store.project_dir(pid) / 'preview'


def record(pid, name, *, base=None, reference=None, image=None):
    if not VERSION.fullmatch(name):
        raise store.StudioError('Невідома версія прев’ю')
    comparison = None
    if base and VERSION.fullmatch(base):
        comparison = {'kind': 'edit', 'base': base}
    elif reference and image and image.is_file():
        stamp = hashlib.sha256(image.read_bytes()).hexdigest()
        target = folder(pid) / 'comparison' / (stamp + '.jpg')
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file():
            temporary = target.with_suffix('.tmp')
            try:
                shutil.copyfile(image, temporary)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        comparison = {'kind': 'clone', 'image': target.name, 'reference_id': reference.get('id'),
                      'title': str(reference.get('title') or '')[:300]}
    if comparison:
        with store.LOCK:
            path = folder(pid) / 'comparisons.json'
            data = store.read_json(path, {}) or {}
            if not isinstance(data, dict):data = {}
            store.atomic_json(path, {**data, name: comparison})


def describe(pid, name, records=None):
    try:
        records = records if records is not None else store.read_json(folder(pid) / 'comparisons.json', {}) or {}
        item = records.get(name) if isinstance(records, dict) else None
        if not isinstance(item, dict):return None
        if item.get('kind') == 'edit' and VERSION.fullmatch(str(item.get('base', ''))):
            return {'kind': 'edit', 'base': item['base']}
        if item.get('kind') == 'clone' and re.fullmatch('[0-9a-f]{64}\\.jpg', str(item.get('image', ''))) and (folder(pid) / 'comparison' / item['image']).is_file():
            return {'kind': 'clone', 'url': f"/api/projects/{pid}/thumbnail-reference/{item['image']}", 'title': str(item.get('title') or '')[:300]}
    except (OSError, ValueError):
        pass
    return None


def source(pid, name):
    store.load_project(pid)
    if not isinstance(name, str) or not re.fullmatch('[0-9a-f]{64}\\.jpg', name):
        raise store.StudioError('Референс прев’ю не знайдено', 404)
    path = folder(pid) / 'comparison' / name
    if not path.is_file():raise store.StudioError('Референс прев’ю не знайдено', 404)
    return path
