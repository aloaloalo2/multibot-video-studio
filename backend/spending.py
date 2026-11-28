"""What the studio's paid services cost today, this week and this month, for the limits panel (user, 18 November 2026:
«знизу… підрахунок… скільки потрачено за сьогодні… і за останні 30 днів. Всього»).

OpenRouter (pictures, thumbnails, translations, DeepSeek) is read from the key's own account counters: usage_daily,
usage_weekly and usage_monthly, which OpenRouter counts by UTC day, week and month. HeyGen and ElevenLabs narration come
from the studio's own receipts in the same UTC windows; ElevenLabs credits are turned into dollars by the saved plan rate
with no tax added (user, 28 November 2026: «елевен лабс прибери податок 20»), as on the project cards. Claude and Codex run on subscriptions and have no price here."""
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
CLAUDE_BACKFILLED = "spending-ledger.claude-backfilled"
# Claude runs on the subscription: its API-equivalent cost divided by the author's coefficient, as on the project cards
# (frontend/project-costs.js claudeSubscriptionDivisor; user, 18 November 2026: «клод не рахується?»)
CLAUDE_DIVISOR = 40   # 35 until 28 November 2026 (user: «на 40 зроби»)


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


def backfill_claude() -> None:
    """Once: the Claude run reports written before Claude went into the journal, the latest report of each run log."""
    marker = store.DATA_ROOT / CLAUDE_BACKFILLED
    if marker.exists():
        return
    latest = {}
    for path in store.PROJECTS_ROOT.glob("*/spend/*.json"):
        try:
            row = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        cost, log = row.get("cost_usd"), row.get("log")
        if not isinstance(cost, (int, float)) or cost <= 0 or not log:
            continue
        key = (path.parents[1].name, log)
        at = row.get("made_at") or path.stat().st_mtime
        if key not in latest or at > latest[key]["at"]:
            latest[key] = {"at": at, "provider": "claude_code", "amount": cost, "identity": log, "category": "production",
                           "project": key[0]}
    try:
        with open(store.DATA_ROOT / LEDGER, "a", encoding="utf-8") as out:
            for line in latest.values():
                out.write(json.dumps(line, ensure_ascii=False) + "\n")
        marker.write_text("done")
    except OSError:
        pass


VIDEO_BACKFILLED = "spending-ledger.video-voice-backfilled"


def backfill_videos() -> None:
    """Once: the host's HeyGen videos and the voices of translations, which reached only the project cards before
    (user, 25 November 2026: «сюди не записується нічого на рахунок Хейгена»), with the times of their receipts."""
    marker = store.DATA_ROOT / VIDEO_BACKFILLED
    if marker.exists():
        return
    import project_costs
    lines = []
    token = project_costs.JOURNAL_ON.set(False)   # read the receipts afresh without writing; the lines go in below
    try:
        for root in sorted(store.PROJECTS_ROOT.glob("*")):
            if not (root / "project.json").is_file():
                continue
            try:
                fresh = project_costs.collect(root, {})
            except (OSError, ValueError, KeyError, TypeError):
                continue
            for key, event in fresh.get("events", {}).items():
                amount = event.get("amount")
                if (event.get("provider") in project_costs.JOURNAL_PROVIDERS and event.get("category") in ("video", "voice")
                        and isinstance(amount, (int, float)) and amount > 0 and event.get("at")):
                    lines.append({"at": event["at"], "provider": event["provider"], "amount": amount,
                                  "identity": key.split(":", 1)[1], "category": event["category"], "project": root.name})
    finally:
        project_costs.JOURNAL_ON.reset(token)
    try:
        with open(store.DATA_ROOT / LEDGER, "a", encoding="utf-8") as out:
            for line in lines:
                out.write(json.dumps(line, ensure_ascii=False) + "\n")
        marker.write_text("done")
    except OSError:
        pass


def charge(provider: str, amount, identity: str, category: str, owner: str) -> None:
    """A paid request outside any project (a channel's voice sample) in the studio-wide journal."""
    if not isinstance(amount, (int, float)) or amount <= 0:
        return
    try:
        with open(store.DATA_ROOT / LEDGER, "a", encoding="utf-8") as out:
            out.write(json.dumps({"at": round(time.time(), 1), "provider": provider, "amount": amount, "identity": identity,
                                  "category": category, "project": owner}, ensure_ascii=False) + "\n")
    except OSError:
        pass
    with _LOCK:
        _CACHE.clear()


PROVIDERS = ("heygen", "elevenlabs", "fishaudio", "claude_code")


def receipts(now: float) -> dict:
    """HeyGen, ElevenLabs, Fish Audio and Claude from the studio-wide journal (project_costs.ledger), which outlives
    deleted projects; every project's index is brought up to date first, so a charge known to its receipts counts."""
    backfill()
    backfill_claude()
    backfill_videos()
    try:
        import project_costs
        project_costs.refresh_all()
    except Exception:   # the panel shows what the journal has; a broken project never hides the totals
        pass
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
                if row.get("provider") in PROVIDERS and (row.get("at") or 0) >= edges["month"]:
                    # a charge recorded twice counts once; a Claude run's report grows, its latest amount stands
                    rows[f"{row['provider']}:{row.get('project')}:{row.get('identity')}"] = row
    except OSError:
        pass
    totals = {name: {"day": 0.0, "week": 0.0, "month": 0.0} for name in PROVIDERS}
    for row in rows.values():
        amount = row.get("amount")
        if not isinstance(amount, (int, float)):
            continue
        usd = (amount if row["provider"] in ("heygen", "fishaudio") else amount / CLAUDE_DIVISOR if row["provider"] == "claude_code"
               else (amount * rate if rate else 0))
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


CHANNELS = "spending-channels.json"   # project id → channel id, kept after a project is deleted


def project_channels() -> dict:
    """Which channel each project belongs to, remembered for good: a deleted project's charges still count to its channel."""
    path = store.DATA_ROOT / CHANNELS
    known = store.read_json(path, {}) or {}
    changed = False
    for project in store.PROJECTS_ROOT.glob("*/project.json"):
        if project.parent.name in known:
            continue
        channel = (store.read_json(project, {}) or {}).get("channel_id")
        if channel:
            known[project.parent.name] = channel
            changed = True
    if changed:
        try:
            store.atomic_json(path, known)
        except OSError:
            pass
    return known


def channel_summary(cid: str, now: float | None = None) -> dict:
    """One channel's spending today and this month by service, from the studio-wide journal: projects' charges (deleted
    projects too) and the channel's own voice samples. OpenRouter here is what the studio's requests recorded; the
    limits panel reads the whole OpenRouter account instead (user, 25 November 2026: «витрати також в налаштування
    каналу… навіть якщо я видаляю проект, все має бути записано»)."""
    now = time.time() if now is None else now
    backfill(); backfill_claude(); backfill_videos()
    try:
        import project_costs
        project_costs.refresh_all()
    except Exception:
        pass
    edges = windows(now)
    owners = project_channels()
    rate = (store.read_json(store.DATA_ROOT / "eleven-credit-usd.json", {}) or {}).get("credit_usd_rate")
    rows = {}
    try:
        with open(store.DATA_ROOT / LEDGER, encoding="utf-8") as source:
            for text in source:
                try:
                    row = json.loads(text)
                except ValueError:
                    continue
                channel = row.get("channel") or owners.get(row.get("project")) or (
                    str(row.get("project"))[8:] if str(row.get("project", "")).startswith("channel:") else None)
                if channel == cid and (row.get("at") or 0) >= edges["month"]:
                    rows[f"{row.get('provider')}:{row.get('project')}:{row.get('identity')}"] = row
    except OSError:
        pass
    names = ("claude_code", "openrouter", "heygen", "elevenlabs", "fishaudio")
    totals = {name: {"day": 0.0, "month": 0.0} for name in names}
    for row in rows.values():
        provider, amount = row.get("provider"), row.get("amount")
        if provider not in totals or not isinstance(amount, (int, float)):
            continue
        usd = (amount / CLAUDE_DIVISOR if provider == "claude_code" else amount * rate if provider == "elevenlabs"
               else amount) if (provider != "elevenlabs" or rate) else 0
        for window in ("day", "month"):
            if row["at"] >= edges[window]:
                totals[provider][window] += usd
    services = {name: {k: round(v, 4) for k, v in values.items()} for name, values in totals.items()}
    total = {window: round(sum(values[window] for values in services.values()), 4) for window in ("day", "month")}
    return {"services": services, "total": total, "checked_at": now}
