"""Explicit private Fish voice creation. Never synthesize or retry an upload here."""
import json
import re
import urllib.request
import urllib.error
import languages
import store


class Rejected(store.StudioError):
    pass


def create(source, text, name, secret):
    body,mime=languages.multipart({'title':name[:90], 'type':'tts', 'visibility':'private',
        'train_mode':'fast', 'enhance_audio_quality':'false', 'generate_sample':'false', 'texts':text},
        [('voices',source,'audio/mpeg')])
    request=urllib.request.Request(languages.FISH+'/model',data=body,
        headers={'Authorization':'Bearer '+secret,'Content-Type':mime},method='POST')
    try:
        with urllib.request.urlopen(request,timeout=240) as response:result=json.load(response)
    except urllib.error.HTTPError as error:
        try:
            detail=json.loads(error.read(4096))
            detail=str(detail.get('message') or detail.get('detail') or detail.get('error') or '')
        except (ValueError,AttributeError):detail=''
        detail=re.sub(r'https?://\S+','[посилання]',detail.replace(secret,'[ключ]'))[:250]
        kind=Rejected if 400<=error.code<500 else store.StudioError
        raise kind(f'Fish Audio: помилка {error.code}. {detail} Автоматичного повтору немає.') from None
    voice_id=result.get('_id') or result.get('id')
    if not isinstance(voice_id,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}',voice_id):
        raise store.StudioError('Fish не повернув ID голосу. Перевірте результат у кабінеті сервісу')
    return voice_id
