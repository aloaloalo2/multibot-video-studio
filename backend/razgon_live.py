"""Live preview for Razgon 2D episodes: no render, the Razgon player draws frames in real time in an iframe.

A Studio project with an internal razgon-link.json ({"razgon_root", "project"}) gets a "Наживо" tab. Opening it starts
`node tools/live.mjs` for that Razgon project on a saved free port (one server per project) and
returns its URL. The server keeps running for quick re-opens and reloads the page whenever the scenes change.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import store

START_LOCK = threading.RLock()


def _saved_port(project: Path, preferred: int) -> int:
    try:
        saved = store.read_json(project / 'build' / 'live-server.json', {}) or {}
    except (OSError, ValueError):
        return preferred
    if not isinstance(saved, dict):
        return preferred
    port = saved.get('port')
    return port if (saved.get('project') == str(project) and type(port) is int and 1024 <= port <= 65535) else preferred


def _remember(info: dict) -> None:
    store.atomic_json(info['project'] / 'build' / 'live-server.json',
                      {'project': str(info['project']), 'port': info['port']})


def _free_port(preferred: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(('127.0.0.1', preferred))
        except OSError:
            probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def _owns(health, info: dict) -> bool:
    return bool(isinstance(health, dict) and health.get('service') == 'razgon-live'
                and health.get('project') == str(info['project']))


def link(project: dict) -> dict | None:
    data = store.razgon_link(project)   # the episode folder's, or the studio's copy when that folder is gone
    if not data:
        return None
    try:
        root, proj = Path(data["razgon_root"]), Path(data["project"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not (root / "tools" / "live.mjs").is_file() or not (proj / "config.json").is_file():
        return None
    preferred = 8781 + int(hashlib.sha256(str(proj).encode()).hexdigest()[:6], 16) % 200
    return {"root": root, "project": proj, "port": _saved_port(proj, preferred)}


def _health(port: int) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/__health", timeout=0.6) as response:
            return json.loads(response.read())
    except (OSError, ValueError):
        return None


def status(pid: str) -> dict:
    info = link(store.load_project(pid))
    if not info:
        return {"available": False}
    health = _health(info["port"])
    running = _owns(health, info)
    return {"available": True, "running": running, "url": f"http://127.0.0.1:{info['port']}/live.html"}


def _listener(port: int) -> int | None:
    found = subprocess.run(["lsof", "-tiTCP:%d" % port, "-sTCP:LISTEN"], capture_output=True, text=True).stdout.split()
    return int(found[0]) if found else None


def _log_tail(project: Path) -> str:
    try:
        lines = [line.strip() for line in (project / "build" / "live.log").read_text(errors="replace").splitlines() if line.strip()]
    except OSError:
        return ""
    return lines[-1][-300:] if lines else ""


def patch_mixed_player(root: Path) -> None:
    """A mixed film's external photo is composited by Studio, not a missing Razgon scene."""
    live = root / "live.html"
    if live.is_file():
        source = live.read_text()
        sample = "const sample = window.SHOT_LIST.find(s => t >= s.start && t < s.end); const f = sample ? Math.max(Math.ceil(sample.start * fps - 1e-8), Math.min(Math.floor(t * fps + 1e-8), Math.ceil(sample.end * fps - 1e-8) - 1)) : Math.floor(t * fps + 1e-8);"
        fixed = source.replace("const f = Math.round(t * fps);", sample).replace("const f = Math.floor(t * fps + 1e-8);", sample) if "const sample = window.SHOT_LIST.find" not in source else source
        if fixed != source:
            store.atomic_text(live, fixed)
    path = root / "engine" / "player.js"
    if not path.is_file():
        return
    old = "const tr = shot.in || { type: 'cut' }"
    new = "const tr = (i > 0 && !getShot(E.shots[i - 1].id)) ? { type: 'cut' } : (shot.in || { type: 'cut' })"
    source = path.read_text()
    if old in source:
        store.atomic_text(path, source.replace(old, new, 1))


def start(pid: str, restart: bool = False) -> dict:
    # Concurrent preview requests must share the same project server and saved URL.
    with START_LOCK:
        return _start(pid, restart)


def _start(pid: str, restart: bool) -> dict:
    info = link(store.load_project(pid))
    if not info:
        raise store.StudioError("Для цього випуску немає проєкту Razgon", 404)
    patch_mixed_player(info["root"])
    url = f"http://127.0.0.1:{info['port']}/live.html"
    if restart:
        # «Перезапустити перегляд»: the live server of this project stops and starts afresh (user, 2 November 2026:
        # «всеодно сіре, хоча код є»); only a server that answers for this very project is stopped
        old = _listener(info["port"])
        health = _health(info["port"])
        if old and _owns(health, info):
            import os, signal
            try:
                os.kill(old, signal.SIGTERM)
            except OSError:
                pass
            for _ in range(30):
                if not _listener(info["port"]):
                    break
                time.sleep(0.1)
    health = _health(info["port"])
    if _owns(health, info):
        _remember(info)
        return {"available": True, "running": True, "url": url}
    node = shutil.which("node") or "/opt/homebrew/bin/node"
    (info['project'] / 'build').mkdir(parents=True, exist_ok=True)
    # A hashed preference can collide. Keep the other project running and retain our alternative URL.
    for _ in range(3):
        info['port'] = _free_port(info['port'])
        url = f"http://127.0.0.1:{info['port']}/live.html"
        with open(info["project"] / "build" / "live.log", "ab") as log:
            process = subprocess.Popen([node, "tools/live.mjs", "--project", str(info["project"]), "--port", str(info["port"])],
                         cwd=info["root"], stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
        for _ in range(40):
            time.sleep(0.15)
            health = _health(info['port'])
            if _owns(health, info):
                _remember(info)
                return {"available": True, "running": True, "url": url}
            if process.poll() is not None:
                break
        # Another app may bind between the probe and Node. Retry that local race only.
        if (health and not _owns(health, info)) or (process.poll() is not None and _listener(info['port'])):
            if process.poll() is None:
                process.terminate()
            continue
        if process.poll() is None:
            process.terminate()
        break
    tail = _log_tail(info["project"])
    raise store.StudioError("Живий перегляд не запустився." + (f" Останній рядок журналу: {tail}" if tail else
                            " Перевірте build/live.log у проєкті Razgon"), 500)


def clean_build(project: dict) -> None:
    """Remove the linked Razgon project's render leftovers with its own tool; it skips renders that are still running."""
    info = link(project)
    tool = info and info["root"] / "tools" / "clean_build.py"
    if tool and tool.is_file():
        subprocess.run([sys.executable, str(tool), "--project", str(info["project"]), "--apply"], cwd=info["root"],
                       capture_output=True, timeout=600)
