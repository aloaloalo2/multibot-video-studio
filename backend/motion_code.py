"""Motion design written as code (user, 25 November 2026: «моушен дизайн професійний, який йому дозволяє робити все, що
він захоче… пишеться кодом»). A clip of kind "animation" with content_type "code" holds the JavaScript source of
`function draw(ctx, t, info)`: Canvas 2D on a transparent canvas the size of the film, `t` in seconds from the clip's start.
The preview runs it live (frontend/motion-code.js); the export renders the same runtime on the studio's own
/motion-code.html into a ProRes 4444 video with alpha (tools/motion_code_render.mjs), laid over the frame like any video.
"""
from __future__ import annotations

import hashlib
import re
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import store

MAX_CODE = 200_000
RENDERER = store.APP_ROOT / "tools" / "motion_code_render.mjs"
RUNTIME = [store.APP_ROOT / "frontend" / "motion-code.js", store.APP_ROOT / "frontend" / "motion-code.html", RENDERER]
STUDIO_URL = os.environ.get("VIDEOKEY_STUDIO_URL", "http://127.0.0.1:8770")


def validate(code) -> str:
    if not isinstance(code, str) or not code.strip():
        raise store.StudioError("Передайте код моушн-дизайну")
    if len(code) > MAX_CODE:
        raise store.StudioError("Код моушн-дизайну задовгий (понад 200 000 символів)")
    if "draw" not in code:
        raise store.StudioError("Код має оголосити function draw(ctx, t, info)")
    return code


def _modules() -> Path:
    import sys
    sys.path.insert(0, str(store.APP_ROOT / "tools"))
    try:
        import razgon_sync
        home = razgon_sync.home()
    except Exception:
        home = None
    return Path(home or store.APP_ROOT / "razgon-2d-studio") / "node_modules"


PAD = 1.6   # seconds drawn before and after a clip: room for any transition at its edges (joins.MAX_SQUEEZE · natural length)


FOLLOW_USE = re.compile(r"info\.(pin|onPhoto|photo)\b")
_PLACE_KEYS = ("start", "duration", "x", "y", "width", "height", "scale", "easing", "keyframes")


def follow_of(project: dict, clip: dict) -> dict | None:
    """The frame's picture the code pins its elements to (user, 26 November 2026: «навчи привязувати елементи легко шоб
    рух повторювався»): the largest picture of the code clip's frame group, its blurred backing and accents left out,
    with its place, zoom and keyframes; the same choice as codeFollow in frontend/universal.js."""
    group = next((g for g in project.get("scene_groups", []) if clip.get("id") in g.get("clip_ids", [])), None)
    if not group:
        return None
    clips = {c["id"]: c for t in project.get("tracks", []) for c in t.get("clips", [])}
    best = None
    for cid in group.get("clip_ids", []):
        c = clips.get(cid)
        title = str((c or {}).get("title", "")).lower()
        if not c or cid == clip.get("id") or c.get("kind") not in ("image", "video") or c.get("content_type") or c.get("frame_background") \
                or "чорний фон" in title or " фон" in title or "акцент" in title:
            continue
        area = float(c.get("width", 1)) * float(c.get("height", 1))
        if best is None or area > best[0] + 1e-9:
            best = (area, c)
    return {k: best[1].get(k) for k in _PLACE_KEYS} if best else None


def spec(project: dict, clip: dict) -> dict:
    follow = {}
    if FOLLOW_USE.search(clip.get("code") or ""):   # only a code that pins to the picture carries it (and re-renders with it)
        follow = {"follow": follow_of(project, clip), "self": {k: clip.get(k) for k in _PLACE_KEYS}}
    return {**follow, "code": clip.get("code") or "", "width": int(project.get("width") or 1920), "height": int(project.get("height") or 1080),
            "fps": int(project.get("fps") or 25), "duration": float(clip["duration"]), "words": clip.get("code_words") or [],
            "pad_head": PAD, "pad_tail": PAD,
            "assets": {name: f"/api/projects/{project['id']}/assets/{aid}/file" for name, aid in (clip.get("code_assets") or {}).items()}}


CHECK_PART = re.compile(rb"[ \t]*/\* check:start.*?/\* check:end \*/(?:[ \t]*\n)?", re.S)


def fingerprint(data: dict) -> str:
    # the text check's parts of the runtime (marked check:start … check:end) never change the drawing: a change to them
    # left every render of every episode out of date (61 clips of Astrofizika, 26 November 2026)
    runtime = [hashlib.sha256(CHECK_PART.sub(b"", path.read_bytes())).hexdigest() for path in RUNTIME if path.is_file()]
    return hashlib.sha256(json.dumps([data, runtime], sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _run(arguments: list, timeout: int) -> dict:
    result = subprocess.run(["node", str(RENDERER), "--studio", STUDIO_URL, "--modules", str(_modules()), *arguments],
                            capture_output=True, text=True, timeout=timeout)
    for line in reversed(result.stdout.splitlines()):
        try:
            answer = json.loads(line)
        except ValueError:
            continue
        if isinstance(answer, dict):
            return answer
    return {"ok": False, "error": (result.stderr or result.stdout or f"код {result.returncode}").strip()[-600:]}


KEEP_SECONDS = 30 * 60   # a render no clip uses any more stays this long: an export started on the older code may still read it


def prune(project: dict) -> int:
    """Drop the renders and checks of motion code no clip of the project uses any more (a new version of the code makes a
    new file; 1.5 GB piled up on «Космос PRO», 25 November 2026). Returns the bytes freed."""
    folder = store.cache_dir(project) / "motion-code"
    if not folder.is_dir():
        return 0
    clips = [c for t in project.get("tracks", []) for c in t.get("clips", []) if c.get("content_type") == "code"]
    used, checks = set(), {"check-" + c["id"] for c in clips}
    for clip in clips:
        try:
            used.add(fingerprint(spec(project, clip))[:32])
        except Exception:
            return 0   # a clip that cannot be read: keep everything
    freed, now = 0, time.time()
    for item in folder.iterdir():
        stem = item.name.split(".")[0]
        try:
            if now - item.stat().st_mtime < KEEP_SECONDS:
                continue
            # a part left by a render that was killed shares its clip's name: it goes all the same (11 GB of them piled up)
            if (stem in used or item.name in checks) and ".part." not in item.name:
                continue
            if item.is_dir():
                freed += sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
                shutil.rmtree(item, ignore_errors=True)
            else:
                freed += item.stat().st_size
                item.unlink(missing_ok=True)
        except OSError:   # gone meanwhile, or unreadable: the next prune looks again
            continue
    return freed


RENDER_AT_ONCE = 3   # one Chromium each, some 0.3–0.5 GB; a clip of 20 s takes about 25 s alone
# for the whole process: every thread that built a manifest (the CapCut warm-up, stills, an export) started its own three
# and the server ran fifteen Chromiums at once, the same clips twice (26 November 2026)
_SLOTS = threading.BoundedSemaphore(RENDER_AT_ONCE)
_TARGETS: dict = {}
_TARGETS_LOCK = threading.Lock()


def render_all(project: dict) -> None:
    """Every motion-code clip of the project not rendered yet, RENDER_AT_ONCE at a time: the export rendered them one
    after another, 48 changed clips some 20 minutes (26 November 2026, «швидкий… експорт»). A clip that fails here is
    left to the export's own call, which reports it."""
    from concurrent.futures import ThreadPoolExecutor
    clips = [c for t in project.get("tracks", []) for c in t.get("clips", []) if c.get("content_type") == "code"]
    folder = store.cache_dir(project) / "motion-code"
    todo = []
    for clip in clips:
        try:
            if not (folder / (fingerprint(spec(project, clip))[:32] + ".mov")).is_file():
                todo.append(clip)
        except (store.StudioError, ValueError, KeyError):
            continue
    if len(todo) < 2:
        return

    def one(clip):
        try:
            render(project, clip)
        except (store.StudioError, OSError, subprocess.SubprocessError):
            pass
    with ThreadPoolExecutor(RENDER_AT_ONCE) as pool:
        list(pool.map(one, todo))


def render(project: dict, clip: dict) -> Path:
    """The clip as a transparent video, made once for the same code, size, rate and length (the cache of the episode)."""
    data = spec(project, clip)
    validate(data["code"])
    folder = store.cache_dir(project) / "motion-code"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (fingerprint(data)[:32] + ".mov")
    if target.is_file() and target.stat().st_size:
        return target
    with _TARGETS_LOCK:
        lock = _TARGETS.setdefault(str(target), threading.Lock())
    with lock:   # a second caller of the same clip waits for the first and takes its file
        if target.is_file() and target.stat().st_size:
            return target
        with _SLOTS:
            return _render(data, clip, target)


def _render(data: dict, clip: dict, target: Path) -> Path:
    spec_file = target.with_suffix(".json")
    store.atomic_json(spec_file, data)
    answer = _run(["--spec", str(spec_file), "--out", str(target)], timeout=max(120, int(data["duration"] * 30)))
    if not answer.get("ok") or not target.is_file():
        raise store.StudioError(f"Моушн-код «{clip.get('title') or clip.get('id')}»: {answer.get('error') or 'не вдалося відрендерити'}")
    return target


def stills(project: dict, clip: dict, moments: list, folder: Path) -> dict:
    """PNG stills (with alpha) of the clip at the given seconds from its start, to check the code before it goes in.
    {ok, stills, error}."""
    data = spec(project, clip)
    validate(data["code"])
    folder.mkdir(parents=True, exist_ok=True)
    spec_file = folder / "spec.json"
    store.atomic_json(spec_file, data)
    answer = _run(["--spec", str(spec_file), "--stills", ",".join(f"{float(t):.3f}" for t in moments), "--out-dir", str(folder)], timeout=120)
    if answer.get("ok") and fades_out(answer.get("stills") or []):
        answer["warning"] = FADES_OUT
    return answer


FADES_OUT = ("графіка зникає до кінця кадру: намальоване має лишатися до кінця шару, перехід забирає його разом із кадром "
             "(приберіть затухання чи відліт наприкінці)")


def coverage(file) -> float:
    """The share of the still's pixels the graphics covers (alpha above a quarter)."""
    from PIL import Image
    with Image.open(file) as image:
        alpha = image.convert("RGBA").getchannel("A")
        histogram = alpha.histogram()
    return sum(histogram[64:]) / max(1, sum(histogram))


def fades_out(stills: list) -> bool:
    """The last still (the clip's end) keeps less than half of the most the graphics covered before it (user, 25 November
    2026: «воно не має пропадати… хай буде до кінця кадра»)."""
    if len(stills) < 2:
        return False
    shares = [coverage(file) for file in stills]
    return max(shares[:-1]) > 0.002 and shares[-1] < 0.5 * max(shares[:-1])
