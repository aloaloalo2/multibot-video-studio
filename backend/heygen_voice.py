"""HeyGen v3 audio only. Explicit model choice, no paid fallback or automatic synthesis retries."""
import json
import os
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
_SYNTHESIS_SLOT=threading.Lock()
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

@job_timing.measure('service')
def call(path,body=None,*,idempotency_key=None):
    data=json.dumps(body).encode() if body is not None else None
    headers={'X-Api-Key':key(),'Content-Type':'application/json'}
    if idempotency_key:headers['Idempotency-Key']=idempotency_key
    request=urllib.request.Request(API+path,data=data,headers=headers)
    try:
        with urllib.request.urlopen(request,timeout=240) as response:return json.load(response)
    except urllib.error.HTTPError as error:
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

def ready_voice(path, *, status_optional=False):
    deadline=time.monotonic()+VOICE_READY_TIMEOUT
    delay=2
    while True:
        voice=call(path).get('data') or {}
        status=voice.get('status')
        if status=='ACTIVE' or (status_optional and status is None and voice):
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
        time.sleep(min(delay,remaining))
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
    with _SYNTHESIS_SLOT:
        result=call('/v3/models/audio/tts',payload)
    url=(result.get('data') or {}).get('audio_url')
    if not isinstance(url,str) or urllib.parse.urlparse(url).scheme!='https':raise store.StudioError('HeyGen не повернув аудіофайл')
    with urllib.request.urlopen(url,timeout=120) as response:
        audio=response.read(100*1024*1024+1)
    if len(audio)>100*1024*1024:raise store.StudioError('Аудіофайл HeyGen завеликий')
    return audio


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
    with _SYNTHESIS_SLOT:
        result=call('/v3/voices/speech',payload)
    url=(result.get('data') or {}).get('audio_url')
    if not isinstance(url,str) or urllib.parse.urlparse(url).scheme!='https':raise store.StudioError('HeyGen не повернув аудіофайл')
    with urllib.request.urlopen(url,timeout=120) as response:audio=response.read(100*1024*1024+1)
    if len(audio)>100*1024*1024:raise store.StudioError('Аудіофайл HeyGen завеликий')
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
