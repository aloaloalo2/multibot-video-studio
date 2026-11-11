"""Publish a complete MP4 across volumes without replacing an existing export."""
from contextlib import contextmanager
import errno
import os
from pathlib import Path
import tempfile


@contextmanager
def prepared(source: Path, destination: Path, cancelled=lambda: False):
    if source.stat().st_dev == destination.parent.stat().st_dev:
        yield source
        return
    # Copy to the destination volume before the short final commit. Cancellation
    # and status reads remain available while a large file is being copied.
    fd, name = tempfile.mkstemp(prefix='.videokey-', suffix='.partial', dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as output, source.open('rb') as stream:
            while True:
                if cancelled():
                    raise InterruptedError('Збереження експорту скасовано')
                chunk = stream.read(8 * 1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        yield temporary
    finally:
        temporary.unlink(missing_ok=True)


def publish(source: Path, destination: Path):
    try:
        # Link is an atomic no-clobber publication, including if another program
        # creates the chosen filename after export_names reserved it.
        os.link(source, destination)
        return
    except FileExistsError:
        raise RuntimeError('Файл з такою назвою вже існує') from None
    except OSError as error:
        if error.errno not in {errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP, errno.ENOSYS}:
            raise
    # Some external filesystems do not support hard links. Reserve the name
    # exclusively, then replace only our own empty reservation with the full file.
    try:
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    except FileExistsError:
        raise RuntimeError('Файл з такою назвою вже існує') from None
    identity = os.fstat(fd)
    os.close(fd)
    try:
        current = destination.stat()
        if (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino) or current.st_size:
            raise RuntimeError('Файл експорту змінився під час збереження')
        os.replace(source, destination)
    except Exception:
        if destination.exists():
            current = destination.stat()
            if (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino) and not current.st_size:
                destination.unlink()
        raise
