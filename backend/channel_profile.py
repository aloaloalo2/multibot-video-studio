"""Cache script samples by source files, independently of the montage's changing revision."""
from collections import OrderedDict
import copy
import hashlib
from pathlib import Path
import threading

import store

LOCK = threading.RLock()
CACHE = OrderedDict()
TEXT_COUNTS = OrderedDict()
LIMIT = 128


def stamp(path):
    try:
        value = Path(path).stat()
        return (value.st_mtime_ns, value.st_size, value.st_ino)
    except (OSError, TypeError):return None


def samples(cid, projects, limit, count_words):
    result = []
    for item in sorted(projects, key=lambda value: value.get('created_at', 0), reverse=True):
        pid = item['id']
        try:path = store.project_path(pid)
        except store.StudioError as error:
            if error.status != 404:raise
            path = None
        key = (str(store.DATA_ROOT), cid, pid)
        with LOCK:
            cached = CACHE.get(key)
            signature = (stamp(path), *(stamp(source) for source in cached.get('sources', []))) if cached else None
            if cached and signature[0] and signature == cached['signature']:
                sample = copy.deepcopy(cached['sample'])
            else:
                try:project = store.load_project(pid)
                except store.StudioError as error:
                    if error.status == 404:continue
                    raise
                script = (project.get('voice_script') or {}).get('text') or ''
                sources = []
                if not script:
                    sources = [store.project_dir(pid) / 'source-timing.json'] if path else []
                    if project.get('plan_source'):sources.append(Path(project['plan_source']))
                    source = store.load_project_narration(pid) or {}
                    script = source.get('spoken_script') or source.get('script') or ''
                digest = hashlib.sha256(script.encode()).hexdigest()
                if digest not in TEXT_COUNTS:TEXT_COUNTS[digest] = count_words(script)
                count = TEXT_COUNTS[digest]
                sample = {'title':project['name'],'opening':script[:800],'ending':script[-250:],'words':count} if count >= 100 else None
                signature = (stamp(path), *(stamp(source) for source in sources))
                CACHE[key] = {'signature':signature,'sources':sources,'sample':sample}
                while len(CACHE) > LIMIT:CACHE.popitem(last=False)
                while len(TEXT_COUNTS) > LIMIT:TEXT_COUNTS.popitem(last=False)
        if sample:
            result.append(copy.deepcopy(sample))
            if len(result) == limit:break
    return result
