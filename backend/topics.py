"""Studio-internal «Теми каналу.txt»: the titles of a channel's episodes, one a line, so a new script picks a fresh topic (or tells an old
one another way) from one short file instead of reading earlier scripts (user, 1 November 2026: «попередні сценарії
не варто передивлятися… просто зберігати теми, заголовки… в текстовому файлі»).

The Studio only appends: a title of a project or of an episode folder with «Метаданные.txt» that the file lacks is
added at the end. Legacy channel files are backed up, verified and migrated. Lines the author wrote or changed stay as they are, nothing is ever removed.
"""
from __future__ import annotations

import shutil
import time
import unicodedata
from pathlib import Path

import store

FILE = "Теми каналу.txt"
HEADER = ("# Теми й заголовки випусків каналу, по одному на рядок. Студія дописує нові сама, правити можна й вручну.\n"
          "# Новий ролик: інша тема або та сама, розказана по-іншому. Старі сценарії для цього читати не треба.\n")


def _key(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def titles(channel: Path) -> list[str]:
    """The channel's episode titles, oldest first: its projects' names, then titled episode folders no project holds."""
    found: list[tuple[float, str]] = []
    held = set()
    cid = store.channel_id(channel)
    if store.PROJECTS_ROOT.is_dir():
        for folder in store.PROJECTS_ROOT.iterdir():
            path = folder / "project.json"
            if not path.is_file():
                continue
            try:
                item = store.listed_project(path)
            except (OSError, ValueError, store.StudioError):
                continue
            if item.get("channel_id") != cid or item.get("deleted_at"):
                continue
            episode = Path(item.get("episode_path") or "")
            held.add(_key(str(episode)))
            name = (store.episode_title(episode) if item.get("episode_path") and episode.is_dir() else None) or item.get("name")
            if name:
                found.append((item.get("created_at") or 0, name))
    for folder in channel.iterdir() if channel.is_dir() else ():
        if folder.is_dir() and _key(str(folder)) not in held and (folder / "Метаданные.txt").is_file():
            title = store.episode_title(folder)
            if title:
                found.append(((folder / "Метаданные.txt").stat().st_mtime * 1000, title))
    return [name.strip() for _, name in sorted(found, key=lambda pair: pair[0]) if name.strip()]


def path(channel: Path) -> Path:
    """Technical history is private to this channel's Studio identity."""
    return store.DATA_ROOT / "channels" / store.channel_id(channel) / FILE


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]


def update(channel: Path) -> list[str]:
    """Merge legacy notes losslessly, then append missing episode titles under one lock."""
    with store.LOCK:
        target = path(channel)
        legacy = channel / FILE
        if target.is_symlink() or legacy.is_symlink():
            raise store.StudioError("Файл тем каналу містить символічне посилання")
        original = legacy.read_bytes() if legacy.is_file() else None
        text = target.read_text(encoding="utf-8") if target.is_file() else HEADER
        have = {_key(line) for line in _lines(text)}
        added = []
        candidates = (_lines(original.decode("utf-8")) if original is not None else []) + titles(channel)
        for title in candidates:
            if _key(title) not in have:
                have.add(_key(title))
                added.append(title)
        merged = text.rstrip("\n") + "\n" + "".join(line + "\n" for line in added)
        if original is not None:
            backup = target.parent / "technical-history" / str(time.time_ns()) / FILE
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy, backup)
            if backup.read_bytes() != original:
                raise OSError("Не вдалося перевірити резервну копію тем каналу")
        if added or original is not None or not target.is_file():
            store.atomic_text(target, merged)
        if original is not None:
            if target.read_text(encoding="utf-8") != merged or legacy.read_bytes() != original:
                raise OSError("Теми каналу змінилися під час перенесення")
            legacy.unlink()
        return added


def history(channel: Path) -> list[str]:
    """Refresh and read the full title ledger, including manually added topics."""
    with store.LOCK:
        update(channel)
        return _lines(path(channel).read_text(encoding="utf-8"))


def update_all() -> None:
    """At start, migrate and refresh enabled and disabled channels."""
    for channel in store.channel_folders(include_disabled=True):
        try:
            update(channel)
        except (OSError, ValueError, store.StudioError):
            continue
