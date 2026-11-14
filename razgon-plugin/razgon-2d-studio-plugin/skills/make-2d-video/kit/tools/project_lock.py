"""One writer of a Razgon project's shared files at a time (assets/index.json, library-picks.json, review.json).

Two frame sessions of one episode may run side by side (user, 14 November 2026); without this, the second session's
read-modify-write of those files could drop the first one's entry.
"""
import contextlib
import fcntl
from pathlib import Path


@contextlib.contextmanager
def project_files(project):
    folder = Path(project) / "build"
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / ".files.lock").open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
