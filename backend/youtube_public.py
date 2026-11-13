"""Read public YouTube metadata without an account, API key or media download."""
import concurrent.futures
import datetime as dt
import json
import re
import time
import urllib.request

import channel_competitors
import store
from idea_reference import NoRedirect

VIDEO_ID = re.compile(r'[A-Za-z0-9_-]{11}')
VIDEO_TTL = 6 * 3600


class SkippedVideo(ValueError):
    """Known non-public or unfinished content is outside the public trend feed."""


def embedded(raw, name):
    match = re.search(r'(?:var\s+' + name + r'|window\["' + name + r'"\]|' + name + r')\s*=\s*', raw)
    if not match: raise ValueError('Public YouTube metadata unavailable')
    value, _ = json.JSONDecoder().raw_decode(raw[match.end():])
    return value


def walk(value, name):
    if isinstance(value, dict):
        if name in value: yield value[name]
        for child in value.values(): yield from walk(child, name)
    elif isinstance(value, list):
        for child in value: yield from walk(child, name)


def text(value):
    if isinstance(value, str): return value
    if not isinstance(value, dict): return ''
    return value.get('simpleText') or value.get('content') or ''.join(r.get('text','') for r in value.get('runs',[]))


def count(value):
    match = re.search(r'([\d,.\s]+)\s*(billion|million|thousand|[KMB])?', value, re.I)
    if not match: return None
    number = match[1].strip().replace(' ','').replace(',','')
    multiplier = {'k':1000,'thousand':1000,'m':1000000,'million':1000000,'b':1000000000,'billion':1000000000}.get((match[2] or '').lower(),1)
    try:return round(float(number)*multiplier)
    except ValueError:return None


def age_days(value):
    match = re.search(r'(\d+)\s*(second|minute|hour|day|week|month|year)', value, re.I)
    if not match:return None
    return int(match[1])*{'second':1/86400,'minute':1/1440,'hour':1/24,'day':1,'week':7,'month':30,'year':365}[match[2].lower()]


def cards(data):
    result=[]
    for video in walk(data,'lockupViewModel'):
        identity=video.get('contentId','')
        if not VIDEO_ID.fullmatch(identity) or video.get('contentType')!='LOCKUP_CONTENT_TYPE_VIDEO':continue
        metadata=video.get('metadata',{}).get('lockupMetadataViewModel',{})
        labels=[p.get('accessibilityLabel') or text(p.get('text')) for row in metadata.get('metadata',{}).get('contentMetadataViewModel',{}).get('metadataRows',[]) for p in row.get('metadataParts',[])]
        age=next((age_days(v) for v in labels if age_days(v) is not None),None)
        result.append({'id':identity,'age':age})
    for video in walk(data,'videoRenderer'):
        identity=video.get('videoId','')
        if VIDEO_ID.fullmatch(identity):result.append({'id':identity,'age':age_days(text(video.get('publishedTimeText')))})
    return list({v['id']:v for v in result}.values())


def page(url):
    return channel_competitors.download(url, 10*1024*1024).decode('utf-8')


def video(identity, expected_channel):
    raw=page('https://www.youtube.com/watch?v='+identity+'&hl=en')
    data=embedded(raw,'ytInitialPlayerResponse')
    playability=data.get('playabilityStatus',{})
    offer=playability.get('errorScreen',{}).get('playerLegacyDesktopYpcOfferRenderer',{})
    reason=str(playability.get('reason') or '').lower()
    if offer.get('offerId')=='sponsors_only_video' or any(term in reason for term in ('members-only','channel\'s members','private video','video has been removed','video is no longer available')):
        raise SkippedVideo('Restricted public video')
    details=data.get('videoDetails',{})
    micro=data.get('microformat',{}).get('playerMicroformatRenderer',{})
    if details.get('isLive') or details.get('isUpcoming') or playability.get('status')=='LIVE_STREAM_OFFLINE':
        raise SkippedVideo('Live or upcoming video')
    if details.get('videoId')!=identity or details.get('channelId')!=expected_channel:
        raise ValueError('Unavailable public video')
    published=micro.get('publishDate') or micro.get('uploadDate')
    if not published or not details.get('lengthSeconds') or 'viewCount' not in details:
        raise ValueError('Incomplete public video metadata')
    date=dt.datetime.fromisoformat(published.replace('Z','+00:00'))
    if date.tzinfo is None:date=date.replace(tzinfo=dt.timezone.utc)
    return {'id':identity,'title':details['title'],'published_at':date.isoformat(),'published_ts':date.timestamp(),
            'views':int(details['viewCount']),'duration':int(details['lengthSeconds']),'fetched_at':time.time()}


def continuation(token, context):
    raw=json.dumps({'context':context,'continuation':token}).encode()
    request=urllib.request.Request('https://www.youtube.com/youtubei/v1/browse?prettyPrint=false',data=raw,headers={'Content-Type':'application/json','User-Agent':'Mozilla/5.0','Accept-Language':'en-US,en;q=0.9'})
    with urllib.request.build_opener(NoRedirect()).open(request,timeout=20) as response:
        raw=response.read(10*1024*1024+1)
    if len(raw)>10*1024*1024:raise ValueError('Response too large')
    return json.loads(raw)


def collect(identity, previous=None):
    if not channel_competitors.CHANNEL_ID.fullmatch(identity):raise store.StudioError('Некоректний канал YouTube')
    raw=page('https://www.youtube.com/channel/'+identity+'/videos?hl=en')
    initial=embedded(raw,'ytInitialData')
    meta=initial.get('metadata',{}).get('channelMetadataRenderer',{})
    if meta.get('externalId')!=identity:raise ValueError('Channel identity mismatch')
    rows=cards(initial);pagination_failed=False
    current=initial
    # Up to 120 latest uploads, stopping once the displayed dates reach 90 days.
    for _ in range(3):
        if len(rows)>=120 or any(v['age'] is not None and v['age']>=90 for v in rows):break
        token=next((c.get('token') for c in walk(current,'continuationCommand') if c.get('token')),None)
        if not token:break
        context=None
        for cfg_match in re.finditer(r'ytcfg\.set\(\s*',raw):
            try:cfg,_=json.JSONDecoder().raw_decode(raw[cfg_match.end():])
            except ValueError:continue
            if isinstance(cfg,dict) and isinstance(cfg.get('INNERTUBE_CONTEXT'),dict):
                context=cfg['INNERTUBE_CONTEXT'];break
        if not context:break
        try:current=continuation(token,context)
        except Exception:
            pagination_failed=True;break
        rows=list({v['id']:v for v in rows+cards(current)}.values())
    candidates=[v for v in rows[:120] if v['age'] is None or v['age']<=100]
    if not rows:raise ValueError('No public channel videos found')
    previous=previous or {};known={v['id']:v for v in previous.get('videos',[]) if VIDEO_ID.fullmatch(v.get('id',''))}
    videos=[];failed=[];skipped=[]
    def fetch(item):
        saved=known.get(item['id'])
        if saved and time.time()-saved.get('fetched_at',previous.get('updated_at',0))<VIDEO_TTL:
            return ('ok',saved)
        try:return ('ok',video(item['id'],identity))
        except SkippedVideo:return ('skip',item['id'])
        except Exception:return ('failed',item['id'])
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for status,item in pool.map(fetch,candidates):
            if status=='ok':videos.append(item)
            elif status=='skip':skipped.append(item)
            else:
                failed.append(item)
                if item in known:videos.append(known[item])
    if candidates and not videos and failed:raise ValueError('Video metadata unavailable')
    if pagination_failed:
        present={v['id'] for v in videos}|set(skipped)
        videos.extend(v for key,v in known.items() if key not in present)
    subscribers=None
    header=initial.get('header',{})
    for value in walk(header,'content'):
        if isinstance(value,str) and re.search(r'\bsubscribers?\b',value,re.I):
            subscribers=count(value);break
    if subscribers is None:
        for value in walk(header,'subscriberCountText'):
            subscribers=count(text(value));break
    return {'name':meta['title'],'subscribers':subscribers,'updated_at':time.time(),'videos':videos,
            'sample_truncated':len(rows)>=120 and all(v['age'] is None or v['age']<90 for v in rows),
            'failed_videos':len(failed),'failed_video_ids':failed,'skipped_videos':len(skipped),'skipped_video_ids':skipped,
            'pagination_incomplete':pagination_failed,'source':'youtube-public'}
