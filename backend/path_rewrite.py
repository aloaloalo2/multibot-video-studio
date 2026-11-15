"""Write a folder's new path wherever the studio's text files hold its old one: a renamed channel folder
(tools/rename_channel.py) or episode folder (episode_folder.py).

A path is found as it was written: as on disk, NFC, NFD, and each as a JSON \\u escape, followed by «/» or «"», so a
longer folder name that starts the same way is left alone. Files are rewritten byte for byte, their formatting kept.
"""
from __future__ import annotations

import json
import os
import unicodedata
from pathlib import Path

TEXT = {".json", ".txt", ".md", ".jsonl", ".csv"}


def forms(path: str) -> list[bytes]:
    seen = []
    for text in {path, unicodedata.normalize("NFC", path), unicodedata.normalize("NFD", path)}:
        for raw in (text.encode(), json.dumps(text)[1:-1].encode()):
            if raw not in seen:
                seen.append(raw)
    return seen


def pairs(old: Path, new: Path) -> list[tuple[bytes, bytes]]:
    target = str(new)
    found = []
    for raw in forms(str(old)):
        written = json.dumps(target)[1:-1].encode() if b"\\u" in raw else target.encode()
        found += [(raw + end, written + end) for end in (b"/", b'"', b"\\/")]
    return found


def text_files(roots, skip: tuple[str, ...] = ()):
    for root in roots:
        root = Path(root)
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if (path.suffix in TEXT and path.is_file() and not path.is_symlink()
                    and not set(skip) & set(path.relative_to(root).parts)):
                yield path


def changes(files, replace: list[tuple[bytes, bytes]]) -> dict[Path, bytes]:
    found = {}
    for path in files:
        try:
            data = path.read_bytes()
        except OSError:
            continue
        result = data
        for a, b in replace:
            result = result.replace(a, b)
        if result != data:
            found[path] = result
    return found


def write(found: dict[Path, bytes]) -> None:
    for path, data in found.items():
        staged = path.with_name(f".rewrite-{path.name}")
        staged.write_bytes(data)
        os.replace(staged, path)
