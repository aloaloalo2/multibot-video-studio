"""Readable, versioned MP4 names without replacing an earlier export."""
import re
import unicodedata
from pathlib import Path


def destination(folder: Path, title: str, reserved=()) -> Path:
    name = unicodedata.normalize('NFC', title or '')
    name = re.sub(r'[\x00-\x1f\x7f/\\:*?"<>|]+', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip(' .') or 'Проєкт'
    # Leave room for the version and extension on filesystems with 255-byte names.
    name = name.encode('utf-8')[:220].decode('utf-8', errors='ignore').rstrip(' .')
    paths = list(folder.iterdir()) if folder.exists() else []
    paths += [Path(p) for p in reserved if Path(p).parent.resolve() == folder.resolve()]
    versions = [int(m.group(1)) for p in paths
                if (m := re.fullmatch(r'v([1-9]\d*)_.+\.mp4', p.name, re.IGNORECASE))]
    return folder / f'v{max(versions, default=0) + 1}_{name}.mp4'
