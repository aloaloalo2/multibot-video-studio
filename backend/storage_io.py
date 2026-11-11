"""Atomic local files and request-scoped JSON reads."""
import copy
import json
import os
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

def _atomic_write(path: Path, text: str, create_parents: bool) -> None:
    if create_parents:
        path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(str(tmp), str(path))
    finally:
        if tmp.exists():
            tmp.unlink()


def atomic_json(path: Path, value: object, *, create_parents=True) -> None:
    _atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n", create_parents)


def atomic_text(path: Path, value: str) -> None:
    _atomic_write(path, value, True)


_READ_SNAPSHOT = threading.local()


@contextmanager
def read_snapshot():
    """Request-local reuse for read-only views; changed files get a new stat key."""
    previous = getattr(_READ_SNAPSHOT, 'values', None)
    _READ_SNAPSHOT.values = previous if previous is not None else {}
    try:
        yield
    finally:
        _READ_SNAPSHOT.values = previous


def read_json(path: Path, default=None):
    if not path.exists():
        return copy.deepcopy(default)
    values = getattr(_READ_SNAPSHOT, 'values', None)
    if values is None:
        return json.loads(path.read_text(encoding="utf-8"))
    stamp = path.stat()
    key = (str(path), stamp.st_mtime_ns, stamp.st_size)
    if key not in values:
        values[key] = json.loads(path.read_text(encoding="utf-8"))
    return values[key]
