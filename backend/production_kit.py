"""The film's shared kit, made once before the parallel frame sessions, and the channel's library of helpers.

User, 15 November 2026: «зроби це все, щоб зекономити нам токени і прибавити в швидкості створення ролику». In one film six
parallel sessions wrote six helper libraries with the same price tags, people and arrows, and edited the shared cast.js,
assets.js and lib.js under each other, so approved neighbours went stale and the final review redid half the film. Now:

1. Before the parallel sessions one kit session reads the whole plan and makes what repeats in the film: the cast, the PNG
   props of every frame and the helpers for recurring elements. It writes no shots. It ends with story/kit.json.
2. While the parallel sessions run, the shared scene files are read-only on disk; a session keeps its own helpers in its
   own file. The final review gets them writable again.
3. The channel keeps a library of general helpers between its films (backend/data/channels/<id>/razgon-library). A new
   film starts with a copy in scenes/channel/; after a finished film the library takes back what the film added or improved.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import time
from pathlib import Path

import store

KIT_FILE = 'story/kit.json'
SHARED = ('scenes/cast.js', 'scenes/assets.js', 'scenes/lib.js', 'scenes/kit.js')
SHARED_DIRS = ('scenes/channel', 'scenes/sets')
LIBRARY_DIR = 'scenes/channel'
KIT_INDEX = 900          # the kit session's log: …-session-900.log
MIN_FRAMES = 11          # a film that one session draws needs no kit stage


def razgon(project: dict) -> Path | None:
    import frame_progress
    return frame_progress.razgon_project(project)


def library_dir(project: dict) -> Path:
    return store.DATA_ROOT / 'channels' / project['channel_id'] / 'razgon-library'


def ready(project: dict) -> bool:
    root = razgon(project)
    if not root:
        return False
    data = store.read_json(root / KIT_FILE, {}) or {}
    return data.get('ready') is True


def needed(project: dict, frames: list[int]) -> bool:
    """A kit pays off when several sessions draw Razgon frames of this film side by side."""
    plan = store.load_project_plan(project['id']) or {}
    razgon_frames = [f['number'] for f in plan.get('frames', []) if f.get('format') == 'razgon_2d' and f['number'] in set(frames)]
    return len(razgon_frames) >= MIN_FRAMES and razgon(project) is not None and not ready(project)


# ---- the channel library ------------------------------------------------------------------------------------------
def seed(project: dict) -> list[str]:
    """Copy the channel's library into the film once (scenes/channel/), so the film stays whole without it."""
    root, source = razgon(project), library_dir(project)
    if not root or not source.is_dir():
        return []
    target = root / LIBRARY_DIR
    copied = []
    for file in sorted(source.glob('*.js')) + sorted(source.glob('*.md')):
        out = target / file.name
        if out.exists():
            continue
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, out)
        copied.append(file.name)
    return copied


def harvest(project: dict) -> list[str]:
    """After a finished film the library takes back the files the film added or changed; the replaced versions are kept."""
    root = razgon(project)
    if not root or not (root / LIBRARY_DIR).is_dir():
        return []
    library = library_dir(project)
    history = library / 'history' / time.strftime('%Y%m%d-%H%M%S')
    taken = []
    for file in sorted((root / LIBRARY_DIR).glob('*')):
        if file.suffix not in ('.js', '.md') or not file.is_file():
            continue
        out = library / file.name
        if out.exists() and out.read_bytes() == file.read_bytes():
            continue
        library.mkdir(parents=True, exist_ok=True)
        if out.exists():
            history.mkdir(parents=True, exist_ok=True)
            shutil.copy2(out, history / file.name)
        shutil.copy2(file, out)
        os.chmod(out, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
        taken.append(file.name)
    return taken


# ---- read-only shared files -------------------------------------------------------------------------------------
def shared_files(project: dict) -> list[Path]:
    root = razgon(project)
    if not root:
        return []
    files = [root / name for name in SHARED if (root / name).is_file()]
    for folder in SHARED_DIRS:
        files += sorted(p for p in (root / folder).glob('*.js') if p.is_file())
    return files


def lock(project: dict) -> list[Path]:
    files = shared_files(project)
    for file in files:
        try:
            os.chmod(file, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        except OSError:
            pass
    return files


def unlock(project: dict) -> None:
    for file in shared_files(project):
        try:
            os.chmod(file, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
        except OSError:
            pass


def chunk_note(project: dict) -> str:
    """What a parallel session is told about the kit."""
    if not ready(project):
        return ''
    root = razgon(project)
    names = ', '.join(str(p.relative_to(root)) for p in shared_files(project)) or 'немає'
    return ('\nСпільний набір фільму вже готовий (story/kit.json): герої, PNG-предмети й помічники для повторюваних елементів. '
            'Бери їх звідти й не роби своїх копій. Ці спільні файли зараз лише для читання, бо паралельно працюють інші сесії: '
            + names + '. Не змінюй їх і не знімай захист. Чого бракує саме твоїм кадрам, клади у свій файл '
            'scenes/lib_<перший кадр партії>.js або в код шоту. Новий предмет додавай як звичайно через assets/.\n')


def brief(project: dict, frames: list[int]) -> str:
    """The kit session: the whole film's recurring material, no shots."""
    tools = store.razgon_rel()
    app = store.app_rel()
    library = library_dir(project)
    lib_note = (f'Бібліотека каналу вже скопійована в scenes/channel/ ({", ".join(sorted(p.name for p in library.glob("*.js")))}). '
                'Спершу перевір, що з неї підходить цьому фільму, і використовуй це.' if library.is_dir() and any(library.glob('*.js'))
                else 'Бібліотеки каналу ще немає: створи scenes/channel/ і поклади туди загальні помічники, які знадобляться й іншим фільмам каналу.')
    return f"""Ти готуєш спільний набір анімаційного фільму в VideoKey Studio перед тим, як кадри почнуть писати кілька сесій паралельно.
Випуск: «{project['name']}», id проєкту студії {project['id']}. Режисуру вже зроблено. Кадри фільму: {frames[0]}–{frames[-1]}.
Якщо проєкту Razgon ще немає: python3 "{app}/tools/razgon_bridge.py" prepare --project-id {project['id']}.

Мета: зробити один раз усе, що повторюється у фільмі, щоб паралельні сесії не будували кожна свої інструменти.
1. Прочитай план усіх кадрів одним викликом: python3 "{app}/tools/studio.py" plan {project['id']}. Прочитай story/bible.md і story/shots.json.
2. Випиши, що повторюється: герої, предмети, фони й типові елементи (цінники, підписи, графіки, лічильники, рух камери).
3. scenes/cast.js: усі постійні герої фільму з їхніми прикметами, однакові в кожному кадрі.
4. Предмети: збери PNG для всіх кадрів фільму зараз, а не по кадру.
   Спершу бібліотека, і це обов'язково для КОЖНОГО предмета: python3 "{tools}/tools/library.py" search <слова> --limit 6 --sheet <аркуш.png>,
   один погляд на аркуш, і use, якщо там є такий самий або досить схожий предмет. Схожий предмет з бібліотеки краще, ніж новий:
   малюй новий лише тоді, коли в бібліотеці нічого придатного немає. Чого немає, малюй аркушами по 6 через
   python3 "{tools}/tools/codex_image.py" --prompt <промпт> --out <assets/src/sheet_X.png> --background, потім --wait і split_sheet.py --clean 40.
   Запускай кілька аркушів у фоні одразу й поки вони малюються, пиши помічники.
   split_sheet сам перевіряє прозорість, розмір і чи не обрізаний кожен предмет і друкує шлях до ОДНОГО аркуша перегляду
   (<аркуш>.preview.png). Окремі PNG предметів не відкривай: подивись лише цей аркуш перегляду, один раз на аркуш.
   Перемальовуй тільки предмет із WARNING або явно не той на аркуші перегляду.
   У kit.json для кожного предмета вкажи "source": "library" або "drawn".
5. scenes/kit.js: помічники фільму для повторюваних елементів (на основі lib.js і scenes/channel/). Кожна експортована функція
   з коротким коментарем над нею: що малює і які аргументи.
6. {lib_note} Туди йде лише те, що не залежить від сюжету цього фільму (типова людина каналу, цінник, графік, підпис, рух камери).
7. Не пиши шоти й не став блоки на таймлайн: це робота наступних сесій.
8. Наприкінці запиши story/kit.json: {{"ready": true, "cast": [...], "props": [...], "helpers": [...], "notes": "що де лежить"}}.
   Без цього файлу сесії кадрів не стартують з набором.

Перевір, що scenes/kit.js і cast.js завантажуються без помилок: node --check для кожного файлу.
Стиль, вигляд людей і правила каналу нижче. Відео не рендери. Помічників не запускай. Поле description кожної команди пиши коротко українською.
"""


def record_cost(project: dict, answer: dict) -> None:
    root = razgon(project)
    if root and (root / KIT_FILE).is_file():
        data = store.read_json(root / KIT_FILE, {}) or {}
        data['made_at'] = time.time()
        data['cost_usd'] = answer.get('total_cost_usd')
        store.atomic_json(root / KIT_FILE, data)
