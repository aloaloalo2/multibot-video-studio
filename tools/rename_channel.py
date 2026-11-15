#!/usr/bin/env python3
"""Give a channel's folder in YOUTUBE the name the studio shows (user, 15 November 2026: «папки каналов переименуй так
как у меня в студии»).

A channel's id is a hash of its folder's path (store.channel_id) and that path sits in every project of the channel
(episode_path, asset paths, plans, language files), so renaming the folder alone would orphan the channel. This tool
renames the folder and, in one pass, writes the new path and the new id wherever the studio keeps the old ones:
backend/data (projects, jobs, channel settings, renders) and the Razgon projects. Logs keep their history as it was.
The channel's own data folder moves to its new id. Run it only while the studio is idle, then restart the studio.

    python3 tools/rename_channel.py "What If" CORBIN            # what would change
    python3 tools/rename_channel.py "What If" CORBIN --apply
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import unicodedata
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "backend"))
import path_rewrite  # noqa: E402
import store  # noqa: E402

ROOTS = (store.DATA_ROOT, APP / "razgon-2d-studio" / "projects")


def find_folder(name: str) -> Path:
    for folder in store.YOUTUBE_ROOT.iterdir():
        if folder.is_dir() and unicodedata.normalize("NFC", folder.name) == unicodedata.normalize("NFC", name):
            return folder
    raise SystemExit(f"Папку «{name}» не знайдено в {store.YOUTUBE_ROOT}")


def id_named(old_id: str) -> list[Path]:
    """Everything in the studio's data named by the channel id: channels/<id>, language-defaults/<id>,
    agent-channel-memory/<id>.json and .lock, language-thumbnail-options/<id>.json and the like."""
    found = []
    for folder in store.DATA_ROOT.iterdir():
        if not folder.is_dir() or folder.name in {"projects", "rename-backups"}:
            continue
        found += [path for path in folder.iterdir() if path.name.startswith(old_id)]
    return sorted(found)


def busy() -> bool:
    check = subprocess.run([sys.executable, str(APP / "tools" / "studio_restart.py"), "--check"], capture_output=True, text=True)
    if check.returncode:
        print(check.stdout.strip())
    return bool(check.returncode)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("old")
    parser.add_argument("new")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    old = find_folder(args.old)
    new = old.with_name(unicodedata.normalize("NFC", args.new.strip()))
    if not args.new.strip() or "/" in args.new or new.name.startswith("."):
        raise SystemExit("Невірна нова назва папки")
    if new.exists():
        raise SystemExit(f"Папка «{new.name}» вже існує")
    if not store.has_channel_settings(old):
        raise SystemExit(f"«{old.name}» не є папкою каналу студії")
    old_id = store.channel_id(old)
    new_id = __import__("hashlib").sha256(str(new).encode()).hexdigest()[:16]
    replace = path_rewrite.pairs(old, new) + [(old_id.encode(), new_id.encode())]
    changed = path_rewrite.changes(path_rewrite.text_files(ROOTS, skip=("rename-backups",)), replace)
    channel_data = store.DATA_ROOT / "channels"
    # Not only channels/<id>: the language voices (language-defaults/<id>), the agents' memory (agent-channel-memory/
    # <id>.json) and other data named by the channel id move too. The first renames left them behind, so CORBIN's
    # episodes lost their Ukrainian and Spanish voices and Космос PRO its wishes (user, 15 November 2026: «був голос»).
    keyed = id_named(old_id)
    print(f"{old.name} → {new.name}: канал {old_id} → {new_id}, файлів до оновлення {len(changed)}"
          f"{', дані каналу переїдуть' if (channel_data / old_id).is_dir() else ''}")
    if not args.apply:
        return
    if busy():
        raise SystemExit("Студія зараз працює: дочекайтеся кінця й запустіть ще раз.")
    if (channel_data / new_id).exists():
        raise SystemExit(f"Дані каналу {new_id} вже існують")
    taken = [path for path in keyed if path.with_name(path.name.replace(old_id, new_id, 1)).exists()]
    if taken:
        raise SystemExit("Дані з новим номером уже існують: " + ", ".join(str(p) for p in taken))
    # the original of every file it rewrites, to undo by hand if anything looks wrong
    import time
    backup = store.DATA_ROOT / "rename-backups" / f"{time.strftime('%Y%m%d-%H%M%S')}-{old_id}"
    for path in changed:
        for root in ROOTS:
            if root in path.parents:
                kept = backup / root.name / path.relative_to(root)
                kept.parent.mkdir(parents=True, exist_ok=True)
                kept.write_bytes(path.read_bytes())
    (backup / "rename.json").write_text(json.dumps({"old": str(old), "new": str(new), "old_id": old_id, "new_id": new_id},
                                                   ensure_ascii=False, indent=2), encoding="utf-8")
    os.rename(old, new)
    moved = {}
    for path in keyed:
        target = path.with_name(path.name.replace(old_id, new_id, 1))
        os.rename(path, target)
        moved[str(path)] = str(target)
    def after(path):
        text = str(path)
        for source, target in moved.items():
            if text == source or text.startswith(source + "/"):
                return Path(target + text[len(source):])
        return path
    path_rewrite.write({after(path): data for path, data in changed.items()})
    if store.channel_id(new) != new_id:
        raise SystemExit(f"Увага: номер нової папки {store.channel_id(new)} не збігся з {new_id}")
    print("Готово. Перезапустіть студію: python3 tools/studio_restart.py")


if __name__ == "__main__":
    main()
