"""Motion design written as code (user, 25 November 2026: «моушен дизайн професійний, який йому дозволяє робити все, що
він захоче… пишеться кодом»). A clip of kind "animation" with content_type "code" holds the JavaScript source of
`function draw(ctx, t, info)`: Canvas 2D on a transparent canvas the size of the film, `t` in seconds from the clip's start.
The preview runs it live (frontend/motion-code.js); the export renders the same runtime on the studio's own
/motion-code.html into a ProRes 4444 video with alpha (tools/motion_code_render.mjs), laid over the frame like any video.
"""
import hashlib
import json
import os
import subprocess
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


def spec(project: dict, clip: dict) -> dict:
    return {"code": clip.get("code") or "", "width": int(project.get("width") or 1920), "height": int(project.get("height") or 1080),
            "fps": int(project.get("fps") or 25), "duration": float(clip["duration"]), "words": clip.get("code_words") or [],
            "assets": {name: f"/api/projects/{project['id']}/assets/{aid}/file" for name, aid in (clip.get("code_assets") or {}).items()}}


def fingerprint(data: dict) -> str:
    runtime = [hashlib.sha256(path.read_bytes()).hexdigest() for path in RUNTIME if path.is_file()]
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


def render(project: dict, clip: dict) -> Path:
    """The clip as a transparent video, made once for the same code, size, rate and length (the cache of the episode)."""
    data = spec(project, clip)
    validate(data["code"])
    folder = store.cache_dir(project) / "motion-code"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (fingerprint(data)[:32] + ".mov")
    if target.is_file() and target.stat().st_size:
        return target
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
    return _run(["--spec", str(spec_file), "--stills", ",".join(f"{float(t):.3f}" for t in moments), "--out-dir", str(folder)], timeout=120)
