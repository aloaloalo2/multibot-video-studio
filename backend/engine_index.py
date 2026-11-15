"""A short index of the Razgon engine for the frame agent, built from the engine files themselves.

Frame sessions used to open engine/core.js, rig2d.js and the other engine files whole to find a function; each
read then stayed in the conversation and was reread at every later step (user, 15 November 2026: «ліміти витрачаються
швидко», 40 million tokens in two days went on rereading the engine and its notes). The index names every exported
function with its arguments and first comment line, so the agent looks up only the one it needs.
"""
import re
import threading
from pathlib import Path

import store

LOCK = threading.Lock()
CACHE = {}
LIMIT = 110


def engine_dir() -> Path:
    return store.APP_ROOT / 'razgon-2d-studio' / 'engine'


def build(folder: Path) -> str:
    rows = []
    for file in sorted(folder.glob('*.js')):
        lines = file.read_text(encoding='utf-8', errors='replace').splitlines()
        items = []
        for number, line in enumerate(lines):
            found = re.match(r'export (?:async )?function (\w+)\s*\(([^)]*)\)', line)
            if found:
                notes, above = [], number - 1
                while above >= 0 and lines[above].strip().startswith('//'):
                    notes.insert(0, lines[above].strip()[2:].strip(' -'))
                    above -= 1
                note = ' '.join(n for n in notes if n)[:LIMIT]
                args = re.sub(r'\s+', ' ', found.group(2)).strip()[:70]
                items.append(f'{found.group(1)}({args}) :{number + 1}' + (f' — {note}' if note else ''))
                continue
            found = re.match(r'export (?:const|let|class) (\w+)', line)
            if found:
                items.append(f'{found.group(1)} :{number + 1}')
        if items:
            rows.append(f'{file.name}: ' + '; '.join(items))
    return '\n'.join(rows)


def index() -> str:
    folder = engine_dir()
    try:
        stamp = tuple((f.name, f.stat().st_mtime_ns) for f in sorted(folder.glob('*.js')))
    except OSError:
        return ''
    with LOCK:
        if CACHE.get('stamp') != stamp:
            try:
                CACHE.update(stamp=stamp, text=build(folder))
            except OSError:
                return ''
        return CACHE['text']


def brief() -> str:
    text = index()
    if not text:
        return ''
    return ('\nПокажчик рушія Razgon (' + str(engine_dir()) + '). Тут усі експортовані функції: аргументи, рядок у файлі '
            'й перший рядок коментаря. Файли рушія цілком не читай: потрібну функцію відкривай Read з offset біля її рядка '
            'і limit до 60 рядків, або Grep -n за назвою. Так рушій не займає місце в розмові до кінця сесії.\n'
            + text + '\n')


def _first_note(text: str, limit: int = 220) -> str:
    """The opening comment or docstring of a file, joined into one line."""
    lines, notes = text.splitlines(), []
    for line in lines[:8]:
        stripped = line.strip()
        if stripped.startswith(('//', '#')) and not stripped.startswith('#!'):
            notes.append(stripped.lstrip('/#').strip())
        elif stripped.startswith(('"""', "'''")):
            notes.append(stripped.strip('"\''))
            if stripped.count('"""') == 1 or stripped.count("'''") == 1:
                continue
            break
        elif notes:
            break
    return ' '.join(n for n in notes if n)[:limit]


def _exports(text: str, limit: int = 30) -> str:
    names = re.findall(r'(?m)^export (?:async )?(?:function|const|let|class) (\w+)', text)
    more = f' … ще {len(names) - limit}' if len(names) > limit else ''
    return ', '.join(names[:limit]) + more


def style_palette(style: str) -> str:
    """The style's own block from engine/styles.js, so the agent need not grep it for colours."""
    try:
        text = (engine_dir() / 'styles.js').read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''
    found = re.search(r'(?m)^\s{2,4}' + re.escape(style) + r': \{', text)
    if not found:
        return ''
    end = re.search(r'(?m)^\s{2,4}\},?\s*$', text[found.end():])
    block = text[found.start():found.end() + (end.end() if end else 1500)]
    return re.sub(r'[ \t]+', ' ', block)[:1500]


def project_index(project: dict) -> str:
    """What this episode already has: its scene libraries, sets, shots and the helper scripts of earlier sessions
    (user, 15 November 2026: about 500 steps in two days went on ls, Grep and reading these files to find them)."""
    import frame_progress
    rows = []
    razgon = frame_progress.razgon_project(project)
    if razgon:
        scenes = razgon / 'scenes'
        for file in sorted(scenes.glob('*.js')) + sorted((scenes / 'sets').glob('*.js')):
            try:
                text = file.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            name = file.relative_to(scenes).as_posix()
            note, names = _first_note(text), _exports(text)
            note = re.sub(r'^(?:scenes/)?' + re.escape(file.name) + r'\s*[—-]\s*', '', note)
            rows.append(f'scenes/{name}: ' + ' | '.join(part for part in (note, 'експорт: ' + names if names else '') if part))
        shots = sorted(p.stem for p in (scenes / 'shots').glob('*.js'))
        if shots:
            rows.append(f'scenes/shots ({len(shots)}): ' + ', '.join(shots))
    work = store.project_dir(project['id']) / 'work'
    scripts = sorted(work.glob('*.py')) if work.is_dir() else []
    for file in scripts[:60]:
        try:
            note = _first_note(file.read_text(encoding='utf-8', errors='replace')[:2000], 120)
        except OSError:
            note = ''
        rows.append(f'work/{file.name}' + (f': {note}' if note else ''))
    if work.is_dir():
        pictures = sum(1 for _ in work.glob('*.png'))
        if pictures:
            rows.append(f'work/: ще {pictures} PNG-аркушів попередніх перевірок, їх не відкривай без потреби')
    try:
        style = (store.read_channel_settings(store.get_channel_folder(project['channel_id'], include_disabled=True), {})
                 .get('animation') or {}).get('style') or ''
    except (store.StudioError, KeyError, OSError):
        style = ''
    palette = style_palette(style) if style and not style.startswith(('custom-', 'studio-')) else ''
    if not rows and not palette:
        return ''
    text = ('\nФайли цього випуску, які вже є (Razgon: ' + (str(razgon) if razgon else 'ще немає') + ', робоча папка: '
            + str(work) + '). Не шукай їх через ls, Glob чи Grep: відкривай потрібний файл одразу, а великий читай '
            'частинами через offset і limit. Наявні бібліотеки й скрипти використовуй повторно.\n' + '\n'.join(rows) + '\n')
    if palette:
        text += f'\nСтиль каналу «{style}» з engine/styles.js (кольори вже тут, styles.js не шукай):\n{palette}\n'
    return text
