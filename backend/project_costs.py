"""Durable project spending index from existing receipts. Never starts paid work."""
from __future__ import annotations

import hashlib
import json
import math
import threading
import time
import uuid
from pathlib import Path

import store

LOCK = threading.RLock()
CACHE = {}
TTL = 15


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def record_at(root: Path, provider: str, amount, *, identity=None, category="thumbnail", estimated=False, language=None):
    """Retain a charge even if its generated picture or prompt later fails validation."""
    with LOCK:
        identity = identity or uuid.uuid4().hex
        path = root / "project-costs.json"
        data = store.read_json(path, {}) or {}
        events = data.setdefault("events", {})
        previous = events.get(f"{provider}:{identity}", {})
        events[f"{provider}:{identity}"] = {**previous,
            "provider": provider, "amount": amount if number(amount) else None,
            "estimated": estimated, "category": category}
        # Keep attribution at the existing billing boundary; observing costs never starts another request.
        try:
            import job_timing
            trace = job_timing.CURRENT.get()
            if trace is not None and trace.project_id == root.name and not previous.get('workflow'):
                events[f"{provider}:{identity}"].update(workflow=trace.workflow, run_id=trace.id)
                if trace.language:
                    events[f"{provider}:{identity}"]["language"] = trace.language
        except (ImportError, AttributeError):
            pass
        if language:
            events[f"{provider}:{identity}"]["language"] = language
        store.atomic_json(path, data)
        CACHE.pop(root.name, None)
        ledger(provider, amount, identity, category, root)


JOURNAL_PROVIDERS = {"heygen", "elevenlabs", "fishaudio"}
import contextvars
JOURNAL_ON = contextvars.ContextVar("project_costs_journal_on")


def ledger(provider, amount, identity, category, root, at=None):
    """Every paid charge in one studio-wide journal with its time, apart from the projects: the limits panel's
    spending survives a deleted project (user, 18 November 2026: «має працювати… навіть якщо я видалю проект»)."""
    if not number(amount) or amount <= 0:
        return
    try:
        if Path(root).resolve().parent != Path(store.PROJECTS_ROOT).resolve():
            return   # a folder outside the studio's projects (a test's) writes no studio-wide charge
    except OSError:
        return
    try:
        import json, time
        line = {"at": round(at if number(at) else time.time(), 1), "provider": provider, "amount": amount, "identity": identity,
                "category": category, "project": Path(root).name}
        # the channel goes with the charge, so a channel's spending survives its deleted projects (user, 25 November 2026)
        channel = (store.read_json(Path(root) / "project.json", {}) or {}).get("channel_id")
        if channel:
            line["channel"] = channel
        with open(store.DATA_ROOT / "spending-ledger.jsonl", "a", encoding="utf-8") as out:
            out.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError:
        pass


def mtime(path: Path):
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def collect(root: Path, data: dict) -> dict:
    if data.get('schema') != 1:
        data['files'] = {}
        data['schema'] = 1
    events, files = data.setdefault("events", {}), data.setdefault("files", {})

    def read(path):
        try:
            stat = path.stat()
            key = str(path.relative_to(root))
            stamp = [stat.st_mtime_ns, stat.st_size]
            if files.get(key) == stamp:
                return None
            value = store.read_json(path, None)
            if value is not None:
                files[key] = stamp
            return value
        except (OSError, ValueError):
            return None

    def put(key, provider, amount, *, category="other", estimated=False, at=None):
        previous = events.get(f"{provider}:{key}", {})
        if provider == 'elevenlabs' and estimated and previous and not previous.get('estimated') and number(previous.get('amount')):
            return
        events[f"{provider}:{key}"] = {**previous, "provider": provider, "amount": amount if number(amount) else None,
                                       "category": category, "estimated": estimated}
        if number(at):
            events[f"{provider}:{key}"]["at"] = round(at, 1)
        if not JOURNAL_ON.get(True):
            return
        # every paid charge the project index learns of reaches the studio-wide journal of the limits panel too: the
        # host's HeyGen videos and the voices of translations were only on the cards (user, 25 November 2026: «сюди не
        # записується нічого на рахунок Хейгена… все перевір, всі підрахунки, всі API»); the panel counts a charge once
        if provider in JOURNAL_PROVIDERS and number(amount) and amount > 0 and previous.get("amount") != amount:
            ledger(provider, amount, key, category, root, at=at)

    # Recover durable per-paragraph receipts if a later status/accounting write was interrupted.
    for path in (root / 'script-editing').glob('*/requests/*/receipt.json'):
        row=read(path)
        if isinstance(row,dict) and row.get('status')!='cancelled_before_submission':
            if row.get('request_id') and row.get('attempt_id'):
                events.pop('openrouter:'+row['attempt_id'],None)
            put(row.get('request_id') or row.get('attempt_id') or str(path.relative_to(root)),
                'openrouter',row.get('cost_usd'),category='script_editing')

    for path in list((root/'script-editing').glob('*/author-receipt.json'))+list((root/'script-editing').glob('*/author-receipts/*.json')):
        row=read(path)
        if isinstance(row,dict):
            put(row.get('identity') or str(path.relative_to(root)), 'claude_code',
                row.get('incremental_cost_usd'),category='script_editing')

    for path in (root / "languages").glob("*/translation-attempts/*/*.json"):
        row = read(path)
        if isinstance(row, dict):
            key = row.get("request_id") or str(path.relative_to(root))
            put(key, "openrouter",
                (row.get("usage") or {}).get("cost"), category="languages")
            events[f"openrouter:{key}"]["language"] = path.relative_to(root).parts[1]

    # Legacy saved totals can fill gaps in an older receipt history, without charging the same request twice.
    saved = store.read_json(root / 'languages/languages.json', {}) or {}
    for code, item in (saved.get('languages') or {}).items():
        known = sum(e['amount'] for e in events.values() if e.get('provider') == 'openrouter'
                    and e.get('language') == code and e.get('category') == 'languages' and number(e.get('amount')))
        floor = item.get('translate_cost')
        if number(floor) and floor > known:
            put(f'legacy-language:{code}', 'openrouter', floor-known, category='languages', estimated=True)
        else:
            events.pop(f'openrouter:legacy-language:{code}', None)

    thumbnail = store.read_json(root / 'thumbnail-job.json', {}) or {}
    if number(thumbnail.get('prompt_cost_usd')) and not any(e.get('category') == 'thumbnail' for e in events.values()):
        put(f"legacy-thumbnail:{thumbnail.get('started_at')}",
            'openrouter' if thumbnail.get('writer') == 'deepseek' else 'claude_code',
            thumbnail['prompt_cost_usd'], category='legacy_thumbnail')

    conversation = read(root / "agent-conversation.json")
    if isinstance(conversation, dict):
        for row in conversation.get("costs", []):
            put(row.get("request_id") or row["id"], "openrouter", row.get("amount_usd"), category="agent")

    # A report may be refreshed after the same run. Its log path is the stable key.
    for path in sorted((root / "spend").glob("*.json")):
        row = read(path)
        if isinstance(row, dict):
            key = str(row.get("log") or path.name)
            previous = events.get(f"claude_code:{key}", {})
            stamp = row.get("log_modified") or 0
            if stamp >= previous.get("modified", 0):
                put(key, "claude_code", row.get("cost_usd"), estimated=not row.get("cost_measured"))
                events[f"claude_code:{key}"]["modified"] = stamp

    for path in (root/'narration/receipts').glob('*.json'):
        row=read(path)
        if isinstance(row,dict) and row.get('provider') in {'elevenlabs','fishaudio','heygen'}:
            put(row['identity'],row['provider'],row.get('amount'),category='narration',estimated=True,at=row.get('created_at') or mtime(path))
    # Recover completed runs predating per-request receipts without charging cache hits twice.
    narration=store.read_json(root/'narration/job.json',{}) or {}
    if narration.get('status')=='done' and not narration.get('cost_receipts_version'):
        provider=narration.get('provider')
        if provider in {'elevenlabs','fishaudio','heygen'}:
            amount=narration.get('estimated_credits' if provider=='elevenlabs' else 'estimated_usd')
            if narration.get('characters')==0:amount=0
            put('legacy-narration:'+str(narration.get('started_at')),provider,amount,category='narration',estimated=True)

    # The host's HeyGen videos (user, 25 November 2026: «на карточці проекта не пише, скільки ми в дійсності потратили»):
    # every video HeyGen accepted is paid by its seconds; a frame cut from a shared video is not a video of its own
    for path in (root / "heygen-frames").glob("*.json"):
        row = read(path)
        if (isinstance(row, dict) and not row.get("one_video") and row.get("video_id")
                and row.get("state") in {"submitted", "completed"}):
            put("video:" + str(row["video_id"]), "heygen", heygen_video_usd(row), category="video", estimated=True, at=row.get("submitted_at") or mtime(path))

    roots = list((root / "languages").glob("*/parts/requests.json"))
    roots += list((root / "languages").glob("*/voice-history/*/parts/requests.json"))
    roots += list((root / "languages").glob("*/sample-parts/*/requests.json"))
    for path in roots:
        rows = read(path)
        if not isinstance(rows, list):
            continue
        config = store.read_json(path.parent / "request.json", {}) or {}
        provider=config.get("provider")
        if provider not in ("elevenlabs","heygen"):
            continue
        for index, row in enumerate(rows):
            # Stable through moving parts to history; cached audio copies have no paid request.
            identity = row.get("request_id") or row.get("receipt_id")
            if not identity:
                stable = {k: row.get(k) for k in ("started_at", "index", "file", "text")}
                identity = hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest() if row.get("started_at") else f"{path.relative_to(root)}:{index}"
            actual = row.get("actual_cost")
            known = number(actual) and row.get("status") == "complete"
            put(identity, provider, actual if known else row.get("estimated_cost"),
                category="voice", estimated=not known, at=row.get("started_at") or mtime(path))

    return data


def heygen_video_usd(row: dict):
    """A HeyGen video's price: its voice's seconds times the per-minute rate of the avatar's kind, kept on the receipt
    (older receipts: the kind known to the studio, else the photo avatar's rate, the one the studio uses)."""
    identity = row.get("identity") or {}
    if identity.get("spans"):
        spans = identity["spans"]
        seconds = sum(float(end) - float(start) for start, end in spans) + float(identity.get("gap") or 0) * (len(spans) - 1)
    elif number(identity.get("start")) and number(identity.get("end")):
        seconds = float(identity["end"]) - float(identity["start"]) + float(identity.get("tail") or 0)
    else:
        return None
    rate = row.get("usd_per_minute")
    if not number(rate):
        import heygen_avatars
        if identity.get("engine") == "avatar_iv":
            rate = heygen_avatars.known_rate_iv(identity.get("look")) or heygen_avatars.RATES_IV["photo_avatar"]
        else:
            rate = heygen_avatars.known_rate(identity.get("look")) or heygen_avatars.RATES["photo_avatar"]
    return round(max(0.0, seconds) * float(rate) / 60, 6)


def totals(data: dict, credit_rate=None) -> dict:
    result = {name: {"amount": 0., "unknown": 0, "estimated": False, "requests": 0}
              for name in ("openrouter", "claude_code", "elevenlabs", "fishaudio", "heygen")}
    language_usd = 0.
    # the voices of the translations, apart from the episode's own narration and host videos: the «Мови» tab shows only what
    # its languages cost (user, 26 November 2026: «нема перекладів, а воно пише 3.19»)
    language_voice = {name: 0. for name in ("elevenlabs", "fishaudio", "heygen")}
    for event in data.get("events", {}).values():
        if event.get("category") == "voice" and event.get("provider") in language_voice and number(event.get("amount")):
            language_voice[event["provider"]] += event["amount"]
        if event.get("provider") not in result:
            continue
        item = result[event["provider"]]
        item["requests"] += 1
        if number(event.get("amount")):
            item["amount"] += event["amount"]
            item["estimated"] |= bool(event.get("estimated"))
            if event.get("category") == "languages" and event["provider"] == "openrouter":
                language_usd += event["amount"]
        else:
            item["unknown"] += 1
    for name, item in result.items():
        item["amount"] = round(item["amount"], 6)
        item["unit"] = "credits" if name == "elevenlabs" else "usd"
        item["usd"] = round(item["amount"] * credit_rate * 1.20, 6) if name == "elevenlabs" and number(credit_rate) else item["amount"] if name != "elevenlabs" else 0. if not item['requests'] else None
    result["elevenlabs"]["estimated"] |= bool(result["elevenlabs"]["requests"])
    result["claude_code"]["equivalent"] = True
    voice_usd = language_voice["fishaudio"] + language_voice["heygen"]
    if language_voice["elevenlabs"]:
        voice_usd = voice_usd + language_voice["elevenlabs"] * credit_rate * 1.20 if number(credit_rate) else None
    return {"providers": result, "languages_usd": round(language_usd, 6),
            "language_voice_usd": round(voice_usd, 6) if voice_usd is not None else None,
            "language_voice_estimated": bool(language_voice["elevenlabs"]), "updated_at": time.time()}


def summary(pid: str, *, credit_rate=None, refresh=False) -> dict:
    store.load_project(pid)
    with LOCK:
        cached = CACHE.get(pid)
        if cached and not refresh and time.monotonic() - cached[0] < TTL and cached[1] == credit_rate:
            return cached[2]
        # Stopped runs may save their native billing receipt after the CLI stream closes.
        # Unchanged receipts only require local file stamps; never call a paid API.
        import spend_report
        spend_report.backfill(pid)
        root = store.project_dir(pid)
        path = root / "project-costs.json"
        data = collect(root, store.read_json(path, {}) or {})
        result = totals(data, credit_rate)
        store.atomic_json(path, {**data, "summary": result})
        CACHE[pid] = (time.monotonic(), credit_rate, result)
        return result


def refresh_all() -> None:
    """Every project's index brought up to date from its receipts, so the limits panel's journal has each charge even
    for a project nobody opened since (unchanged receipt files are skipped by their stamps; no paid request)."""
    for root in sorted(Path(store.PROJECTS_ROOT).glob("*")):
        if not (root / "project.json").is_file():
            continue
        with LOCK:
            path = root / "project-costs.json"
            try:
                before = store.read_json(path, {}) or {}
                data = collect(root, json.loads(json.dumps(before)))
                if data != before:
                    store.atomic_json(path, data)
                    CACHE.pop(root.name, None)
            except (OSError, ValueError, KeyError, TypeError):
                continue
