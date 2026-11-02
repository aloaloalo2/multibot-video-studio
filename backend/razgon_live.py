"""Live preview for Razgon 2D episodes: no render, the Razgon player draws frames in real time in an iframe.

An episode folder that holds razgon.json ({"razgon_root", "project"}) gets a "Наживо" tab. Opening it starts
`node tools/live.mjs` for that Razgon project on a port derived from the project path (one server per project) and
returns its URL. The server keeps running for quick re-opens and reloads the page whenever the scenes change.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import store


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
    return {"root": root, "project": proj, "port": 8781 + int(hashlib.sha256(str(proj).encode()).hexdigest()[:6], 16) % 200}


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
    running = bool(health and health.get("project") == str(info["project"]))
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


def start(pid: str, restart: bool = False) -> dict:
    info = link(store.load_project(pid))
    if not info:
        raise store.StudioError("Для цього випуску немає проєкту Razgon", 404)
    url = f"http://127.0.0.1:{info['port']}/live.html"
    if restart:
        # «Перезапустити перегляд»: the live server of this project stops and starts afresh (user, 2 November 2026:
        # «всеодно сіре, хоча код є»); only a server that answers for this very project is stopped
        old = _listener(info["port"])
        health = _health(info["port"])
        if old and (not health or health.get("project") == str(info["project"])):
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
    if health and health.get("project") == str(info["project"]):
        return {"available": True, "running": True, "url": url}
    if health:
        raise store.StudioError("Порт живого перегляду зайнятий іншим проєктом", 409)
    node = shutil.which("node") or "/opt/homebrew/bin/node"
    log = open(info["project"] / "build" / "live.log", "ab")
    subprocess.Popen([node, "tools/live.mjs", "--project", str(info["project"]), "--port", str(info["port"])],
                     cwd=info["root"], stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
    for _ in range(40):
        time.sleep(0.15)
        if _health(info["port"]):
            return {"available": True, "running": True, "url": url}
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
