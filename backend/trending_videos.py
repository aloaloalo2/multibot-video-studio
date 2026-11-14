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
MIN_VIEWS = 4000


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
    """Compare per-day views with the channel's other recent films. Shorts never enter the selection (user,
    14 November 2026: «шорти мені прикріпляти до у тренді не потрібно взагалі»): a video up to 180 s counts only when it
    is about as long as the channel's regular films (a 2:59 film among four-minute ones), never a 20-second clip."""
    usable = [v for v in videos if 0 <= now - v['published_ts'] <= 90 * 86400 and v['duration'] > 0]
    longer = [v['duration'] for v in usable if v['duration'] > 180]
    floor = statistics.median(longer) / 2 if longer else None
    films = [v for v in usable if v['duration'] > 180 or (floor is not None and v['duration'] >= floor)]
    result = []
    for video in films:
        age = (now - video['published_ts']) / 86400
        if age > 14 or video['views'] < MIN_VIEWS:
            continue
        peers = [p for p in films if p['id'] != video['id']]
        if len(peers) < 4:
            continue
        baseline = statistics.median(p['views'] / max(1, (now - p['published_ts']) / 86400) for p in peers)
        score = (video['views'] / max(1, age)) / max(1, baseline)
        if score >= 1.5 and video['views'] > 0:
            result.append({**video, 'score': round(score, 2), 'baseline_daily': round(baseline), 'sample_size': len(peers), 'early': age < 1})
    return sorted(result, key=lambda v: (v['score'], v['views']), reverse=True)

API_NOTE = []   # why the last refresh read the public pages although a key is saved (one line, without the key)


def collect(identity, previous=None):
    """With the author's YouTube Data API key the official API answers in a few requests; without one, or when the key
    fails, the public pages are read as before."""
    import youtube_api
    secret = youtube_api.key()
    if secret and not API_NOTE:
        try:
            return youtube_api.collect(identity, secret, previous)
        except youtube_api.ApiError as error:
            API_NOTE.append('YouTube Data API: ' + str(error) + '. Дані читаю з публічних сторінок, це повільніше')
        except (ValueError, KeyError):
            pass   # this one channel: the public page may still answer
    return youtube_public.collect(identity, previous)


def cache_path():
    return store.DATA_ROOT / 'trending-videos.json'


def used_video_ids():
    """Creation receipts outlive project renames/deletion and identify the exact source globally."""
    import idea_reference
    used = set()
    for path in (store.DATA_ROOT / 'trending-idea-requests').glob('*.json'):
        try:
            receipt = store.read_json(path, {})
        except (OSError, ValueError):
            continue
        if not isinstance(receipt, dict) or not isinstance(receipt.get('project_id'), str) or not receipt['project_id']:
            continue
        identity = receipt.get('reference_id')
        if isinstance(identity, str) and idea_reference.VIDEO_ID.fullmatch(identity):
            used.add(identity)
    return used


def view():
    linked = sources()
    cache = trending_titles.decorate(store.read_json(cache_path(), {}))
    used = used_video_ids()
    cards, warnings = [], []
    for identity, source in linked.items():
        entry = cache.get(identity)
        if not entry: continue
        if entry.get('sample_truncated'): warnings.append(source['name'] + ': вибірка обмежена 120 останніми відео')
        if entry.get('failed_videos'): warnings.append(source['name'] + ': не вдалося отримати дані для '+str(entry['failed_videos'])+' відео')
        if entry.get('pagination_incomplete'): warnings.append(source['name'] + ': список відео оновлено частково; попередні дані збережено')
        for video in rank(entry['videos'], time.time()):
            if video['id'] in used:
                continue
            cards.append({**video, 'competitor_id': identity, 'competitor_name': entry['name'], 'subscribers': entry['subscribers'],
                          'for_channels': source['for_channels'], 'updated_at': entry['updated_at']})
    cards.sort(key=lambda v: (v['score'], v['views']), reverse=True)
    with LOCK:
        running, errors = RUNNING, list(ERRORS)
    return {'videos': cards, 'competitor_icons': {identity: source['icon_url'] for identity, source in linked.items() if source.get('icon_url')},
            'running': running, 'errors': errors, 'warnings': warnings,
            'competitors': len(linked), 'checked': sum(i in cache for i in linked),
            'channels': list({c['id']: c for s in linked.values() for c in s['for_channels']}.values()),
            'needs_refresh': any(i not in cache or time.time()-cache[i]['updated_at'] >= TTL or cache[i].get('failed_videos') or cache[i].get('pagination_incomplete') for i in linked)}


def refresh():
    global RUNNING, LAST_START, ERRORS
    linked = sources()
    with LOCK:
        if RUNNING or time.time() - LAST_START < 60: return view_unlocked_busy()
        if not linked: return {'running': False}
        RUNNING, LAST_START, ERRORS = True, time.time(), []
        API_NOTE.clear()
    def work():
        global RUNNING, ERRORS
        try:
            cache = store.read_json(cache_path(), {})
            import concurrent.futures
            import youtube_api
            has_key = bool(youtube_api.key())
            # with a key, what was read from the public pages (often with gaps) is read again through the API at once
            stale = [(identity, source) for identity, source in linked.items()
                     if not ((previous := cache.get(identity)) and time.time()-previous['updated_at'] < TTL
                             and not (previous.get('failed_videos') or previous.get('pagination_incomplete'))
                             and not (has_key and previous.get('source') != 'youtube-api'))]
            def one(pair):
                identity, source = pair
                try:
                    return identity, collect(identity, cache.get(identity)), None
                except Exception:
                    return identity, None, source['name'] + ': YouTube тимчасово не надав дані. Спробуйте пізніше'
            # The official API answers several channels at once without trouble; the public pages are read one channel
            # at a time, YouTube stops answering an address that asks too fast.
            pool = concurrent.futures.ThreadPoolExecutor(max_workers=6) if has_key else None
            try:
                for identity, entry, error in (pool.map(one, stale) if pool else map(one, stale)):
                    if entry is not None:
                        cache[identity] = entry
                        store.atomic_json(cache_path(), cache)
                    else:
                        with LOCK: ERRORS.append(error)
            finally:
                if pool: pool.shutdown()
            try:
                used = used_video_ids()
                visible = [video for identity, entry in cache.items() if identity in linked for video in rank(entry['videos'], time.time()) if video['id'] not in used]
                trending_titles.update(visible)
            except Exception:
                with LOCK: ERRORS.append('Не вдалося перекласти заголовки. Натисніть ↻, щоб повторити')
            finally:
                store.atomic_json(cache_path(), trending_titles.decorate(cache))
            if API_NOTE:
                with LOCK: ERRORS.append(API_NOTE[0])
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
    import episode_ideas as ideas
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
               'request_id': request_id, 'use_thumbnail': use_thumbnail, 'use_hero':body.get('use_hero')}
    receipt = store.DATA_ROOT / 'trending-idea-requests' / (request_id+'.json')
    def replay():
        return idea_reference.start_openings(cid, payload, source={'id': identity, 'title': title}, receipt_path=receipt)
    with ideas.LOCK:
        if store.read_json(receipt, {}).get('project_id'):
            return replay()
        if identity in used_video_ids():
            raise store.StudioError('Цю ідею вже використано для випуску. Оновіть добірку.', 409)
    linked, cache = sources(), store.read_json(cache_path(), {})
    source = next(({'id': identity, 'title': v['title'], 'url': 'https://www.youtube.com/watch?v='+identity,
                    'author': entry['name']} for competitor, entry in cache.items() if competitor in linked
                   for v in entry.get('videos', []) if v.get('id') == identity), None)
    if source is None:
        raise store.StudioError('Відео вже немає у збереженій добірці. Оновіть сторінку.', 404)
    if use_thumbnail:
        source = idea_reference.inspect(cid, source['url'])
    with ideas.LOCK:
        # Another tab may have created the same idea while the reference was loading.
        if store.read_json(receipt, {}).get('project_id'):
            return replay()
        if identity in used_video_ids():
            raise store.StudioError('Цю ідею вже використано для випуску. Оновіть добірку.', 409)
        return idea_reference.start_openings(cid, payload, source=source, receipt_path=receipt)
