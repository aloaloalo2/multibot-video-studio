"""HeyGen v3 audio only. Explicit model choice, no paid fallback or automatic synthesis retries."""
import json
import os
import socket
import urllib.request
import urllib.error
import urllib.parse
import threading
import time
import credentials
import store
import job_timing

API='https://api.heygen.com'
DEFAULT_MODEL='heygen-voice-1-turbo-free'
# One phrase at a time again: two at once made HeyGen answer 429 until two narrations stopped (16 November 2026,
# user: «хейген не сильно любить багато запросів»). The worker pool stays, sized by SLOTS.
SLOTS=1
_SYNTHESIS_SLOT=threading.BoundedSemaphore(SLOTS)
SLOT_WAIT=600   # longest wait in the queue for HeyGen before a phrase gives up with a clear note


class synthesis_slot:
    """At most SLOTS phrases at a time go to HeyGen. The queue listens for «Зупинити» and never waits forever: four voicings
    froze for 20 minutes behind one stuck phrase and could not be cancelled (user, 16 November 2026: «ру також завис»)."""
    def __enter__(self):
        waited=0.0
        while not _SYNTHESIS_SLOT.acquire(timeout=1):
            stop_point()
            waited+=1
            if waited>=SLOT_WAIT:
                raise store.StudioError('HeyGen довго зайнятий іншою фразою. Зроблені фрази збережено, продовжіть пізніше')
        return self

    def __exit__(self,*exc):
        _SYNTHESIS_SLOT.release()
        return False
# Whole narrations, the original's and every translation's, take HeyGen in turn, first come first served (user,
# 16 November 2026: «хай встають в чергу просто хай пише озвучка в черзі… в перекладах теж»). Ten narrations at once
# used to fight for the one phrase slot in random order, and a phrase that waited over SLOT_WAIT stopped its narration.
# Samples do not queue: they are short and share only the phrase slot.
JOB_QUEUE=[]
JOB_TURN=threading.Condition()


def queue_wait(owner,waiting=None):
    """Wait until `owner` is first in the narration queue. `waiting(ahead)` hears how many narrations are ahead whenever
    that changes; a stop (STOP.check) leaves the queue at once."""
    with JOB_TURN:
        if owner not in JOB_QUEUE:JOB_QUEUE.append(owner)
    told=None
    try:
        while True:
            with JOB_TURN:ahead=JOB_QUEUE.index(owner)
            if ahead==0:return
            if waiting and ahead!=told:waiting(ahead)
            told=ahead
            stop_point()
            with JOB_TURN:JOB_TURN.wait(1)
    except BaseException:
        queue_leave(owner);raise


def queue_leave(owner):
    with JOB_TURN:
        if owner in JOB_QUEUE:JOB_QUEUE.remove(owner)
        JOB_TURN.notify_all()


def queue_ahead(owner):
    """How many narrations wait before `owner`, or None when it is not queued."""
    with JOB_TURN:
        return JOB_QUEUE.index(owner) if owner in JOB_QUEUE else None


VOICE_READY_TIMEOUT=120
MODELS={'heygen-voice-1':'HeyGen Voice 1','heygen-voice-1-turbo':'HeyGen Voice Turbo','heygen-voice-1-turbo-free':'HeyGen Voice Turbo Free','starfish':'Starfish'}
RATES={'heygen-voice-1':30/1000000,'heygen-voice-1-turbo':15/1000000,'heygen-voice-1-turbo-free':0}
STARFISH_PER_MINUTE=.12
# Duration estimate only: actual Starfish charges depend on generated audio length.
RATES['starfish']=STARFISH_PER_MINUTE/900

def estimate(settings):
    text=settings['text']
    if settings['heygen_model']=='starfish':
        import re, html
        if settings.get('heygen_starfish_ssml'):text=html.unescape(re.sub(r'<[^>]*>','',text))
        return {'unit':'usd','amount':len(text)*RATES['starfish']/settings.get('heygen_starfish_speed',1.),'estimated':True,'per_minute':STARFISH_PER_MINUTE}
    return {'unit':'usd','amount':len(text)*RATES[settings['heygen_model']]}

def key():
    secret=os.environ.get('HEYGEN_API_KEY')
    if secret:return secret
    try:return credentials.vault().read(credentials.service_name('heygen'))
    except RuntimeError:raise store.StudioError('Додайте ключ HeyGen у загальних налаштуваннях студії') from None

RETRY_AFTER=15   # seconds before the one automatic repeat of a gateway error
GATEWAY={502,503,504}
# HeyGen allows 30 speech requests a minute per account (developers.heygen.com, generate-model-speech). Every narration of
# the studio, original or translated, shares one key, so they share one budget: a little under the limit, spread over a
# sliding minute. This replaced the one-project-at-a-time queue of HeyGen narrations (user, 14 November 2026).
SPEECH_PATHS=('/v3/models/audio/tts','/v3/voices/speech')
SPEECH_PER_MINUTE=28
SPEECH_SENT=[]
SPEECH_LOCK=threading.Lock()
RATE_LIMIT_WAITS=4      # 429 answers waited out in a row before the narration stops
RATE_LIMIT_MAX_WAIT=120

class Gateway(Exception):
    def __init__(self,code):self.code=code

class RateLimited(Exception):
    def __init__(self,seconds):self.seconds=seconds

class NotSent(Exception):
    """The request never reached HeyGen (the name did not resolve, the connection was refused): nothing was made or
    paid, so it is safe to send again (17 November 2026: a DNS blip stopped a narration at 104 of 127)."""

class Lost(Exception):
    """The connection broke or timed out after the request was sent: HeyGen may have made (and billed) it."""

NETWORK_RETRIES=3   # quiet repeats of a request that never left this Mac, RETRY_AFTER apart


def network_failure(error):
    reason=getattr(error,'reason',error)
    if isinstance(reason,(socket.gaierror,ConnectionRefusedError)) or 'nodename nor servname' in str(reason):
        return NotSent(str(reason))
    return Lost(str(reason))

# A narration's stop button is heard while a phrase waits here too: the worker sets STOP.check, which raises when the
# author pressed «Зупинити» (user, 15 November 2026: «Зупиняємо… не можу зупинити» while HeyGen made it wait minutes).
STOP=threading.local()


def stop_point():
    check=getattr(STOP,'check',None)
    if check:check()


def pause(seconds):
    """Sleep in steps of up to a second, listening for a stop (counted steps, so a frozen test clock cannot loop)."""
    left=max(0.0,float(seconds))
    while True:
        stop_point()
        if left<=0:return
        step=min(left,1.0);time.sleep(step);left-=step


def speech_turn(now=time.monotonic,sleep=time.sleep):
    """Wait until one more speech request fits into the shared minute, then count it. A wait counts as «Черга»."""
    import contextlib
    with contextlib.ExitStack() as waiting:
        queued=False
        while True:
            with SPEECH_LOCK:
                moment=now()
                while SPEECH_SENT and moment-SPEECH_SENT[0]>=60:SPEECH_SENT.pop(0)
                if len(SPEECH_SENT)<SPEECH_PER_MINUTE:
                    SPEECH_SENT.append(moment);return
                pause=60-(moment-SPEECH_SENT[0])+.05
            if not queued:waiting.enter_context(job_timing.span('queue'));queued=True
            stop_point()
            sleep(min(max(pause,.05),1))

@job_timing.measure('service')
def call(path,body=None,*,idempotency_key=None):
    # HeyGen's gateway sometimes answers 502/503/504 in the middle of a long narration (13 and 14 November 2026). Such an
    # answer carries no audio, so the same request is sent once more after 15 s (user: «один автоматичний повтор там через
    # 15 секунд»); any other error, or a second gateway error, stops as before. A 429 (over the limit) is waited out for
    # as long as HeyGen's Retry-After says, a few times in a row: nothing was made, so nothing is paid twice.
    speech=path.startswith(SPEECH_PATHS)
    # a lost answer may be repeated only where a second request costs nothing: a status read, or the free model
    free=not speech or (body or {}).get('model')=='heygen-voice-1-turbo-free'
    gateway_retried=False
    waits=network=0
    while True:
        if speech:speech_turn()
        try:return _call(path,body,idempotency_key=idempotency_key)
        except (NotSent,Lost) as error:
            if isinstance(error,Lost) and not free:
                raise store.StudioError('HeyGen не відповів після запиту, повтору не буде, щоб не заплатити двічі. Зроблені фрази збережено, продовжіть пізніше') from None
            network+=1
            if network>NETWORK_RETRIES:
                raise store.StudioError('Немає зв’язку з HeyGen кілька хвилин поспіль. Зроблені фрази збережено, продовжіть пізніше') from None
            pause(RETRY_AFTER*network)
        except RateLimited as limited:
            waits+=1
            if waits>RATE_LIMIT_WAITS:
                raise store.StudioError('Ліміт запитів HeyGen не відпускає кілька хвилин поспіль. Зроблені фрази збережено, продовжіть пізніше') from None
            with job_timing.span('queue'):   # HeyGen's limit is a wait, not its work: «Черга» in «Час роботи»
                pause(min(max(limited.seconds,5),RATE_LIMIT_MAX_WAIT))
        except Gateway as error:
            if gateway_retried:
                raise store.StudioError(f'HeyGen: помилка {error.code}, і повтор через {RETRY_AFTER} с теж не вдався. Зроблені фрази збережено, продовжіть пізніше') from None
            gateway_retried=True
            pause(RETRY_AFTER)

LIMIT_LOG_BYTES=512*1024


def note_limit(path,body,error,seconds):
    """One line per 429 in data/heygen-limits.jsonl: which model, HeyGen's own code and its Retry-After. Turbo Free
    shares a capacity with every free user and answers 429 below the account's 30 a minute (developers.heygen.com,
    heygen-voice-speech); on 17 November 2026 a Turbo Free narration waited 46 of its 51 minutes while paid Turbo of
    Космос PRO voiced 520 phrases in 26 minutes without one wait, and nothing recorded what HeyGen said."""
    try:
        code=None
        try:
            returned=json.loads(error.read(4096)).get('error',{})
            code=str(returned.get('code') or '')[:40] if isinstance(returned,dict) else None
        except (ValueError,TypeError,AttributeError,OSError):pass
        log=store.DATA_ROOT/'heygen-limits.jsonl'
        if log.is_file() and log.stat().st_size>LIMIT_LOG_BYTES:
            log.replace(log.with_suffix('.jsonl.1'))
        line={'at':round(time.time(),1),'path':path.split('?')[0][:60],'model':(body or {}).get('model'),'code':code,
              'retry_after':seconds or None}
        with open(log,'a',encoding='utf-8') as out:out.write(json.dumps(line)+'\n')
    except OSError:pass


def _call(path,body=None,*,idempotency_key=None):
    data=json.dumps(body).encode() if body is not None else None
    headers={'X-Api-Key':key(),'Content-Type':'application/json'}
    if idempotency_key:headers['Idempotency-Key']=idempotency_key
    request=urllib.request.Request(API+path,data=data,headers=headers)
    try:
        # a shorter wait for one answer: a stop is heard at the latest after it (was 240 s)
        with urllib.request.urlopen(request,timeout=90) as response:return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code in GATEWAY:raise Gateway(error.code) from None
        if error.code==429:
            try:seconds=float(error.headers.get('Retry-After') or 0)
            except (TypeError,ValueError):seconds=0
            note_limit(path,body,error,seconds)
            raise RateLimited(seconds or 20) from None
        # Retain the provider's validation reason, never credentials or download URLs.
        detail=''
        try:
            returned=json.loads(error.read(16384)).get('error',{})
            if isinstance(returned,dict):
                reason=str(returned.get('message') or '')[:600]
                param=str(returned.get('param') or '')[:80]
                import re
                reason=re.sub(r'https?://\S+','[посилання]',reason)
                reason=reason.replace(key(),'[ключ]')
                if param=='voice_id' and 'not compatible' in reason:
                    reason='Цей голос несумісний із вибраною моделлю. Натисніть «Створити голос із запису» для нового instant-клону.'
                detail=(' ('+param+')' if param else '')+(': '+reason if reason else '')
        except (ValueError,TypeError,AttributeError):pass
        messages={401:'Перевірте ключ HeyGen',402:'Недостатньо коштів HeyGen',403:'Ключ HeyGen не має доступу',429:'Ліміт HeyGen. Спробуйте пізніше; платного повтору не буде'}
        raise store.StudioError(messages.get(error.code,f'HeyGen: помилка {error.code}{detail}. Автоматичного повтору немає')) from None
    except (urllib.error.URLError,OSError) as error:   # no HTTP answer at all: see NotSent and Lost
        raise network_failure(error) from None


def download(url):
    """The finished audio, a free GET: repeated on a network failure, and checked against its Content-Length, since
    Python 3.9 returns a cut-off body without an error and a clipped take would be cached for good."""
    for attempt in range(1,NETWORK_RETRIES+1):
        try:
            with urllib.request.urlopen(url,timeout=120) as response:
                audio=response.read(100*1024*1024+1)
                headers=getattr(response,'headers',None)
                expected=headers.get('Content-Length') if headers is not None else None
            if len(audio)>100*1024*1024:raise store.StudioError('Аудіофайл HeyGen завеликий')
            if expected and expected.isdigit() and len(audio)!=int(expected):raise Lost(f'{len(audio)} of {expected} bytes')
            return audio
        except (urllib.error.URLError,OSError,Lost) as error:
            if attempt==NETWORK_RETRIES:
                raise store.StudioError('Не вдалося завантажити готовий звук HeyGen. Зроблені фрази збережено, продовжіть пізніше') from None
            pause(RETRY_AFTER*attempt)

def voices(model='heygen-voice-1'):
    if model not in MODELS:raise store.StudioError('Невідома модель HeyGen')
    call('/v3/users/me')
    result=[]
    for kind in ['private','public']:
        token=None
        for _ in range(10):
            query={'type':kind,'limit':100}
            if model=='starfish':query['engine']='starfish'
            if token:query['token']=token
            page=call(('/v3/voices?' if model=='starfish' else '/v3/models/audio/voices?')+urllib.parse.urlencode(query))
            for row in page.get('data') or []:
                if model=='starfish':
                    if 'starfish' in (row.get('available_engines') or []):result.append({k:row.get(k) for k in ['voice_id','name','language','support_locale','support_pause']})
                    continue
                if row.get('status')=='ACTIVE':result.append({k:row.get(k) for k in ['voice_id','name','mode','language']})
            token=page.get('next_token')
            if not page.get('has_more') or not token:break
    return {'voices':result}

READY={}          # voice path -> (time, voice) of a voice HeyGen called ready
READY_FOR=600     # seconds a ready voice is trusted without asking again


def ready_voice(path, *, status_optional=False):
    # a ready voice stays ready: asking HeyGen before every phrase doubled the requests its limit counts (17 November
    # 2026: narrations waited 17–51 minutes on 429 answers, while the voicing itself takes about 2 s a phrase)
    known=READY.get(path)
    if known and time.monotonic()-known[0]<READY_FOR:
        return known[1]
    deadline=time.monotonic()+VOICE_READY_TIMEOUT
    delay=2
    while True:
        voice=call(path).get('data') or {}
        status=voice.get('status')
        if status=='ACTIVE' or (status_optional and status is None and voice):
            READY[path]=(time.monotonic(),voice)
            return voice
        if status=='FAILED':
            reason=voice.get('failure_reason')
            messages={
                'INVALID_AUDIO':'HeyGen не зміг прочитати запис. Завантажте інший аудіофайл.',
                'PREPROCESSING_FAILED':'HeyGen не зміг підготувати запис. Додайте чіткіший приклад голосу.',
            }
            raise store.StudioError(messages.get(reason,'HeyGen не зміг створити цей голос. Виберіть інший голос або додайте новий приклад.'))
        if status!='PENDING':
            raise store.StudioError('HeyGen повернув невідомий статус голосу. Перевірте вибраний голос.')
        remaining=deadline-time.monotonic()
        if remaining<=0:
            raise store.StudioError('HeyGen усе ще готує голос. Повторіть спробу трохи пізніше з тим самим голосом.')
        pause(min(delay,remaining))
        delay=min(delay*2,8)


@job_timing.measure('service')
def synthesize(settings):
    if not settings.get('heygen_voice_id'):raise store.StudioError('Виберіть голос HeyGen')
    if settings['heygen_model']=='starfish':return synthesize_starfish(settings)
    voice=ready_voice('/v3/models/audio/voices/'+urllib.parse.quote(settings['heygen_voice_id'],safe=''))
    if settings['heygen_model']!='heygen-voice-1' and voice.get('mode')=='professional':
        raise store.StudioError('Turbo підтримує instant-голоси. Виберіть HeyGen Voice 1 для professional-голосу')
    payload={'model':settings['heygen_model'],'voice_id':settings['heygen_voice_id'],
        'text':settings['text'],'language':settings['language'],
        'output_format':{'encoding':'mp3','sample_rate_hertz':44100,'bitrate_bps':128000}}
    if voice.get('mode')!='professional':payload['expressiveness_boost']=settings.get('heygen_expressiveness',.5)
    with synthesis_slot():
        result=call('/v3/models/audio/tts',payload)
    url=(result.get('data') or {}).get('audio_url')
    if not isinstance(url,str) or urllib.parse.urlparse(url).scheme!='https':raise store.StudioError('HeyGen не повернув аудіофайл')
    return download(url)


def synthesize_starfish(settings):
    text=settings['text']
    if not 1<=len(text)<=5000:raise store.StudioError('Starfish приймає від 1 до 5000 символів за запит')
    if settings.get('heygen_starfish_ssml'):
        import xml.etree.ElementTree as ET
        try:ET.fromstring('<speak>'+text+'</speak>')
        except ET.ParseError:raise store.StudioError('Перевірте SSML: закрийте теги та запишіть & як &amp;') from None
    voice=ready_voice('/v3/voices/'+urllib.parse.quote(settings['heygen_voice_id'],safe=''),status_optional=True)
    if voice.get('available_engines') is not None and 'starfish' not in voice['available_engines']:
        raise store.StudioError('Виберіть сумісний голос у списку Starfish')
    payload={'voice_id':settings['heygen_voice_id'],'text':text,
             'speed':settings.get('heygen_starfish_speed',1.),'language':settings['language'],
             'input_type':'ssml' if settings.get('heygen_starfish_ssml') else 'text'}
    if settings.get('heygen_starfish_locale'):payload['locale']=settings['heygen_starfish_locale']
    with synthesis_slot():
        result=call('/v3/voices/speech',payload)
    url=(result.get('data') or {}).get('audio_url')
    if not isinstance(url,str) or urllib.parse.urlparse(url).scheme!='https':raise store.StudioError('HeyGen не повернув аудіофайл')
    audio=download(url)
    # Starfish can return WAV; the Studio's immutable raw cache stores real MP3.
    import tempfile
    from pathlib import Path
    import languages
    with tempfile.TemporaryDirectory() as tmp:
        source=Path(tmp)/'source.audio';target=Path(tmp)/'speech.mp3';source.write_bytes(audio)
        languages.run(['ffmpeg','-v','error','-nostdin','-y','-i',str(source),'-vn','-ar','44100','-ac','1','-b:a','128k',str(target)],'підготувати звук Starfish')
        return target.read_bytes()


def clone_instant(path, name, language, identity):
    import base64
    audio=path.read_bytes()
    if len(audio)>16*1024*1024:raise store.StudioError('Приклад голосу завеликий')
    result=call('/v3/models/audio/voices',{'mode':'instant','name':name[:64],
        'language':language,'remove_background_noise':False,
        'audio':[{'type':'base64','media_type':'audio/mpeg','data':base64.b64encode(audio).decode()}]},idempotency_key=identity)
    voice_id=(result.get('data') or {}).get('voice_id')
    if not voice_id:raise store.StudioError('HeyGen не повернув ID нового голосу')
    return voice_id
