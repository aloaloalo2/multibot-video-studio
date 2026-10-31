#!/usr/bin/env python3
"""Restart VideoKey Studio so that it outlives the agent that restarted it.

    python3 "VideoKey Studio/tools/studio_restart.py"            # restart, or start if it is down
    python3 "VideoKey Studio/tools/studio_restart.py" --check    # only show what is running now, change nothing

A server started from an agent's own shell (`nohup python3 backend/app.py &`) stays in that agent's process tree and dies
with the session: on 30 October 2026 the studio went down at 16:38 when the Claude sessions closed. This script starts it
in its own session (parent launchd), the same way the studio starts its own director and live-view processes.

Before stopping a running studio it asks it what is in progress (exports, speech recognition, director, frame creation,
thumbnails, the studio agent) and refuses while anything is, because a restart breaks all of them. --force skips that.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
LOG = Path.home() / "Library/Logs/VideoKey Studio/server.log"
HOST, PORT = "127.0.0.1", 8770
STUDIO = f"http://{HOST}:{PORT}"
BUSY = {"queued", "running", "in_progress", "cancelling"}


def get(path: str, timeout: float = 5):
    try:
        with urllib.request.urlopen(STUDIO + path, timeout=timeout) as response:
            return json.loads(response.read())
    except (OSError, ValueError):
        return None


def alive() -> bool:
    return (get("/api/health", 1) or {}).get("service") == "multibot-video-studio"


def busy_work() -> list[str]:
    """Everything the running studio would lose on a restart, one line each: one request to a studio that has
    /api/studio/status, a walk over every project for an older one."""
    status = get("/api/studio/status", 30)
    if isinstance(status, dict) and isinstance(status.get("busy"), list):
        return status["busy"]
    found = [f"експорт {job['project_id']}: {job.get('progress', 0)}%, {job.get('stage', '')}"
             for job in (get("/api/exports/active") or {}).get("jobs", []) if job.get("status") in BUSY]
    for channel in (get("/api/channels") or {}).get("channels", []):
        for item in (get(f"/api/projects?channel={channel['id']}") or {}).get("projects", []):
            pid, name = item["id"], item.get("name") or item["id"]
            request = ((get(f"/api/projects/{pid}") or {}).get("project") or {}).get("production_request")
            checks = {
                "розпізнавання озвучки": ((get(f"/api/projects/{pid}/analysis") or {}).get("job") or {}).get("status"),
                "режисура": ((get(f"/api/projects/{pid}/director") or {}).get("director") or {}).get("status"),
                "створення кадрів": request.get("status") if isinstance(request, dict) else None,
                "прев'ю": ((get(f"/api/projects/{pid}/thumbnail") or {}).get("job") or {}).get("status"),
                "агент студії": ((get(f"/api/projects/{pid}/agent") or {}).get("job") or {}).get("status"),
            }
            found += [f"{what}: {channel.get('name')} / {name}" for what, status in checks.items() if status in BUSY]
    return found


def listener() -> int | None:
    out = subprocess.run(["lsof", "-tiTCP:%d" % PORT, "-sTCP:LISTEN"], capture_output=True, text=True).stdout.split()
    return int(out[0]) if out else None


def stop(pid: int) -> bool:
    os.kill(pid, signal.SIGTERM)
    for _ in range(40):
        if listener() is None:
            return True
        time.sleep(0.25)
    return False


def start() -> int:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "ab") as log:
        process = subprocess.Popen([sys.executable, "-u", "backend/app.py", "--host", HOST, "--port", str(PORT)], cwd=APP,
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(80):
        if alive():
            return process.pid
        if process.poll() is not None:
            break
        time.sleep(0.25)
    sys.exit(f"Студія не запустилася. Діагностика: {LOG}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="лише показати, що зараз виконується, нічого не змінювати")
    parser.add_argument("--force", action="store_true", help="перезапустити, навіть якщо щось виконується")
    args = parser.parse_args()

    running = alive()
    work = busy_work() if running else []
    print("Студія працює" if running else "Студія не відповідає")
    for line in work:
        print(" · " + line)
    if args.check:
        sys.exit(1 if work else 0)
    if work and not args.force:
        sys.exit("Перезапуск обірве це. Дочекайтеся завершення або запустіть з --force, якщо користувач погодив.")

    old = listener()
    if old and not stop(old):
        sys.exit(f"Стара студія (pid {old}) не зупинилася за 10 с, нову не запускаю")
    pid = start()
    print(f"Студію запущено окремо від сесії агента: pid {pid}, {STUDIO}/")


if __name__ == "__main__":
    main()
