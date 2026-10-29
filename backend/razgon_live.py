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
    path = Path(project.get("episode_path", "")) / "razgon.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
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


def start(pid: str) -> dict:
    info = link(store.load_project(pid))
    if not info:
        raise store.StudioError("Для цього випуску немає проєкту Razgon", 404)
    url = f"http://127.0.0.1:{info['port']}/live.html"
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
    raise store.StudioError("Живий перегляд не запустився. Перевірте build/live.log у проєкті Razgon", 500)


def clean_build(project: dict) -> None:
    """Remove the linked Razgon project's render leftovers with its own tool; it skips renders that are still running."""
    info = link(project)
    tool = info and info["root"] / "tools" / "clean_build.py"
    if tool and tool.is_file():
        subprocess.run([sys.executable, str(tool), "--project", str(info["project"]), "--apply"], cwd=info["root"],
                       capture_output=True, timeout=600)
