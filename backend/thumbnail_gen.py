"""A YouTube thumbnail for a project: Claude Opus 5.5 writes the picture's prompt, Codex (ChatGPT image generation) draws it.

The settings of a run are the project's title and script, which the author may edit first, and free wishes. Claude Code
(on the claude.ai subscription, Read only) picks the one moment from the script and writes the prompt the way the
channel's approved ones are written («Еталон стилю/Еталон промпт прев'ю*.txt», with the approved thumbnails and the
style frames to look at), as the thumbnails of the first episodes were made. Codex then draws exactly that prompt with
the style frames attached and saves one picture next to the prompt («Превью vN.png», «Промпт прев'ю vN.txt»).

The studio keeps the thumbnails in the project's own folder (data/projects/<id>/preview), so they outlive the episode
folder: the new picture becomes «Превью.png» there and the project card's cover, and an earlier one that has no version
copy is kept as «Превью до vN.png». While the episode folder exists it gets a copy as well: «Превью.png» next to the
video and the picture with its prompt in «Превью», as the channel rules ask.
"""
from __future__ import annotations

import filecmp, json, re, shutil, subprocess, tempfile, threading, time
from pathlib import Path

from PIL import Image, UnidentifiedImageError

import director
import frame_progress
import store
import job_timing
import channel_hero
import agent_storage
import image_delivery
import thumbnail_compare

CODEX = Path("/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex")
PREVIEW = "Превью.png"
FOLDER = "Превью"
TIMEOUT = 20 * 60
PROMPT_TIMEOUT = 10 * 60
TRENDING_RULES = Path(__file__).parent / "prompts" / "trending_thumbnail.md"
# the prompt is the creative half of the thumbnail (user, 30 October 2026: «краще, щоб Claude Code писав промпт, як і
# раніше було... получались дуже круті результати»)
PROMPT_EFFORT = "high"
# Animated projects take their look from made frames; regular projects can start from their script and title.
PROMPT_WRITERS = ("claude", "trending")
MIN_FRAMES = 2
STILLS = 3
ACTIVE: set[str] = set()
LOCK = threading.Lock()


def keep_dir(pid: str) -> Path:
    """The studio's own folder for the project's thumbnails: versions, prompts, logs and the current «Превью.png».
    It lives with the project, so the thumbnail outlives the episode folder (user, 30 October 2026)."""
    return store.project_dir(pid) / "preview"


def episode_preview(project: dict) -> Path | None:
    folder = Path(project.get("episode_path") or "")
    if not project.get("episode_path") or not folder.is_dir():
        return None
    return next((path for path in (folder / PREVIEW, folder / "Превью.jpg", folder / "Превью.jpeg") if path.is_file()), None)


def preview(project: dict) -> Path | None:
    """The project's thumbnail as the studio keeps it. One that so far lies only in the episode folder, or was replaced
    there by hand, is copied in on first sight."""
    source = episode_preview(project)
    try:
        kept = keep_dir(project["id"]) / PREVIEW
    except store.StudioError:            # a project the studio does not hold has only the episode's own
        return source
    if source and (not kept.is_file() or source.stat().st_mtime > kept.stat().st_mtime
                   and not (source.suffix == ".png" and filecmp.cmp(source, kept, shallow=False))):
        kept.parent.mkdir(exist_ok=True)
        with Image.open(source) as image:
            image.convert("RGB").save(kept)
    return kept if kept.is_file() else None


def first_title(folder: Path) -> str | None:
    """The first A/B title in the episode's «Метаданные.txt», if there is one."""
    return store.episode_title(folder)


VERSION = re.compile(r"Превью (?:до )?v(\d+)\.png")


def versions(pid: str) -> list[dict]:
    """Every thumbnail made for the project, newest first: «Превью vN.png» and the earlier «Превью до vN.png» (the one
    that stood before vN), with who wrote the prompt and which one is the cover now (user, 1 November 2026: «немає
    бібліотеки моїх прев'юшок»)."""
    work = keep_dir(pid)
    if not work.is_dir():
        return []
    kept = work / PREVIEW
    items = []
    try:comparisons = store.read_json(work / 'comparisons.json', {}) or {}
    except (OSError, ValueError):comparisons = {}
    for path in work.glob("Превью*.png"):
        match = VERSION.fullmatch(path.name)
        if not match:
            continue
        number = int(match.group(1))
        prompt = work / f"Промпт прев'ю v{number}.txt"
        head = ''
        if " до " not in path.name and prompt.is_file():
            with prompt.open(encoding='utf-8', errors='replace') as source:head = source.read(200)
        writer = "deepseek" if head.startswith("[DeepSeek]") else "trending" if head.startswith(("[Трендове прев’ю", "[Клонування · Codex]")) else "edit" if head.startswith("[Правка") else None
        edit = re.match(r"\[Правка Превью (?:до )?v(\d+)\.png\] (.*)", head)
        comparison = thumbnail_compare.describe(pid, path.name, comparisons)
        legacy = re.match(r'\[Правка (Превью (?:до )?v[1-9][0-9]*\.png)\]', head)
        if not comparison and legacy:comparison = {'kind':'edit','base':legacy.group(1)}
        items.append({"name": path.name, "number": number, "earlier": " до " in path.name, "writer": writer,
                      **({'comparison': comparison} if comparison else {}),
                      **({"from": int(edit.group(1)), "notes": edit.group(2).strip()} if edit else {}),
                      "current": kept.is_file() and filecmp.cmp(path, kept, shallow=False), "time": path.stat().st_mtime})
    return sorted(items, key=lambda item: (item["number"], not item["earlier"]), reverse=True)


def version_file(pid: str, name: str) -> Path:
    path = keep_dir(pid) / name
    if not VERSION.fullmatch(name) or not path.is_file():
        raise store.StudioError("Прев'ю не знайдено", 404)
    return path


def choose(pid: str, name: str) -> dict:
    """Make one of the made thumbnails the cover again: the studio's «Превью.png» and, while the episode folder is
    there, the one next to the video."""
    source = version_file(pid, name)
    with LOCK:
        if pid in ACTIVE:
            raise store.StudioError("Зачекайте, доки домалюється нове прев'ю", 409)
        shutil.copyfile(source, keep_dir(pid) / PREVIEW)
        project = store.load_project(pid)
        folder = Path(project.get("episode_path") or "")
        if project.get("episode_path") and folder.is_dir():
            image_delivery.copy_png(source, folder / PREVIEW)
    return {"versions": versions(pid)}


def creation_min_frames(project: dict) -> int:
    return MIN_FRAMES if store.project_animated(project) else 0


def defaults(pid: str) -> dict:
    project = store.load_project(pid)
    import idea_reference
    clone, _ = idea_reference.for_project(pid)
    folder = Path(project.get("episode_path") or "")
    plan = store.load_project_narration(pid) or {}
    script = plan.get("spoken_script") or plan.get("script") or (project.get("voice_script") or {}).get("text") or ""
    if not script and project.get("episode_path") and (folder / "Сценарий.txt").is_file():
        script = (folder / "Сценарий.txt").read_text(encoding="utf-8", errors="replace")
    return {"title": (first_title(folder) if folder.is_dir() and project.get("episode_path") else None) or project["name"], "script": script.strip(), "job": state(pid),
            "preview": bool(preview(project)), "pictures": store.picture_count(project), "min_frames": 0 if clone else creation_min_frames(project),
            "creation_min_frames": creation_min_frames(project), "reference_selection": True, "clone_reference": clone,
            "versions": versions(pid), "writers": list(PROMPT_WRITERS), "image_editing": True,
            "hero_reference": channel_hero.info(project['channel_id']) if project.get('channel_id') else None}


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


def code_stills(project: dict, work: Path) -> list[Path]:
    """Stills of up to three frames a Razgon episode holds as code, not rendered («Кадр ролику N.png»): the Razgon player
    draws each at the middle of its frame (render.mjs --stills); the video itself stays unrendered."""
    razgon = frame_progress.razgon_project(project)
    drawn = set(frame_progress.drawn(project["id"])) if razgon else set()
    frames = [frame for frame in (store.read_json(razgon / "story" / "studio_frames.json", {}) if razgon else {}).get("frames") or []
              if frame["number"] in drawn]
    if not frames:
        return []
    count = min(STILLS, len(frames))
    moments = [(frame["start"] + frame["end"]) / 2 for frame in (frames[round(i * (len(frames) - 1) / max(1, count - 1))] for i in range(count))]
    out = razgon / "build" / "thumbnail-stills"
    node = shutil.which("node") or "/opt/homebrew/bin/node"
    done = subprocess.run([node, "render.mjs", "--project", str(razgon), "--stills", ",".join(f"{t:.2f}" for t in moments), "--dir", str(out)],
                          cwd=razgon.parents[1], capture_output=True, timeout=600)
    if done.returncode:
        return []
    # render.mjs names a still «<t>s_<t>.png» and adds contact sheets: the stills in time order
    found = sorted((path for path in out.glob("*.png") if not path.name.startswith("sheet_")),
                   key=lambda path: float(path.stem.rsplit("_", 1)[-1]))
    stills = []
    for number, source in enumerate(found[:count], 1):
        target = work / f"Кадр ролику {number}.png"
        shutil.copyfile(source, target)
        stills.append(target)
    return stills


def episode_link(folder: Path) -> dict | None:
    project = store.project_for_episode(store.channel_id(folder.parent), folder)
    if project:
        return store.razgon_link(project)
    return store.read_json(folder / 'razgon.json', None)


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
    link = episode_link(folder)
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


def clone_brief(title: str, wishes: str, name: str, refs: list[Path]) -> str:
    """One isolated reference-adaptation contract for all prompt writers, without new-idea rules."""
    import idea_reference
    images = '\n'.join(str(path) for path in refs)
    return ("Write the English image-generation prompt for an original image built from the reference idea. "
            "Inspect the attached images (use Read for these local image files if available):\n" + images + "\n\n"
            + idea_reference.thumbnail_rules(title, name)
            + "\nAUTHOR'S EXPLICIT CHANGES FOR THIS CLONE ONLY:\n" + (wishes.strip() or 'None. Keep its idea and wording; create original visuals.')
            + "\nReturn only the image prompt. Quote the exact lettering read from the source image, in its original language. "
            "The separate image generator cannot see the source: fully describe the new image, with no source filenames or reference-relative instructions. "
            "Your role at this step is to write the prompt; the Studio runs image generation afterward.")


@job_timing.measure('service')
def write_prompt_codex(text: str, work: Path, refs: list[Path], name: str) -> tuple[str, dict]:
    """A fresh text-only authoring session; its visual context never reaches the drawing session."""
    output = work / ('codex-prompt-' + Path(name).stem + '.txt')
    output.unlink(missing_ok=True)
    command = [str(CODEX), "exec", "--ephemeral", "-s", "read-only", "--skip-git-repo-check",
               "-C", str(work), "--output-last-message", str(output)]
    for ref in refs: command += ["-i", str(ref)]
    result = subprocess.run(command + ["-"], input=text + "\nWrite the prompt only. Do not generate any image or invoke image generation in this session.",
                            cwd=work, text=True, capture_output=True, timeout=PROMPT_TIMEOUT)
    written = output.read_text(encoding='utf-8').strip() if output.is_file() else ''
    (work / ('Лог промпту ' + Path(name).stem + '.txt')).write_text(result.stdout + result.stderr, encoding='utf-8')
    if result.returncode or len(written) < 200:
        raise RuntimeError('Codex не написав промпт прев’ю. ' + (result.stderr or result.stdout)[-300:])
    return written, {}


@job_timing.measure('service')
def draw_clone_from_text(prompt: str, name: str, work: Path, hero: Path | None):
    """An isolated fresh session receives text and optional host identity, with no competitor pixels/files/history."""
    with tempfile.TemporaryDirectory(prefix='videokey-new-thumbnail-') as temp:
        clean = Path(temp)
        command = [str(CODEX), "exec", "--ephemeral", "-s", "workspace-write", "--skip-git-repo-check", "-C", str(clean)]
        if hero:
            portrait = clean / 'Головний герой.png'
            shutil.copyfile(hero, portrait)
            command += ['-i', str(portrait)]
        instructions = drawing(prompt, name) + """
Create the image from scratch from the written description above. This is a new image-generation session.
The competitor thumbnail is not an input to this session. Do not open, retrieve, trace or edit it.
Use only the written scene description and exact lettering. An attached channel portrait, if any, supplies host identity only.
Follow the explicit host inclusion choice in the written prompt. When the host is requested, use the attached portrait's exact identity, face and age. Keep neutral subjects distinct.
Generate original scene pixels, typography and composition. Save one new PNG in this working directory.
"""
        result = subprocess.run(command + ['-'], input=instructions, cwd=clean, text=True, capture_output=True, timeout=TIMEOUT)
        made = clean / name
        if made.is_file(): shutil.copyfile(made, work / name)
        return result


def drawing(prompt_text: str, name: str) -> str:
    """What Codex gets: Claude's prompt, word for word, and where the one picture goes."""
    return f"""{prompt_text.strip()}

Use the built-in image generation tool with exactly this prompt and make exactly one image. Save it in the current working
directory as "{name}" and reply only with the saved path."""


def trending(title: str, script: str, wishes: str, name: str) -> str:
    """Codex owns both the creative concept and drawing, using the author's English rules."""
    rules = TRENDING_RULES.read_text(encoding="utf-8").strip()
    return f"""{rules}

VIDEO TITLE (preserve its language):
{title}

AUTHOR'S WISHES (take priority when choosing the concept):
{wishes.strip() or 'Choose the strongest concept yourself.'}

VIDEO NARRATION:
{script.strip()[:12000]}

Save the finished image in the current working directory as "{name}".
This creates a new thumbnail version. Use the attached frames for style and character reference.
"""


@job_timing.measure('service')
def write_prompt(text: str, cwd: Path, work: Path, effort: str = PROMPT_EFFORT) -> tuple[str, dict]:
    """Claude Code writes the picture's prompt; returns it with the run's answer (cost, session)."""
    try:
        cli = director.executable()
    except RuntimeError as error:
        raise RuntimeError(str(error)) from None
    command = [str(cli), "--model", director.MODEL, "--effort", effort, "--strict-mcp-config", "--allowedTools", "Read",
               "--add-dir", str(work), "--output-format", "json", "-p"]
    result = subprocess.run(command, input=text, cwd=cwd, text=True, capture_output=True, timeout=PROMPT_TIMEOUT)
    try:
        answer = json.loads(result.stdout.strip().splitlines()[-1]) if result.stdout.strip() else {}
    except ValueError:
        answer = {}
    import project_costs
    project_costs.record_at(work.parent, 'claude_code', answer.get('total_cost_usd'))
    if director.limit_stop(answer):
        raise RuntimeError(director.limit_stop(answer) + " Прев'ю можна згенерувати, коли ліміт оновиться.")
    written = re.sub(r"^```\w*\n|\n```$", "", str(answer.get("result") or "").strip()).strip()
    if result.returncode or answer.get("is_error") or len(written) < 200:
        raise RuntimeError("Claude не написав промпт прев'ю. " + (written or result.stderr or result.stdout)[-300:].strip())
    return written, answer


def editing(notes: str, name: str) -> str:
    """What Codex gets for an author's remark on a thumbnail already made: the picture itself is attached."""
    return f"""Edit the attached YouTube thumbnail. Change only this, as the author asks (in Ukrainian or Russian):
{notes.strip()}

Keep everything else as it is: the composition, the characters and their look, the style, the colours, the text that is not
asked to change. Preserve the image dimensions and all existing branding.
Use the built-in image generation tool and make exactly one image. Save it in the current working directory as "{name}"
and reply only with the saved path."""


@job_timing.track('thumbnail', project='pid', job=lambda values: state(values['pid']))
def run(pid: str, title: str, script: str, wishes: str, writer: str = "claude", base: str | None = None, use_hero: bool | None = None, reference_id: str | None = None) -> None:
    data = {}
    try:
        data = state(pid) or {}
        project = store.load_project(pid)
        # the episode folder may be gone: its parent is still the channel with its approved samples and style frames
        folder = Path(project["episode_path"])
        work = keep_dir(pid)
        work.mkdir(exist_ok=True)
        number = 1 + max([int(m.group(1)) for p in work.glob("Превью *.png") if (m := VERSION.fullmatch(p.name))] or [0])
        name = f"Превью v{number}.png"
        import idea_reference
        clone, clone_image = idea_reference.thumbnail_reference(project, reference_id)
        hero, hero_rules = channel_hero.prepare(project, work, use_hero) if not base or use_hero is not None else (None, '')
        if use_hero is True:
            if not hero:raise store.StudioError('Не знайдено фото ведучого каналу для цього прев’ю.',409)
            hero_rules += '\nEXPLICIT HOST CHOICE FOR THIS IMAGE: include the exact attached channel host prominently, preserving identity, facial features and age. This overrides earlier optional-host or people-free suggestions. Never substitute a generic person or the source presenter.\n'
        if clone and not base and use_hero is None:
            # The attached hero is conditional here: extras stay extras, object-only references stay people-free.
            hero_rules = '\nГоловний герой.png is our host identity reference ONLY when replacing a source presenter. Do not add this host to neutral story-subject or object-only concepts.\n' if hero else ''
        channel_wishes = str(director.channel_settings(project).get("thumbnail_wishes") or "").strip()
        try:
            agent_rules = agent_storage.get_memory(project['channel_id']).strip()
        except (store.StudioError, KeyError):
            agent_rules = ''
        if agent_rules:
            wishes = ("Shared channel Agent rules (apply relevant thumbnail wishes; specific current wishes take priority):\n"
                      + agent_rules + "\n\nSpecific wishes for this thumbnail:\n" + wishes)
        if base:
            # an author's remark on a picture already made: Codex redraws that picture, the remark is the prompt
            refs, answer = [version_file(pid, base)], {}
            written, note = editing(wishes, name), f"[Правка {base}] {wishes.strip()}"
        else:
            if channel_wishes and not clone:
                wishes = "Постійні побажання каналу до прев’ю:\n" + channel_wishes + "\n\nПобажання до цього прев’ю, пріоритетні:\n" + wishes
            # the video's own frames are the reference; the channel's style frames only stand in when they cannot be read
            if clone:
                snapshot = work / 'idea-reference.jpg'
                shutil.copyfile(clone_image, snapshot)
                refs = [snapshot]
            else:
                refs = frame_stills(project, work) or code_stills(project, work) or references(folder)
            # Each writer sees the same clone-only rules and source image. New ideas retain their own brief.
            prompt_refs = ([*refs, hero] if clone and hero else ([hero] if hero else []) + refs)
            if clone:
                text = clone_brief(title, wishes, name, prompt_refs) + hero_rules
                if writer == "trending":
                    written, answer = write_prompt_codex(text, work, prompt_refs, name)
                else:
                    written, answer = write_prompt(text, folder.parent, work, effort=store.channel_effort(project))
            elif writer == "trending":
                written, answer = trending(title, script, wishes, name), {"total_cost_usd": 0}
            else:
                text = brief(title, script, wishes, folder, prompt_refs) + hero_rules
                written, answer = write_prompt(text, folder.parent, work, effort=store.channel_effort(project))
            note = (("[Клонування · Codex] " if clone else "[Трендове прев’ю · Codex] ") if writer == "trending" else "") + written
        if hero:
            refs = [*refs, hero] if clone and not base else [hero, *refs]
        if clone and not base:
            # The reference belongs only to prompt analysis. The drawing session is intentionally source-free.
            note += "\n[Нова генерація з текстового промпту; картинка конкурента не передається генератору]\n"
        elif not base and channel_wishes and channel_wishes not in written:
            preferences = "\nChannel thumbnail preferences (apply these; specific wishes for this thumbnail take priority):\n" + channel_wishes + "\n"
            written += preferences
            note += preferences
        if not clone or base or use_hero is not None:
            written += hero_rules
            note += hero_rules
        (work / f"Промпт прев'ю v{number}.txt").write_text(note + "\n", encoding="utf-8")
        data.update(stage="drawing", prompt_cost_usd=answer.get("total_cost_usd"))
        store.atomic_json(job_path(pid), data)
        # Clone drawings run in a fresh, clean workspace with text and optional host identity only.
        with job_timing.span('service'):
            if clone and not base:
                result = draw_clone_from_text(written, name, work, hero)
            else:
                command = [str(CODEX), "exec", "-s", "workspace-write", "--skip-git-repo-check", "-C", str(work)]
                for ref in refs: command += ["-i", str(ref)]
                result = subprocess.run(command + ["-"], input=written if base or writer == "trending" else drawing(written, name), cwd=work, text=True,
                                        capture_output=True, timeout=TIMEOUT)
        (work / f"Лог генерації v{number}.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
        made = work / name
        try:
            with Image.open(made) as image:
                image.verify()
        except (OSError, UnidentifiedImageError):
            raise RuntimeError("Codex не зберіг картинку. " + (result.stderr or result.stdout)[-300:].strip())
        with job_timing.span('saving'):
            try:thumbnail_compare.record(pid, name, base=base, reference=clone, image=clone_image)
            except (OSError, ValueError):pass  # Optional comparison cannot discard a completed image.
            kept = work / PREVIEW
            preview(project)                        # a thumbnail put into the episode folder by hand is kept first
            if kept.is_file() and not any(filecmp.cmp(kept, other, shallow=False) for other in work.glob("Превью *.png")):
                shutil.copy2(kept, work / f"Превью до v{number}.png")
            shutil.copyfile(made, kept)
            # the channel rules keep the thumbnail next to the video too, with its prompt in «Превью», while that folder exists
            if folder.is_dir():
                (folder / FOLDER).mkdir(exist_ok=True)
                image_delivery.copy_png(made, folder / FOLDER / made.name)
                prompt_file = work / f"Промпт прев'ю v{number}.txt"
                shutil.copyfile(prompt_file, folder / FOLDER / prompt_file.name)
                image_delivery.copy_png(made, folder / PREVIEW)
            data.update(status="done", file=name, finished_at=time.time(), error=None)
    except subprocess.TimeoutExpired as error:
        late = ("Codex" if writer == "trending" else "Claude") + " не написав промпт за 10 хвилин" if error.timeout == PROMPT_TIMEOUT else "Codex не встиг за 20 хвилин"
        data.update(status="failed", error=late, finished_at=time.time())
    except (OSError, RuntimeError, store.StudioError) as error:
        data.update(status="failed", error=str(error), finished_at=time.time())
    except Exception:
        import traceback
        traceback.print_exc()
        data.update(status='failed', error='Не вдалося завершити прев’ю. Збережені версії доступні.', finished_at=time.time())
    finally:
        try:
            store.atomic_json(job_path(pid), data)
        finally:   # a full disk must not leave the project «drawing» until a restart
            with LOCK:
                ACTIVE.discard(pid)


def start(pid: str, title: str, script: str, wishes: str = "", writer: str = "claude", base: str | None = None, use_hero: bool | None = None, reference_id: str | None = None) -> dict:
    if use_hero is not None and not isinstance(use_hero, bool):
        raise store.StudioError('Оберіть, чи використовувати головного героя', 400)
    if writer not in PROMPT_WRITERS:
        raise store.StudioError("Для промпту прев’ю оберіть Codex або Claude", 400)
    if writer == "trending" and base:
        raise store.StudioError("Трендове прев’ю створюється як нова версія, без бази для редагування", 400)
    if base is not None and (not isinstance(base, str) or not base):
        raise store.StudioError("Оберіть прев’ю для правок", 400)
    if base:
        if base != "current":
            version_file(pid, base)
        if not str(wishes or "").strip():
            raise store.StudioError("Напишіть, що змінити в прев'ю")
    project = store.load_project(pid)
    import idea_reference
    if base and reference_id is not None:
        raise store.StudioError('Референс клонування не використовується для правок готового прев’ю', 400)
    clone, _ = idea_reference.thumbnail_reference(project, reference_id)
    title, script, wishes = (str(value or "").strip() for value in (title, script, wishes))
    if not title:
        raise store.StudioError("Вкажіть заголовок")
    required = creation_min_frames(project)
    if not base and not clone and required and store.picture_count(project) < required:
        raise store.StudioError(f"Прев'ю можна створити, коли готові хоча б {required} кадри ролику: з них береться стиль", 409)
    if not CODEX.is_file():
        raise store.StudioError("Не знайдено Codex у ChatGPT.app", 503)
    with LOCK:
        if pid in ACTIVE:
            return state(pid)
        if base == "current":
            source = preview(project)
            if not source:
                raise store.StudioError("Прев’ю не знайдено", 404)
            existing = next((item['name'] for item in versions(pid) if item['current']), None)
            if existing:
                base = existing
            else:
                number = 1 + max((item['number'] for item in versions(pid)), default=0)
                base = f"Превью до v{number}.png"
                shutil.copy2(source, keep_dir(pid) / base)
        data = {"status": "running", "stage": "drawing" if base or writer == "trending" and not clone else "prompt", "started_at": time.time(), "title": title, "wishes": wishes,
                "writer": writer, "use_hero": use_hero, "reference_id": reference_id, **({"base": base} if base else {})}
        ACTIVE.add(pid)
        try:
            store.atomic_json(job_path(pid), data)
        except Exception:
            ACTIVE.discard(pid)
            raise
    try:
        threading.Thread(target=run, args=(pid, title, script, wishes, writer, base, use_hero, reference_id), daemon=True).start()
    except Exception:
        data.update(status='failed', error='Не вдалося запустити створення прев’ю', finished_at=time.time())
        try:
            store.atomic_json(job_path(pid), data)
        finally:
            with LOCK:
                ACTIVE.discard(pid)
        raise
    return data
