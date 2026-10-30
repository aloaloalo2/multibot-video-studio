"""A YouTube thumbnail for a project, drawn by Codex (ChatGPT image generation) through its command line.

The settings of a run are the project's title and script, which the author may edit first, and free wishes. Codex works
in the episode's «Превью» folder with the channel's style frames attached and saves exactly one picture there next to its
prompt («Превью vN.png», «Промпт прев'ю vN.txt»), as the channel rules ask. The new picture becomes «Превью.png» in the
episode folder and the project card's cover; an earlier «Превью.png» that has no copy in «Превью» is kept there first.
"""
from __future__ import annotations

import filecmp, re, shutil, subprocess, threading, time
from pathlib import Path

from PIL import Image, UnidentifiedImageError

import store

CODEX = Path("/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex")
PREVIEW = "Превью.png"
FOLDER = "Превью"
TIMEOUT = 20 * 60
ACTIVE: set[str] = set()
LOCK = threading.Lock()


def episode(project: dict) -> Path:
    path = Path(project.get("episode_path") or "")
    if not project.get("episode_path") or not path.is_dir():
        raise store.StudioError("У проєкту немає папки випуску")
    return path


def preview(project: dict) -> Path | None:
    try:
        path = episode(project) / PREVIEW
    except store.StudioError:
        return None
    return path if path.is_file() else None


def first_title(folder: Path) -> str | None:
    """The first A/B title in the episode's «Метаданные.txt», if there is one."""
    meta = folder / "Метаданные.txt"
    if not meta.is_file():
        return None
    lines = meta.read_text(encoding="utf-8", errors="replace").splitlines()
    for i, line in enumerate(lines):
        if re.match(r"\s*(ТАЙТЛ|ЗАГОЛОВ|HEADLINE|TITLE)", line, re.I):
            return next((item.strip() for item in lines[i + 1:] if item.strip() and not item.startswith("=")), None)
    return None


def defaults(pid: str) -> dict:
    project = store.load_project(pid)
    folder = episode(project)
    plan = store.load_project_plan(pid) or {}
    script = plan.get("spoken_script") or plan.get("script") or ""
    if not script and (folder / "Сценарий.txt").is_file():
        script = (folder / "Сценарий.txt").read_text(encoding="utf-8", errors="replace")
    return {"title": first_title(folder) or project["name"], "script": script.strip(), "job": state(pid),
            "preview": bool(preview(project))}


def job_path(pid: str) -> Path:
    return store.project_dir(pid) / "thumbnail-job.json"


def state(pid: str) -> dict | None:
    data = store.read_json(job_path(pid), None)
    if isinstance(data, dict) and data.get("status") == "running" and pid not in ACTIVE:
        data.update(status="failed", error="Студію перезапустили під час генерації. Спробуйте ще раз.")
    return data


def references(folder: Path) -> list[Path]:
    """The channel's style frames («Еталон стилю/Референс кадру*.png»), so the thumbnail is drawn in the video's look."""
    style = folder.parent / "Еталон стилю"
    return sorted(style.glob("Референс кадру*.png"))[:2] if style.is_dir() else []


def prompt(title: str, script: str, wishes: str, refs: list[Path], name: str) -> str:
    style = (f"Style: the same 2D look as the {len(refs)} attached reference frame{'s' if len(refs) > 1 else ''}, polished to the level of a "
             "top YouTube channel thumbnail." if refs else "Style: polished to the level of a top YouTube channel thumbnail.")
    return f"""YouTube thumbnail for the video "{title}". Landscape 16:9, 1536x864 or wider.

{style} One clean, bold, high-contrast image that reads instantly at phone size: one single moment from the video that
makes a viewer click, a strong emotion, one focal point, no clutter.

Pick that moment from the video's script below. Text: at most one or two huge words that add to the title, or none.
Leave the top-right corner empty (the channel logo goes there) and keep the bottom-right corner clear (YouTube puts the
video length there). No other text, watermarks, borders or frames.
{f'''
The author's wishes, which come first:
{wishes.strip()}
''' if wishes.strip() else ''}
Script of the video:
{script.strip()[:12000]}

Use the built-in image generation tool and make exactly one image. Save it in the current working directory as
"{name}", save the prompt you gave the image tool next to it as "{name.replace('Превью', "Промпт прев'ю").replace('.png', '.txt')}",
and reply only with the saved path."""


def run(pid: str, title: str, script: str, wishes: str) -> None:
    data = state(pid) or {}
    try:
        project = store.load_project(pid)
        folder = episode(project)
        work = folder / FOLDER
        work.mkdir(exist_ok=True)
        number = 1 + max([int(m.group(1)) for p in work.glob("Превью v*.png") if (m := re.match(r"Превью v(\d+)", p.stem))] or [0])
        name = f"Превью v{number}.png"
        refs = references(folder)
        command = [str(CODEX), "exec", "-s", "workspace-write", "--skip-git-repo-check", "-C", str(work)]
        for ref in refs:
            command += ["-i", str(ref)]
        result = subprocess.run(command + ["-"], input=prompt(title, script, wishes, refs, name), cwd=work, text=True,
                                capture_output=True, timeout=TIMEOUT)
        (work / f"Лог генерації v{number}.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
        made = work / name
        try:
            with Image.open(made) as image:
                image.verify()
        except (OSError, UnidentifiedImageError):
            raise RuntimeError("Codex не зберіг картинку. " + (result.stderr or result.stdout)[-300:].strip())
        root = folder / PREVIEW
        if root.is_file() and not any(filecmp.cmp(root, other, shallow=False) for other in work.glob("Превью*.png")):
            shutil.copy2(root, work / f"Превью до v{number}.png")
        shutil.copyfile(made, root)
        data.update(status="done", file=name, finished_at=time.time(), error=None)
    except subprocess.TimeoutExpired:
        data.update(status="failed", error="Codex не встиг за 20 хвилин", finished_at=time.time())
    except (OSError, RuntimeError, store.StudioError) as error:
        data.update(status="failed", error=str(error), finished_at=time.time())
    finally:
        store.atomic_json(job_path(pid), data)
        with LOCK:
            ACTIVE.discard(pid)


def start(pid: str, title: str, script: str, wishes: str = "") -> dict:
    project = store.load_project(pid)
    episode(project)
    title, script, wishes = (str(value or "").strip() for value in (title, script, wishes))
    if not title:
        raise store.StudioError("Вкажіть заголовок")
    if not CODEX.is_file():
        raise store.StudioError("Не знайдено Codex у ChatGPT.app", 503)
    with LOCK:
        if pid in ACTIVE:
            return state(pid)
        ACTIVE.add(pid)
        data = {"status": "running", "started_at": time.time(), "title": title, "wishes": wishes}
        store.atomic_json(job_path(pid), data)
    threading.Thread(target=run, args=(pid, title, script, wishes), daemon=True).start()
    return data
