"""Content fingerprints for incremental visual review, shared by sheets/status.

Unknown scene modules are global dependencies. Named shot modules are local,
with static imports followed transitively; adjacent shots are included for cuts.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

TAKE = re.compile(r"(?:take|registerShot)\(\s*['\"]([\w-]+)['\"]")
LOOP = re.compile(r"for\s*\(\s*const\s+(\w+)\s+of\s+\[([^\]]*)\]\s*\)\s*take\(\s*\1\b")
IMPORT = re.compile(r"(?:from\s*|import\s*\(?\s*)['\"]([^'\"]+)['\"]")


def fingerprints(proj: Path, root: Path, frames: list[dict]) -> dict[int, str]:
    proj, root = proj.resolve(), root.resolve()
    story = json.loads((proj / "story/shots.json").read_text())
    shots = story["shots"]
    files = sorted((proj / "scenes").rglob("*.js"))
    texts = {p: p.read_text(encoding="utf-8", errors="replace") for p in files}
    owners, shared = {}, set()
    for p, text in texts.items():
        ids = set(TAKE.findall(text))
        for _, values in LOOP.findall(text):
            ids.update(re.findall(r"['\"]([\w-]+)['\"]", values))
        if not ids:
            shared.add(p)
        for item in ids:
            owners.setdefault(item, set()).add(p)
    hashes = {}

    def file_hash(p):
        if p not in hashes:
            hashes[p] = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "missing"
        return (str(p), hashes[p])

    def dependencies(paths):
        found, pending = set(), list(paths)
        while pending:
            p = pending.pop()
            if p in found:
                continue
            found.add(p)
            for spec in IMPORT.findall(texts.get(p, "")):
                target = ((root / spec.lstrip("/")) if spec.startswith("/") else p.parent / spec).resolve()
                if target in texts and target not in found:
                    pending.append(target)
        return sorted(found)

    # Audio does not affect pixels. Visual overlays/config/assets/engine do.
    global_files = [proj / "config.json", Path(__file__).resolve(), Path(__file__).with_name("frame_review.py").resolve(),
                    root / "render.mjs", root / "player.html", root / "live.html"]
    for directory, pattern in ((root / "engine", "*"), (proj / "assets", "*"), (proj / "input", "*")):
        global_files += [p for p in directory.rglob(pattern) if p.is_file() and p.suffix.lower() not in {".wav", ".mp3", ".m4a", ".mp4"}]
    global_files += dependencies(shared)
    common = [file_hash(p) for p in sorted(set(global_files))]
    global_story = {k: v for k, v in story.items() if k not in {"shots", "sfx", "music", "amb"}}
    result = {}
    for f in frames:
        indices = [i for i, s in enumerate(shots) if s["start"] < f["end"] and s["end"] > f["start"]]
        indices = sorted({j for i in indices for j in (i - 1, i, i + 1) if 0 <= j < len(shots)})
        own_shots = [shots[i] for i in indices]
        ids = {p["id"] for s in own_shots for p in [s, *s.get("parts", [])]}
        local = dependencies({p for item in ids for p in owners.get(item, set())})
        payload = [common, global_story, f, own_shots, [file_hash(p) for p in local]]
        result[f["n"]] = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return result
