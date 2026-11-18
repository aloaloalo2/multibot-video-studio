"""What the studio's paid services cost today, this week and this month, for the limits panel (user, 18 November 2026:
«знизу… підрахунок… скільки потрачено за сьогодні… і за останні 30 днів. Всього»).

OpenRouter (pictures, thumbnails, translations, DeepSeek) is read from the key's own account counters: usage_daily,
usage_weekly and usage_monthly, which OpenRouter counts by UTC day, week and month. HeyGen and ElevenLabs narration come
from the studio's own receipts in the same UTC windows; ElevenLabs credits are turned into dollars by the saved plan rate
with the author's 20% tax, as on the project cards. Claude and Codex run on subscriptions and have no price here."""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import credentials
import store

CACHE_SECONDS = 300
_CACHE: dict = {}
_LOCK = threading.Lock()


def windows(now: float) -> dict:
    day = datetime.fromtimestamp(now, timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return {"day": day.timestamp(), "week": (day - timedelta(days=day.weekday())).timestamp(),
            "month": day.replace(day=1).timestamp()}


def openrouter() -> dict | None:
    try:
        key = credentials.vault().read(credentials.service_name("openrouter"))
        request = urllib.request.Request("https://openrouter.ai/api/v1/key", headers={"Authorization": "Bearer " + key})
        with urllib.request.urlopen(request, timeout=8) as response:
            data = json.load(response).get("data") or {}
    except (RuntimeError, OSError, ValueError, urllib.error.URLError):
        return None
    pick = lambda name: round(float(data[name]), 4) if isinstance(data.get(name), (int, float)) else None
    return {"day": pick("usage_daily"), "week": pick("usage_weekly"), "month": pick("usage_monthly"),
            "limit": data.get("limit"), "limit_remaining": pick("limit_remaining")}


LEDGER = "spending-ledger.jsonl"
BACKFILLED = "spending-ledger.backfilled"


def backfill() -> None:
    """Once: the narration receipts written before the journal, with their times, so the month starts complete."""
    marker = store.DATA_ROOT / BACKFILLED
    if marker.exists():
        return
    lines = []
    for path in store.PROJECTS_ROOT.glob("*/narration/receipts/*.json"):
        try:
            row = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if row.get("provider") in ("heygen", "elevenlabs") and isinstance(row.get("amount"), (int, float)) and row["amount"] > 0:
            lines.append({"at": row.get("created_at") or path.stat().st_mtime, "provider": row["provider"], "amount": row["amount"],
                          "identity": row.get("identity") or path.stem, "category": "narration", "project": path.parents[2].name})
    try:
        with open(store.DATA_ROOT / LEDGER, "a", encoding="utf-8") as out:
            for line in lines:
                out.write(json.dumps(line, ensure_ascii=False) + "\n")
        marker.write_text("done")
    except OSError:
        pass


def receipts(now: float) -> dict:
    """HeyGen and ElevenLabs from the studio-wide journal (project_costs.ledger), which outlives deleted projects."""
    backfill()
    edges = windows(now)
    rate = (store.read_json(store.DATA_ROOT / "eleven-credit-usd.json", {}) or {}).get("credit_usd_rate")
    rows = {}
    try:
        with open(store.DATA_ROOT / LEDGER, encoding="utf-8") as source:
            for text in source:
                try:
                    row = json.loads(text)
                except ValueError:
                    continue
                if row.get("provider") in ("heygen", "elevenlabs") and (row.get("at") or 0) >= edges["month"]:
                    rows[f"{row['provider']}:{row.get('identity')}"] = row   # a charge recorded twice counts once
    except OSError:
        pass
    totals = {name: {"day": 0.0, "week": 0.0, "month": 0.0} for name in ("heygen", "elevenlabs")}
    for row in rows.values():
        amount = row.get("amount")
        if not isinstance(amount, (int, float)):
            continue
        usd = amount if row["provider"] == "heygen" else (amount * rate * 1.2 if rate else 0)
        for window, start in edges.items():
            if row["at"] >= start:
                totals[row["provider"]][window] += usd
    return {name: {k: round(v, 4) for k, v in values.items()} for name, values in totals.items()}


def summary(now: float | None = None) -> dict:
    now = time.time() if now is None else now
    with _LOCK:
        if _CACHE.get("at", 0) > now - CACHE_SECONDS:
            return _CACHE["value"]
    services = {"openrouter": openrouter(), **receipts(now)}
    total = {window: round(sum((values or {}).get(window) or 0 for values in services.values()), 4) for window in ("day", "week", "month")}
    value = {"services": services, "total": total, "checked_at": now}
    with _LOCK:
        _CACHE.update(at=now, value=value)
    return value
