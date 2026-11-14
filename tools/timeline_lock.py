"""One timeline change of a project at a time, across every agent on this Mac.

Two frame sessions of one episode may run side by side (user, 14 November 2026). Each change reads the project's
revision and sends it back; without a lock the second session's change would meet «версія змінилась» (409). Holding
this lock from reading the project to sending the change keeps the revision fresh. Other projects are not held up.
"""
from __future__ import annotations

import contextlib
import fcntl
import re
import time
from pathlib import Path

LOCKS = Path(__file__).resolve().parents[1] / "backend" / "data" / "locks"


@contextlib.contextmanager
def timeline_lock(project_id: str, timeout: float = 600):
    LOCKS.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^0-9A-Za-z_-]", "_", str(project_id))[:64] or "project"
    with (LOCKS / f"timeline-{name}.lock").open("w") as handle:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() > deadline:
                    raise TimeoutError("Таймлайн цього проєкту довго зайнятий іншою командою") from None
                time.sleep(.2)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
