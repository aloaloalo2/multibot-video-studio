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
        events[f"{provider}:{identity}"] = {
            "provider": provider, "amount": amount if number(amount) else None,
            "estimated": estimated, "category": category}
        if language:
            events[f"{provider}:{identity}"]["language"] = language
        store.atomic_json(path, data)
        CACHE.pop(root.name, None)


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

    def put(key, provider, amount, *, category="other", estimated=False):
        previous = events.get(f"{provider}:{key}", {})
        if provider == 'elevenlabs' and estimated and previous and not previous.get('estimated') and number(previous.get('amount')):
            return
        events[f"{provider}:{key}"] = {"provider": provider, "amount": amount if number(amount) else None,
                                       "category": category, "estimated": estimated}

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

    roots = list((root / "languages").glob("*/parts/requests.json"))
    roots += list((root / "languages").glob("*/voice-history/*/parts/requests.json"))
    roots += list((root / "languages").glob("*/sample-parts/*/requests.json"))
    for path in roots:
        rows = read(path)
        if not isinstance(rows, list):
            continue
        config = store.read_json(path.parent / "request.json", {}) or {}
        if config.get("provider") != "elevenlabs":
            continue
        for index, row in enumerate(rows):
            # Stable through moving parts to history; cached audio copies have no paid request.
            identity = row.get("request_id") or row.get("receipt_id")
            if not identity:
                stable = {k: row.get(k) for k in ("started_at", "index", "file", "text")}
                identity = hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest() if row.get("started_at") else f"{path.relative_to(root)}:{index}"
            actual = row.get("actual_cost")
            known = number(actual) and row.get("status") == "complete"
            put(identity, "elevenlabs", actual if known else row.get("estimated_cost"),
                category="voice", estimated=not known)

    return data


def totals(data: dict, credit_rate=None) -> dict:
    result = {name: {"amount": 0., "unknown": 0, "estimated": False, "requests": 0}
              for name in ("openrouter", "claude_code", "elevenlabs")}
    language_usd = 0.
    for event in data.get("events", {}).values():
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
    return {"providers": result, "languages_usd": round(language_usd, 6), "updated_at": time.time()}


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
