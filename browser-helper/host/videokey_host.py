#!/usr/bin/python3
"""The browser extension's helper: starts VideoKey Studio on this Mac and nothing else.

The browser runs it for the Multi Bot extension only (the allowed origin in its manifest, written by install.py via
«Встановити.command»). install.py copies it to ~/Library/Application Support/VideoKey Studio with config.json naming
«Запустить студию.command»: macOS does not let Chrome run programs from a protected folder such as Documents, where the
studio may live (user, 1 November 2026: «помощник не установлен», though it was). It reads one message
({"command": "start"}) and asks macOS to open the command, as a double click does, in a hidden Terminal (`open -g -j`),
so nothing of Chrome's needs to read the studio's folder; a marker tells the command not to open a second tab. It waits
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


def command() -> Path:
    try:
        return Path(json.loads((HERE / "config.json").read_text(encoding="utf-8"))["command"])
    except (OSError, ValueError, KeyError, TypeError):
        return HERE.parents[1] / "Запустить студию.command"   # run from the studio's own folder


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
    MARKER.parent.mkdir(parents=True, exist_ok=True)
    MARKER.write_text(str(time.time()))
    run = subprocess.run(["/usr/bin/open", "-g", "-j", str(target)], capture_output=True, text=True, timeout=30)
    if run.returncode:
        send({"ok": False, "error": "macOS не відкрив «Запустить студию.command»: " + (run.stderr or run.stdout).strip()[-200:]})
        return
    for _ in range(120):          # the update check at start can take a while
        if alive():
            send({"ok": True})
            return
        time.sleep(0.5)
    send({"ok": False, "error": "Студія не відповіла за хвилину. Журнал: ~/Library/Logs/VideoKey Studio/server.log"})


if __name__ == "__main__":
    main()
