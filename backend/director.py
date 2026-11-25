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

import json, os, re, shutil, signal, subprocess, sys, threading, time
from pathlib import Path

import razgon_sound
import agent_storage
import store
import job_timing
import motion_direction
import process_cleanup
import work_guard
import montage_context

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
# A second session of the same run (two frame sessions of one episode side by side, 14 November 2026) is kept here
# under the same feed, so a stop reaches both, and both write into one activity feed.
RUNNING_MORE: dict[str, list] = {}
FEEDS: dict[str, list] = {}
FEED_LOCK = threading.Lock()
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
        if data.get("stage") == "kit":
            # cut during the early «Підготовка»: the plan is made; production makes the kit itself
            data.update(status="done", stage=None, kit="failed")
        else:
            import episode_pause
            stopped = ((episode_pause.paused(pid) or {}).get("stopped") or {}).get("director")
            if isinstance(stopped, dict):
                # the pause is stopping him: between his exit and the pause's own note he reads as paused, never as a
                # restart (user, 25 November 2026: after a pause «нічого не відбулося… треба було оновити сторінку»)
                data.update(status="paused", error=None)
            else:
                data.update(status="failed", interrupted=True,
                            error="Режисуру перервав перезапуск студії. Натисніть «Продовжити режисуру», і режисер почне знову.")
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
    is_animated = animated(project)
    text = razgon_brief(project) if is_animated else frames_brief(project)
    import script_timing
    if script_timing.estimated(store.load_project_plan(project["id"])):
        # the director works while the voice is made (user, 16 November 2026: «якщо є сценарій, то… вже можемо починати»)
        text += ("\nОзвучка ще готується: час речень і слів у плані приблизний, порахований за сценарієм у темпі каналу. "
                 "Групуй речення в кадри за змістом як завжди. Після озвучки студія сама підставить точний час "
                 "і збереже твої кадри, повторної режисури не буде.\n")
    settings = channel_settings(project)
    if settings.get("generated_image_style"):
        text += "\nПріоритет автора для створених зображень Codex: " + settings["generated_image_style"] + "\nВрахуй ці побажання у форматі та ідеї відповідних кадрів.\n"
    import channel_hero
    if channel_hero.production_rule(project):
        text += ("\nУ каналу є фото головного героя: кадри з ним студія малює через Codex у нових позах і ракурсах."
                 " Де доречно, став героя в задум кадру й опиши його дію та емоцію.\n")
    if settings.get("accents") or is_animated:
        text += ("\nАкценти на кадрах увімкнені. " if settings.get("accents") else "\nУ постановці анімованої сцени: ")
        text += motion_direction.ACCENTS + "\nУ задумі відповідного кадру запиши ціль, вигляд і момент появи, щоб монтажер міг відтворити рішення.\n"
    else:
        text += "\nДодаткові акценти поверх кадрів вимкнені в налаштуваннях каналу.\n"
    if settings.get("host_graphics") and float((settings.get("weights") or {}).get("host", 0) or 0) > 0:
        text += ("\nМоушн-графіка над ведучим увімкнена. " + motion_direction.HOST_GRAPHICS +
                 "\nУ задумі кожного кадру host коротко запиши, яку графіку показати й на якому слові, або що кадр лишається чистим.\n")
    import animation_preferences
    return text + montage_context.rules(project) + montage_context.COMMANDS + animation_preferences.instructions(project, planning=True) + sound_brief(project, include_workflow=not is_animated) + animation_style(project) + channel_memory(project)


def sound_brief(project: dict, *, scoped=False, include_workflow=True) -> str:
    import sound_settings
    text = sound_settings.instructions(project, scoped=scoped, include_workflow=include_workflow)
    # the channel's own design kit travels with the sound brief to every agent that plans or makes frames
    # (channel_design.py, 25 November 2026: «кожен канал має свою унікальність»)
    try:
        import channel_design
        text += channel_design.brief(project)
    except Exception:
        pass
    return text


def channel_settings(project: dict) -> dict:
    try:
        return store.read_channel_settings(store.get_channel_folder(project["channel_id"], include_disabled=True), {}) or {}
    except (store.StudioError, KeyError):
        return {}


def channel_memory(project: dict) -> str:
    try:
        memory = montage_context.sections(agent_storage.get_memory(project["channel_id"]).strip())
    except (store.StudioError, KeyError):
        memory = ""
    # the Claude Code memory notes of this channel and of all channels (author_rules.py), so the director and the frame
    # agent work by the same notes a Claude Code session in the YOUTUBE folder does (user, 8 November 2026)
    try:
        import author_rules
        notes = author_rules.claude_memory(store.get_channel_folder(project["channel_id"], include_disabled=True).name, limit=20000, montage_only=True)
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

Правила монтажу цього каналу наведені в завданні нижче. Повні AGENTS.md, CLAUDE.md, сценарії інших випусків і архіви не читай.

Твоє завдання: план кадрів за змістом озвучки.
1. python3 "{studio}/tools/studio.py" sentences {project['id']} показує пронумеровані речення з часом, формати каналу з їхніми частками та обмеження.
2. Спершу план сцен, потім кадри (автор, 25 листопада 2026: «агент… зразу має прописати… це кадр такий, це кадр такий… щоб потім
   це не виправляти… план кадрів має бути якісніший»). Прочитай озвучку цілком і випиши для себе перелік сцен: де відбувається,
   що робиться, який головний предмет. Одна сцена це одне місце й одна безперервна дія; нова сцена починається там, де змінюється
   місце, предмет чи думка. Кожна сцена стає рівно одним кадром, тож кадри з'являються вже з готової структури, а не речення за реченням.
   Сусідні речення про одну думку йдуть в один кадр, а нова думка, дія чи предмет починають новий.
   Кадр складається з цілих речень підряд, кожне речення стоїть рівно в одному кадрі.
   Кожному кадру дай формат, який найкраще покаже саме цю репліку, і тримай частки форматів за тривалістю близько до часток каналу.
   Формати, позначені «Авто», використовуй за змістом і обирай їхню частку самостійно. Для них показані відсотки лише орієнтовні; усі правила монтажу й розподілу зберігаються.
   generated_photo означає створене Codex зображення будь-якого стилю: фото, інфографіка, схема, рентген чи ілюстрація. Вибирай стиль за змістом репліки.
   У полі idea одним реченням опиши композицію і доречну дію чи рух, що допомагає зрозуміти репліку.
   Головний предмет задуму видно від початку; нові елементи доповнюють сцену. Спокійна фаза для читання допустима.
   Для текстового кадру (text) idea описує всю композицію вставки під цей момент: що на фоні (відео ведучого цієї ж секунди,
   картинка чи відео випуску, колір, градієнт, сітка, візерунок), як його оброблено (розмиття, затемнення, шум), колір і місце
   тексту та як з'являються слова. Кожна текстова вставка інша за попередню, а візуальним стилем пасує до каналу й решти ролика;
   побажання автора в правилах каналу йдуть першими.
   Кадр зазвичай має одне-три речення, це орієнтир. Одна безперервна сцена (те саме місце, та сама дія, камера йде далі)
   завжди лишається одним кадром, скільки б речень у ній не було: не розрізай її на два кадри з тією самою картинкою.
   Кадр razgon_2d це ціла анімована сцена з кількома шотами, як в анімаційному випуску: зазвичай 15–40 с і кілька речень, а не
   одне-три.
   Перед записом пройди всі пари сусідніх кадрів: сусідній кадр ніколи не повторює попередній ні предметом, ні композицією, ні
   картинкою. Якщо другий кадр показує той самий предмет, місце чи картинку, що й перший (камера наїжджає на те, що вже на
   екрані, та сама мозаїка, та сама зірка), це одна сцена: об'єднай їх в один кадр. Якщо це справді нова думка, дай кадру
   інший предмет чи інший погляд (автор, 25 листопада 2026: «55-й, 56-й кадр. Це та сама сцена… чому вона розрізана»;
   «наступна сцена… не може бути така сама»).
   Якщо sentences називає початок ролика, кадри 1–3 мають саме ці формати, це вибір автора каналу. Якщо sentences повертає host_rules, останній кадр обов’язково host, перший теж host, коли початок ролика не задає першому кадру інший формат, ведучий ніколи не йде два кадри підряд, його появи рівномірно розподілені по всій тривалості.
   Для host переважно обирай короткі завершені фрази, доречні за змістом. У межах заданої частки краще частіше показувати ведучого на коротких репліках упродовж усього ролика, ніж зосереджувати його появу в кількох довгих кадрах. Не розривай речення чи цілісну думку штучно.
{motion_direction.PLANNING}
3. Запиши кадри у файл {answer} так: {{"frames": [{{"sentences": [1, 2], "format": "stock_video", "idea": "..."}}]}}.
   Перевір їх командою python3 "{studio}/tools/studio.py" frames {project['id']} "{answer}" --dry-run: студія перевіряє речення,
   частки форматів і чергування та пише, що виправити. Коли перевірка проходить, запусти ту саму
   команду без --dry-run, і план кадрів піде в студію.

Не шукай стоки, не генеруй картинки, не монтуй і нічого не рендери: це наступний крок, і його запускає користувач.
Автор бачить твої дії наживо: поле description кожної команди пиши коротко українською, наприклад «Читаю правила каналу».
Наприкінці коротко напиши українською, скільки кадрів вийшло і які частки форматів."""


def razgon_brief(project: dict) -> str:
    """The author directs from one compact contract; the local helper handles file plumbing."""
    root = store.YOUTUBE_ROOT
    episode = Path(project['episode_path'])
    rel = episode.relative_to(root) if root in episode.parents else episode
    tool = store.APP_ROOT / 'tools/direction.py'
    packet = store.project_dir(project['id']) / 'director-context.txt'
    return f"""Ти режисер анімаційного випуску VideoKey Studio. Озвучка й сценарій уже прийняті.
{motion_direction.ANIMATION_TEXT}
Випуск «{project['name']}», id {project['id']}, папка «{rel}», канал «{episode.parent.name}».
Твоє творче завдання: зв’язні епізоди, смислові шоти, композиція, камера, переходи, PNG предмети та доречні звукові події.
{motion_direction.PLANNING}

Порядок для цього запуску:
1. Одна команда готує робочу папку, чинний стиль і компактний пакет з усіма реченнями та технічною схемою:
   python3 "{tool}" prepare {project['id']}
2. Прочитай "{packet}" один раз. Він містить точну схему direction.json, переходи, музику й вибір звуків.
   Склади режисуру за змістом усієї озвучки й запиши один story/direction.json у надрукованій робочій папці.
   Речення групуєш сам: одна безперервна дія може охоплювати багато речень; наступний шот продовжує попередній стан.
   Зміна місця дії (інший set, інша сцена замість попередньої) завжди починає новий шот: один шот показує одне місце.
   Перехід туди (наїзд камери, перетворення предмета) робиш стиком двох шотів, а не сценою всередині одного.
   Повний перелік SFX і музичні повороти продумай разом з усіма шотами, до запуску перевірки.
3. Одна команда перевіряє всі поля, слова й час подій, direction_check.py, цілісність озвучки та записує план кадрів у Studio:
   python3 "{tool}" apply {project['id']} <абсолютний-шлях/story/direction.json>
   Вона сама зберігає shots.json, beats.json і bible.md та виконує razgon_bridge.py plan.
   Виправляй лише конкретні помилки з цього звіту; збери всі виправлення перед одним повторним запуском.
   Не додавай по одному необов’язковому ефекту після успішної перевірки. На WARN дай коротке змістовне пояснення в bible.

Для справді неоднозначного слова отримай лише його речення:
python3 "{tool}" words {project['id']} --sentence N
Джерела та таймінги захищено підписом у пакеті. Зміна озвучки або налаштувань вимагає свіжого пакета.
Схему не потрібно відновлювати з чужого випуску. Не читай попередні gen_shots.py, gen_sound.py, код мосту,
рендерера чи мікшера для звичайної режисури; потрібний контракт уже в пакеті. Не пиши службових генераторів
і скриптів для виведення всіх послівних таймінгів. Особливий технічний дефект діагностуй лише за конкретною помилкою.
Правила каналу й актуальні побажання наведені нижче. Етапи сценарію, озвучки, малювання, перевірки картинок
та експорту поза цим завданням. Не малюй сцени, не генеруй картинки, не рендери відео, не змінюй налаштування
каналу й нічого не публікуй. Логотип додає Studio, залиш його зону вільною.
Наприкінці коротко українською повідом кількість шотів, кадрів і SFX, зміст епізодів та реальні зауваження."""


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
            ("codex_image.py", "codex", "Малює аркуш картинок"), ("sheet_2x2", "opus", "Ріже аркуш на чотири картинки"), ("split_sheet", "codex", "Ріже аркуш на окремі предмети"),
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


# one more try in the same session; a second drop in a row stops the run with «Продовжити», which starts a fresh, short
# session from the saved work (user, 19 November 2026: each retry of a grown session cost about $5 and dropped again)
LOST_RETRIES = 1
LOST_WAIT = 20     # seconds before the first retry, more each time
LOST_PROMPT = ("Попередня відповідь обірвалась через втрату з'єднання з сервером, а не через твою помилку. "
               "Продовж те саме завдання з місця, де зупинився: перевір, що вже збережено на диску й у студії, "
               "не переробляй готове й доведи завдання до кінця.")


LOST_NOTE = ("З'єднання з Claude обірвалось двічі поспіль посеред відповіді. Готове збережено; натисніть «Продовжити», "
             "і робота піде в новій короткій сесії.")


def lost(answer: dict) -> bool:
    """The run stopped because the connection to Claude dropped mid-stream (19 November 2026: three of four frame
    sessions of Karl's «Voyager 1» ended «API Error: Connection lost mid-response» and the whole film read failed)."""
    return (answer.get("terminal_reason") == "api_error" and (answer.get("api_error") == "connection_failed"
            or "connection lost" in str(answer.get("result") or "").casefold()))


def run_json(command: list, prompt: str, cwd, timeout: float, keep=None):
    """A one-answer Claude run (`--output-format json`): a dropped connection asks the same question again, up to
    LOST_RETRIES times in a row (user, 19 November 2026: «у всіх випадках»). keep(stdout, answer) is called for every
    answer, a lost one too, so each paid answer is recorded. Returns the last process and its answer."""
    import model_json
    for attempt in range(LOST_RETRIES + 1):
        done = subprocess.run(command, input=prompt, cwd=cwd, text=True, capture_output=True, timeout=timeout)
        answer = {}
        for line in reversed((done.stdout or "").strip().splitlines()):   # the envelope is the last JSON object line
            try:
                answer = model_json.loads(line, kinds=(dict,))
                break
            except ValueError:
                continue
        if keep:
            keep(done.stdout or "", answer)
        if attempt == LOST_RETRIES or not ((done.returncode or answer.get("is_error")) and lost(answer)):
            return done, answer
        time.sleep(LOST_WAIT * (attempt + 1))
    return done, answer


@job_timing.measure('service')
def claude(cli: Path, prompt: str, log: Path, activity: Path, timeout: int, resume: str | None = None,
           effort: str = EFFORT, model: str = MODEL, env: dict | None = None) -> tuple[int, dict]:
    """Run Claude Code on a brief; a dropped connection resumes the same session up to LOST_RETRIES times in a row,
    each answer's cost counted. Returns the exit code and the final result event."""
    started = time.monotonic()
    code, answer = _claude_once(cli, prompt, log, activity, timeout, resume, effort, model, env)
    for attempt in range(1, LOST_RETRIES + 1):
        session = answer.get("session_id")
        left = timeout - (time.monotonic() - started) - LOST_WAIT * attempt
        if not ((code or answer.get("is_error")) and lost(answer) and session) or left <= 60 or str(activity) in CANCELLED:
            break
        time.sleep(LOST_WAIT * attempt)
        if str(activity) in CANCELLED:
            break
        import production_sessions
        more_code, more = _claude_once(cli, LOST_PROMPT, log.with_name(f"{log.stem}-resend{attempt}{log.suffix}"), activity,
                                       int(left), session, effort, model, env)
        code, answer = more_code, production_sessions.merge_answers(answer, more)
    return code, answer


def _claude_once(cli: Path, prompt: str, log: Path, activity: Path, timeout: int, resume: str | None = None,
                 effort: str = EFFORT, model: str = MODEL, env: dict | None = None) -> tuple[int, dict]:
    """Run Claude Code on a brief, streaming its events: the log keeps them all, the activity feed the readable ones.
    Returns the exit code and the final result event (cost, usage, the agent's last message)."""
    if model not in store.DIRECTOR_MODELS:
        raise store.StudioError("Невідома модель режисера")
    command = [str(cli), "--model", model, "--effort", effort, "--strict-mcp-config", "--safe-mode", "--setting-sources", "", "--permission-mode", "acceptEdits",
               "--disallowedTools", "Agent", "Task",
               "--allowedTools", *ALLOWED, "--output-format", "stream-json", "--verbose", "-p"] + (["--resume", resume] if resume else [])
    for folder in (store.APP_ROOT, store.DATA_ROOT):
        if not store.under(folder, store.YOUTUBE_ROOT) and (folder == store.APP_ROOT or not store.under(folder, store.APP_ROOT)):
            command += ['--add-dir', str(folder)]
    # its own process group; kill() also stops the commands, renders and helpers under it
    # the agents draw frames as code; only «Експорт MP4» renders them, so razgon_bridge.py refuses push and final here
    process = subprocess.Popen(command, cwd=store.YOUTUBE_ROOT, text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, start_new_session=True, env={**os.environ, NO_RENDER: "1", **(env or {})})
    feed = str(activity)
    with FEED_LOCK:
        alone = feed not in RUNNING and not RUNNING_MORE.get(feed)
        if feed in RUNNING:RUNNING_MORE.setdefault(feed, []).append(process)
        else:RUNNING[feed] = process
        if alone:FEEDS[feed] = []
    expired = threading.Event()
    watchdog = None
    answer, steps = {}, []
    stopped_after_result = False
    try:
        if str(activity) in CANCELLED:
            kill(process)
        watchdog = threading.Timer(timeout, lambda: (expired.set(), kill(process)))
        watchdog.start()
        with FEED_LOCK:
            if not FEEDS.get(feed):store.atomic_json(activity, [])
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
                        with FEED_LOCK:
                            shared = (FEEDS.get(feed, []) + [steps[-1]])[-40:]
                            FEEDS[feed] = shared
                            store.atomic_json(activity, shared)
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
        with FEED_LOCK:
            more = RUNNING_MORE.get(feed) or []
            if process in more:more.remove(process)
            elif RUNNING.get(feed) is process:
                if more:RUNNING[feed] = more.pop(0)
                else:RUNNING.pop(feed, None)
            if not more:RUNNING_MORE.pop(feed, None)
            if feed not in RUNNING:FEEDS.pop(feed, None)
        import spend_report   # where this run spent the limits, saved beside the project once the log is complete
        spend_report.record_later(log)
    if expired.is_set():
        raise subprocess.TimeoutExpired(command, timeout)
    return (0 if stopped_after_result else process.returncode), answer or {"is_error": True, "result": "Claude Code завершився без відповіді"}


AUTH_LOST = re.compile(r"Failed to authenticate|claude auth login|Please run /login|Invalid API key|OAuth token (?:has )?expired"
                       r"|authentication_error|Not logged in", re.I)
AUTH_NOTE = ("Claude Code на цьому Mac вийшов з облікового запису. Увійдіть у налаштуваннях студії, розділ «Claude Code», "
             "і натисніть «Продовжити»: усе зроблене збережено.")


def limit_stop(answer: dict) -> str | None:
    """When the run stopped because the Claude subscription limit ran out: a readable note with the reset time. A login
    that expired stops the same way and goes on the same way once the author signs in again (17 November 2026: frames
    1–52 read «не вдалися… Виберіть кадри й почніть ще раз» for an expired login)."""
    text = str(answer.get("result") or "")
    if AUTH_LOST.search(text) or answer.get("api_error") in {"authentication_failed", "authentication_error"}:
        return AUTH_NOTE
    if lost(answer):
        # stopped like a limit: the card offers «Продовжити», and it goes on in a fresh session
        return LOST_NOTE
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
    with FEED_LOCK:
        processes = [p for p in [RUNNING.get(feed), *(RUNNING_MORE.get(feed) or [])] if p]
    for process in processes:
        kill(process)


def stop_asked(pid: str, kind: str) -> bool:
    """Whether a stop of this run was asked, without taking the mark: the run's own end still reads it through
    cancelled() (a check on the way used to eat it, and a Codex-limit pause then read «Призупинено на ваше прохання»)."""
    return str(activity_path(pid, kind)) in CANCELLED


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
            plan = store.load_project_plan(pid) or {}
            # the voice was timed while he worked on the script: his shots move onto it in their own thread (no lock
            # held, no paid calls), which starts the frames itself when asked
            # every channel: a photo channel's Razgon workspace made on the script takes the voice the same way
            # (a fresh direction after a changed text left it estimated and the frames were refused for good)
            moving = (data.get('status') == 'done' and (plan.get('timing') or {}).get('status') == 'audio_synced'
                      and retime_soon(pid, bool(data.get('create_video'))))
            if data.get('status') == 'done' and data.get('create_video') and not moving:
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
        if data.get("status") == "done" and not cancelled_now(pid):
            early_kit(pid, cli, data)
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
            import script_timing
            if data.get("status") == "done" and not script_timing.estimated(store.load_project_plan(pid)) and not workspace_estimated(pid):
                # the shots and their sound cues are written: the film's music and effects go on the timeline at once
                # (razgon_sound.py; a photo channel's film is not due and is left alone). A direction on times from the
                # script waits for the voice: retime() lays them then.
                razgon_sound.start(pid, "director")


def cancelled_now(pid: str) -> bool:
    return str(activity_path(pid, "director")) in CANCELLED


def early_kit(pid: str, cli: Path, data: dict) -> None:
    """An animated direction made on the script while the voice is made: the film's kit («Підготовка») follows it at once
    (user, 16 November 2026: «інколи озвучка йде 30 хвилин»). The kit session is the one production would start first
    (production_kit.py); once story/kit.json is ready, production skips that stage. Whisper's times wait for this run
    (wait_idle), which costs nothing: the frames could not start before the kit anyway. A kit that fails is made by
    production as before."""
    import script_timing
    project = store.load_project(pid)
    plan = store.load_project_plan(pid) or {}
    if not script_timing.estimated(plan):
        return
    try:
        import production
        import production_kit
        import production_sessions
        frames = [f["number"] for f in plan.get("frames", [])]
        razgon_frames = sum(1 for f in plan.get("frames", []) if f.get("format") == "razgon_2d")
        if not animated(project) and razgon_frames >= production_kit.MIN_FRAMES and production_kit.razgon(project) is None:
            # a photo channel's film with Razgon frames (user, 16 November 2026: «а тут не було підготовки?… зроби»):
            # its Razgon workspace is made now, on the times from the script; the real voice refreshes it later
            subprocess.run([sys.executable, str(store.APP_ROOT / "tools" / "razgon_bridge.py"), "prepare", "--project-id", pid],
                           capture_output=True, text=True, timeout=300, cwd=str(store.APP_ROOT))
            project = store.load_project(pid)
        if not frames or not production_kit.needed(project, frames):
            return
        production_kit.seed(project)
        data["stage"] = "kit"
        save(pid, {**data, "status": "running"})   # «Підготовка» shows as work; «done» is written when the run ends
        with job_timing.separate("kit", pid) as timing:   # «Підготовка» has its own row in «Час роботи»
            with production_sessions.STUDIO_SESSIONS:
                _, answer = claude(cli, production.kit_brief(project, len(frames)), store.project_dir(pid) / "director-kit.log",
                                   activity_path(pid, "director"), TIMEOUT, effort=data["effort"], model=data["model"],
                                   env={"VIDEOKEY_PROJECT_ID": pid, "VIDEOKEY_STUDIO_URL": "http://127.0.0.1:8770"})
            production_kit.record_cost(store.load_project(pid), answer)
            data.update(kit="ready" if production_kit.ready(store.load_project(pid)) else "failed", kit_cost_usd=answer.get("total_cost_usd"))
            if data["kit"] == "ready":
                timing["status"] = "complete"
    except Exception as error:   # the direction stays done; production makes the kit itself
        data.update(kit="failed", kit_error=str(error)[:400])
    finally:
        data.pop("stage", None)


def start_kit(pid: str) -> bool:
    """«Продовжити» after a pause taken during the early «Підготовка»: the kit goes on beside the voice again, as it ran
    before the pause (17 November 2026: the Moon film's pause stopped the kit before its two sheets were drawn, and play
    resumed only the voice, so the kit waited for the frames). False when there is nothing to make or a run is on."""
    import production_kit
    project = store.load_project(pid)
    if production_kit.ready(project):
        return False
    with LOCK:
        if pid in ACTIVE:
            return False
        ACTIVE.add(pid)

    def work():
        data = state(pid) or {}
        try:
            data.update(model=data.get("model") or store.channel_director_model(project),
                        effort=data.get("effort") or store.channel_effort(project),
                        started_at=time.time())   # «Працює N хв» counts this kit, not the director's earlier run
            early_kit(pid, executable(), data)
        except Exception as error:   # the frames make the kit themselves, as after any failed kit
            data.update(kit="failed", kit_error=str(error)[:400])
        finally:
            stopped = cancelled(pid, "director")   # consume a pause's stop mark, or it kills the next director run
            with LOCK:
                ACTIVE.discard(pid)
                try:
                    if not stopped:   # a pause records the stopped kit itself (episode_pause._settle_director)
                        save(pid, {**data, "status": "done", "finished_at": time.time()})
                except OSError:
                    pass

    try:
        threading.Thread(target=work, daemon=True).start()
    except Exception:
        with LOCK:
            ACTIVE.discard(pid)   # never left «running» with no thread: recognition would wait for it for hours
        raise
    return True


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
                # a pass on the script's estimated times makes no frames: they wait for the voice
                "create_video": reason == 'create_video' or reason != 'script' and previous.get('status') == 'failed' and bool(previous.get('create_video'))}
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
    import episode_pause
    if episode_pause.note(pid, "after_voice", create_video=bool(create_video)):
        return   # the episode is paused: «Продовжити» takes this step
    try:
        if store.project_plan_mode(store.load_project(pid)) == "direct":
            return
        if create_video and pid in ACTIVE:
            start(pid, 'create_video')
            return
        plan = store.load_project_plan(pid) or {}
        # a new recognition of the same sentences keeps the director's frames; only a fresh or changed text needs a pass
        if plan.get("frame_source") == "razgon-direction" and not plan.get("director_stale"):
            if retime_soon(pid, create_video):
                return   # the thread moves the shots onto the voice, then the music and the frames
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
        # recorded in every case, so the plan page says why nothing went on (it used to vanish without create_video)
        failed(pid, str(error))
        if create_video:
            raise


RETIME_TIMEOUT = 600


RETIMING: set[str] = set()
WANT_FRAMES: set[str] = set()   # moves whose end should start the frames (whoever asked, first or later)


def failed(pid: str, message: str) -> None:
    """A step after the director that could not go on: kept as the director's `creation_error`, which the plan page shows
    with «Продовжити створення» (16 November 2026 stability pass: such failures were only printed to the log)."""
    try:
        data = state(pid) or {}
        data["creation_error"] = message
        save(pid, data)
    except (OSError, ValueError, store.StudioError):
        pass


def workspace_estimated(pid: str) -> bool:
    """The Razgon workspace still carries the times estimated from the script, or a move onto the voice was cut halfway
    (the marker tools/direction.py retime leaves until it has committed)."""
    try:
        link = store.read_json(store.project_dir(pid) / "razgon-link.json", {}) or {}
    except (store.StudioError, OSError, ValueError):
        return False
    root = Path(link.get("project") or "")
    if not link.get("project") or not root.is_dir():
        return False
    return bool((store.read_json(root / "story" / "studio_frames.json", {}) or {}).get("estimated")) or (root / "story" / ".retime-pending").exists()


def retime_soon(pid: str, create_video: bool = False) -> bool:
    """Move the direction onto the real voice in a thread of its own, holding no lock of the studio: its subprocess
    talks to the studio over HTTP (16 November 2026 review: run under store.LOCK or the update mutex it froze the studio
    for ten minutes). Then the music, and the frames when asked; a failure starts a fresh direction. False when nothing
    needed moving."""
    if not workspace_estimated(pid):
        return False
    with LOCK:
        if pid in RETIMING:
            if create_video:
                WANT_FRAMES.add(pid)   # a second caller asking for the frames is heard by the move already running
            return True
        RETIMING.add(pid)
        if create_video:
            WANT_FRAMES.add(pid)

    wanted = [False]

    def moved():
        # the move is over: the frames may start now (store.request_production refuses while the pid is RETIMING;
        # 16 November 2026 the thread started the frames before leaving RETIMING and every request was refused)
        with LOCK:
            if pid in RETIMING:
                wanted[0] = pid in WANT_FRAMES
            RETIMING.discard(pid)
            WANT_FRAMES.discard(pid)
        return wanted[0]

    def frames():
        import production
        production.start_from_plan(pid)

    def work():
        try:
            plan = store.load_project_plan(pid) or {}
            if (plan.get("timing") or {}).get("status") != "audio_synced":
                return   # the voice is not timed yet: the recognition calls again
            if not animated(store.load_project(pid)):
                # a photo channel's Razgon workspace: the real voice, words and frames; no direction to move
                done = refresh_workspace(pid)
                if moved() and done:
                    frames()
                elif not done:
                    failed(pid, "Не вдалося перенести робочу папку Razgon на справжню озвучку. Натисніть «Продовжити створення», щоб спробувати ще раз.")
            elif retime(pid):
                if moved():
                    frames()
            else:
                # the move failed: a fresh direction, unless the author paused the episode meanwhile (then «Продовжити»
                # takes this step; a paused episode starts nothing new, AGENTS.md)
                want = moved()
                import episode_pause
                if not episode_pause.note(pid, "after_voice", create_video=want):
                    start(pid, "create_video" if want else "voice")
        except Exception as error:
            # a failure on the way is shown on the plan page with «Продовжити створення», never only printed
            import traceback
            traceback.print_exc()
            failed(pid, str(error) if isinstance(error, store.StudioError) else "Не вдалося продовжити після переносу режисури на озвучку. Натисніть «Продовжити створення».")
        finally:
            moved()
    threading.Thread(target=work, daemon=True).start()
    return True


def resume_retimes() -> None:
    """At start-up: a move onto the voice cut by a restart goes on by itself (its marker kept the frames refused as
    «ще переносимо» for good). The frames follow when the director was asked for the whole video."""
    time.sleep(20)
    for folder in sorted((store.DATA_ROOT / "projects").glob("*/razgon-link.json")):
        pid = folder.parent.name
        try:
            if pid in ACTIVE or not workspace_estimated(pid):
                continue
            plan = store.load_project_plan(pid) or {}
            if (plan.get("timing") or {}).get("status") != "audio_synced" or plan.get("director_stale"):
                continue
            import episode_pause
            if episode_pause.paused(pid) is not None:
                continue   # a paused episode starts nothing by itself; «Продовжити» carries its steps
            project = store.load_project(pid)
            if animated(project) and plan.get("frame_source") != "razgon-direction":
                continue   # no director's shots to move: the director's own way after the voice decides, not a restart
            request = (project.get("production_request") or {}).get("status")
            retime_soon(pid, bool((state(pid) or {}).get("create_video")) and request not in {"requested", "in_progress", "done"})
        except Exception:
            import traceback
            traceback.print_exc()


def refresh_workspace(pid: str) -> bool:
    """A photo channel's Razgon workspace made on the script (the early kit) takes the real voice (razgon_bridge prepare).
    Its default shots follow the frames again; the kit stays. True when done."""
    try:
        result = subprocess.run([sys.executable, str(store.APP_ROOT / "tools" / "razgon_bridge.py"), "prepare", "--project-id", pid],
                                capture_output=True, text=True, timeout=RETIME_TIMEOUT, cwd=str(store.APP_ROOT))
    except (OSError, subprocess.SubprocessError) as exc:
        error = str(exc)
    else:
        if result.returncode == 0 and not workspace_estimated(pid):
            return True
        error = (result.stderr or result.stdout).strip()[-600:]
    store.atomic_json(store.project_dir(pid) / "director-retime-error.json", {"error": error, "at": time.time()})
    print(f"[director] workspace refresh {pid} failed: {error}", file=sys.stderr, flush=True)
    return False


def retime(pid: str) -> bool:
    """An animated direction made on times from the script moves onto the voice Whisper has just timed
    (tools/direction.py retime, no paid calls). Returns False when that failed: the plan is then marked director_stale
    and the director makes a fresh pass, as for a changed text. Called from retime_soon's thread only."""
    try:
        if not workspace_estimated(pid):
            return True
        result = subprocess.run([sys.executable, str(store.APP_ROOT / "tools" / "direction.py"), "retime", pid],
                                capture_output=True, text=True, timeout=RETIME_TIMEOUT, cwd=str(store.APP_ROOT))
        if result.returncode == 0:
            import episode_pause
            if not episode_pause.note(pid, "sound"):   # paused meanwhile: «Продовжити» lays the music
                razgon_sound.start(pid, "director")
            return True
        error = (result.stderr or result.stdout).strip()[-600:]
    except (OSError, subprocess.SubprocessError) as exc:
        error = str(exc)
    plan = store.load_project_plan(pid) or {}
    store.attach_plan(pid, dict(plan, director_stale=True))
    data = state(pid) or {}
    data["retime_error"] = error
    save(pid, data)
    # kept apart too: the fresh direction that follows rewrites the director's state (16 November 2026, «Нептун»)
    store.atomic_json(store.project_dir(pid) / "director-retime-error.json", {"error": error, "at": time.time()})
    print(f"[director] retime {pid} failed, a fresh direction follows: {error}", file=sys.stderr, flush=True)
    return False


def wait_idle(pid: str, limit: float = 3 * 3600, step: float = 3.0) -> None:
    """Whisper has timed the voice while the director still works on the script: its times wait for his plan."""
    waited = 0.0
    while pid in ACTIVE and waited < limit:
        time.sleep(step)
        waited += step


def montage_started(project: dict) -> bool:
    """A picture, video or text of the film is on the timeline already (the channel's plate and logo do not count)."""
    overlay = {cid for group in project.get("scene_groups") or [] if group.get("role") == "overlay" for cid in group.get("clip_ids", [])}
    return any(clip.get("kind") in {"image", "video", "text", "animation"} and clip.get("id") not in overlay
               for layer in project.get("tracks") or [] for clip in layer.get("clips") or [])
