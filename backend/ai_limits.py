"""How much of the 5-hour limit Claude Code and Codex have left (user, 14 November 2026: «ліміти кодекса і ліміти
клод-кода… лише 5-годинні… скільки залишилось»).

Claude Code is read from its account usage endpoint with the existing local CLI
login. This is a read-only account request, not a model call. Local stream logs
are an explicitly dated fallback. Codex uses its existing session rate-limit
receipts. Credentials never enter responses, saved state or diagnostic messages.
"""
from __future__ import annotations

import os
import json
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
import re
import threading
import time
from pathlib import Path

WINDOW = 5 * 3600
TAIL = 2 * 1024 * 1024        # the latest events sit at a log's end
CACHE_SECONDS = 15
# The account usage route answers 429 «Rate limited» when asked every few seconds (15 November 2026: the panel froze on
# «Останні дані: 9 хв тому»). Ask it at most every ACCOUNT_EVERY seconds, wait as long as a 429 says (or
# ACCOUNT_BACKOFF), and in between take the studio runs' own rate_limit_event receipts when they are newer.
ACCOUNT_EVERY = 180
ACCOUNT_BACKOFF = 600
ACCOUNT_RETRY = 60
_ACCOUNT: dict = {}

# Claude's plan may have a 5-hour window and a weekly one, or the weekly one alone (user, 15 November 2026: «у мене тижн
# ліміт тепер лише в клода»): the window shown is the 5-hour one when the newest receipt has it, else the weekly one.
CLAUDE_WINDOW = re.compile(rb'"(five_hour|seven_day)":\{"utilization":([0-9.]+),"resetsAt":([0-9]+)')
CLAUDE_LOGS = 30          # the newest studio logs are enough to find the newest receipts
WEEK = 7 * 86400
CODEX = re.compile(rb'\{"used_percent":([0-9.]+),"window_minutes":300,"resets_at":([0-9]+)\}')

_LOCK = threading.Lock()
_CACHE: dict = {}


def _recent(paths, now: float, within: float = WINDOW):
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            continue
        if now - stat.st_mtime <= within:
            yield path, stat


def _tail(path: Path, size: int) -> bytes:
    try:
        with open(path, "rb") as source:
            source.seek(max(0, size - TAIL))
            return source.read()
    except OSError:
        return b""


def _best(found):
    """[(used 0..1, resets_at, seen_at)] → the newest window with its highest use."""
    if not found:
        return None
    resets = max(item[1] for item in found)
    same = [item for item in found if item[1] == resets]
    used = max(item[0] for item in same)
    seen = max(item[2] for item in same)
    return used, resets, seen


def claude_logs(data_root: Path):
    return (data_root / "projects").glob("*/*.log")


def codex_logs(home: Path):
    return (home / ".codex" / "sessions").rglob("*.jsonl")


def read(data_root: Path, home: Path | None = None, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    home = Path(home or os.path.expanduser("~"))
    claude, codex = {"five_hour": [], "seven_day": []}, []
    newest, kinds = 0.0, set()
    logs = sorted(((stat.st_mtime, path, stat) for path, stat in _recent(claude_logs(data_root), now, WEEK)), reverse=True)
    for mtime, path, stat in logs[:CLAUDE_LOGS]:
        events = [line for line in _tail(path, stat.st_size).split(b"\n") if b'"rate_limit_event"' in line]
        for order, event in enumerate(events):
            for kind, used, resets in CLAUDE_WINDOW.findall(event):
                claude[kind.decode()].append((float(used), int(resets), mtime, order))
        if events and mtime > newest:
            newest, kinds = mtime, {kind.decode() for kind, _, _ in CLAUDE_WINDOW.findall(events[-1])}
    window = "five_hour" if "five_hour" in kinds or not kinds and claude["five_hour"] else "seven_day"
    for path, stat in _recent(codex_logs(home), now):
        text = _tail(path, stat.st_size)
        codex += [(float(u) / 100, int(r), stat.st_mtime) for u, r in CODEX.findall(text)]
    # Codex writes a receipt with every request it makes, so its newest one is current however old it is: no work, no
    # use (15 November 2026: «Останні дані: 22 хв тому» over a Codex that had simply been idle).
    codex_view = _view(_best(codex), now)
    if codex_view.get("known"):
        codex_view["stale"] = False
    # the newest receipt wins: a plan change renews a window in place (15 November 2026: the weekly window went from
    # 98% used to 0 with the same reset time when the 5-hour one went away)
    found = [item for item in claude[window] if window == "seven_day" or now - item[2] <= WINDOW]
    latest = max(found, key=lambda item: (item[2], item[3]), default=None)
    claude_view = _view(latest[:3] if latest else None, now)
    if claude_view.get("known"):
        claude_view["window"] = window
    return {"claude": claude_view, "codex": codex_view, "checked_at": now}


def _view(best, now: float) -> dict:
    if not best:
        return {"known": False}
    used, resets, seen = best
    if resets <= now:
        return {"known": False, "reset": True, "resets_at": None, "seen_at": seen, "source":"logs", "stale":True}
    return {"known": True, "left": max(0, min(100, round(100 - used * 100))), "reset": False,
            "resets_at": resets, "seen_at": seen, "source":"logs", "stale":now-seen>90}


def claude_usage(home=None, now=None):
    """Use the same OAuth usage route as the installed CLI, without refreshing auth."""
    home=Path(home or Path.home());now=time.time() if now is None else now
    try:
        credentials=home/'.claude/.credentials.json'
        if credentials.is_file():
            saved=json.loads(credentials.read_text())
        elif sys.platform=='darwin':
            command=subprocess.run(['security','find-generic-password','-s','Claude Code-credentials','-w'],
                                   capture_output=True,text=True,timeout=3)
            if command.returncode:return None
            saved=json.loads(command.stdout)
        else:return None
        if not isinstance(saved,dict):return None
        token=(saved.get('claudeAiOauth') or {}).get('accessToken')
        if not isinstance(token,str) or not token:return None
        request=urllib.request.Request('https://api.anthropic.com/api/oauth/usage?skip_spend=1',headers={
            'Authorization':'Bearer '+token,'anthropic-beta':'oauth-2025-04-20','User-Agent':'VideoKey-Studio/1.0'})
        try:
            with urllib.request.urlopen(request,timeout=5) as response:data=json.load(response)
        except urllib.error.HTTPError as error:
            if error.code==429:
                try:wait=float(error.headers.get('Retry-After') or ACCOUNT_BACKOFF)
                except (TypeError,ValueError):wait=ACCOUNT_BACKOFF
                return {'retry_after':max(ACCOUNT_EVERY,min(wait,3600))}
            return None
        kind='five_hour' if isinstance(data.get('five_hour'),dict) else 'seven_day'
        window=data.get(kind) or {}
        utilization=window.get('utilization')
        if type(utilization) not in (int,float) or not 0<=utilization<=100:return None
        resets=datetime.fromisoformat(window['resets_at'].replace('Z','+00:00')).timestamp()
        if resets<=now:return None
        return {**_view((utilization/100,resets,now),now),'source':'account','stale':False,'window':kind}
    except (OSError,ValueError,TypeError,KeyError,AttributeError,subprocess.SubprocessError):
        return None


def codex_usage(home=None, now=None):
    """Codex's own account usage, the route its CLI reads for /status, with the existing local login and no refresh.
    The session logs only know the last request Codex made, so after an idle while, a reset or another login they showed
    an old remainder (user, 15 November 2026: «кодекс ліміт теж не правильно показує не актуально»)."""
    home=Path(home or Path.home());now=time.time() if now is None else now
    try:
        saved=json.loads((home/'.codex'/'auth.json').read_text())
        tokens=saved.get('tokens') or {}
        token=tokens.get('access_token')
        if not isinstance(token,str) or not token:return None
        headers={'Authorization':'Bearer '+token,'User-Agent':'VideoKey-Studio/1.0'}
        if isinstance(tokens.get('account_id'),str) and tokens['account_id']:headers['ChatGPT-Account-Id']=tokens['account_id']
        request=urllib.request.Request('https://chatgpt.com/backend-api/wham/usage',headers=headers)
        try:
            with urllib.request.urlopen(request,timeout=5) as response:data=json.load(response)
        except urllib.error.HTTPError as error:
            if error.code==429:
                try:wait=float(error.headers.get('Retry-After') or ACCOUNT_BACKOFF)
                except (TypeError,ValueError):wait=ACCOUNT_BACKOFF
                return {'retry_after':max(ACCOUNT_EVERY,min(wait,3600))}
            return None
        window=(data.get('rate_limit') or {}).get('primary_window') or {}
        used=window.get('used_percent')
        resets=window.get('reset_at')
        if type(used) not in (int,float) or not 0<=used<=100 or type(resets) not in (int,float) or resets<=now:return None
        result={**_view((used/100,float(resets),now),now),'source':'account','stale':False}
        # the weekly window too: the grey track of the indicator shows what is left of the week (user, 16 November 2026:
        # «недільний ліміт теж враховував для кодексу»)
        week=(data.get('rate_limit') or {}).get('secondary_window') or {}
        week_used,week_resets=week.get('used_percent'),week.get('reset_at')
        if type(week_used) in (int,float) and 0<=week_used<=100 and type(week_resets) in (int,float) and week_resets>now:
            result.update(week_left=max(0,min(100,round(100-week_used))),week_resets_at=float(week_resets))
        return result
    except (OSError,ValueError,TypeError,KeyError,AttributeError):
        return None


_CODEX_ACCOUNT: dict = {}


def _account(now: float, state: dict | None = None, fetch=None):
    """The latest account reading, asked again only when its time has come."""
    state = _ACCOUNT if state is None else state
    fetch = fetch or claude_usage
    if now >= state.get('next', 0):
        got = fetch()
        if got and 'retry_after' in got:
            state['next'] = now + got['retry_after']
        elif got:
            state.update(value=got, next=now + ACCOUNT_EVERY)
        else:
            state['next'] = now + ACCOUNT_RETRY
    account = state.get('value')
    return account if account and (account.get('resets_at') or 0) > now else None


def _merge(account, logs, now: float) -> dict:
    """The account reading, unless a studio run reported the same window later: use only grows within a window."""
    if not account:
        return logs
    if logs.get('known') and (logs.get('seen_at') or 0) > (account.get('seen_at') or 0):
        same = (logs.get('window', 'five_hour') == account.get('window', 'five_hour')
                and abs((logs.get('resets_at') or 0) - account['resets_at']) < 300)
        fresh = now - (account.get('seen_at') or 0) <= ACCOUNT_EVERY + 60
        # the same window: use only grows, the lower remainder wins. Another window: a fresh account reading wins, since
        # a run log's time is the file's and can move without a new receipt (user, 15 November 2026: the panel showed
        # «на 5 годин лишилось 25%» from the morning's receipts while the account had only its weekly window, 94% left)
        week = {key: account[key] for key in ('week_left', 'week_resets_at') if key in account}
        if same:
            return {**logs, 'left': min(logs['left'], account['left']), **week}
        if not fresh:
            return {**logs, **week}
    return {**account, 'stale': now - (account.get('seen_at') or 0) > ACCOUNT_EVERY + 60}


def cached(data_root: Path) -> dict:
    with _LOCK:
        now = time.time()
        if _CACHE.get('root') == str(data_root) and _CACHE.get("at", 0) > now - CACHE_SECONDS:
            return _CACHE["value"]
        value = read(data_root)
        value['claude'] = _merge(_account(now), value['claude'], now)
        value['codex'] = _merge(_account(now, _CODEX_ACCOUNT, codex_usage), value['codex'], now)
        _CACHE.update(root=str(data_root), at=time.time(), value=value)
        return value
