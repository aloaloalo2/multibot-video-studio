"""ElevenLabs model discovery and the dialogue transports used by current voice models.

Keys stay in the Studio vault. The catalogue is metadata only; discovery never generates speech.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import threading
import time
from contextlib import contextmanager
import urllib.error
import urllib.parse
import urllib.request

import credentials
import store

BASE = "https://api.elevenlabs.io/v1"
# Public ElevenAPI list prices, checked 2026-11-03. These are estimates, not account debits.
API_USD_PER_CHAR = {"eleven_v4": 0.00008, "eleven_v4_turbo": 0.00004}
API_PRICE_CHECKED = "2026-11-03"
API_PRICE_SOURCE = "https://elevenlabs.io/pricing/api"
# Monthly subscription allocation, not an extra cash debit. Public price checked 2026-11-05.
MONTHLY_USD = {"free": 0, "starter": 6, "creator": 22, "pro": 99, "scale": 299, "business": 990}
MONTHLY_CREDITS = {"free": 10000, "starter": 30000, "creator": 121000, "pro": 600000, "scale": 1800000, "business": 6000000}
DEFAULT_MODEL = "eleven_v4"
# Author-selected planning allowance. This is not a provider debit or catalogue rate.
STUDIO_ESTIMATE_RATES = {"eleven_v4_turbo": 0.26}
PRIORITY = ["eleven_v4", "eleven_v4_turbo"]
FALLBACK = [
    {"id": mid, "name": name, "note": note, "credits_per_char": None, "languages": [],
     "max_chars": 1800 if mid.startswith(("eleven_v3", "eleven_v4")) else 10000,
     "verified": False}
    for mid, name, note in [
        ("eleven_v4", "Eleven v4", "виразна озвучка · 90+ мов"),
        ("eleven_v4_turbo", "Eleven v4 Turbo", "швидка озвучка · 90+ мов"),
    ]
]
_cache = {}
_refreshing = set()
_ui_lock = threading.Lock()
_metadata_mode = threading.local()
_lock = threading.Lock()
_balances = {}
_balance_lock = threading.Lock()
_credit_rates = {}
_credit_scopes = {}
CREDIT_RATE_TTL = 86400
HISTORY_PAGES = 3


def finite_number(value) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def balance(refresh: bool = False) -> dict:
    """Read remaining account credits independently of the slower model catalogue."""
    try:
        secret=credentials.vault().read(credentials.service_name('elevenlabs'))
    except RuntimeError:
        return {'state':'unavailable','error':'Додайте ключ ElevenLabs у налаштуваннях студії.'}
    signature=hashlib.sha256(secret.encode()).hexdigest()
    with _balance_lock:
        cached=_balances.get(signature)
        if cached and not refresh and time.monotonic()-cached[0]<(30 if cached[1]['state']=='ready' else 10):
            return dict(cached[1])
        try:
            account=get('/user/subscription',secret)
            limit,used=account.get('character_limit'),account.get('character_count')
            if any(isinstance(value,bool) or not isinstance(value,(int,float)) or value<0 for value in (limit,used)):
                raise RuntimeError('ElevenLabs не повернув коректний баланс кредитів.')
            result={'state':'ready','remaining_credits':max(0,int(limit)-int(used)),
                    'total_credits':int(limit),'used_credits':int(used),'checked_at':time.time()}
            tier = str(account.get('tier') or '').lower()
            fee, included = MONTHLY_USD.get(tier), MONTHLY_CREDITS.get(tier)
            if fee is not None and included:
                result.update(credit_usd_rate=fee/included, credit_usd_estimated=True,
                              credit_usd_basis=f'{tier.title()}: ${fee:g} / {included:,} кредитів (орієнтовно, без податків і знижок)',
                              credit_usd_source='https://elevenlabs.io/pricing')
                store.atomic_json(store.DATA_ROOT/'eleven-credit-usd.json',
                                  {k:result[k] for k in ('credit_usd_rate','credit_usd_basis','credit_usd_source')})
        except (RuntimeError,ValueError,TypeError,AttributeError) as error:
            result={**(cached[1] if cached else {}),'state':'stale' if cached and 'remaining_credits' in cached[1] else 'unavailable',
                    'error':str(error)}
        _balances[signature]=(time.monotonic(),result)
        return dict(result)


def invalidate_balance() -> None:
    with _balance_lock:
        for account,(_,result) in list(_balances.items()):
            _balances[account]=(float('-inf'),result)


def get(path: str, secret: str):
    request = urllib.request.Request(BASE + path, headers={"xi-api-key": secret, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read(4096).decode('utf-8', errors='replace')
        if error.code in (401, 403) and 'user_read' in detail:
            raise RuntimeError('Для балансу дозвольте User → Access у налаштуваннях ключа ElevenLabs.') from None
        raise RuntimeError(f"ElevenLabs: помилка {error.code} під час перевірки підключення") from None
    except (OSError, ValueError):
        raise RuntimeError("ElevenLabs зараз не відповідає на перевірку підключення") from None


def normalize_models(raw: list) -> list[dict]:
    if not isinstance(raw, list):
        raise RuntimeError("ElevenLabs повернув некоректний список моделей")
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        mid = str(item.get("model_id") or "")
        if mid not in PRIORITY or item.get("is_deprecated"):
            continue
        rates = item.get("model_rates") or {}
        if not isinstance(rates,dict):rates={}
        rate = rates.get("character_cost_multiplier")
        discount = rates.get("cost_discount_multiplier", 1)
        rate = float(rate) * float(discount) if finite_number(rate) and finite_number(discount) and rate > 0 and discount > 0 else None
        if not finite_number(rate):rate=None
        dialogue = mid.startswith(("eleven_v3", "eleven_v4"))
        result.append({"id": mid, "name": item.get("name") or mid,
                       "note": "потрібен доступ до моделі" if item.get("requires_alpha_access") else "діалогова озвучка" if dialogue else "озвучка",
                       "credits_per_char": rate, "verified": True,
                       "languages": [x["language_id"] for x in item.get("languages", []) if x.get("language_id")],
                       "max_chars": min(1800 if dialogue else 10000, int(item.get("maximum_text_length_per_request") or 10000)),
                       "can_use_style": bool(item.get("can_use_style")),
                       "can_use_speaker_boost": bool(item.get("can_use_speaker_boost"))})
    return sorted(result, key=lambda m: (PRIORITY.index(m["id"]) if m["id"] in PRIORITY else len(PRIORITY), m["name"]))


def observed_credit_rate(history: list, mid: str) -> float | None:
    """Estimate current per-character debits from individual history records, never sum incomplete streams as a bill."""
    points = credit_points(history, mid)
    # Streaming history contains short chunks rounded to whole credits. Regressing
    # their rounded debit directly biases the rate upwards (0.2 becomes 0.25).
    if len(points)<5 or sum(n for n,_ in points)<250:return None
    # This tariff-grid inference is an estimate, not an exact billing rate. A small
    # rounding tolerance allows historical separator chunks, but the newest eligible
    # debit has a veto so an older majority cannot override a changed tariff.
    eligible=[item for item in history if credit_points([item],mid)]
    dated=[item for item in eligible if finite_number(item.get('date_unix'))]
    latest_stamp=max(item['date_unix'] for item in dated) if dated else None
    newest=[item for item in dated if item['date_unix']==latest_stamp] if dated else eligible[:1]
    latest_points=credit_points(newest,mid)
    rates=[step/20 for step in range(1,101)
           if all(abs(n*step/20-c)<=1.01 for n,c in latest_points)
           and sum(abs(n*step/20-c)<=1.01 for n,c in points)/len(points)>=.9]
    return rates[0] if len(rates)==1 else None


def credit_points(history: list, mid: str) -> list[tuple[int, float]]:
    points = []
    for item in history:
        if not isinstance(item,dict):continue
        if item.get("model_id")!=mid:continue
        dialogue=item.get("dialogue") or []
        if isinstance(dialogue,dict):dialogue=dialogue.get("inputs",[])
        if not isinstance(dialogue,list):dialogue=[]
        text=item.get("text") or "".join(str(x.get("text") or "") for x in dialogue if isinstance(x,dict))
        if not isinstance(text,str):continue
        count=len(text)
        before,after=item.get("character_count_change_from"),item.get("character_count_change_to")
        if count<20 or not finite_number(before) or not finite_number(after):continue
        credits=after-before
        if 0<credits<=count*5:points.append((count,credits))
    return points


def recent_history(secret: str, mid: str, now: float, evidence_after: float | None = None) -> list:
    """Read a bounded number of pages, without synthesis or storing account text."""
    cutoff = max(now-CREDIT_RATE_TTL,evidence_after if evidence_after is not None else now-CREDIT_RATE_TTL)
    query = {"page_size":100,"source":"TTS","model_id":mid,"date_after_unix":int(cutoff)}
    rows, seen_ids, cursors = [], set(), set()
    for _ in range(HISTORY_PAGES):
        try:
            page = get('/history?'+urllib.parse.urlencode(query), secret)
        except (RuntimeError, TypeError, ValueError):
            break
        if not isinstance(page,dict) or not isinstance(page.get('history'),list):break
        cursor = page.get('last_history_item_id')
        if isinstance(cursor,str) and cursor in cursors:break
        for item in page['history']:
            if not isinstance(item,dict):continue
            stamp, item_id = item.get('date_unix'), item.get('history_item_id')
            if not finite_number(stamp) or not cutoff <= stamp <= now:continue
            if item.get('source') not in (None,'TTS') or not credit_points([item],mid):continue
            if not isinstance(item_id,str) or not item_id or item_id in seen_ids:continue
            seen_ids.add(item_id)
            rows.append(item)
        if observed_credit_rate(rows,mid) is not None:break
        if not page.get('has_more') or not isinstance(cursor,str) or not cursor:break
        cursors.add(cursor)
        query['start_after_history_item_id'] = cursor
    return rows


def subscription_signature(account: dict | None) -> str | None:
    if not isinstance(account,dict) or not isinstance(account.get('tier'),str) or not account['tier']:return None
    fields = {key:account.get(key) for key in ('tier','status','currency')}
    if any(value is not None and not isinstance(value,str) for value in fields.values()):return None
    return hashlib.sha256(json.dumps(fields,sort_keys=True).encode()).hexdigest()


def credit_rate_path(signature: str, mid: str):
    # store.DATA_ROOT respects MULTIBOT_STUDIO_DATA; the default backend/data is ignored by Git.
    return store.DATA_ROOT / 'eleven-credit-rates' / signature / (mid+'.json')


def credit_scope(signature, mid, baseline, subscription, now) -> float:
    """Old debits cannot be relabelled as evidence for a newly observed plan/rate."""
    if not subscription or not finite_number(baseline) or baseline <= 0:
        return now  # An account-read outage is not evidence that its tariff changed.
    fields = {'key_signature':signature,'model':mid,'subscription_signature':subscription,
              'catalog_credits_per_char':baseline}
    path = credit_rate_path(signature,mid).with_suffix('.scope.json')
    previous = _credit_scopes.get((signature,mid))
    unreadable = False
    if previous is None:
        try:
            with path.open(encoding='utf-8') as handle:previous=json.loads(handle.read(16384))
        except FileNotFoundError:pass
        except (OSError,ValueError,TypeError):unreadable=True
    valid = (isinstance(previous,dict) and previous.get('schema')==1
             and finite_number(previous.get('evidence_after')) and finite_number(previous.get('checked_at'))
             and previous['evidence_after'] <= previous['checked_at'] <= now)
    changed = previous is not None and (not valid or previous.get('fields') != fields)
    cutoff = now if unreadable or changed else previous['evidence_after'] if valid else now-CREDIT_RATE_TTL
    current = {'schema':1,'fields':fields,'evidence_after':cutoff,'checked_at':now}
    _credit_scopes[(signature,mid)] = current
    try:store.atomic_json(path,current)
    except (OSError,ValueError,TypeError):pass
    return cutoff


def valid_credit_record(record, signature, mid, baseline, subscription, now) -> bool:
    if not isinstance(record,dict) or type(record.get('schema')) is not int or record['schema'] != 1 or not subscription:return False
    if (record.get('key_signature'),record.get('model'),record.get('subscription_signature')) != (signature,mid,subscription):return False
    if not finite_number(baseline) or baseline <= 0 or not finite_number(record.get('catalog_credits_per_char')) or record['catalog_credits_per_char'] != baseline:return False
    rate = record.get('rate')
    if not finite_number(rate) or not 0 < rate <= 5:return False
    dates = [record.get(key) for key in ('observed_at','evidence_latest_at','checked_at')]
    if not all(finite_number(value) for value in dates):return False
    oldest, latest, checked = dates
    if not 0 <= now-oldest <= CREDIT_RATE_TTL or not oldest <= latest <= checked <= now:return False
    samples, chars = record.get('samples'), record.get('characters')
    return type(samples) is int and samples >= 5 and type(chars) is int and chars >= 250


def retained_credit_rate(signature, mid, baseline, subscription, now, evidence_after=None):
    record = _credit_rates.get((signature,mid))
    if record is False:return None
    def valid(value):
        return (valid_credit_record(value,signature,mid,baseline,subscription,now)
                and (evidence_after is None or value['observed_at'] >= evidence_after))
    if valid(record):return record
    try:
        with credit_rate_path(signature,mid).open(encoding='utf-8') as handle:
            record = json.loads(handle.read(16384))
    except (OSError,ValueError,TypeError):
        return None
    return record if valid(record) else None


def keep_credit_rate(record) -> None:
    _credit_rates[(record['key_signature'],record['model'])] = dict(record)
    try:
        store.atomic_json(credit_rate_path(record['key_signature'],record['model']),record)
    except (OSError,ValueError,TypeError):
        pass  # A read-only/full disk must not break discovery or discard the current observation.


def invalidate_credit_rate(signature: str, mid: str, now: float) -> None:
    _credit_rates[(signature,mid)] = False
    try:
        # Replace instead of unlinking: the reason remains explicit and another process
        # cannot revive an older valid record after this one observed conflicting debits.
        store.atomic_json(credit_rate_path(signature,mid),{'invalidated_at':now,'reason':'conflicting_debit'})
    except (OSError,ValueError,TypeError):
        pass


@contextmanager
def nonblocking_metadata(enabled=True):
    previous = getattr(_metadata_mode, 'cached', False)
    _metadata_mode.cached = enabled
    try:
        yield
    finally:
        _metadata_mode.cached = previous


def ui_catalog() -> dict:
    """Immediate cached metadata for UI. Refresh the provider in one background worker."""
    try:
        secret = credentials.vault().read(credentials.service_name('elevenlabs'))
    except RuntimeError:
        return {'models': FALLBACK, 'verified': False, 'error': 'Додайте ключ ElevenLabs у налаштуваннях студії'}
    signature = hashlib.sha256(secret.encode()).hexdigest()
    cached = _cache.get(signature)
    if cached and time.monotonic()-cached[0] < 300:
        return cached[1]
    saved = store.read_json(store.DATA_ROOT/'eleven-catalog'/f'{signature}.json', {}) or {}
    result = cached[1] if cached else saved.get('data') or {'models': FALLBACK, 'verified': False}
    with _ui_lock:
        if signature not in _refreshing:
            _refreshing.add(signature)
            def refresh_metadata():
                try:
                    fresh = catalog()
                    store.atomic_json(store.DATA_ROOT/'eleven-catalog'/f'{signature}.json', {'data': fresh})
                finally:
                    with _ui_lock:
                        _refreshing.discard(signature)
            threading.Thread(target=refresh_metadata, daemon=True).start()
    return result


def catalog(refresh: bool = False) -> dict:
    try:
        secret = credentials.vault().read(credentials.service_name("elevenlabs"))
    except RuntimeError:
        return {"models": FALLBACK, "verified": False, "error": "Додайте ключ ElevenLabs у налаштуваннях студії"}
    signature = hashlib.sha256(secret.encode()).hexdigest()
    with _lock:
        cached = _cache.get(signature)
        if cached and not refresh and time.monotonic() - cached[0] < 300:
            return cached[1]
        try:
            models = normalize_models(get("/models", secret))
            if not models:
                raise RuntimeError("ElevenLabs не повернув моделей озвучення")
            result = {"models": models, "verified": True}
            account = None
            try:
                account = get("/user/subscription", secret)
                result["remaining_credits"] = max(0, int(account["character_limit"]) - int(account["character_count"]))
            except (RuntimeError, KeyError, TypeError, ValueError):
                pass
            subscription = subscription_signature(account)
            for spec in models:
                now, baseline = time.time(), spec.get('credits_per_char')
                cutoff = credit_scope(signature,spec['id'],baseline,subscription,now)
                history = recent_history(secret,spec['id'],now,cutoff)
                points = credit_points(history,spec['id'])
                rate = observed_credit_rate(history,spec['id'])
                record = retained_credit_rate(signature,spec['id'],baseline,subscription,now,cutoff)
                if rate is not None:
                    dates = [item['date_unix'] for item in history]
                    record = {'schema':1,'key_signature':signature,'model':spec['id'],
                              'subscription_signature':subscription,'catalog_credits_per_char':baseline,
                              'rate':rate,'observed_at':min(dates),'evidence_latest_at':max(dates),
                              'checked_at':now,'samples':len(points),'characters':sum(n for n,_ in points)}
                    if valid_credit_record(record,signature,spec['id'],baseline,subscription,now):
                        keep_credit_rate(record)
                    else:
                        record = None
                elif record and any(abs(n*record['rate']-c)>1.01 for n,c in points):
                    invalidate_credit_rate(signature,spec['id'],now)
                    record = None  # A new conflicting debit must veto even a warm/disk cached rate.
                if record:
                    spec.update(catalog_credits_per_char=baseline,credits_per_char=record['rate'],
                                credit_rate_source='recent_history',credit_rate_estimate=True,
                                credit_rate_observed_at=record['observed_at'],
                                credit_rate_evidence_latest_at=record['evidence_latest_at'])
        except (RuntimeError, TypeError, ValueError) as error:
            fallback = [dict(spec) for spec in (cached[1]['models'] if cached else FALLBACK)]
            for spec in fallback:
                observed_at = spec.get('credit_rate_observed_at')
                if spec.get('credit_rate_source')=='recent_history' and (
                        not finite_number(observed_at) or not 0 <= time.time()-observed_at <= CREDIT_RATE_TTL):
                    spec['credits_per_char'] = spec.pop('catalog_credits_per_char',None)
                    for field in ('credit_rate_source','credit_rate_estimate','credit_rate_observed_at','credit_rate_evidence_latest_at'):
                        spec.pop(field,None)
            result = {"models": fallback, "verified": False, "error": str(error)}
        _cache[signature] = (time.monotonic(), result)
        return result


def model(mid: str) -> dict | None:
    return next((m for m in catalog()["models"] if m["id"] == mid), None)


def estimate_rate(mid: str) -> float | None:
    if mid in STUDIO_ESTIMATE_RATES:
        return STUDIO_ESTIMATE_RATES[mid]
    if getattr(_metadata_mode, 'cached', False):
        return next((m.get('credits_per_char') for m in ui_catalog()['models'] if m['id'] == mid), None)
    return (model(mid) or {}).get('credits_per_char')


class SpeechAudio(bytes):
    """Audio plus the provider's per-request receipt, when HTTP supplies one."""
    def __new__(cls, audio: bytes, headers):
        result = super().__new__(cls, audio)
        try:
            value = float(headers.get('character-cost'))
            result.credits = value if math.isfinite(value) and value >= 0 else None
        except (TypeError, ValueError):
            result.credits = None
        return result


def settings(mid: str) -> dict:
    # v4 does not support style, speed or speaker boost; v3's natural stability is 0.5.
    if mid.startswith("eleven_v4"):
        return {"stability": 0.5, "similarity_boost": 0.75}
    if mid.startswith("eleven_v3"):
        return {"stability": 0.5}
    out = {"stability": 0.5, "similarity_boost": 0.75}
    spec = model(mid) or {}
    if spec.get("can_use_style"):
        out["style"] = 0.0
    if spec.get("can_use_speaker_boost"):
        out["use_speaker_boost"] = True
    return out


def streamed_dialogue(secret: str, voice_id: str, text: str, mid: str) -> bytes:
    """Turbo uses the documented Text to Dialogue WebSocket, with one registered voice."""
    try:
        from websockets.sync.client import connect
        from websockets.exceptions import WebSocketException
    except ImportError:
        raise RuntimeError("Для Eleven v4 Turbo встановіть залежності студії: python3 tools/doctor.py --install") from None
    url = "wss://api.elevenlabs.io/v1/text-to-dialogue/stream-input?" + urllib.parse.urlencode({
        "model_id": mid, "output_format": "mp3_44100_128"})
    deadline, audio, complete = time.monotonic() + 300, [], False
    try:
        with connect(url, open_timeout=20, max_size=16 * 1024 * 1024) as socket:
            socket.send(json.dumps({"voices": [voice_id], "xi_api_key": secret, "settings": settings(mid)}))
            socket.send(json.dumps({"inputs": [{"text": text, "voice_id": voice_id, "new_turn": True}]}))
            socket.send(json.dumps({"close_socket": True}))
            while time.monotonic() < deadline:
                msg = json.loads(socket.recv(timeout=max(0.1, deadline - time.monotonic())))
                if msg.get("error"):
                    # The server may echo input. Keep credentials out of errors and logs.
                    raise RuntimeError("ElevenLabs відхилив потокове озвучення. Перевірте доступ до моделі й баланс.")
                if msg.get("audio"):
                    audio.append(base64.b64decode(msg["audio"], validate=True))
                if msg.get("is_final"):
                    complete = True
                    break
    except (OSError, TimeoutError, WebSocketException):
        raise RuntimeError("ElevenLabs перервав потокове озвучення; неповний звук не збережено") from None
    if not complete or not audio:
        raise RuntimeError("ElevenLabs не завершив потокове озвучення; неповний звук не збережено")
    return b"".join(audio)
