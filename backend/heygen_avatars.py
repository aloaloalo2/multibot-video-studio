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


def supports_avatar_iii(look_id):
    result = _read(f'/v3/avatars/looks/{quote(look_id, safe="")}')
    row = result.get('data') if isinstance(result, dict) else None
    if not isinstance(row, dict) or row.get('id') != look_id:
        raise StudioError('HeyGen не підтвердив вибраний образ аватара.', 502)
    engines = row.get('supported_api_engines')
    if not isinstance(engines, list):
        raise StudioError('HeyGen не повідомив, чи підтримує цей образ Avatar III.', 502)
    return 'avatar_iii' in engines


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
