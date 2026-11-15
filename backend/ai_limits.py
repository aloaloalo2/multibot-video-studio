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

CLAUDE = re.compile(rb'"five_hour":\{"utilization":([0-9.]+),"resetsAt":([0-9]+)')
CLAUDE_PLAIN = re.compile(rb'"resetsAt":([0-9]+),"rateLimitType":"five_hour"[^}]*?"utilization":([0-9.]+)')
CODEX = re.compile(rb'\{"used_percent":([0-9.]+),"window_minutes":300,"resets_at":([0-9]+)\}')

_LOCK = threading.Lock()
_CACHE: dict = {}


def _recent(paths, now: float):
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            continue
        if now - stat.st_mtime <= WINDOW:
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
    claude, codex = [], []
    for path, stat in _recent(claude_logs(data_root), now):
        text = _tail(path, stat.st_size)
        claude += [(float(u), int(r), stat.st_mtime) for u, r in CLAUDE.findall(text)]
        claude += [(float(u), int(r), stat.st_mtime) for r, u in CLAUDE_PLAIN.findall(text)]
    for path, stat in _recent(codex_logs(home), now):
        text = _tail(path, stat.st_size)
        codex += [(float(u) / 100, int(r), stat.st_mtime) for u, r in CODEX.findall(text)]
    # Codex writes a receipt with every request it makes, so its newest one is current however old it is: no work, no
    # use (15 November 2026: «Останні дані: 22 хв тому» over a Codex that had simply been idle).
    codex_view = _view(_best(codex), now)
    if codex_view.get("known"):
        codex_view["stale"] = False
    return {"claude": _view(_best(claude), now), "codex": codex_view, "checked_at": now}


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
        window=data.get('five_hour') or {}
        utilization=window.get('utilization')
        if type(utilization) not in (int,float) or not 0<=utilization<=100:return None
        resets=datetime.fromisoformat(window['resets_at'].replace('Z','+00:00')).timestamp()
        if resets<=now:return None
        return {**_view((utilization/100,resets,now),now),'source':'account','stale':False}
    except (OSError,ValueError,TypeError,KeyError,AttributeError,subprocess.SubprocessError):
        return None


def _account(now: float):
    """The latest account reading, asked again only when its time has come."""
    if now >= _ACCOUNT.get('next', 0):
        got = claude_usage()
        if got and 'retry_after' in got:
            _ACCOUNT['next'] = now + got['retry_after']
        elif got:
            _ACCOUNT.update(value=got, next=now + ACCOUNT_EVERY)
        else:
            _ACCOUNT['next'] = now + ACCOUNT_RETRY
    account = _ACCOUNT.get('value')
    return account if account and (account.get('resets_at') or 0) > now else None


def _merge(account, logs, now: float) -> dict:
    """The account reading, unless a studio run reported the same window later: use only grows within a window."""
    if not account:
        return logs
    same = logs.get('known') and abs((logs.get('resets_at') or 0) - account['resets_at']) < 300
    if same and (logs.get('seen_at') or 0) > (account.get('seen_at') or 0):
        return {**logs, 'left': min(logs['left'], account['left'])}
    return {**account, 'stale': now - (account.get('seen_at') or 0) > ACCOUNT_EVERY + 60}


def cached(data_root: Path) -> dict:
    with _LOCK:
        now = time.time()
        if _CACHE.get('root') == str(data_root) and _CACHE.get("at", 0) > now - CACHE_SECONDS:
            return _CACHE["value"]
        value = read(data_root)
        value['claude'] = _merge(_account(now), value['claude'], now)
        _CACHE.update(root=str(data_root), at=time.time(), value=value)
        return value
