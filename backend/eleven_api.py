"""ElevenLabs model discovery and the dialogue transports used by current voice models.

Keys stay in the Studio vault. The catalogue is metadata only; discovery never generates speech.
"""
from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import credentials

BASE = "https://api.elevenlabs.io/v1"
# Public ElevenAPI list prices, checked 2026-11-03. These are estimates, not account debits.
API_USD_PER_CHAR = {"eleven_v4": 0.00008, "eleven_v4_turbo": 0.00004}
API_PRICE_CHECKED = "2026-11-03"
API_PRICE_SOURCE = "https://elevenlabs.io/pricing/api"
DEFAULT_MODEL = "eleven_v4"
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
_lock = threading.Lock()
_balances = {}
_balance_lock = threading.Lock()


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
        rate = rates.get("character_cost_multiplier")
        discount = rates.get("cost_discount_multiplier", 1)
        rate = float(rate) * float(discount) if isinstance(rate, (int, float)) and isinstance(discount, (int, float)) else None
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
    points=[]
    for item in history:
        if item.get("model_id")!=mid:continue
        dialogue=item.get("dialogue") or []
        if isinstance(dialogue,dict):dialogue=dialogue.get("inputs",[])
        text=item.get("text") or "".join(str(x.get("text") or "") for x in dialogue if isinstance(x,dict))
        count=len(text)
        before,after=item.get("character_count_change_from"),item.get("character_count_change_to")
        if count<20 or not isinstance(before,(int,float)) or not isinstance(after,(int,float)):continue
        credits=after-before
        if 0<credits<=count*5:points.append((count,credits))
    # Streaming history contains short chunks rounded to whole credits. Regressing
    # their rounded debit directly biases the rate upwards (0.2 becomes 0.25).
    if len(points)<5 or sum(n for n,_ in points)<250:return None
    # Do not guess when short, rounded chunks support several tariffs equally.
    # A whole-credit residual also covers the provider's per-chunk separator.
    rates=[step/20 for step in range(1,101)
           if sum(abs(n*step/20-c)<=1.01 for n,c in points)/len(points)>=.9]
    return rates[0] if len(rates)==1 else None


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
            try:
                account = get("/user/subscription", secret)
                result["remaining_credits"] = max(0, int(account["character_limit"]) - int(account["character_count"]))
            except (RuntimeError, KeyError, TypeError, ValueError):
                pass
            for spec in models:
                rate=None
                old=next((m for m in cached[1]['models'] if m['id']==spec['id']),{}) if cached else {}
                try:
                    query=urllib.parse.urlencode({"page_size":100,"source":"TTS","model_id":spec["id"],"date_after_unix":int(time.time()-7*86400)})
                    history=get("/history?"+query,secret)
                    rate=observed_credit_rate(history.get("history",[]),spec["id"])
                except (RuntimeError,KeyError,TypeError,ValueError):
                    pass
                observed_at=time.time()
                if rate is None and old.get('credit_rate_source')=='recent_history' \
                        and observed_at-old.get('credit_rate_observed_at',0)<86400 \
                        and old.get('catalog_credits_per_char')==spec.get('credits_per_char'):
                    rate=old['credits_per_char']
                    observed_at=old['credit_rate_observed_at']
                if rate is not None:
                    spec["catalog_credits_per_char"]=spec.get("credits_per_char")
                    spec["credits_per_char"]=rate
                    spec["credit_rate_source"]="recent_history"
                    spec["credit_rate_observed_at"]=observed_at
        except (RuntimeError, TypeError, ValueError) as error:
            result = {"models": cached[1]["models"] if cached else FALLBACK, "verified": False, "error": str(error)}
        _cache[signature] = (time.monotonic(), result)
        return result


def model(mid: str) -> dict | None:
    return next((m for m in catalog()["models"] if m["id"] == mid), None)


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
