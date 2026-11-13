"""Per-language channel narration choices and explicitly requested, cached samples."""
import copy
import hashlib
import json
import re
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path

import eleven_api
import heygen_voice
import language_defaults
import languages
import store
import voice_cache

LOCK=threading.RLock()
ACTIVE=set()
TEXTS={
 'uk':'Сьогодні розберемо це на простому прикладі. Зверніть увагу на деталі та послухайте, як звучить цей голос.',
 'ru':'Сегодня разберём это на простом примере. Обратите внимание на детали и послушайте, как звучит этот голос.',
 'en':'Today we will explore this with a simple example. Listen to the details and the natural rhythm of this voice.',
 'de':'Heute erklären wir das an einem einfachen Beispiel. Achten Sie auf die Details und den natürlichen Klang dieser Stimme.',
 'es':'Hoy lo explicaremos con un ejemplo sencillo. Presta atención a los detalles y escucha cómo suena esta voz.',
 'pl':'Dzisiaj wyjaśnimy to na prostym przykładzie. Zwróć uwagę na szczegóły i posłuchaj, jak brzmi ten głos.',
 'fr':'Nous allons expliquer cela avec un exemple simple. Écoutez les détails et le rythme naturel de cette voix.',
 'pt':'Hoje vamos explicar isso com um exemplo simples. Preste atenção aos detalhes e ouça como esta voz soa.',
 'it':'Oggi lo spiegheremo con un esempio semplice. Ascolta i dettagli e il ritmo naturale di questa voce.',
 'tr':'Bugün bunu basit bir örnekle açıklayacağız. Ayrıntılara dikkat edin ve bu sesin doğal ritmini dinleyin.',
 'nl':'Vandaag leggen we dit uit met een eenvoudig voorbeeld. Let op de details en luister naar het natuurlijke ritme van deze stem.',
 'hi':'आज हम इसे एक आसान उदाहरण से समझेंगे। ध्यान से सुनिए कि यह आवाज़ कितनी सहज लगती है।',
 'ar':'سنشرح اليوم هذا الأمر بمثال بسيط. استمع إلى التفاصيل وإلى الإيقاع الطبيعي لهذا الصوت.',
 'ja':'今日は簡単な例で説明します。この声の自然な響きとリズムを聞いてみてください。',
 'ko':'오늘은 간단한 예를 들어 설명하겠습니다. 이 목소리의 자연스러운 소리와 리듬을 들어 보세요.',
 'zh':'今天我们用一个简单的例子来说明。请仔细聆听这个声音的细节和自然节奏。',
 'id':'Hari ini kita akan menjelaskannya dengan contoh sederhana. Dengarkan detail dan irama alami suara ini.',
 'cs':'Dnes si to vysvětlíme na jednoduchém příkladu. Všímejte si detailů a poslechněte si přirozený rytmus tohoto hlasu.',
 'ro':'Astăzi vom explica acest lucru printr-un exemplu simplu. Ascultă detaliile și ritmul natural al acestei voci.',
 'kk':'Бүгін мұны қарапайым мысалмен түсіндіреміз. Осы дауыстың табиғи үні мен ырғағын тыңдап көріңіз.',
}


def options():
    return {'providers':[{'id':key,'name':value['name']} for key,value in languages.PROVIDERS.items()],
            'elevenlabs':[{'id':row['id'],'name':row['name']} for row in eleven_api.FALLBACK],
            'heygen':languages.heygen_models(),
            'fishaudio':[{'id':key,'name':row['name'],'default_style':languages.FISH_ENGINE_STYLES.get(key,languages.FISH_STYLE)} for key,row in languages.FISH_ENGINES.items()],
            'styles':[{'id':key,'name':row['name']} for key,row in languages.FISH_STYLES.items()]}


def choices(cid,code,raw=None):
    languages.check_code(code)
    if raw is not None and not isinstance(raw,dict):raise store.StudioError('Невірні налаштування голосу')
    saved={**language_defaults.settings(cid,code),**(raw or {})}
    provider=saved.get('provider','fishaudio');eleven=saved.get('eleven_engine',languages.ELEVEN_MODEL);fish=saved.get('fish_engine',languages.FISH_ENGINE)
    if not isinstance(saved.get('fish_styles',{}),dict):raise store.StudioError('Невірна подача Fish Audio')
    styles=dict(saved.get('fish_styles') or {});style=saved.get('fish_style') if raw and 'fish_style' in raw else styles.get(fish,saved.get('fish_style'))
    style=style or languages.FISH_ENGINE_STYLES.get(fish,languages.FISH_STYLE)
    if not all(isinstance(value,str) for value in (provider,eleven,fish,style)) or provider not in languages.PROVIDERS or eleven not in eleven_api.PRIORITY or fish not in languages.FISH_ENGINES or style not in languages.FISH_STYLES:
        raise store.StudioError('Невідомі сервіс, модель або подача голосу')
    if any(key not in languages.FISH_ENGINES or value not in languages.FISH_STYLES for key,value in styles.items()):raise store.StudioError('Невірна подача Fish Audio')
    styles[fish]=style
    model=saved.get('heygen_model',heygen_voice.DEFAULT_MODEL);voice_id=saved.get('heygen_voice_id','')
    if not isinstance(model,str) or model not in heygen_voice.MODELS or not isinstance(voice_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{0,128}',voice_id):
        raise store.StudioError('Невірна модель або ID голосу HeyGen')
    return {'provider':provider,'eleven_engine':eleven,'fish_engine':fish,'fish_style':style,'fish_styles':styles,
            'heygen_model':model,'heygen_voice_id':voice_id}


def save(cid,updates):
    store.get_channel_folder(cid)
    if not isinstance(updates,dict) or not updates:raise store.StudioError('Оберіть налаштування мови')
    with language_defaults.LOCK:
        selected={code:choices(cid,code,raw) for code,raw in updates.items()}
        path=language_defaults.root(cid)/'current.json';current=store.read_json(path,{}) or {}
        payload=copy.deepcopy(current.get('payload') or {'settings':{},'languages':[],'voices':{}})
        attach={code:languages.channel_voice(cid,code) for code in selected if not (payload.get('voices') or {}).get(code)}
        attach={code:example for code,example in attach.items() if example}
        version=current.get('version') or uuid.uuid4().hex
        if attach:
            previous=version;version=uuid.uuid4().hex;base=language_defaults.root(cid)
            for code,voice in (payload.get('voices') or {}).items():
                source=base/previous/code
                if voice and not voice.get('remote_only') and source.is_dir():shutil.copytree(source,base/version/code)
            for code,example in attach.items():
                dest=base/version/code;dest.mkdir(parents=True,exist_ok=True);target=dest/'own-voice.mp3'
                shutil.copy2(example['path'],target);(dest/'own-voice.txt').write_text(example['text'],encoding='utf-8')
                meta=store.read_json(example['meta'],{}) or {}
                meta.update(example_level_version=languages.EXAMPLE_LEVEL_VERSION,example_source_stamp=languages.example_source_stamp(target),example_normalized_copy=False)
                store.atomic_json(dest/'own-voice.json',meta)
                known=meta.get('eleven_voice_id') if meta.get('eleven_stamp')==example['stamp'] else None
                payload.setdefault('voices',{})[code]={'sha256':voice_cache.file_hash(target),'text':example['text'],'clone':known}
        payload.setdefault('language_settings',{}).update(selected)
        payload['languages']=list(dict.fromkeys([*payload.get('languages',[]),*selected]))
        signature=language_defaults.signature(payload)
        if signature!=current.get('signature'):
            store.atomic_json(path,{**current,'channel_id':cid,'payload':payload,'signature':signature,
                                    'version':version,'saved_at':time.time()})
    return {'settings':selected}


def folder(cid,code):
    store.get_channel_folder(cid);languages.check_code(code)
    return store.DATA_ROOT/'channels'/cid/'translation-samples'/code


def describe(cid,code,raw=None,text=None):
    settings=choices(cid,code,raw);example=languages.channel_voice(cid,code)
    remote=language_defaults.remote_ids(cid,code)
    text=TEXTS[code] if text is None else text
    if not isinstance(text,str) or not 1<=len(text.strip())<=1000:raise store.StudioError('Текст зразка має містити від 1 до 1000 символів')
    text=text.strip();provider=settings['provider']
    effective={'provider':provider,'model':settings['eleven_engine'] if provider=='elevenlabs' else settings['fish_engine']}
    if provider=='heygen':effective['model']=settings['heygen_model']
    if provider=='fishaudio':effective.update(style=settings['fish_style'],voice_model=remote.get(provider) or (example.get('fish_model') if example else None))
    reference=remote.get(provider) or (voice_cache.file_hash(example['path']) if example else None)
    if provider=='heygen':
        explicit=settings['heygen_voice_id'] or remote.get('heygen')
        reference=explicit if explicit or effective['model']=='starfish' else reference
    identity=hashlib.sha256(json.dumps([1,code,effective,reference,text],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    root=folder(cid,code);target=root/(identity+'.mp3');job=store.read_json(root/'job.json',{}) or {}
    if job.get('key')!=identity:job={}
    if job.get('status')=='running' and (cid,code) not in ACTIVE:
        job={**job,'status':'failed','error':'Роботу перервано. Зразок не запускається повторно автоматично.'}
    receipt=store.read_json(target.with_suffix('.json'),{}) or {}
    sample={'key':identity,'duration':receipt.get('duration'),'url':f'/api/channels/{cid}/voices/{code}/sample/file?key={identity}'} if target.is_file() and receipt.get('status')=='done' else None
    if provider=='elevenlabs':
        rate=eleven_api.STUDIO_ESTIMATE_RATES.get(settings['eleven_engine'])
        estimate={'unit':'credits','amount':__import__('math').ceil(len(text)*rate) if rate is not None else None}
    elif provider=='heygen':
        estimate=heygen_voice.estimate({**settings,'text':text})
    else:
        spec=languages.FISH_ENGINES[settings['fish_engine']]
        rate=spec['promo'][0] if spec.get('promo') and time.time()<spec['promo'][1] else spec['per_char']
        estimate={'unit':'usd','amount':len(text.encode('utf-8'))*rate}
    if sample:estimate['amount']=0
    return {'settings':settings,'text':text,'key':identity,'available':bool(reference),'sample':sample,'job':job,'estimate':estimate,'working':(cid,code) in ACTIVE}


def busy(cid=None):
    with LOCK:return any(channel==cid for channel,code in ACTIVE) if cid else bool(ACTIVE)


def _voice(cid,code,settings,example,remote):
    provider=settings['provider']
    if provider=='heygen':
        return languages.translation_heygen_voice(cid,code,settings['heygen_model'],settings['heygen_voice_id'] or remote.get(provider),example)
    if provider=='fishaudio':
        return {'model_id':remote.get(provider) or (example.get('fish_model') if example else None),
                'audio':example['path'].read_bytes() if example else b'', 'text':example['text'] if example else '',
                'engine':settings['fish_engine'],'style':settings['fish_style'],'language':code}
    import channel_voice_lab
    known=remote.get(provider) or (example.get('known_clone') if example else None)
    lab=channel_voice_lab.validated({'provider':'elevenlabs','language':code,'model':settings['eleven_engine'],
                                   'eleven_voice_id':known or '', 'noise_cleanup':False,'delivery':'neutral'})
    ref={'prepared_path':str(example['path']),'clone_owner':cid} if example else {}
    secret,identity=channel_voice_lab.clone(cid,lab,ref)
    original=languages.channel_voice(cid,code)
    if example and original and voice_cache.file_hash(original['path'])==voice_cache.file_hash(example['path']):
        with language_defaults.LOCK:
            meta=store.read_json(original['meta'],{}) or {}
            meta.update(eleven_voice_id=identity,eleven_stamp=original['stamp']);store.atomic_json(original['meta'],meta)
            path=language_defaults.root(cid)/'current.json';saved=store.read_json(path,{}) or {}
            voice=((saved.get('payload') or {}).get('voices') or {}).get(code)
            if voice and voice.get('sha256')==voice_cache.file_hash(original['path']):
                voice['clone']=identity;saved['signature']=language_defaults.signature(saved['payload']);store.atomic_json(path,saved)
    return {'id':identity,'engine':settings['eleven_engine'],'language':code}


def _run(cid,code,settings,example,job):
    root=folder(cid,code);target=root/(job['key']+'.mp3')
    try:
        voice=_voice(cid,code,settings,example,job['remote_ids'])
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            staged=Path(temporary)/'sample.mp3'
            credits=languages.speak(settings['provider'],voice,job['text'],staged)
            duration=store.media_duration(staged)
            if not duration or duration<=0:raise RuntimeError('Сервіс повернув неповний зразок голосу')
            staged.replace(target)
        job.update(status='done',duration=duration,credits=credits,finished_at=time.time())
        store.atomic_json(target.with_suffix('.json'),job)
        if settings['provider']=='elevenlabs':eleven_api.invalidate_balance()
    except Exception as error:job.update(status='failed',error=str(error)[:500],finished_at=time.time())
    finally:
        with LOCK:
            try:
                store.atomic_json(root/'job.json',job)
                store.atomic_json(root/'requests'/(job['client_id']+'.json'),job)
            finally:ACTIVE.discard((cid,code))


def start(cid,code,raw,text,client_id):
    if not isinstance(client_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',client_id):raise store.StudioError('Оновіть вікно зразка голосу')
    with LOCK:
        state=describe(cid,code,raw,text);root=folder(cid,code)
        receipt=store.read_json(root/'requests'/(client_id+'.json'),{}) or {}
        if receipt:
            if receipt.get('key')!=state['key']:raise store.StudioError('Цей запит уже використано для іншого зразка',409)
            return state
        if (cid,code) in ACTIVE:raise store.StudioError('Зразок цією мовою вже створюється',409)
        if not state['available']:raise store.StudioError('Додайте приклад або ID голосу для цього сервісу',409)
        if state['sample']:return state
        target=root/(state['key']+'.mp3')
        if target.is_file():
            duration=store.media_duration(target)
            if not duration:raise store.StudioError('Збережений зразок пошкоджено. Повторний платний запит не запущено.',409)
            store.atomic_json(target.with_suffix('.json'),{'status':'done','key':state['key'],'duration':duration,'recovered':True})
            return describe(cid,code,raw,text)
        languages.language_quality.require(code,state['text'])
        root.mkdir(parents=True,exist_ok=True)
        remote=language_defaults.remote_ids(cid,code)
        provider=state['settings']['provider']
        explicit=remote.get(provider) or (provider=='heygen' and state['settings']['heygen_voice_id'])
        example=None if explicit else languages.channel_voice(cid,code)
        if example:
            saved=store.read_json(language_defaults.root(cid)/'current.json',{}) or {}
            known=((saved.get('payload') or {}).get('voices') or {}).get(code) or {}
            clone=known.get('clone') if known.get('sha256')==voice_cache.file_hash(example['path']) else None
            inputs=root/'inputs'/client_id;inputs.mkdir(parents=True,exist_ok=True)
            source=inputs/'reference.mp3';shutil.copy2(example['path'],source)
            if voice_cache.file_hash(source)!=voice_cache.file_hash(example['path']) or describe(cid,code,raw,text)['key']!=state['key']:raise store.StudioError('Приклад голосу змінився. Повторіть вибір.',409)
            shutil.copy2(example['meta'],inputs/'reference.json')
            example={**example,'path':source,'meta':inputs/'reference.json','stamp':source.stat().st_mtime_ns,'known_clone':clone}
        if describe(cid,code,raw,text)['key']!=state['key']:raise store.StudioError('Голос змінився. Повторіть вибір.',409)
        job={'status':'running','key':state['key'],'settings':state['settings'],'text':state['text'],
             'client_id':client_id,'started_at':time.time(),'estimate':state['estimate'],
             'remote_ids':remote}
        store.atomic_json(root/'job.json',job);store.atomic_json(root/'requests'/(client_id+'.json'),job)
        ACTIVE.add((cid,code))
        try:threading.Thread(target=_run,args=(cid,code,state['settings'],example,job),daemon=True).start()
        except Exception:
            ACTIVE.discard((cid,code));job.update(status='failed',error='Не вдалося запустити зразок');store.atomic_json(root/'job.json',job);store.atomic_json(root/'requests'/(client_id+'.json'),job);raise
    return describe(cid,code,raw,text)


def audio_file(cid,code,key):
    if not isinstance(key,str) or not re.fullmatch(r'[0-9a-f]{64}',key):raise store.StudioError('Зразок не знайдено',404)
    path=folder(cid,code)/(key+'.mp3')
    if not path.is_file():raise store.StudioError('Зразок ще не готовий',404)
    return path
