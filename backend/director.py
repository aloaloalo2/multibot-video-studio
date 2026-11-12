"""Direction of an episode by the channel-selected Claude model and effort, started as soon as the voice is recognised.

The Studio hands the episode to Claude Code once Whisper has turned the voice into timed words and the plan follows the
voice; no channel gets its frames from the sentence splitter (user, 31 October 2026: «план завжди робить клод-код, тобто
режисер… на основі тих пропорцій, які були вказані в каналі»). Claude Code runs on the user's claude.ai subscription, in
the YOUTUBE folder. For an animated channel it does the director's steps of the channel rules: razgon_bridge.py
prepare, the shot table (story/gen_shots.py) written by meaning, the film's sound cues (story/gen_sound.py: effects at
absolute times and ambience per shot, kept by gen_shots.py when it runs again), direction_check.py without FAIL, and
razgon_bridge.py plan, which writes the frame plan back into the Studio; a finished run lays the music and effects on the
timeline (razgon_sound.py). For a photo or video channel it groups the sentences into frames
by meaning, gives each a format within the channel's shares and hands them in through tools/studio.py frames
(backend/director_plan.py checks them). It draws no scenes and renders nothing. The state of the run lives next to the
project (director.json), its full answer in director.log, and the plan page shows it.
"""
from __future__ import annotations

import json, os, re, shutil, signal, subprocess, threading, time
from pathlib import Path

import razgon_sound
import agent_storage
import store
import job_timing
import motion_direction
import process_cleanup
import work_guard

MODEL = store.DEFAULT_DIRECTOR_MODEL
EFFORT = "high"
TIMEOUT = 3 * 3600
RESULT_EXIT_GRACE = 3
ACTIVE: set[str] = set()
LOCK = threading.Lock()
NO_RENDER = "MULTIBOT_RENDER_ON_EXPORT"   # set for the agents; tools/razgon_bridge.py then refuses push and final
# The Claude Code process behind each live activity feed, so a run can be stopped with every tool it started; a feed
# whose run was stopped on purpose (episode_restart) ends without writing its state back.
RUNNING: dict[str, subprocess.Popen] = {}
CANCELLED: set[str] = set()
# Bash is limited to the commands direction needs; file edits are accepted inside the YOUTUBE folder.
# Helpers are disabled to keep frame progress local and avoid multiplying the context.
ALLOWED = ["Read", "Write", "Edit", "Glob", "Grep"] + [f"Bash({cmd}:*)" for cmd in
           ("python3", "node", "ls", "cat", "head", "tail", "wc", "grep", "find", "mkdir", "cp", "mv", "diff", "jq")]


def state_path(pid: str) -> Path:
    return store.project_dir(pid) / "director.json"


def state(pid: str) -> dict | None:
    data = store.read_json(state_path(pid), None)
    if isinstance(data, dict) and data.get("status") in {"queued", "running"} and pid not in ACTIVE:
        data.update(status="failed", error="Студію перезапустили під час режисури. Запустіть її ще раз.")
    return data


def save(pid: str, data: dict) -> None:
    store.atomic_json(state_path(pid), data)


def executable() -> Path:
    found = shutil.which("claude")
    if found:
        return Path(found)
    candidates = [Path.home() / ".local/bin/claude", Path.home() / ".claude/local/claude"]
    bundled = Path.home() / "Library/Application Support/Claude/claude-code"
    if bundled.is_dir():
        candidates += sorted(bundled.glob("*/*/claude.app/Contents/MacOS/claude"), key=lambda p: p.stat().st_mtime, reverse=True)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError("Не знайдено Claude Code на цьому Mac")


def animated(project: dict) -> bool:
    # one answer across the studio, a switched-off channel included (store.project_animated)
    return store.project_animated(project)


def brief(project: dict) -> str:
    text = razgon_brief(project) if animated(project) else frames_brief(project)
    settings = channel_settings(project)
    if settings.get("generated_image_style"):
        text += "\nПріоритет автора для створених зображень Codex: " + settings["generated_image_style"] + "\nВрахуй ці побажання у форматі та ідеї відповідних кадрів.\n"
    if settings.get("accents"):
        text += "\nАкценти на кадрах увімкнені. Продумай власне монтажне рішення для цього каналу: де підкреслити деталь, показати ім’я, важливе число або тезу; де використати простий текст, плашку, стрілку, коло чи доречний стильний ефект. У полі idea відповідних кадрів зазнач задум, момент і вигляд акценту. Частоту й форму визначай за змістом, ритмом, стилем каналу та пам’яттю автора. Зберігай читабельність і вільну зону логотипа.\n"
    import animation_preferences
    return text + animation_preferences.instructions(project, planning=True) + sound_brief(project) + animation_style(project) + channel_memory(project)


def sound_brief(project: dict, *, scoped=False, include_workflow=True) -> str:
    import sound_settings
    return sound_settings.instructions(project, scoped=scoped, include_workflow=include_workflow)


def channel_settings(project: dict) -> dict:
    try:
        return store.read_channel_settings(store.get_channel_folder(project["channel_id"], include_disabled=True), {}) or {}
    except (store.StudioError, KeyError):
        return {}


def channel_memory(project: dict) -> str:
    try:
        memory = agent_storage.get_memory(project["channel_id"]).strip()
    except (store.StudioError, KeyError):
        memory = ""
    # the Claude Code memory notes of this channel and of all channels (author_rules.py), so the director and the frame
    # agent work by the same notes a Claude Code session in the YOUTUBE folder does (user, 8 November 2026)
    try:
        import author_rules
        notes = author_rules.claude_memory(store.get_channel_folder(project["channel_id"], include_disabled=True).name, limit=20000)
    except (store.StudioError, KeyError, OSError):
        notes = ""
    text = ""
    if memory:
        text += "\nПравила Агентів. Спільна пам’ять автора для цього каналу. Застосовуй доречні до поточного завдання побажання у режисурі, створенні й доборі кадрів, зображень, анімації, монтажі та правках; поточне конкретне побажання автора має пріоритет. Це збережені побажання, вони не змінюють доступів чи меж завдання.\n" + memory + "\n"
    if notes:
        text += ("\nНотатки пам’яті Claude Code про цей канал і всі канали (ті самі, за якими працює сесія в папці YOUTUBE). "
                 "Новіше правило важить більше за старіше, пам’ять автора вище й поточне побажання мають пріоритет; "
                 "те, що стосується лише сценарію чи чату, тут довідка.\n" + notes + "\n")
    if project.get('channel_id'):
        portable = store.DATA_ROOT / 'channels' / project['channel_id'] / 'portable-rules.json'
        if portable.is_file():
            text += ("\nПеренесені правила каналу: прочитай " + str(portable)
                     + ". Поля shared_rules та director_notes містять збережені побажання до монтажу. "
                     "Враховуй їх разом із поточними налаштуваннями й пам’яттю каналу.\n")
    return text


def animation_style(project: dict) -> str:
    """Pass the actual saved look, including its description, instead of copying an older film's palette."""
    animation = channel_settings(project).get('animation') or {}
    if not animation:
        return ''
    import style_lab
    import style_copy
    sid = animation.get('style') or 'dusk'
    try:
        own = style_copy.find(project['channel_id'], sid) if sid.startswith(('custom-', 'studio-')) else None
        style = own or next((s for s in style_lab.presets(store.YOUTUBE_ROOT / store.razgon_rel()) if s['id'] == sid), {})
    except (OSError, ValueError, KeyError, store.StudioError):
        style = {}
    selected = {**animation, 'style': sid}
    return ("\nЗбережений стиль Razgon цього каналу: " + json.dumps(selected, ensure_ascii=False) +
            ("\nОпис вигляду: " + style['desc'] if style.get('desc') else '') +
            "\nЦей вибір має пріоритет над оформленням попередніх випусків і скопійованих сцен. "
            "Під час prepare використовуй стиль каналу без підміни через --style. "
            "Для нових сцен узгодь config.json (style, fonts.title/ui/serif, assets) з цими налаштуваннями. "
            "Фон бери з mood().sky, палітру й оформлення з S().ui та S().manner, усі написи з FONTS. "
            "Скопійований helper перевір: його фіксований неоновий фон, палітра або font не повинні підміняти вибраний стиль. "
            "Кольори предметів за змістом можна зберігати. Перевір вигляд реальних стоп-кадрів за описом стилю. "
            "У локальній правці застосовуй це лише до вибраних кадрів, без глобальної зміни прийнятого ролика.\n")


def frames_brief(project: dict) -> str:
    """A photo or video channel: the director only plans the frames; the montage is the next step."""
    root, studio = store.YOUTUBE_ROOT, store.app_rel()
    episode = Path(project["episode_path"])
    channel = episode.parent
    rel = episode.relative_to(root) if root in episode.parents else episode
    answer = store.project_dir(project["id"]) / "director-frames.json"
    return f"""Ти режисер випуску каналу «{channel.name}» у VideoKey Studio. Озвучку щойно розпізнано, і студія поділила її на речення з часом.

Випуск: «{project['name']}», id проєкту студії {project['id']}, папка випуску «{rel}».
Робоча папка: {root}. Студія працює на http://127.0.0.1:8770.
Службові JSON, плани, таймінги, запити й проміжні файли зберігай усередині VideoKey Studio. Папка випуску містить матеріали користувача та готові результати. План отримуй через API студії; зв’язок анімації через GET/POST /api/projects/<id>/razgon-link.

Спершу прочитай правила каналу {store.channel_rules_source(channel)}: як ділити озвучку на кадри і для чого який формат; сценарії інших випусків не читай.

Твоє завдання: план кадрів за змістом озвучки.
1. python3 "{studio}/tools/studio.py" sentences {project['id']} показує пронумеровані речення з часом, формати каналу з їхніми частками та обмеження.
2. Поділи речення на кадри. Сусідні речення про одну думку йдуть в один кадр, а нова думка, дія чи предмет починають новий.
   Кадр складається з цілих речень підряд, кожне речення стоїть рівно в одному кадрі.
   Кожному кадру дай формат, який найкраще покаже саме цю репліку, і тримай частки форматів за тривалістю близько до часток каналу.
   generated_photo означає створене Codex зображення будь-якого стилю: фото, інфографіка, схема, рентген чи ілюстрація. Вибирай стиль за змістом репліки.
   У полі idea одним реченням опиши композицію і доречну дію чи рух, що допомагає зрозуміти репліку.
   Головний предмет задуму видно від початку; нові елементи доповнюють сцену. Спокійна фаза для читання допустима.
   Якщо sentences повертає host_rules, перший і останній кадри обов’язково host, ведучий ніколи не йде два кадри підряд, його появи рівномірно розподілені по всій тривалості.
{motion_direction.PLANNING}
3. Запиши кадри у файл {answer} так: {{"frames": [{{"sentences": [1, 2], "format": "stock_video", "idea": "..."}}]}}.
   Перевір їх командою python3 "{studio}/tools/studio.py" frames {project['id']} "{answer}" --dry-run: студія перевіряє речення,
   кількість речень у кадрі, частки форматів і чергування та пише, що виправити. Коли перевірка проходить, запусти ту саму
   команду без --dry-run, і план кадрів піде в студію.

Не шукай стоки, не генеруй картинки, не монтуй і нічого не рендери: це наступний крок, і його запускає користувач.
Автор бачить твої дії наживо: поле description кожної команди пиши коротко українською, наприклад «Читаю правила каналу».
Наприкінці коротко напиши українською, скільки кадрів вийшло і які частки форматів."""


def razgon_brief(project: dict) -> str:
    root = store.YOUTUBE_ROOT
    episode = Path(project["episode_path"])
    channel = episode.parent
    rel = episode.relative_to(root) if root in episode.parents else episode
    SOUND_DESIGN = f"{store.app_rel()}/razgon-plugin/razgon-2d-studio-plugin/skills/make-2d-video/references/sound-design.md"
    return f"""Ти режисер анімаційного випуску в VideoKey Studio. Озвучку щойно розпізнано, план студії «За озвучкою».

Випуск: «{project['name']}», id проєкту студії {project['id']}, папка випуску «{rel}», канал «{channel.name}».
Робоча папка: {root}. Студія працює на http://127.0.0.1:8770.
Службові JSON, плани, таймінги, запити й проміжні файли зберігай усередині VideoKey Studio. Папка випуску містить матеріали користувача та готові результати. План отримуй через API студії; зв’язок анімації через GET/POST /api/projects/<id>/razgon-link.

{motion_direction.PLANNING}

Спершу прочитай правила: {root / 'AGENTS.md'}, {store.channel_rules_source(channel)} і навик режисури Razgon
({store.razgon_rel()}/skills або плагін «{store.app_rel()}/razgon-plugin/razgon-2d-studio-plugin/skills/make-2d-video»: storytelling і story breakdown).
Великі документи самої студії (її AGENTS.md, CLAUDE.md, docs/) і сценарії інших випусків не читай: усе потрібне для режисури є тут, у правилах каналу й у навику.
Як зроблено режисуру раніше, подивись в одному-двох найновіших випусках ({store.razgon_rel()}/projects/*/story/gen_shots.py,
ls -t покаже найновіші), а не в усіх.

Твоє завдання: режисура, звук і план кадрів, кроки 3–5 правил каналу.
1. python3 "{store.app_rel()}/tools/episode.py" "{rel}" показує, на якому кроці випуск. Якщо проєкту Razgon ще немає:
   python3 "{store.app_rel()}/tools/razgon_bridge.py" prepare --project-id {project['id']}
2. Режисура за змістом озвучки: напиши story/gen_shots.py проєкту Razgon (таблиця дублів: речення, епізод, декорація, перехід, що в кадрі)
   і запусти його. Кадри ділиш за змістом, не за кількістю слів. Кожна дія відбувається рівно в одному шоті: наступний шот
   описує наступний крок і починає з того стану, яким закінчився попередній, а не повторює дію. Дія в тому самому місці лишається
   одним шотом (JOIN), мітка set означає реальне місце, а перехід ставиш лише там, де справді змінюється сцена. Потім python3 {store.razgon_rel()}/tools/direction_check.py --project <проєкт>
   має пройти без FAIL. На WARN відповідай у story/bible.md або виправляй.
3. Звук фільму лише в межах вибору автора з розділу ЗВУК РОЛИКА нижче. Для вимкнених пунктів пропусти відповідну роботу. Дозволені звуки за {SOUND_DESIGN}: там назви ефектів, їхні правила й гучності. Музичний план (music) пишеш у gen_shots.py, як у попередніх випусках.
   Ефекти й атмосферу запиши в story/shots.json окремим скриптом story/gen_sound.py: напиши його й запусти, він читає shots.json і timeline/words.json.
   - "sfx" для всього фільму: [{{"t": 81.4, "name": "ding", "gain": -10, "seed": 3, "shot": "e12", "why": "слова, під які він звучить"}}], де t означає
     секунди від початку фільму. Ефект звучить на видиму подію шоту (поява, удар, відкриття, число, перехід) у мить її слова, приблизно один
     на 15–25 секунд. Два ефекти не стоять ближче ніж за 0,3 с, і голос лишається чистим.
   - "amb" на більшості шотів за місцем дії: {{"name": "city", "gain": -24, "seed": 7}} (rain, wind, city, roomtone, murmur, hum), від −18 до −28.
   gen_shots.py при кожному запуску бере їх з попереднього shots.json, щоб нова нарізка шотів не стерла звук:
   old = json.loads(шлях.read_text()) якщо файл є, sfx=old.get("sfx", []) у story і amb=old_amb.get(id шоту), де old_amb = {{s["id"]: s.get("amb") for s in old.get("shots", [])}}.
   Після кожного запуску gen_shots.py запускай і gen_sound.py. direction_check.py рахує ефекти й атмосферу і попереджає, коли їх мало або вони накладаються.
   Музику й ефекти на таймлайн студія кладе сама, щойно ти закінчиш, без рендеру: push для цього не потрібен.
4. python3 "{store.app_rel()}/tools/razgon_bridge.py" check --razgon <проєкт>, потім python3 "{store.app_rel()}/tools/razgon_bridge.py" plan --razgon <проєкт>: план кадрів іде в студію.

Не малюй сцени, не генеруй картинки, не рендери відео, не змінюй стиль у config.json і нічого не публікуй: це наступні кроки, і їх запускає користувач.
Автор бачить твої дії наживо: поле description кожної команди пиши коротко українською, наприклад «Читаю правила каналу».
Наприкінці коротко напиши українською: скільки шотів, кадрів студії і звукових ефектів вийшло, які епізоди, що лишилося з WARN і що не вдалося, якщо таке було."""


def spent(answer: dict, started: float | None = None) -> dict:
    """What a run actually used: tokens in (cached ones included) and out, and minutes. Claude Code may close with several
    results (it resumes after background work); their per-model usage is cumulative, so the last one holds the whole run,
    and the minutes are the wall clock from the start."""
    models = answer.get("modelUsage") if isinstance(answer.get("modelUsage"), dict) else {}
    if models:
        tokens_in = sum(int(u.get("inputTokens") or 0) + int(u.get("cacheReadInputTokens") or 0) + int(u.get("cacheCreationInputTokens") or 0) for u in models.values())
        tokens_out = sum(int(u.get("outputTokens") or 0) for u in models.values())
    else:
        usage = answer.get("usage") if isinstance(answer.get("usage"), dict) else {}
        tokens_in = sum(int(usage.get(key) or 0) for key in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
        tokens_out = int(usage.get("output_tokens") or 0)
    minutes = (time.time() - started) / 60 if started else float(answer.get("duration_ms") or 0) / 60000
    return {"tokens_in": tokens_in, "tokens_out": tokens_out, "minutes": round(minutes, 1)}


# What the agent is doing, in the author's words: each command or file it touches becomes one line of the activity
# feed on the plan, so the author sees the work move.
# Each line also names who does it: Opus directs, writes and picks props from the library, Codex draws new props,
# Razgon renders, and helpers are the agents Opus sends off in parallel. Steps that write into the Studio are the
# director's too: the Studio itself only receives them.
COMMANDS = [("razgon_bridge.py prepare", "opus", "Готує проєкт Razgon зі студії"), ("gen_shots.py", "opus", "Розбиває озвучку на шоти"),
            ("gen_sound.py", "opus", "Розставляє звукові ефекти й атмосферу"),
            ("direction_check", "opus", "Перевіряє режисуру"), ("razgon_bridge.py check", "opus", "Перевіряє, що шоти покривають озвучку"),
            ("razgon_bridge.py plan", "opus", "Записує план кадрів у студію"), ("razgon_bridge.py slots", "opus", "Ставить кадри кодом на таймлайн"),
            ("codex_image.py", "codex", "Малює аркуш предметів"), ("split_sheet", "codex", "Ріже аркуш на окремі предмети"),
            ("library.py", "opus", "Шукає предмети в бібліотеці"), ("--sheet", "razgon", "Готує стоп-кадри для перевірки"),
            ("render.mjs", "razgon", "Готує стоп-кадри для перевірки"), ("episode.py", "opus", "Дивиться, на якому кроці випуск"),
            ("frame_review", "opus", "Переглядає кадри")]


def describe(tool: str, args: dict) -> tuple[str, str] | None:
    """(who, what) for one action of the agent, or None for the ones not worth a line."""
    name = Path(str(args.get("file_path") or args.get("path") or "")).name
    if tool == "Bash":
        command = str(args.get("command") or "")
        found = next(((who, text) for key, who, text in COMMANDS if key in command), None)
        note = str(args.get("description") or "")
        # the agent's own note is shown when it writes it in Ukrainian, as the brief asks
        return found or ("opus", note if re.search("[а-яіїєґ]", note, re.I) else "Вивчає матеріали й готує роботу")
    if tool in {"Task", "Agent"}:
        return "helper", str(args.get("description") or "Окреме завдання")
    if tool in {"Write", "Edit", "MultiEdit"} and name:
        # what the file is for, never its name
        target = str(args.get("file_path"))
        what = ("Пише сцени" if "/scenes/" in target else "Описує предмети для художника" if "prompt" in name
                else "Пише режисуру шотів" if name in {"gen_shots.py", "shots.json"} else "Розставляє звук фільму" if name == "gen_sound.py"
                else "Записує задум ролика" if name == "bible.md"
                else "Готує допоміжні файли")
        return "opus", what
    if tool == "Read":
        return "opus", "Вивчає матеріали й готує роботу"
    return None


def activity_path(pid: str, kind: str) -> Path:
    return store.project_dir(pid) / f"{kind}-activity.json"


@job_timing.measure('service')
def claude(cli: Path, prompt: str, log: Path, activity: Path, timeout: int, resume: str | None = None,
           effort: str = EFFORT, model: str = MODEL) -> tuple[int, dict]:
    """Run Claude Code on a brief, streaming its events: the log keeps them all, the activity feed the readable ones.
    Returns the exit code and the final result event (cost, usage, the agent's last message)."""
    if model not in store.DIRECTOR_MODELS:
        raise store.StudioError("Невідома модель режисера")
    command = [str(cli), "--model", model, "--effort", effort, "--strict-mcp-config", "--permission-mode", "acceptEdits",
               "--disallowedTools", "Agent", "Task",
               "--allowedTools", *ALLOWED, "--output-format", "stream-json", "--verbose", "-p"] + (["--resume", resume] if resume else [])
    for folder in (store.APP_ROOT, store.DATA_ROOT):
        if not store.under(folder, store.YOUTUBE_ROOT) and (folder == store.APP_ROOT or not store.under(folder, store.APP_ROOT)):
            command += ['--add-dir', str(folder)]
    # its own process group; kill() also stops the commands, renders and helpers under it
    # the agents draw frames as code; only «Експорт MP4» renders them, so razgon_bridge.py refuses push and final here
    process = subprocess.Popen(command, cwd=store.YOUTUBE_ROOT, text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, start_new_session=True, env={**os.environ, NO_RENDER: "1"})
    RUNNING[str(activity)] = process
    expired = threading.Event()
    watchdog = None
    answer, steps = {}, []
    stopped_after_result = False
    try:
        if str(activity) in CANCELLED:
            kill(process)
        watchdog = threading.Timer(timeout, lambda: (expired.set(), kill(process)))
        watchdog.start()
        store.atomic_json(activity, [])
        process.stdin.write(prompt)
        process.stdin.close()
        with log.open("w", encoding="utf-8") as out:
            for line in process.stdout:
                out.write(line)
                out.flush()
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("type") == "result":
                    answer = event
                    watchdog.cancel()
                    # A terminal result closes the model turn. Background tools
                    # can inherit stdout and keep both the CLI and this reader
                    # waiting indefinitely after the work has already finished.
                    break
                if event.get("type") != "assistant":
                    continue
                for part in (event.get("message") or {}).get("content") or []:
                    action = describe(part.get("name"), part.get("input") or {}) if part.get("type") == "tool_use" else None
                    if action and (not steps or steps[-1]["text"] != action[1]):
                        steps = (steps + [{"t": time.time(), "who": action[0], "text": action[1]}])[-40:]
                        store.atomic_json(activity, steps)
        if answer:
            try:
                process.wait(timeout=RESULT_EXIT_GRACE)
            except subprocess.TimeoutExpired:
                stopped_after_result = True
                kill(process)
                try:
                    process.wait(timeout=RESULT_EXIT_GRACE)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        else:
            process.wait()
    finally:
        if watchdog is not None:watchdog.cancel()
        process_cleanup.stop_group(process, children=descendants(process.pid) if process.poll() is None else ())
        process.stdout.close()
        RUNNING.pop(str(activity), None)
        import spend_report   # where this run spent the limits, saved beside the project once the log is complete
        spend_report.record_later(log)
    if expired.is_set():
        raise subprocess.TimeoutExpired(command, timeout)
    return (0 if stopped_after_result else process.returncode), answer or {"is_error": True, "result": "Claude Code завершився без відповіді"}


def limit_stop(answer: dict) -> str | None:
    """When the run stopped because the Claude subscription limit ran out: a readable note with the reset time."""
    text = str(answer.get("result") or "")
    if answer.get("api_error") != "usage_limit_reached" and not re.search(r"hit your \w+ limit", text):
        return None
    reset = re.search(r"resets (\d{1,2})(?::(\d{2}))?\s*([ap]m)", text, re.I)
    if not reset:
        return "Закінчився ліміт підписки Claude."
    hour = int(reset.group(1)) % 12 + (12 if reset.group(3).lower() == "pm" else 0)
    return f"Закінчився ліміт підписки Claude, він оновиться о {hour:02d}:{reset.group(2) or '00'}."


def descendants(pid: int) -> list[int]:
    """Every process under `pid`, read from ps."""
    try:
        table = subprocess.run(["ps", "-axo", "pid=,ppid="], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    children: dict[int, list[int]] = {}
    for line in table.splitlines():
        parts = line.split()
        if len(parts) == 2 and all(part.isdigit() for part in parts):
            children.setdefault(int(parts[1]), []).append(int(parts[0]))
    found, todo = [], [pid]
    while todo:
        for child in children.get(todo.pop(), []):
            found.append(child)
            todo.append(child)
    return found


def kill(process: subprocess.Popen) -> None:
    """Stop the run with everything it started. Claude Code gives each command a process group of its own, so the run's
    group alone would leave a render going (30 October 2026): the processes under it are stopped as well."""
    under = descendants(process.pid)
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        process.kill()
    for child in under:
        try:
            os.kill(child, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass


def stop(pid: str, kind: str) -> None:
    """Stop the live run whose feed is `kind` («director» or «production») on this project; its state is not written back."""
    feed = str(activity_path(pid, kind))
    import production
    if feed not in RUNNING and pid not in (ACTIVE if kind == "director" else production.ACTIVE):
        return   # nothing runs: a stop mark left here would stop the next run the moment it starts
    CANCELLED.add(feed)
    process = RUNNING.get(feed)
    if process:
        kill(process)


def cancelled(pid: str, kind: str) -> bool:
    """True once for a run stopped on purpose, at its end."""
    feed = str(activity_path(pid, kind))
    found = feed in CANCELLED
    CANCELLED.discard(feed)
    return found


@job_timing.track('planning', project='pid', job=lambda values: state(values['pid']))
def run(pid: str, cli: Path) -> None:
    # the run always leaves ACTIVE, whatever fails on the way, so the director can be started again
    try:
        _run(pid, cli)
    finally:
        with work_guard.MUTEX:
            with LOCK:
                ACTIVE.discard(pid)
            data = state(pid) or {}
            if data.get('status') == 'done' and data.get('create_video'):
                try:
                    import production
                    production.start_from_plan(pid)
                except (OSError, RuntimeError, store.StudioError) as error:
                    data['creation_error'] = str(error)
                    save(pid, data)


def _run(pid: str, cli: Path) -> None:
    data = {"started_at": time.time()}
    try:
        data = state(pid) or {}
        project = store.load_project(pid)
        data.update(status="running", started_at=time.time(), model=store.channel_director_model(project), effort=store.channel_effort(project), error=None, creation_error=None, summary=None, limit=False)
        save(pid, data)
        code, answer = claude(cli, brief(project), store.project_dir(pid) / "director.log", activity_path(pid, "director"), TIMEOUT, effort=data["effort"], model=data["model"])
        plan = store.load_project_plan(pid) or {}
        plan_file = store.project_plan_file(store.load_project(pid))
        # the run counts only if it wrote a fresh director plan into the Studio
        directed = (plan.get("frame_source") == "razgon-direction" and not plan.get("director_stale")
                    and plan_file is not None and plan_file.stat().st_mtime >= data["started_at"])
        if limit_stop(answer):
            data.update(status="failed", limit=True, error=limit_stop(answer))
        elif code or answer.get("is_error") or not directed:
            data.update(status="failed", error=(answer.get("result") or "Режисура не записала план кадрів у студію")[-600:])
        else:
            data.update(status="done", summary=(answer.get("result") or "").strip()[-2000:], frames=len(plan.get("frames") or []))
        data.update(cost_usd=answer.get("total_cost_usd"), session_id=answer.get("session_id"), turns=answer.get("num_turns"), **spent(answer, data["started_at"]))
    except subprocess.TimeoutExpired:
        data.update(status="failed", error="Режисура не вклалася в 3 години")
    except (OSError, store.StudioError) as error:
        data.update(status="failed", error=str(error))
    except Exception:
        import traceback
        traceback.print_exc()
        data.update(status='failed', error='Режисуру зупинено через помилку студії. Збережені матеріали доступні.')
    finally:
        if not cancelled(pid, "director"):
            with LOCK:
                # A second click can join an already-running direction with automatic frame creation.
                if (state(pid) or {}).get('create_video'):
                    data['create_video'] = True
                data["finished_at"] = time.time()
                try:
                    save(pid, data)
                except OSError:
                    pass
            if data.get("status") == "done":
                # the shots and their sound cues are written: the film's music and effects go on the timeline at once
                # (razgon_sound.py; a photo channel's film is not due and is left alone)
                razgon_sound.start(pid, "director")


def start(pid: str, reason: str = "voice") -> dict:
    """Start the director for a project; a second start while one runs returns the running one."""
    project = store.load_project(pid)
    if store.project_plan_mode(project) == "direct":
        raise store.StudioError("У каналі вибрано «Без плану». Монтуйте ролик без запуску режисера", 409)
    if not project.get("episode_path"):
        raise store.StudioError("У випуску немає папки")
    import production
    if pid in production.ACTIVE:
        # a new direction would rewrite the frames under the frame agent at work
        raise store.StudioError("Агент саме створює кадри цього випуску. Дочекайтеся, поки він закінчить", 409)
    with LOCK:
        if pid in ACTIVE:
            if reason == 'create_video':
                data = state(pid) or {}
                data['create_video'] = True
                save(pid, data)
            return state(pid)
        try:
            cli = executable()
        except RuntimeError as error:
            raise store.StudioError(str(error), 503) from None
        previous = state(pid) or {}
        data = {"status": "queued", "reason": reason, "queued_at": time.time(), "model": store.channel_director_model(project), "effort": store.channel_effort(project),
                "create_video": reason == 'create_video' or previous.get('status') == 'failed' and bool(previous.get('create_video'))}
        ACTIVE.add(pid)
        try:
            save(pid, data)
        except Exception:
            ACTIVE.discard(pid)
            raise
    try:
        threading.Thread(target=run, args=(pid, cli), daemon=True).start()
    except Exception:
        data.update(status='failed', error='Не вдалося запустити режисера', finished_at=time.time())
        try:
            save(pid, data)
        finally:
            with LOCK:
                ACTIVE.discard(pid)
        raise
    return data


def after_voice(pid: str, create_video=False) -> None:
    """Called when a voice analysis has been applied to the plan: the episode goes on to direction by itself."""
    try:
        if store.project_plan_mode(store.load_project(pid)) == "direct":
            return
        if create_video and pid in ACTIVE:
            start(pid, 'create_video')
            return
        plan = store.load_project_plan(pid) or {}
        # a new recognition of the same sentences keeps the director's frames; only a fresh or changed text needs a pass
        if plan.get("frame_source") == "razgon-direction" and not plan.get("director_stale"):
            if create_video:
                import production
                production.start_from_plan(pid)
            return
        project = store.load_project(pid)
        # a photo episode already cut on an older plan keeps that montage: new frames would no longer match its clips
        if not animated(project) and plan.get("frame_source") != "razgon-direction" and montage_started(project):
            if create_video:
                import production
                production.start_from_plan(pid)
            return
        start(pid, "create_video" if create_video else "voice")
    except store.StudioError as error:
        if create_video:
            data = state(pid) or {}
            data['creation_error'] = str(error)
            save(pid, data)
            raise


def montage_started(project: dict) -> bool:
    """A picture, video or text of the film is on the timeline already (the channel's plate and logo do not count)."""
    overlay = {cid for group in project.get("scene_groups") or [] if group.get("role") == "overlay" for cid in group.get("clip_ids", [])}
    return any(clip.get("kind") in {"image", "video", "text", "animation"} and clip.get("id") not in overlay
               for layer in project.get("tracks") or [] for clip in layer.get("clips") or [])
