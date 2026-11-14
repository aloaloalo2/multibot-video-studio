"""At most SLOTS stills renders (`render.mjs --stills`, one Chromium of about 2 GB each) at a time on this Mac, however
many frame sessions run side by side (user, 14 November 2026: «65 кадрів… 6 сесій… щоб швидко було»). The sessions
draw and think at once; only their Chromium waits for a free slot. Slots are lock files in the Razgon folder, so every
process sees the same ones, and a crashed holder frees its slot with its process.
"""
from __future__ import annotations

import contextlib
import fcntl
import os
import time
from pathlib import Path

SLOTS = max(1, int(os.environ.get("RAZGON_STILL_SLOTS", "2")))
WAIT = 1.0


@contextlib.contextmanager
def slot(root: Path):
    folder = Path(root) / ".locks"
    folder.mkdir(exist_ok=True)
    told = False
    while True:
        for number in range(SLOTS):
            handle = open(folder / f"stills-{number}.lock", "w")
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                handle.close()
                continue
            try:
                yield number
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
                handle.close()
            return
        if not told:
            print(f"  waiting for a free stills slot ({SLOTS} at a time on this Mac)", flush=True)
            told = True
        time.sleep(WAIT)
