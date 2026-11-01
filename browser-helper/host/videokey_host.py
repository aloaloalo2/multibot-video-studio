#!/usr/bin/python3
"""The browser extension's helper: starts VideoKey Studio on this Mac and nothing else.

The browser runs it for the Multi Bot extension only (the allowed origin in its manifest, written by install.py via
«Встановити.command»). install.py copies it to ~/Library/Application Support/VideoKey Studio with config.json naming
«Запустить студию.command»: macOS does not let Chrome run programs from a protected folder such as Documents, where the
studio may live (user, 1 November 2026: «помощник не установлен», though it was). It reads one message
({"command": "start"}) and starts the server directly, with no Terminal (start_directly); only when that fails it asks
macOS to open the command, as a double click does, in a hidden Terminal (`open -g -j`), with a marker so the command
opens no second tab. It waits
until the studio answers and replies {"ok": true}, or {"ok": false, "error": ...}.
"""
import json
import struct
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
HEALTH = "http://127.0.0.1:8770/api/health"
MARKER = Path.home() / "Library/Caches/VideoKey Studio/no-open"


LOG = Path.home() / "Library/Logs/VideoKey Studio/server.log"


def command() -> Path:
    try:
        return Path(json.loads((HERE / "config.json").read_text(encoding="utf-8"))["command"])
    except (OSError, ValueError, KeyError, TypeError):
        return HERE.parents[1] / "Запустить студию.command"   # run from the studio's own folder


def wait_alive(seconds: float) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        if alive():
            return True
        time.sleep(0.5)
    return False


def start_directly(app: Path) -> bool:
    """Start the server with no Terminal at all (user, 1 November 2026: «запускає та кнопка всеодно термінал»): its
    own session, the same start the studio's tools use. macOS may first ask to let Chrome into the folder the studio
    lives in (Documents); until that is allowed, or when it is refused, this fails and the command is opened instead."""
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "ab") as log:
            process = subprocess.Popen(["/usr/bin/python3", "-u", "backend/app.py", "--host", "127.0.0.1", "--port", "8770"],
                                       cwd=app, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    except OSError:
        return False
    end = time.time() + 25
    while time.time() < end:
        if alive():
            return True
        if process.poll() is not None:
            return False
        time.sleep(0.5)
    return alive()


def read():
    size = sys.stdin.buffer.read(4)
    if len(size) < 4:
        return None
    return json.loads(sys.stdin.buffer.read(struct.unpack("<I", size)[0]))


def send(message):
    data = json.dumps(message, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(data)) + data)
    sys.stdout.buffer.flush()


def alive():
    try:
        with urllib.request.urlopen(HEALTH, timeout=1) as response:
            return b"multibot-video-studio" in response.read()
    except OSError:
        return False


def main():
    message = read()
    if not isinstance(message, dict) or message.get("command") != "start":
        send({"ok": False, "error": "Невідома команда"})
        return
    if alive():
        send({"ok": True})
        return
    target = command()
    if start_directly(target.parent):
        send({"ok": True})
        return
    MARKER.parent.mkdir(parents=True, exist_ok=True)
    MARKER.write_text(str(time.time()))
    run = subprocess.run(["/usr/bin/open", "-g", "-j", str(target)], capture_output=True, text=True, timeout=30)
    if run.returncode:
        send({"ok": False, "error": "macOS не відкрив «Запустить студию.command»: " + (run.stderr or run.stdout).strip()[-200:]})
        return
    if wait_alive(60):            # the update check at start can take a while
        send({"ok": True})
        return
    send({"ok": False, "error": "Студія не відповіла за хвилину. Журнал: ~/Library/Logs/VideoKey Studio/server.log"})


if __name__ == "__main__":
    main()
