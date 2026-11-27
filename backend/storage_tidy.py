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
- kept/*.m4a of a sound whose original lies in the studio's own media (projects/<id>/media, narration-ending): the copy is
  there for an episode folder the author deletes, and these originals do not go with it (882 MB on 25 November 2026).
- the rebuilt caches of an episode (CACHE_FOLDERS) nothing wrote for CACHE_AGE, CapCut previews of a project and the
  shared capcut-cache past CAPCUT_AGE, the shared capcut-cache beyond CAPCUT_LIMIT (oldest first), and cache/<name>-vN
  once a newer cache/<name>-vM exists (the code reads only the newest version).

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
LEVELED_AGE = QUIET             # an unused leveled copy (up to 700 MB a film) goes after the quiet hour; it is rebuilt
                                # from its voice in a minute if needed (was a week: 3.5 GB lay unused; 17 November 2026)
CAPCUT_AGE = 10 * 3600         # a CapCut transition render not used for 10 hours is rebuilt when needed (user, 27 November
                                # 2026: «10 год вистачить, щоб очистити переходи»; three days before)
CAPCUT_LIMIT = 2 * 1024 ** 3    # the shared CapCut cache keeps at most this much, the least recently used going first
CACHE_AGE = 7 * 86400           # an episode's rebuilt cache nothing wrote for a week goes whole
# What the studio makes again by itself when it needs it (space.CACHE, «Звільнити місце»): export chunks, the engine's
# render cache, stills, stock sheets, motion-code renders, held copies for transitions, CapCut previews of seams.
CACHE_FOLDERS = ("renders", "render-cache", "stills", "stock", "motion-code", "held-tails", "capcut")
IDLE_FOLDERS = ("renders", "render-cache", "stills", "stock", "capcut")   # the other two have their own prune
# Where a project's own sound lies for good: only a copy kept of a file elsewhere is worth its place.
LASTING = ("media", "narration-ending")


def _size(path: Path) -> int:
    try:
        return path.stat().st_size if path.is_file() else sum(item.stat().st_size for item in path.rglob("*")
                                                                if item.is_file() and not item.is_symlink())
    except OSError:
        return 0


def _used(path: Path) -> float:
    """When a cache file was last written or read."""
    stat = path.stat()
    return max(stat.st_mtime, stat.st_atime)


def _written_since(folder: Path, moment: float) -> bool:
    """Whether anything in the folder was written after the moment; stops at the first such file."""
    stack = [folder]
    while stack:
        try:
            with os.scandir(stack.pop()) as entries:
                for entry in entries:
                    if entry.is_symlink():
                        continue
                    if entry.stat().st_mtime > moment:
                        return True
                    if entry.is_dir():
                        stack.append(Path(entry.path))
        except OSError:
            return True   # what cannot be read may be in use
    return False


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
    def renders(self, folder: Path) -> None:
        """Motion-code renders no clip uses any more (an older code or format: ProRes ones took 1.3 GB for 11 s) and the
        held copies of transitions past their age or the folder's limit (they reached 24 GB on 25 November 2026)."""
        if not self.apply:
            return
        try:
            import joins
            import motion_code
            project = json.loads((folder / "project.json").read_text(encoding="utf-8"))
            before = _size(folder / "motion-code") + _size(folder / "held-tails")
            motion_code.prune(project)
            if (folder / "held-tails").is_dir():
                joins._prune_held(folder / "held-tails")
            freed = before - _size(folder / "motion-code") - _size(folder / "held-tails")
        except Exception:   # a render folder never stops the tidy of the rest
            return
        if freed > 0:
            self.freed += freed
            self.files += 1
            self.by_kind["рендери моушн-коду й переходів"] = self.by_kind.get("рендери моушн-коду й переходів", 0) + freed

    def caches(self, folder: Path) -> None:
        """An episode's rebuilt caches nobody wrote to for CACHE_AGE, and its seam previews unused for CAPCUT_AGE (a
        preview is named by the code it shows, so the ones of an older code are never read again: 351 MB on 25 November)."""
        for name in IDLE_FOLDERS:
            cache = folder / name
            if cache.is_dir() and not cache.is_symlink() and not _written_since(cache, self.now - CACHE_AGE):
                self.drop(cache, "кеш випуску, не потрібний тиждень")
        for item in (folder / "capcut").glob("*"):
            try:
                old = item.is_file() and self.now - _used(item) > CAPCUT_AGE
            except OSError:
                continue
            if old:
                self.drop(item, "кеш переходів CapCut")

    def kept(self, folder: Path) -> None:
        """Kept copies (keep.py) whose original lies in the studio's own lasting folders: nothing deletes those with the
        episode folder, so resolve_asset never falls back to the copy. A copy left half made by a killed FFmpeg goes too."""
        try:
            project = json.loads((folder / "project.json").read_text(encoding="utf-8"))
            assets = {asset["id"]: asset for asset in project.get("assets", []) if isinstance(asset, dict) and asset.get("id")}
        except (OSError, ValueError, AttributeError, TypeError, KeyError):
            return
        for copy in (folder / "kept").glob("*.m4a"):
            if copy.name.endswith(".tmp.m4a"):
                if not _recent(copy, self.now):
                    self.drop(copy, "зайві копії звуку")
                continue
            source = Path((assets.get(copy.stem) or {}).get("path") or "")
            if lasting(source, folder):
                self.drop(copy, "зайві копії звуку")

    def project(self, folder: Path, caches: bool = True) -> None:
        """`caches=False` leaves the rebuilt caches to the caller (space.free removes them whole)."""
        self.renders(folder)
        if caches:
            self.caches(folder)
        self.kept(folder)
        for work in (folder / "languages").glob("*"):
            if work.is_dir():
                self.language(work)
        self.revisions(folder / "narration")
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


    def revisions(self, narration: Path) -> None:
        """A sentence revision's working WAVs (the whole voice decoded twice, its patches and takes) once it has ended:
        later runs read only its text.txt and proof.json, and the takes stay in the phrase cache (1.9 GB on 17 November
        2026)."""
        try:
            job = json.loads((narration / "revision-job.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            job = {}
        running = job.get("id") if job.get("status") in {"queued", "running", "cancelling"} else None
        for entry in (narration / "revisions").glob("*"):
            if not entry.is_dir() or entry.name == running or _recent(entry, self.now):
                continue
            for item in [*entry.glob("*.wav"), *entry.glob("*-effects.flac")]:
                self.drop(item, "проміжні WAV переозвучки")

    # ---- CapCut transition renders ---------------------------------------------------------------------------
    def capcut(self) -> None:
        """Renders unused for CAPCUT_AGE, then the least recently used beyond CAPCUT_LIMIT (never one of the last hour:
        an export may be reading it)."""
        files = []
        for item in (self.data_root / "capcut-cache").glob("*"):
            try:
                if item.is_file():
                    files.append((_used(item), item.stat().st_size, item))
            except OSError:
                continue
        total = 0
        for used, size, item in sorted(files, reverse=True):
            if self.now - used > CAPCUT_AGE or (total + size > CAPCUT_LIMIT and self.now - used > QUIET):
                self.drop(item, "кеш переходів CapCut")
            else:
                total += size

    # ---- earlier versions of shared caches -----------------------------------------------------------------------
    def versions(self) -> None:
        newest: dict[str, int] = {}
        found = []
        for folder in (self.data_root / "cache").glob("*-v*"):
            name, _, number = folder.name.rpartition("-v")
            if folder.is_dir() and name and number.isdigit():
                found.append((name, int(number), folder))
                newest[name] = max(newest.get(name, 0), int(number))
        for name, number, folder in found:
            if number < newest[name] and not _written_since(folder, self.now - QUIET):
                self.drop(folder, "старі версії кешу")
    # ---- leveled voice copies --------------------------------------------------------------------------------
    def leveled(self, projects: list[Path]) -> None:
        # only the projects of this very data folder can say which copies are unused: any other list (a test's own
        # projects) would make every real copy look unused
        own = (self.data_root / "projects").resolve()
        if any(Path(folder).resolve().parent != own for folder in projects):
            return
        live, sources = set(), set()
        def remember(path: Path) -> None:
            try:
                stat = path.stat()
            except OSError:
                return
            key = f"{path.resolve()}\0{stat.st_size}\0{stat.st_mtime_ns}"   # audio_level._key
            live.add(hashlib.sha1(key.encode()).hexdigest()[:20])
            sources.add((str(path.resolve()), stat.st_size))   # the same voice by path and size, whatever its file time
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
            try:
                side = json.loads(copy.with_suffix(".json").read_text(encoding="utf-8"))
                kept = (side.get("source"), side.get("size")) in sources
            except (OSError, ValueError, AttributeError):
                kept = False
            if copy.stem not in live and not kept and old:
                self.drop(copy, "невикористаний вирівняний голос")
                copy.with_suffix(".json").unlink(missing_ok=True)

    def run(self, skip: set[str]) -> dict:
        root = self.data_root / "projects"
        projects = sorted(path for path in root.glob("*") if (path / "project.json").is_file())
        for folder in projects:
            if folder.name not in skip:
                self.project(folder)
        self.leveled(projects)
        self.capcut()
        self.versions()
        return self.report()

    def report(self) -> dict:
        return {"freed": self.freed, "files": self.files, "by_kind": dict(self.by_kind), "applied": self.apply}


def lasting(source: Path, folder: Path) -> bool:
    """Whether a sound lies, as a real file, in a lasting folder of its own project."""
    try:
        source, folder = source.resolve(), folder.resolve()
        inside = source.relative_to(folder).parts
        return len(inside) > 1 and inside[0] in LASTING and source.is_file() and source.stat().st_size > 0
    except (OSError, ValueError):
        return False


def tidy(data_root: Path, skip: set[str] = frozenset(), apply: bool = True) -> dict:
    """Clear what the studio no longer reads, leaving the projects in `skip` (work runs there) as they are."""
    return Tidy(data_root, apply).run(set(skip))


def gigabytes(value: int) -> str:
    return f"{value / 2**30:.1f} ГБ"
