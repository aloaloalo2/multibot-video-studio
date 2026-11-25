"""Read the connected workspace's private HeyGen avatars and looks."""

from urllib.parse import quote, urlencode, urlsplit

import heygen_voice
from studio_errors import StudioError


def page(group_id=None, token=None):
    params = {'ownership': 'private', 'limit': 24}
    if group_id:
        params['group_id'] = group_id
    if token:
        params['token'] = token
    path = '/v3/avatars/looks' if group_id else '/v3/avatars'
    result = _read(f'{path}?{urlencode(params)}')
    if not isinstance(result, dict) or not isinstance(result.get('data'), list):
        raise StudioError('HeyGen повернув невідомий формат списку аватарів.', 502)
    items = []
    for row in result['data']:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id']:
            continue
        if row.get('ownership') == 'public' or (group_id and row.get('group_id') != group_id):
            continue
        items.append(_avatar(row))
    next_token = result.get('next_token')
    return {'items': items, 'next_token': next_token if result.get('has_more') and isinstance(next_token, str) and next_token != token else None}


def group(group_id):
    result = _read(f'/v3/avatars/{quote(group_id, safe="")}')
    row = result.get('data') if isinstance(result, dict) else None
    if not isinstance(row, dict) or row.get('id') != group_id:
        raise StudioError('HeyGen не повернув дані вибраного аватара.', 502)
    return _avatar(row)


def engines(look_id):
    """The API engines HeyGen offers for a look (avatar_iii, avatar_iv, …)."""
    result = _read(f'/v3/avatars/looks/{quote(look_id, safe="")}')
    row = result.get('data') if isinstance(result, dict) else None
    if not isinstance(row, dict) or row.get('id') != look_id:
        raise StudioError('HeyGen не підтвердив вибраний образ аватара.', 502)
    found = row.get('supported_api_engines')
    if not isinstance(found, list):
        raise StudioError('HeyGen не повідомив, чи підтримує цей образ Avatar III.', 502)
    return found


def supports_avatar_iii(look_id):
    return 'avatar_iii' in engines(look_id)


def _read(path):
    try:
        return heygen_voice._call(path, timeout=12)
    except heygen_voice.RateLimited:
        raise StudioError('HeyGen тимчасово обмежив запити. Спробуйте трохи пізніше.', 429) from None
    except (heygen_voice.Gateway, heygen_voice.NotSent, heygen_voice.Lost, ValueError):
        raise StudioError('Не вдалося завантажити аватари з HeyGen.', 502) from None


def _avatar(row):
    return {'id': row['id'], 'name': row.get('name') if isinstance(row.get('name'), str) else '',
            'preview_image_url': _preview_url(row.get('preview_image_url'))}


def _preview_url(value):
    if not isinstance(value, str):
        return None
    try:
        url = urlsplit(value)
        if url.scheme == 'https' and url.hostname and not url.username and not url.password:
            return value
    except ValueError:
        pass
    return None


# What a minute of Avatar III video costs through the API, by the look's kind (user, 25 November 2026: «одну ціну»):
# a digital twin, made from a recording of a real person, $0.60; a photo or studio avatar $0.99. The kind is asked of
# HeyGen once a look and kept, so the estimate costs no request after that.
RATES = {'digital_twin': 0.60, 'photo_avatar': 0.99, 'studio_avatar': 0.99}


def _kinds_path():
    import store
    return store.DATA_ROOT / 'heygen-avatar-kinds.json'


def look_rate(look_id):
    """{'avatar_type', 'usd_per_minute'} of a look; an unknown kind is priced as a photo avatar, the dearer one."""
    import store
    kinds = store.read_json(_kinds_path(), {}) or {}
    kind = kinds.get(look_id)
    if not kind:
        result = _read(f'/v3/avatars/looks/{quote(look_id, safe="")}')
        row = result.get('data') if isinstance(result, dict) else None
        kind = row.get('avatar_type') if isinstance(row, dict) and isinstance(row.get('avatar_type'), str) else ''
        if kind:
            kinds[look_id] = kind
            store.atomic_json(_kinds_path(), kinds)
    twin = 'twin' in kind or kind in {'video_avatar', 'instant_avatar'}
    rate = RATES['digital_twin'] if twin else RATES.get(kind, RATES['photo_avatar'])
    return {'avatar_type': kind or None, 'usd_per_minute': rate}


def known_rate(look_id):
    """The per-minute rate of a look whose kind the studio already knows (from the estimate), else None; asks nothing."""
    import store
    kind = (store.read_json(_kinds_path(), {}) or {}).get(look_id)
    if not kind:
        return None
    twin = 'twin' in kind or kind in {'video_avatar', 'instant_avatar'}
    return RATES['digital_twin'] if twin else RATES.get(kind, RATES['photo_avatar'])


# Avatar IV a minute through the API (platform.heygen.com/pricing, 25 November 2026): it takes a motion prompt
RATES_IV = {'digital_twin': 4.83, 'photo_avatar': 2.31, 'studio_avatar': 4.83}


def known_rate_iv(look_id):
    import store
    kind = (store.read_json(_kinds_path(), {}) or {}).get(look_id)
    if not kind:
        return None
    twin = 'twin' in kind or kind in {'video_avatar', 'instant_avatar'}
    return RATES_IV['digital_twin'] if twin else RATES_IV.get(kind, RATES_IV['photo_avatar'])


def cached_photo(channel_id, group_id):
    """The chosen avatar's picture kept in the channel's data (user, 25 November 2026: «постійно підгружається… в кеш
    зберегти»): read from HeyGen once a look, then served from disk."""
    import re
    import urllib.request
    import store
    if not isinstance(group_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{4,80}', group_id):
        raise StudioError('Невірний аватар', 400)
    folder = store.DATA_ROOT / 'channels' / channel_id
    target = folder / f'heygen-avatar-{group_id}.jpg'
    if target.is_file() and target.stat().st_size:
        return target
    url = group(group_id).get('preview_image_url')
    if not url:
        raise StudioError('У аватара HeyGen немає фото', 404)
    folder.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix('.part')
    with urllib.request.urlopen(url, timeout=30) as response, part.open('wb') as out:
        out.write(response.read(20_000_000))
    part.replace(target)
    for old in folder.glob('heygen-avatar-*.jpg'):   # a former avatar's picture goes
        if old != target:
            old.unlink(missing_ok=True)
    return target
