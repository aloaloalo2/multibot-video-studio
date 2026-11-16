#!/usr/bin/env python3
"""Tidy the channel folders: only episode folders stay in a channel, everything else moves into its «Інше».

User, 16 November 2026: «в папці каналів має бути лише папки випусків, а все остальне засунути в якусь папку інше.
Якщо вони кудись прив'язані до чогось, то краще їх переприв'язати.»

An episode folder is one a studio project points at, or one that holds a script, metadata, a voice or the studio's
«VideoKey» folder. The agents' own instruction files (AGENTS.md, CLAUDE.md, MEMORY.md) stay where agents look for them.
Every path the studio wrote to a moved item (projects, channel data, Razgon projects) is rewritten like a channel
rename does (backend/path_rewrite.py); the code finds «Голоси для перекладу» and «Еталон стилю» in «Інше» itself
(store.channel_extra). Without --apply it only prints the plan. Run it only while the studio is idle, then restart.

    python3 tools/tidy_channels.py            # the plan
    python3 tools/tidy_channels.py --apply    # move and rewrite
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "backend"))
import path_rewrite  # noqa: E402
import store  # noqa: E402

KEEP = {"AGENTS.md", "CLAUDE.md", "MEMORY.md", store.CHANNEL_OTHER}
# The studio reads these while it works (translation voices, thumbnail style): they move only while it is idle and
# right before its restart; everything else can move at any time (user, 16 November 2026: «нічого не зробив»).
LIVE = {"Голоси для перекладу", "Еталон стилю"}
ROOTS = (store.DATA_ROOT, APP / "razgon-2d-studio" / "projects")
nfc = lambda text: unicodedata.normalize("NFC", str(text))


def project_folders() -> set[str]:
    found = set()
    for path in (store.DATA_ROOT / "projects").glob("*/project.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if item.get("episode_path") and not item.get("deleted_at"):
            found.add(nfc(Path(item["episode_path"])))
    return found


def episode(folder: Path, known: set[str]) -> bool:
    if nfc(folder) in known:
        return True
    try:
        names = [nfc(p.name) for p in folder.iterdir()]
    except OSError:
        return False
    return any(n == store.EPISODE_STORE or n.startswith(("Сценарий", "Сценарій", "Метаданные", "Озвучка", "Превью", "Прев'ю"))
               for n in names)


def plan(live: bool = True) -> list[tuple[Path, Path]]:
    known = project_folders()
    moves = []
    for channel in store.list_channels():
        folder = Path(channel["path"])
        for item in sorted(folder.iterdir(), key=lambda p: nfc(p.name)):
            if item.name.startswith(".") or nfc(item.name) in KEEP:
                continue
            if item.is_dir() and episode(item, known):
                continue
            if not live and nfc(item.name) in LIVE:
                continue
            moves.append((item, folder / store.CHANNEL_OTHER / item.name))
    return moves


def busy() -> bool:
    out = subprocess.run([sys.executable, str(APP / "tools" / "studio_restart.py"), "--check"], capture_output=True, text=True)
    return out.returncode != 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--now", action="store_true", help="move all but the folders the studio reads while it works")
    args = parser.parse_args()
    moves = plan(live=not args.now)
    replace = [pair for old, new in moves for pair in path_rewrite.pairs(old, new)]
    changed = path_rewrite.changes(path_rewrite.text_files(ROOTS, skip=("rename-backups", "tidy-backups")), replace) if moves else {}
    by_channel: dict[str, list[str]] = {}
    for old, _ in moves:
        by_channel.setdefault(old.parent.name, []).append(old.name)
    for channel, names in by_channel.items():
        print(f"{nfc(channel)}: у «{store.CHANNEL_OTHER}» переїде {len(names)}")
        for name in names:
            print(f"   {nfc(name)}")
    print(f"Файлів студії з цими шляхами: {len(changed)}")
    if not args.apply or not moves:
        return
    if not args.now and busy():
        raise SystemExit("Студія зараз працює: дочекайтеся кінця й запустіть ще раз.")
    taken = [new for _, new in moves if new.exists()]
    if taken:
        raise SystemExit("У «Інше» вже є: " + ", ".join(nfc(p) for p in taken))
    backup = store.DATA_ROOT / "tidy-backups" / time.strftime("%Y%m%d-%H%M%S")
    for path in changed:
        for root in ROOTS:
            if Path(root) in path.parents:
                kept = backup / Path(root).name / path.relative_to(root)
                kept.parent.mkdir(parents=True, exist_ok=True)
                kept.write_bytes(path.read_bytes())
    backup.mkdir(parents=True, exist_ok=True)
    (backup / "moves.json").write_text(json.dumps([[str(a), str(b)] for a, b in moves], ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    for old, new in moves:
        new.parent.mkdir(exist_ok=True)
        os.rename(old, new)
    path_rewrite.write(changed)
    print(f"Готово: переміщено {len(moves)}, оновлено файлів студії {len(changed)}. Копії змінених файлів: {backup}")
    print("Перезапустіть студію: python3 tools/studio_restart.py")


if __name__ == "__main__":
    main()
