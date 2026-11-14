"""How much of the 5-hour limit Claude Code and Codex have left (user, 14 November 2026: «ліміти кодекса і ліміти
клод-кода… лише 5-годинні… скільки залишилось»).

Both are read from what the tools already write on this Mac, so a look costs no request and no limit:
- Claude Code prints a `rate_limit_event` into the stream-json log of every studio run (director, frame agent): the
  five-hour window's `utilization` (0..1) and `resetsAt`. Claude Code sessions outside the studio write no such log,
  so the value is the one of the latest studio run, with the time it was seen.
- Codex writes `rate_limits` into its session files (~/.codex/sessions): the window of 300 minutes has `used_percent`
  and `resets_at`.

Within one window the use only grows, so of all events the newest window counts with its highest use. A window whose
reset time has passed is shown as reset (100% left) until a new event says otherwise.
"""
from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path

WINDOW = 5 * 3600
TAIL = 2 * 1024 * 1024        # the latest events sit at a log's end
CACHE_SECONDS = 60

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
    return {"claude": _view(_best(claude), now), "codex": _view(_best(codex), now), "checked_at": now}


def _view(best, now: float) -> dict:
    if not best:
        return {"known": False}
    used, resets, seen = best
    if resets <= now:
        return {"known": True, "left": 100, "reset": True, "resets_at": None, "seen_at": seen}
    return {"known": True, "left": max(0, min(100, round(100 - used * 100))), "reset": False,
            "resets_at": resets, "seen_at": seen}


def cached(data_root: Path) -> dict:
    with _LOCK:
        if _CACHE.get("at", 0) > time.time() - CACHE_SECONDS:
            return _CACHE["value"]
    value = read(data_root)
    with _LOCK:
        _CACHE.update(at=time.time(), value=value)
    return value
