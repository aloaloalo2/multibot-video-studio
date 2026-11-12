"""Author-selected, licensed original SFX, retained locally outside the code repository."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent / 'data/sfx-library/mixkit-20261112'


def catalog():
    path = ROOT / 'catalog.json'
    if not path.is_file():
        return []
    rows = json.loads(path.read_text(encoding='utf-8'))
    return [{**r, 'name': str(ROOT / (r['mixkit_id'] + '.wav')),
             'preview_url': '/api/sfx-library/' + r['mixkit_id'] + '.wav'}
            for r in rows if (ROOT / (r['mixkit_id'] + '.wav')).is_file()]


def allowed(sound):
    if not sound['effects']['enabled']:
        return []
    categories = set(sound['effects']['categories'])
    return [row['name'] for row in catalog() if row['category'] in categories]


def find(name):
    return next((row for row in catalog() if row['name'] == name), None)


def instructions(sound):
    rows = [r for r in catalog() if r['name'] in set(allowed(sound))]
    if not rows:
        return ''
    return ('\nАВТОРСЬКА ДОБІРКА SFX. Для нових анімацій використовуй саме ці завантажені файли. '
            'У cue.name записуй повний шлях із каталогу. Обирай доречні звуки під видимі події: '
            'поява тексту, рух, результат, жарт, напруга. Не озвучуй кожен рух; голос має лишатися чітким. '
            'Короткі ефекти використовуй із природною тривалістю, довгі за потреби обрізай через dur, максимум 6 с. '
            'Студія розміщує кожну подію окремим редагованим аудіокліпом на доріжці SFX. '
            'Не зводь цю добірку з музикою чи голосом і не дублюй її в amb. '
            'Для нових анімацій amb залишай порожнім: у цій добірці немає фонової атмосфери. '
            'Цей каталог визначає вибір звуків для нового ролика; приклади синтезованих ефектів у загальних довідках замінюй файлами каталогу.\n' +
            '\n'.join(f"{r['name']} | {r['label']} | {r['duration_seconds']} с" for r in rows) + '\n')


def without_library(story):
    result = copy.deepcopy(story)
    names = {r['name'] for r in catalog()}
    result['sfx'] = [c for c in result.get('sfx', []) if c.get('name') not in names]
    for shot in result.get('shots', []):
        shot['sfx'] = [c for c in shot.get('sfx', []) if c.get('name') not in names]
        if (shot.get('amb') or {}).get('name') in names:
            shot.pop('amb', None)
    return result


def place(studio, pid, story):
    """Use normal Studio actions; identical cues are idempotent and author edits survive."""
    rows = {r['name']: r for r in catalog()}
    cues = list(story.get('sfx') or [])
    cues += [{**c, 't': float(s['start']) + float(c.get('at', 0))}
             for s in story.get('shots', []) for c in s.get('sfx') or []]
    events = []
    for cue in cues:
        row = rows.get(cue.get('name'))
        if row is None:
            continue
        duration = float(cue.get('dur') or row['duration_seconds'])
        gain = float(cue.get('gain', -8))
        at = float(cue['t'])
        if not all(math.isfinite(v) for v in (at, duration, gain)) or at < 0 or duration <= 0:
            raise ValueError('Невірна подія SFX')
        events.append({'name': cue['name'], 't': at, 'dur': max(.1, min(6, duration)), 'gain': gain})
    for offset in range(0, len(events), 200):
        project = studio.project(pid)
        studio.call('POST', f'/api/projects/{pid}/ops', {
            'expected_revision': project['revision'],
            'ops': [{'op': 'soundtrack', 'cues': events[offset:offset + 200]}]})
    return len(events)
