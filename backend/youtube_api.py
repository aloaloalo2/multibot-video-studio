"""Competitor uploads through the official YouTube Data API v3 with the author's own key («Ключі сервісів»).

Read-only public data: a channel's name and subscribers, its latest uploads and each upload's views, date and length.
One channel costs up to seven quota units of the free 10 000 a day (channels.list 1, up to three pages of
playlistItems.list, up to three videos.list calls of 50 ids). The key never appears in logs or error messages.
"""
import datetime as dt
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import channel_competitors
import credentials
import store

BASE = 'https://www.googleapis.com/youtube/v3/'
DURATION = re.compile(r'P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?')


class ApiError(RuntimeError):
    """The key is missing, wrong or out of quota; the caller reads the public pages instead."""


def key():
    try:
        if credentials.vault().configured(credentials.service_name('youtube')) is not True:
            return None
        value = credentials.vault().read(credentials.service_name('youtube'))
    except RuntimeError:
        return None
    return value.strip() or None


def call(resource, secret, **params):
    url = BASE + resource + '?' + urllib.parse.urlencode({**params, 'key': secret})
    request = urllib.request.Request(url, headers={'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read(8 * 1024 * 1024))
    except urllib.error.HTTPError as error:
        try:
            detail = json.loads(error.read(65536)).get('error', {})
            reason = (detail.get('errors') or [{}])[0].get('reason') or detail.get('status') or ''
        except (ValueError, AttributeError):
            reason = ''
        if reason in ('quotaExceeded', 'dailyLimitExceeded', 'rateLimitExceeded'):
            raise ApiError('денний ліміт ключа вичерпано') from None
        if error.code in (400, 401, 403):
            raise ApiError('ключ не підходить або YouTube Data API v3 не ввімкнено для нього') from None
        raise ApiError('YouTube Data API відповів помилкою %d' % error.code) from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise ApiError('YouTube Data API не відповів') from None


def seconds(value):
    match = DURATION.fullmatch(value or '')
    if not match:
        return 0
    days, hours, minutes, secs = (int(part or 0) for part in match.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + secs


def stamp(value):
    date = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if date.tzinfo is None:
        date = date.replace(tzinfo=dt.timezone.utc)
    return date


def collect(identity, secret, previous=None):
    if not channel_competitors.CHANNEL_ID.fullmatch(identity):
        raise store.StudioError('Некоректний канал YouTube')
    data = call('channels', secret, part='snippet,statistics,contentDetails', id=identity)
    items = data.get('items') or []
    if not items:
        raise ValueError('Channel not found')
    channel = items[0]
    uploads = channel.get('contentDetails', {}).get('relatedPlaylists', {}).get('uploads')
    if not uploads:
        raise ValueError('Channel has no uploads list')
    now, ids, token, reached = time.time(), [], None, False
    # Up to 150 latest uploads, stopping once their dates pass 100 days (the selection compares the last 90).
    for _ in range(3):
        page = call('playlistItems', secret, part='contentDetails', playlistId=uploads, maxResults=50,
                    **({'pageToken': token} if token else {}))
        for item in page.get('items', []):
            details = item.get('contentDetails', {})
            published = details.get('videoPublishedAt')
            if not details.get('videoId') or not published:
                continue
            if now - stamp(published).timestamp() > 100 * 86400:
                reached = True
                continue
            ids.append(details['videoId'])
        token = page.get('nextPageToken')
        if reached or not token:
            break
    truncated = bool(token) and not reached
    videos, skipped = [], []
    for start in range(0, len(ids), 50):
        batch = ids[start:start + 50]
        page = call('videos', secret, part='snippet,contentDetails,statistics', id=','.join(batch), maxResults=50)
        for item in page.get('items', []):
            snippet, stats = item.get('snippet', {}), item.get('statistics', {})
            length = seconds(item.get('contentDetails', {}).get('duration'))
            if snippet.get('liveBroadcastContent', 'none') != 'none' or 'viewCount' not in stats or not length:
                skipped.append(item.get('id'))   # live, upcoming, members-only or unfinished
                continue
            date = stamp(snippet['publishedAt'])
            videos.append({'id': item['id'], 'title': snippet.get('title', ''), 'published_at': date.isoformat(),
                           'published_ts': date.timestamp(), 'views': int(stats['viewCount']), 'duration': length,
                           'fetched_at': time.time()})
    if not videos and not ids:
        raise ValueError('No public channel videos found')
    subscribers = channel.get('statistics', {}).get('subscriberCount')
    return {'name': channel.get('snippet', {}).get('title', ''), 'subscribers': int(subscribers) if subscribers is not None else None,
            'updated_at': time.time(), 'videos': videos, 'sample_truncated': truncated, 'failed_videos': 0,
            'failed_video_ids': [], 'skipped_videos': len(skipped), 'skipped_video_ids': skipped,
            'pagination_incomplete': False, 'source': 'youtube-api'}
