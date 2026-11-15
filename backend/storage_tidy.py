"""Clear what the studio piles up on disk and never reads again (user, 14 November 2026: «проблема з вагою видео кей
студио… так, і прибери зараз»). On that day the studio held 69 GB with 8 GB left on the disk.

What goes, and why it is safe:
- languages/<code>/parts/*.wav and voice-history/*/**.wav: the fitted phrases and silences a voicing glues into
  voice.mp3. Every voicing makes them again from the paid MP3 takes (languages.py, «-line.wav», «-gap.wav»), and a refit
  works in a temporary folder, so once voice.mp3 is made they are dead weight (7.8 GB on that day).
- voice-history/*/voice.mp3 except in the newest entry: earlier full voicings; nothing in the studio reads them.
- mix-history and recovery except their newest entry: earlier soundtracks and refit backups, never read back.
- production-*.log over LOG_LIMIT: only their tail is kept.
- leveled/*.flac no file of any project plays any more (the key is the voice's path, size and time).

What stays: the paid takes (parts/*.mp3, voice-history/*/parts/*.mp3), voice-cache, every JSON and text, the current
voice.mp3 and mix, montage media, Razgon renders and code. A project with work running is not touched.

Stand-alone on purpose (no store import), so tools/storage_tidy.py can run it next to a running studio.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from pathlib import Path

LOG_LIMIT = 2 * 1024 * 1024     # a production log longer than this keeps its last LOG_KEEP bytes
LOG_KEEP = 1024 * 1024
QUIET = 3600                    # a file written during the last hour may belong to work in progress
LEVELED_AGE = 7 * 86400         # an unused leveled copy goes only after a week (a voice being replaced comes back fast)


def _size(path: Path) -> int:
    try:
        return path.stat().st_size if path.is_file() else sum(item.stat().st_size for item in path.rglob("*")
                                                                if item.is_file() and not item.is_symlink())
    except OSError:
        return 0


def _recent(path: Path, now: float) -> bool:
    try:
        return now - path.stat().st_mtime < QUIET
    except OSError:
        return True


class Tidy:
    def __init__(self, data_root: Path, apply: bool = True):
        self.data_root = Path(data_root)
        self.apply = apply
        self.freed = 0
        self.files = 0
        self.by_kind: dict[str, int] = {}
        self.now = time.time()

    def drop(self, path: Path, kind: str) -> None:
        size = _size(path)
        if self.apply:
            try:
                shutil.rmtree(path) if path.is_dir() and not path.is_symlink() else path.unlink()
            except FileNotFoundError:
                return
            except OSError:
                return
        self.freed += size
        self.files += 1
        self.by_kind[kind] = self.by_kind.get(kind, 0) + size

    # ---- one language of one project -------------------------------------------------------------------------
    def language(self, work: Path) -> None:
        if not (work / "voice.mp3").is_file() or any(_recent(work / name, self.now) for name in ("parts", "voice.mp3")):
            return   # not voiced yet, or a voicing may be running: its WAVs are still needed
        if (work / "joined.wav").exists() or (work / "voice-new.mp3").exists():
            return   # a voicing stopped half way or runs now
        for wav in (work / "parts").glob("*.wav"):
            self.drop(wav, "проміжні WAV озвучки")
        history = sorted((path for path in (work / "voice-history").glob("*") if path.is_dir()), key=lambda p: p.name)
        for entry in history:
            for wav in entry.rglob("*.wav"):
                self.drop(wav, "проміжні WAV озвучки")
        for entry in history[:-1]:
            if (entry / "voice.mp3").is_file():
                self.drop(entry / "voice.mp3", "старі версії озвучки")
        for folder, kind in (("mix-history", "старі версії міксу"), ("recovery", "старі резервні копії")):
            entries = sorted((path for path in (work / folder).glob("*") if path.is_dir()), key=lambda p: p.name)
            for entry in entries[:-1]:
                self.drop(entry, kind)

    # ---- one project ---------------------------------------------------------------------------------------
    def project(self, folder: Path) -> None:
        for work in (folder / "languages").glob("*"):
            if work.is_dir():
                self.language(work)
        for log in folder.glob("production-*.log"):
            try:
                size = log.stat().st_size
            except OSError:
                continue
            if size <= LOG_LIMIT or _recent(log, self.now):
                continue
            if self.apply:
                # Keep the cost of the whole run before only its tail remains.
                try:
                    import spend_report
                    if not spend_report.trimmed(log):
                        spend_report.record(log)
                except Exception:
                    pass
                with open(log, "rb") as source:
                    source.seek(size - LOG_KEEP)
                    tail = source.read()
                tail = tail[tail.find(b"\n") + 1:] if b"\n" in tail else tail
                staged = log.with_suffix(".log.tmp")
                staged.write_bytes("… початок журналу обрізано, щоб звільнити місце …\n".encode() + tail)
                os.replace(staged, log)
                self.freed += size - _size(log)
            else:
                self.freed += size - LOG_KEEP
            self.files += 1
            self.by_kind["логи виробництва"] = self.by_kind.get("логи виробництва", 0) + max(0, size - LOG_KEEP)

    # ---- leveled voice copies --------------------------------------------------------------------------------
    def leveled(self, projects: list[Path]) -> None:
        live = set()
        def remember(path: Path) -> None:
            try:
                stat = path.stat()
            except OSError:
                return
            key = f"{path.resolve()}\0{stat.st_size}\0{stat.st_mtime_ns}"   # audio_level._key
            live.add(hashlib.sha1(key.encode()).hexdigest()[:20])
        for folder in projects:
            if not (folder / "project.json").is_file():
                continue
            try:
                project = json.loads((folder / "project.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return   # a project that cannot be read may still play one of them: leave all
            for asset in project.get("assets", []) if isinstance(project, dict) else []:
                if isinstance(asset, dict) and asset.get("path"):
                    remember(Path(asset["path"]))
            for voice in (folder / "languages").glob("*/voice.*"):
                remember(voice)
        for copy in (self.data_root / "leveled").glob("*.flac"):
            try:
                old = self.now - copy.stat().st_mtime > LEVELED_AGE
            except OSError:
                continue
            if copy.stem not in live and old:
                self.drop(copy, "невикористаний вирівняний голос")

    def run(self, skip: set[str]) -> dict:
        root = self.data_root / "projects"
        projects = sorted(path for path in root.glob("*") if (path / "project.json").is_file())
        for folder in projects:
            if folder.name not in skip:
                self.project(folder)
        self.leveled(projects)
        return self.report()

    def report(self) -> dict:
        return {"freed": self.freed, "files": self.files, "by_kind": dict(self.by_kind), "applied": self.apply}


def tidy(data_root: Path, skip: set[str] = frozenset(), apply: bool = True) -> dict:
    """Clear what the studio no longer reads, leaving the projects in `skip` (work runs there) as they are."""
    return Tidy(data_root, apply).run(set(skip))


def gigabytes(value: int) -> str:
    return f"{value / 2**30:.1f} ГБ"
