"""A YouTube thumbnail for a project: Claude Opus 5.5 writes the picture's prompt, Codex (ChatGPT image generation) draws it.

The settings of a run are the project's title and script, which the author may edit first, and free wishes. Claude Code
(on the claude.ai subscription, Read only) picks the one moment from the script and writes the prompt the way the
channel's approved ones are written («Еталон стилю/Еталон промпт прев'ю*.txt», with the approved thumbnails and the
style frames to look at), as the thumbnails of the first episodes were made. Codex then draws exactly that prompt in the
episode's «Превью» folder with the style frames attached and saves one picture next to the prompt («Превью vN.png»,
«Промпт прев'ю vN.txt»). The new picture becomes «Превью.png» in the episode folder and the project card's cover; an
earlier «Превью.png» that has no copy in «Превью» is kept there first.
"""
from __future__ import annotations

import filecmp, json, re, shutil, subprocess, threading, time
from pathlib import Path

from PIL import Image, UnidentifiedImageError

import director
import store

CODEX = Path("/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex")
PREVIEW = "Превью.png"
FOLDER = "Превью"
TIMEOUT = 20 * 60
PROMPT_TIMEOUT = 10 * 60
# the prompt is the creative half of the thumbnail (user, 30 October 2026: «краще, щоб Claude Code писав промпт, як і
# раніше було... получались дуже круті результати»)
PROMPT_EFFORT = "high"
# the thumbnail takes its look from the video's own frames, so a few must be made first (user, 30 October 2026)
MIN_FRAMES = 2
STILLS = 3
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
            "preview": bool(preview(project)), "pictures": len(pictures(project)), "min_frames": MIN_FRAMES}


def job_path(pid: str) -> Path:
    return store.project_dir(pid) / "thumbnail-job.json"


def state(pid: str) -> dict | None:
    data = store.read_json(job_path(pid), None)
    if isinstance(data, dict) and data.get("status") == "running" and pid not in ACTIVE:
        data.update(status="failed", error="Студію перезапустили під час генерації. Спробуйте ще раз.")
    return data


def examples(folder: Path) -> tuple[list[Path], list[Path]]:
    """The channel's approved thumbnail prompts and pictures in «Еталон стилю», the bar a new prompt is written to."""
    style = folder.parent / "Еталон стилю"
    if not style.is_dir():
        return [], []
    return sorted(style.glob("Еталон промпт прев'ю*.txt"))[:3], sorted(style.glob("Еталон прев'ю*.png"))[:3]


def pictures(project: dict) -> list[dict]:
    """The video's made frames: pictures on the timeline, apart from the channel's logo and plate, in time order."""
    clips = [clip for track in project.get("tracks", []) for clip in track.get("clips", [])
             if clip.get("kind") in {"video", "image"} and not re.search("Логотип|Плашка", clip.get("title") or "")]
    return sorted(clips, key=lambda clip: float(clip.get("start") or 0))


def frame_stills(project: dict, work: Path) -> list[Path]:
    """Stills of up to three made frames spread over the video («Кадр ролику N.png»), the style reference of the thumbnail."""
    clips, assets = pictures(project), {asset.get("id"): asset for asset in project.get("assets", [])}
    if not clips:
        return []
    count = min(STILLS, len(clips))
    chosen = [clips[round(i * (len(clips) - 1) / max(1, count - 1))] for i in range(count)]
    stills = []
    for number, clip in enumerate(chosen, 1):
        source, target = Path((assets.get(clip.get("asset_id")) or {}).get("path") or ""), work / f"Кадр ролику {number}.png"
        if not source.is_file():
            continue
        if clip["kind"] == "image":
            with Image.open(source) as image:
                image.convert("RGB").save(target)
        else:
            moment = float(clip.get("trim_start") or 0) + float(clip.get("duration") or 0) / 2
            done = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-ss", f"{moment:.3f}", "-i", str(source), "-frames:v", "1", str(target)],
                                  capture_output=True, timeout=60)
            if done.returncode or not target.is_file():
                continue
        stills.append(target)
    return stills


def references(folder: Path) -> list[Path]:
    """The channel's style frames («Еталон стилю/Референс кадру*.png»), so the thumbnail is drawn in the video's look."""
    style = folder.parent / "Еталон стилю"
    # the numbered frames show the channel's current look; named ones («(сон)») belong to one older episode
    return sorted(style.glob("Референс кадру*.png"), key=lambda path: ("(" in path.name, path.name))[:2] if style.is_dir() else []


def brief(title: str, script: str, wishes: str, folder: Path, refs: list[Path]) -> str:
    """What Claude gets: the channel's bar, the video, the author's wishes; it answers with the prompt alone."""
    prompts, pictures = examples(folder)
    attached = ", ".join(path.name for path in refs) or "немає"
    wished = f"\nПобажання автора, вони головні:\n{wishes.strip()}\n" if wishes.strip() else ""
    approved = "\n\n".join(f"--- {path.name}\n{path.read_text(encoding='utf-8', errors='replace').strip()[:3000]}" for path in prompts)
    approved = f"\nТак писалися схвалені прев'ю каналу. Тримай цю будову, тон і рівень деталей:\n\n{approved}\n" if approved else ""
    look = "; ".join(str(path) for path in [*refs, *pictures])
    look = f"\nПеред тим як писати, подивись інструментом Read ці картинки, щоб знати стиль і героя: {look}\n" if look else ""
    # a Razgon episode describes its heroes and world in the story bible: the thumbnail's hero must be the video's
    link = store.read_json(folder / "razgon.json", None)
    bible = Path(link["project"]) / "story" / "bible.md" if isinstance(link, dict) and link.get("project") else None
    if bible and bible.is_file():
        look += f"Герої, їхній вигляд і світ ролику описані тут, прочитай перед тим як писати: {bible}\n"
    return f"""Ти пишеш промпт для прев'ю YouTube-ролика. Картинку за ним намалює Codex вбудованим генератором зображень, до нього
будуть прикріплені кадри цього ролику як референс стилю й героя: {attached}. Прев'ю має виглядати як цей ролик.

Ролик: "{title}".
{wished}
Правила каналу для прев'ю: один кадр у стилі ролику, як у топових каналів; сильна емоція; один фокус, без нагромадження;
текст максимум одне-два величезні слова, що доповнюють заголовок, або без тексту; жодних дрібних звукових написів;
правий верхній кут порожній під логотип каналу, правий нижній вільний під тривалість відео; без рамок і водяних знаків.
Візьми зі сценарію один момент, на який глядач клікне, і опиши його точно: герой, поза, вираз обличчя, предмети, фон,
світло, кольори, де стоїть текст.
{approved}{look}
Сценарій ролику:
{script.strip()[:12000]}

Відповідай тільки самим промптом англійською, без вступу, пояснень і лапок навколо. Не пиши, куди зберегти файл: це додасть студія."""


def drawing(prompt_text: str, name: str) -> str:
    """What Codex gets: Claude's prompt, word for word, and where the one picture goes."""
    return f"""{prompt_text.strip()}

Use the built-in image generation tool with exactly this prompt and make exactly one image. Save it in the current working
directory as "{name}" and reply only with the saved path."""


def write_prompt(text: str, cwd: Path) -> tuple[str, dict]:
    """Claude Code writes the picture's prompt; returns it with the run's answer (cost, session)."""
    try:
        cli = director.executable()
    except RuntimeError as error:
        raise RuntimeError(str(error)) from None
    command = [str(cli), "--model", director.MODEL, "--effort", PROMPT_EFFORT, "--strict-mcp-config", "--allowedTools", "Read",
               "--output-format", "json", "-p"]
    result = subprocess.run(command, input=text, cwd=cwd, text=True, capture_output=True, timeout=PROMPT_TIMEOUT)
    try:
        answer = json.loads(result.stdout.strip().splitlines()[-1]) if result.stdout.strip() else {}
    except ValueError:
        answer = {}
    if director.limit_stop(answer):
        raise RuntimeError(director.limit_stop(answer) + " Прев'ю можна згенерувати, коли ліміт оновиться.")
    written = re.sub(r"^```\w*\n|\n```$", "", str(answer.get("result") or "").strip()).strip()
    if result.returncode or answer.get("is_error") or len(written) < 200:
        raise RuntimeError("Claude не написав промпт прев'ю. " + (written or result.stderr or result.stdout)[-300:].strip())
    return written, answer


def run(pid: str, title: str, script: str, wishes: str) -> None:
    data = state(pid) or {}
    try:
        project = store.load_project(pid)
        folder = episode(project)
        work = folder / FOLDER
        work.mkdir(exist_ok=True)
        number = 1 + max([int(m.group(1)) for p in work.glob("Превью v*.png") if (m := re.match(r"Превью v(\d+)", p.stem))] or [0])
        name = f"Превью v{number}.png"
        # the video's own frames are the reference; the channel's style frames only stand in when they cannot be read
        refs = frame_stills(project, work) or references(folder)
        # 1. Claude picks the moment and writes the prompt; it is kept next to the picture even if the drawing fails
        written, answer = write_prompt(brief(title, script, wishes, folder, refs), folder.parent)
        (work / f"Промпт прев'ю v{number}.txt").write_text(written + "\n", encoding="utf-8")
        data.update(stage="drawing", prompt_cost_usd=answer.get("total_cost_usd"))
        store.atomic_json(job_path(pid), data)
        # 2. Codex draws it with the channel's style frames attached
        command = [str(CODEX), "exec", "-s", "workspace-write", "--skip-git-repo-check", "-C", str(work)]
        for ref in refs:
            command += ["-i", str(ref)]
        result = subprocess.run(command + ["-"], input=drawing(written, name), cwd=work, text=True,
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
    except subprocess.TimeoutExpired as error:
        late = "Claude не написав промпт за 10 хвилин" if error.timeout == PROMPT_TIMEOUT else "Codex не встиг за 20 хвилин"
        data.update(status="failed", error=late, finished_at=time.time())
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
    if len(pictures(project)) < MIN_FRAMES:
        raise store.StudioError(f"Прев'ю можна створити, коли готові хоча б {MIN_FRAMES} кадри ролику: з них береться стиль", 409)
    if not CODEX.is_file():
        raise store.StudioError("Не знайдено Codex у ChatGPT.app", 503)
    with LOCK:
        if pid in ACTIVE:
            return state(pid)
        ACTIVE.add(pid)
        data = {"status": "running", "stage": "prompt", "started_at": time.time(), "title": title, "wishes": wishes}
        store.atomic_json(job_path(pid), data)
    threading.Thread(target=run, args=(pid, title, script, wishes), daemon=True).start()
    return data
