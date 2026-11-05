#!/usr/bin/env python3
"""Keep the Razgon 2D studio in the YOUTUBE folder up to date with the kit the Studio ships.

The Razgon plugin lives in this repository (razgon-plugin/…/make-2d-video/kit). On first use Claude copies the kit into
a working folder (`What If/razgon-2d-studio` or any `<YOUTUBE>/…/razgon-2d-studio` with `render.mjs`), next to the
projects, node_modules and the prop library. When the Studio updates from GitHub, its kit changes but that copy does
not, so the Studio brings the copy up to date at every start (user, 31 October 2026: «щоб це все обновлялось»).

Safe by design, with a manifest of what it wrote (`.videokey-kit.json` in the copy):
- a file missing in the copy is added;
- a file the Studio wrote before and nobody changed since is replaced by the new kit version;
- a file that already equals the kit is only recorded;
- a file changed by hand (it matches neither the last written version nor the kit) is left alone and reported;
- a file the kit no longer has is removed only when nobody changed it since the Studio wrote it.
`projects/`, `node_modules/`, `build/`, `assets/` and anything else outside the kit are never touched. When
`package.json` changes, `npm install` runs in the copy.

    python3 tools/razgon_sync.py [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
YOUTUBE = APP_ROOT.parent
KIT = APP_ROOT / "razgon-plugin" / "razgon-2d-studio-plugin" / "skills" / "make-2d-video" / "kit"
MANIFEST = ".videokey-kit.json"
# The Razgon working copy lives inside the studio's own folder (user, 1 November 2026: «цю папку з What If прибрати й
# засунути саме в VideoKey Studio»); it moved from What If at the first start of this version (move_home). It is in the
# studio's .gitignore: its projects, node_modules and builds never reach GitHub.
HOME = APP_ROOT / "razgon-2d-studio"
OLD_HOME = YOUTUBE / "What If" / "razgon-2d-studio"
NEVER = {"projects", "node_modules", "build", "assets", ".git"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def home() -> Path:
    """Where the Razgon working copy is: in the studio, or still in What If before the move."""
    return OLD_HOME if (OLD_HOME / "render.mjs").is_file() and not (HOME / "render.mjs").is_file() else HOME


def move_home(old: Path = OLD_HOME, new: Path = HOME, youtube: Path = YOUTUBE) -> bool:
    """Move the working copy from What If into the studio's folder once, as a rename on the same disk (no copying of
    gigabytes), then point every episode's razgon.json and the channels' rules at the new place. Nothing moves when the
    new place is taken, the old one is a link, or the two are on different disks."""
    if not (old / "render.mjs").is_file() or old.is_symlink() or new.exists():
        return False
    if os.stat(old).st_dev != os.stat(new.parent).st_dev:
        return False
    os.rename(old, new)
    relink(old, new, youtube)
    return True


def relink(old: Path, new: Path, youtube: Path = YOUTUBE) -> None:
    """Rewrite the paths that name the old place: each episode's razgon.json and the channels' AGENTS.md / CLAUDE.md."""
    old_s, new_s = str(old), str(new)
    rel_old = old.relative_to(youtube).as_posix() if youtube in old.parents else None
    rel_new = new.relative_to(youtube).as_posix() if youtube in new.parents else None
    for link in [*youtube.glob("*/*/razgon.json"), *APP_ROOT.glob("backend/data/projects/*/razgon-link.json")]:
        try:
            data = json.loads(link.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        changed = False
        for key, value in list(data.items()):
            if isinstance(value, str) and (value == old_s or value.startswith(old_s + "/")):
                data[key] = new_s + value[len(old_s):]
                changed = True
        if changed:
            temp = link.with_name(link.name + ".tmp")
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(temp, link)
    for rules in [*youtube.glob("*/AGENTS.md"), *youtube.glob("*/CLAUDE.md"), *youtube.glob("AGENTS.md"), *youtube.glob("CLAUDE.md")]:
        if new in rules.parents or APP_ROOT in rules.parents:
            continue
        try:
            text = rules.read_text(encoding="utf-8")
        except OSError:
            continue
        moved = text.replace(old_s, new_s)
        if rel_old and rel_new:
            moved = moved.replace(rel_old, rel_new)
        if moved != text:
            rules.write_text(moved, encoding="utf-8")


def kit_files(kit: Path = KIT) -> dict[str, Path]:
    files = {}
    for path in sorted(kit.rglob("*")):
        rel = path.relative_to(kit)
        if path.is_file() and rel.parts[0] not in NEVER and "__pycache__" not in rel.parts and path.name != ".DS_Store":
            files[rel.as_posix()] = path
    return files


def copies(youtube: Path = YOUTUBE) -> list[Path]:
    """Razgon working folders: What If's and any other `razgon-2d-studio` with a renderer, two levels deep."""
    found = []
    for pattern in ("razgon-2d-studio", "*/razgon-2d-studio"):
        for folder in sorted(youtube.glob(pattern)):
            if folder.is_dir() and (folder / "render.mjs").is_file() and folder.resolve() != KIT.resolve():
                found.append(folder)
    return found


def sync(target: Path, kit: Path = KIT, dry: bool = False) -> dict:
    """Bring one working copy up to date; returns lists of added, updated, removed and kept (hand-changed) files."""
    manifest_path = target / MANIFEST
    try:
        written = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        written = {}
    files = kit_files(kit)
    report = {"added": [], "updated": [], "removed": [], "kept": []}
    record = {}
    for rel, source in files.items():
        new = digest(source)
        path = target / rel
        if not path.exists():
            report["added"].append(rel)
        else:
            have = digest(path)
            if have == new:
                record[rel] = new
                continue
            if written.get(rel) != have:
                report["kept"].append(rel)   # changed by hand: the author's version stays
                if rel in written:
                    record[rel] = written[rel]
                continue
            report["updated"].append(rel)
        if not dry:
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, path)
        record[rel] = new
    for rel, old in written.items():
        if rel in files or Path(rel).parts[0] in NEVER:
            continue
        path = target / rel
        if path.is_file() and digest(path) == old:
            report["removed"].append(rel)
            if not dry:
                path.unlink()
        elif path.is_file():
            report["kept"].append(rel)
    if not dry:
        manifest_path.write_text(json.dumps(record, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        if "package.json" in report["added"] + report["updated"] and shutil.which("npm"):
            subprocess.run(["npm", "install", "--no-audit", "--no-fund"], cwd=target, capture_output=True, timeout=900)
    return report


def at_start() -> None:
    """Called by the Studio at start: every working copy is brought up to date; problems never stop the Studio."""
    if not KIT.is_dir():
        return
    try:
        move_home()
    except OSError:
        pass   # it stays in What If and works from there
    for target in copies():
        try:
            sync(target)
        except (OSError, subprocess.SubprocessError):
            continue
        collect_props(target)


def collect_props(target: Path) -> None:
    """The shared prop library (`library/props`) gathers the picture props of every Razgon project, so a later video
    can reuse them. It was filled only when a new prop sheet was cut, so props made before never reached it (user,
    1 November 2026: «папки Library я взагалі не бачив»). Adding only: clones on a Mac, nothing is removed."""
    tool = target / "tools" / "library.py"
    if tool.is_file() and (target / "projects").is_dir():
        try:
            subprocess.run([sys.executable, str(tool), "collect"], cwd=target, capture_output=True, timeout=600)
        except (OSError, subprocess.SubprocessError):
            pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="лише показати, що змінилося б")
    args = parser.parse_args(argv)
    targets = copies()
    if not targets:
        print("Папку Razgon-студії не знайдено: її створить Claude під час першої анімації.")
        return 0
    for target in targets:
        report = sync(target, dry=args.dry_run)
        print(f"{target.relative_to(YOUTUBE) if YOUTUBE in target.parents else target}:")
        print(f"  додано {len(report['added'])}, оновлено {len(report['updated'])}, прибрано {len(report['removed'])}")
        for rel in report["kept"]:
            print(f"  змінено вручну, лишаю як є: {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
