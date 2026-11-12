"""Channel-local saved YouTube competitors; public identity lookup only."""
import base64
import io
import json
import re
import urllib.parse
import urllib.request

from PIL import Image, ImageOps
import store
from idea_reference import NoRedirect

CHANNEL_ID = re.compile(r'UC[A-Za-z0-9_-]{22}')


def channel_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise store.StudioError('Вставте посилання на канал YouTube')
    value = value.strip()
    if not re.match(r'^https?://', value): value = 'https://' + value
    try:
        parsed = urllib.parse.urlsplit(value)
        valid = parsed.scheme in ('https', 'http') and parsed.hostname in ('youtube.com', 'www.youtube.com', 'm.youtube.com') and not parsed.username and not parsed.password and parsed.port in (None, 80, 443)
    except ValueError:
        valid = False
    if not valid:
        raise store.StudioError('Потрібне посилання на канал YouTube')
    parts = urllib.parse.unquote(parsed.path).strip('/').split('/')
    if parts and parts[-1] in ('videos', 'shorts', 'streams', 'featured', 'about', 'playlists'): parts.pop()
    if len(parts) == 1 and re.fullmatch(r'@[\w.\-]{1,100}', parts[0]):
        path = urllib.parse.quote(parts[0], safe='@.-')
    elif len(parts) == 2 and parts[0] in ('channel', 'c', 'user') and re.fullmatch(r'[\w.\-]{1,100}', parts[1]):
        if parts[0] == 'channel' and not CHANNEL_ID.fullmatch(parts[1]):
            raise store.StudioError('Некоректний ідентифікатор каналу YouTube')
        path = '/'.join(urllib.parse.quote(p, safe='.-') for p in parts)
    else:
        raise store.StudioError('Вставте посилання на канал, наприклад youtube.com/@channel')
    return 'https://www.youtube.com/' + path


def download(url, limit):
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'en-US,en;q=0.9'})
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=15) as response:
        raw = response.read(limit + 1)
    if len(raw) > limit: raise store.StudioError('Відповідь YouTube завелика', 502)
    return raw


def inspect(url):
    url = channel_url(url)
    try:
        text = download(url + '?hl=en', 6 * 1024 * 1024).decode('utf-8')
        match = re.search(r'(?:var\s+ytInitialData|window\["ytInitialData"\]|ytInitialData)\s*=\s*', text)
        if not match: raise ValueError('No channel metadata')
        data, _ = json.JSONDecoder().raw_decode(text[match.end():])
        metadata = data.get('metadata', {}).get('channelMetadataRenderer', {})
        name, identity = metadata.get('title'), metadata.get('externalId')
        if not isinstance(name, str) or not name.strip() or not isinstance(identity, str) or not CHANNEL_ID.fullmatch(identity):
            raise ValueError('No channel identity')
        thumbnails = metadata.get('avatar', {}).get('thumbnails', [])
        avatar = thumbnails[-1]['url']
        image_url = urllib.parse.urlsplit(avatar)
        if image_url.scheme != 'https' or image_url.hostname not in ('yt3.ggpht.com', 'yt3.googleusercontent.com') or image_url.username or image_url.password or image_url.port not in (None, 443):
            raise ValueError('Invalid avatar host')
        with Image.open(io.BytesIO(download(avatar, 2 * 1024 * 1024))) as source:
            if source.width * source.height > 16_000_000: raise ValueError('Avatar too large')
            image = ImageOps.exif_transpose(source).convert('RGB')
            image.thumbnail((160, 160))
            output = io.BytesIO()
            image.save(output, format='PNG')
        icon = 'data:image/png;base64,' + base64.b64encode(output.getvalue()).decode('ascii')
        return {'id': identity, 'name': name.strip()[:300], 'url': 'https://www.youtube.com/channel/' + identity, 'source_url': url, 'icon_url': icon}
    except store.StudioError:
        raise
    except Exception:
        raise store.StudioError('Не вдалося отримати назву й логотип каналу з YouTube. Перевірте посилання та спробуйте ще раз.', 502) from None


def path(cid):
    store.get_channel_folder(cid)
    return store.DATA_ROOT / 'channels' / cid / 'competitors.json'


def read(cid):
    rows = store.read_json(path(cid), {}).get('competitors', [])
    if not isinstance(rows, list): raise store.StudioError('Пошкоджений список конкурентів')
    return rows


def add(cid, url):
    canonical = channel_url(url)
    with store.LOCK:
        for row in read(cid):
            if canonical in (row.get('url'), row.get('source_url')): return {'competitors': read(cid)}
    item = inspect(canonical)
    with store.LOCK:
        rows = read(cid)
        if not any(row['id'] == item['id'] for row in rows):
            if len(rows) >= 50: raise store.StudioError('Можна зберегти до 50 конкурентів')
            rows.append(item)
            store.atomic_json(path(cid), {'competitors': rows})
    return {'competitors': rows}


def remove(cid, identity):
    if not CHANNEL_ID.fullmatch(identity): raise store.StudioError('Конкурента не знайдено', 404)
    with store.LOCK:
        rows = [row for row in read(cid) if row['id'] != identity]
        store.atomic_json(path(cid), {'competitors': rows})
    return {'competitors': rows}
