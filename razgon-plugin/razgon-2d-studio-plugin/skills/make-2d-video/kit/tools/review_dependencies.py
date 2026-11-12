"""Content fingerprints for incremental visual review, shared by sheets/status.

Unknown modules and global effects are shared dependencies. Named shot modules
and pure helpers are local, with imports followed transitively and adjacent cuts.
"""
from __future__ import annotations

import hashlib
import fnmatch
import json
import re
import subprocess
from subprocess import run as run_parser
from pathlib import Path

TAKE = re.compile(r"(?:take|registerShot)\(\s*['\"]([\w-]+)['\"]")
LOOP = re.compile(r"for\s*\(\s*const\s+(\w+)\s+of\s+\[([^\]]*)\]\s*\)\s*take\(\s*\1\b")
IMPORT = re.compile(r"(?:from\s*|import\s*\(?\s*)['\"]([^'\"]+)['\"]")


def scene_usage(root, texts):
    """Use the installed renderer's parser; uncertain analysis keeps all assets."""
    try:
        answer = run_parser(['node', str(Path(__file__).with_name('review_assets.cjs'))],
            input=json.dumps({'root':str(root),'files':[{'path':str(p),'source':text} for p,text in texts.items()]}),
            capture_output=True, text=True, timeout=15)
        data = json.loads(answer.stdout) if answer.returncode == 0 else None
        def valid(entry):
            return (isinstance(entry, dict) and all(isinstance(entry.get(k), list) and
                    all(isinstance(v, str) for v in entry[k]) for k in ('takes','names','patterns')) and
                    all(isinstance(entry.get(k), bool) for k in ('dynamic','global')))
        if isinstance(data, dict) and all(valid(data.get(str(p))) for p in texts):
            return data
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return {}


def fingerprints(proj: Path, root: Path, frames: list[dict]) -> dict[int, str]:
    proj, root = proj.resolve(), root.resolve()
    story = json.loads((proj / "story/shots.json").read_text())
    shots = story["shots"]
    files = sorted((proj / "scenes").rglob("*.js"))
    texts = {p: p.read_text(encoding="utf-8", errors="replace") for p in files}
    usage = scene_usage(root, texts)
    owners, shared = {}, set()
    for p, text in texts.items():
        ids = set(usage.get(str(p), {}).get('takes', [])) if usage else set(TAKE.findall(text))
        if not usage:
            for _, values in LOOP.findall(text):
                ids.update(re.findall(r"['\"]([\w-]+)['\"]", values))
        if not ids and usage.get(str(p), {}).get('global', True):
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
                allowed = proj in target.parents or root / 'engine' in target.parents
                if (target in texts or allowed and target.is_file()) and target not in found:
                    pending.append(target)
        return sorted(found)

    # Visual runtime and shared drawing code affect every frame. Asset-generation
    # prompts, unrelated PNGs and an appended registry entry do not.
    global_files = [proj / "config.json", Path(__file__).resolve(), Path(__file__).with_name("frame_review.py").resolve(),
                    Path(__file__).with_name('review_assets.cjs').resolve(),
                    root / "render.mjs", root / "player.html", root / "live.html"]
    global_files += [p for p in (root / 'engine').rglob('*') if p.is_file()]
    media = [p for directory in ('assets','input') for p in (proj / directory).rglob('*')
             if p.is_file() and p.suffix.lower() not in {'.wav','.mp3','.m4a','.mp4'}]
    shared_paths = dependencies(shared)
    global_files += shared_paths
    global_files += [p for p in media if p.suffix.lower() in {'.woff','.woff2','.ttf','.otf'}]
    common = [file_hash(p) for p in sorted(set(global_files))]
    registry = proj / 'assets/index.json'
    try:
        names = json.loads(registry.read_text()) if registry.is_file() else []
    except (OSError, ValueError):
        names = None
    registry_known = isinstance(names, list) and all(isinstance(n, str) for n in names)
    registry_names = set(names) if registry_known else set()
    global_story = {k: v for k, v in story.items() if k not in {"shots", "sfx", "music", "amb"}}
    result = {}
    for f in frames:
        indices = [i for i, s in enumerate(shots) if s["start"] < f["end"] and s["end"] > f["start"]]
        indices = sorted({j for i in indices for j in (i - 1, i, i + 1) if 0 <= j < len(shots)})
        own_shots = [shots[i] for i in indices]
        ids = {p["id"] for s in own_shots for p in [s, *s.get("parts", [])]}
        local = dependencies({p for item in ids for p in owners.get(item, set())})
        relevant = set(local) | set(shared_paths)
        unknown = not usage or not registry_known or any(usage.get(str(p), {}).get('dynamic', True) for p in relevant)
        literals = {value for p in relevant for value in usage.get(str(p), {}).get('names', [])}
        patterns = {value for p in relevant for value in usage.get(str(p), {}).get('patterns', [])}
        def referenced(p):
            if p == registry:
                return False  # Only membership of the frame's possible props matters.
            relative = p.relative_to(proj).as_posix()
            forms = (p.stem, p.name, relative, '/project/'+relative, './'+relative)
            return any(form in literals or any(fnmatch.fnmatchcase(form, pattern) for pattern in patterns) for form in forms)
        used = media if unknown else [p for p in media if referenced(p)]
        assets = [file_hash(p) for p in sorted(used)]
        membership = [(str(p.relative_to(proj)), p.stem in registry_names) for p in used if p.parent == registry.parent]
        payload = [common, global_story, f, own_shots, [file_hash(p) for p in local], assets, membership]
        result[f["n"]] = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return result
