#!/usr/bin/python3
"""The browser extension's helper: starts VideoKey Studio on this Mac and nothing else.

The browser runs it for the Multi Bot extension only (the allowed origin in its manifest, written by install.py via
«Встановити.command»). It reads one message ({"command": "start"}), runs «Запустить студию.command» in its own session
(so the studio outlives the helper and the browser) without opening a tab, waits until the studio answers and replies
{"ok": true}, or {"ok": false, "error": ...}.
"""
import json
import os
import struct
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parents[2]
COMMAND = APP / "Запустить студию.command"
HEALTH = "http://127.0.0.1:8770/api/health"
LOG = Path.home() / "Library/Logs/VideoKey Studio/extension.log"


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
    if not COMMAND.is_file():
        send({"ok": False, "error": f"Не знайдено {COMMAND.name} у папці студії"})
        return
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "ab") as log:
        subprocess.Popen(["/bin/zsh", str(COMMAND)], cwd=APP, env={**os.environ, "VIDEOKEY_NO_OPEN": "1"},
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    for _ in range(120):          # the update check at start can take a while
        if alive():
            send({"ok": True})
            return
        time.sleep(0.5)
    send({"ok": False, "error": f"Студія не відповіла за хвилину. Діагностика: {LOG.parent / 'server.log'}"})


if __name__ == "__main__":
    main()
