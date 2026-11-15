"""One writer of a Razgon project's shared files at a time (assets/index.json, library-picks.json, review.json).

Two frame sessions of one episode may run side by side (user, 14 November 2026); without this, the second session's
read-modify-write of those files could drop the first one's entry.
"""
import contextlib
import fcntl
from pathlib import Path


@contextlib.contextmanager
def project_files(project):
    # A relative --project run from another folder named no project: refuse instead of making «projects/<slug>/build»
    # there (user, 15 November 2026: an empty «projects» folder appeared in the YouTube folder).
    if not (Path(project) / "story").is_dir():
        raise SystemExit(f"Проєкт Razgon не знайдено: {project}. Вкажіть повний шлях до папки проєкту.")
    folder = Path(project) / "build"
    folder.mkdir(exist_ok=True)
    with (folder / ".files.lock").open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
