"""«Теми каналу.txt»: the titles of a channel's episodes, one a line, so a new script picks a fresh topic (or tells an old
one another way) from one short file instead of reading earlier scripts (user, 1 November 2026: «попередні сценарії
не варто передивлятися… просто зберігати теми, заголовки… в текстовому файлі»).

The Studio only appends: a title of a project or of an episode folder with «Метаданные.txt» that the file lacks is
added at the end. Lines the author wrote or changed stay as they are, nothing is ever removed.
"""
from __future__ import annotations

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


def update(channel: Path) -> list[str]:
    """Append the channel's titles the file lacks; returns the added ones."""
    path = channel / FILE
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else HEADER
    have = {_key(line) for line in text.splitlines() if line.strip() and not line.startswith("#")}
    added = []
    for title in titles(channel):
        if _key(title) not in have:
            have.add(_key(title))
            added.append(title)
    if added or not path.is_file():
        store.atomic_text(path, text.rstrip("\n") + "\n" + "".join(line + "\n" for line in added))
    return added


def update_all() -> None:
    """At start and after a project is made or renamed: every channel's file catches up; a problem never stops the Studio."""
    for channel in store.channel_folders(include_disabled=True):
        try:
            update(channel)
        except (OSError, store.StudioError):
            continue
