"""HeyGen v3 audio only. Explicit model choice, no paid fallback or automatic synthesis retries."""
import json
import os
import urllib.request
import urllib.error
import urllib.parse
import credentials
import store

API='https://api.heygen.com'
MODELS={'heygen-voice-1':'HeyGen Voice 1','heygen-voice-1-turbo':'HeyGen Voice Turbo','heygen-voice-1-turbo-free':'HeyGen Voice Turbo Free'}
RATES={'heygen-voice-1':30/1000000,'heygen-voice-1-turbo':15/1000000,'heygen-voice-1-turbo-free':0}

def key():
    secret=os.environ.get('HEYGEN_API_KEY')
    if secret:return secret
    try:return credentials.vault().read(credentials.service_name('heygen'))
    except RuntimeError:raise store.StudioError('Додайте ключ HeyGen у загальних налаштуваннях студії') from None

def call(path,body=None):
    data=json.dumps(body).encode() if body is not None else None
    request=urllib.request.Request(API+path,data=data,headers={'X-Api-Key':key(),'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=240) as response:return json.load(response)
    except urllib.error.HTTPError as error:
        # Never include credential-bearing headers or a returned download URL in errors.
        messages={401:'Перевірте ключ HeyGen',402:'Недостатньо коштів HeyGen',403:'Ключ HeyGen не має доступу',429:'Ліміт HeyGen. Спробуйте пізніше; платного повтору не буде'}
        raise store.StudioError(messages.get(error.code,f'HeyGen: помилка {error.code}. Автоматичного повтору немає')) from None

def voices():
    call('/v3/users/me')
    result=[]
    for kind in ['private','public']:
        token=None
        for _ in range(10):
            query={'type':kind,'limit':100}
            if token:query['token']=token
            page=call('/v3/models/audio/voices?'+urllib.parse.urlencode(query))
            for row in page.get('data') or []:
                if row.get('status')=='ACTIVE':result.append({k:row.get(k) for k in ['voice_id','name','mode','language']})
            token=page.get('next_token')
            if not page.get('has_more') or not token:break
    return {'voices':result}

def synthesize(settings):
    if not settings.get('heygen_voice_id'):raise store.StudioError('Виберіть голос HeyGen')
    voice=call('/v3/models/audio/voices/'+urllib.parse.quote(settings['heygen_voice_id'],safe='')).get('data') or {}
    if voice.get('status')!='ACTIVE':raise store.StudioError('Голос HeyGen ще не готовий')
    if settings['heygen_model']!='heygen-voice-1' and voice.get('mode')=='professional':
        raise store.StudioError('Turbo підтримує instant-голоси. Виберіть HeyGen Voice 1 для professional-голосу')
    payload={'model':settings['heygen_model'],'voice_id':settings['heygen_voice_id'],
        'text':settings['text'],'language':settings['language'],
        'output_format':{'encoding':'mp3','sample_rate_hertz':44100,'bitrate_bps':128000}}
    if voice.get('mode')!='professional':payload['expressiveness_boost']=.5
    result=call('/v3/models/audio/tts',payload)
    url=(result.get('data') or {}).get('audio_url')
    if not isinstance(url,str) or urllib.parse.urlparse(url).scheme!='https':raise store.StudioError('HeyGen не повернув аудіофайл')
    with urllib.request.urlopen(url,timeout=120) as response:
        audio=response.read(100*1024*1024+1)
    if len(audio)>100*1024*1024:raise store.StudioError('Аудіофайл HeyGen завеликий')
    return audio
