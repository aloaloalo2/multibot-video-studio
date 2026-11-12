"""Cached discovery of public competitor videos, without keys or accounts."""
import statistics
import threading
import time

import channel_competitors
import youtube_public
import trending_titles
import store

LOCK = threading.Lock()
RUNNING = False
LAST_START = 0
ERRORS = []
TTL = 6 * 3600


def sources():
    result = {}
    for folder in store.channel_folders():
        cid = store.channel_id(folder)
        name = store.read_channel_settings(folder, {}).get('display_name') or folder.name
        for row in channel_competitors.read(cid):
            if not channel_competitors.CHANNEL_ID.fullmatch(row.get('id', '')):
                continue
            item = result.setdefault(row['id'], {**row, 'for_channels': []})
            item['for_channels'].append({'id': cid, 'name': name})
    return result


def rank(videos, now):
    """Compare per-day views with other recent uploads of similar duration."""
    usable = [v for v in videos if 0 <= now - v['published_ts'] <= 90 * 86400 and v['duration'] > 0]
    result = []
    for video in usable:
        age = (now - video['published_ts']) / 86400
        if age > 14:
            continue
        peers = [p for p in usable if p['id'] != video['id'] and (p['duration'] <= 180) == (video['duration'] <= 180)]
        if len(peers) < 4:
            continue
        baseline = statistics.median(p['views'] / max(1, (now - p['published_ts']) / 86400) for p in peers)
        score = (video['views'] / max(1, age)) / max(1, baseline)
        if score >= 1.5 and video['views'] > 0:
            result.append({**video, 'score': round(score, 2), 'baseline_daily': round(baseline), 'sample_size': len(peers), 'early': age < 1})
    return sorted(result, key=lambda v: (v['score'], v['views']), reverse=True)


def collect(identity):
    return youtube_public.collect(identity)


def cache_path():
    return store.DATA_ROOT / 'trending-videos.json'


def view():
    linked = sources()
    cache = trending_titles.decorate(store.read_json(cache_path(), {}))
    cards, warnings = [], []
    for identity, source in linked.items():
        entry = cache.get(identity)
        if not entry: continue
        if entry.get('sample_truncated'): warnings.append(source['name'] + ': вибірка обмежена 120 останніми відео')
        if entry.get('failed_videos'): warnings.append(source['name'] + ': частина відео тимчасово недоступна')
        for video in rank(entry['videos'], time.time()):
            cards.append({**video, 'competitor_id': identity, 'competitor_name': entry['name'], 'subscribers': entry['subscribers'],
                          'for_channels': source['for_channels'], 'updated_at': entry['updated_at']})
    cards.sort(key=lambda v: (v['score'], v['views']), reverse=True)
    with LOCK:
        running, errors = RUNNING, list(ERRORS)
    return {'videos': cards, 'competitor_icons': {identity: source['icon_url'] for identity, source in linked.items() if source.get('icon_url')},
            'running': running, 'errors': errors, 'warnings': warnings,
            'competitors': len(linked), 'checked': sum(i in cache for i in linked),
            'channels': list({c['id']: c for s in linked.values() for c in s['for_channels']}.values()),
            'needs_refresh': any(i not in cache or time.time()-cache[i]['updated_at'] >= TTL for i in linked)}


def refresh():
    global RUNNING, LAST_START, ERRORS
    linked = sources()
    with LOCK:
        if RUNNING or time.time() - LAST_START < 60: return view_unlocked_busy()
        if not linked: return {'running': False}
        RUNNING, LAST_START, ERRORS = True, time.time(), []
    def work():
        global RUNNING, ERRORS
        try:
            cache = store.read_json(cache_path(), {})
            for identity, source in linked.items():
                if identity in cache and time.time()-cache[identity]['updated_at'] < TTL: continue
                try:
                    cache[identity] = collect(identity)
                    store.atomic_json(cache_path(), cache)
                except Exception:
                    with LOCK: ERRORS.append(source['name'] + ': YouTube тимчасово не надав дані. Спробуйте пізніше')
            try:
                visible = [video for identity, entry in cache.items() if identity in linked for video in rank(entry['videos'], time.time())]
                trending_titles.update(visible)
            except Exception:
                with LOCK: ERRORS.append('Не вдалося перекласти заголовки. Натисніть ↻, щоб повторити')
            finally:
                store.atomic_json(cache_path(), trending_titles.decorate(cache))
        finally:
            with LOCK: RUNNING = False
    threading.Thread(target=work, name='youtube-trends', daemon=True).start()
    return {'running': True}


def view_unlocked_busy():
    return {'running': RUNNING, 'retry_after': max(0, 60-int(time.time()-LAST_START))}


def busy():
    with LOCK:
        return RUNNING


def use_idea(body):
    """Create one project and enter the normal author workflow after explicit submission."""
    import re
    import idea_reference
    identity = body.get('video_id')
    if not isinstance(identity, str) or not idea_reference.VIDEO_ID.fullmatch(identity):
        raise store.StudioError('Оберіть відео з добірки', 400)
    cid = body.get('channel_id')
    store.get_channel_folder(cid)
    title = store.validated_name(body.get('title'))
    count, use_thumbnail, request_id = body.get('target_words'), body.get('use_thumbnail'), body.get('request_id')
    if type(count) is not int or not 200 <= count <= 15000:
        raise store.StudioError('Вкажіть обсяг від 200 до 15 000 слів')
    if type(use_thumbnail) is not bool:
        raise store.StudioError('Оберіть, чи використовувати прев’ю конкурента')
    if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', request_id):
        raise store.StudioError('Оновіть вікно й повторіть створення зачинів')
    payload = {'reference_id': identity, 'title': title, 'target_words': count,
               'request_id': request_id, 'use_thumbnail': use_thumbnail}
    receipt = store.DATA_ROOT / 'trending-idea-requests' / (request_id+'.json')
    if store.read_json(receipt, {}).get('project_id'):
        return idea_reference.start_openings(cid, payload, source={'id': identity, 'title': title}, receipt_path=receipt)
    linked, cache = sources(), store.read_json(cache_path(), {})
    source = next(({'id': identity, 'title': v['title'], 'url': 'https://www.youtube.com/watch?v='+identity,
                    'author': entry['name']} for competitor, entry in cache.items() if competitor in linked
                   for v in entry.get('videos', []) if v.get('id') == identity), None)
    if source is None:
        raise store.StudioError('Відео вже немає у збереженій добірці. Оновіть сторінку.', 404)
    if use_thumbnail:
        source = idea_reference.inspect(cid, source['url'])
    return idea_reference.start_openings(cid, payload, source=source, receipt_path=receipt)
