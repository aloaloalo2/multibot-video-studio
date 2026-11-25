"""Author-selected, licensed original SFX, retained locally outside the code repository."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent / 'data/sfx-library/mixkit-20261112'


# Music and cartoon sounds left the SFX list (user, 21 November 2026: «SFX не може бути музикою… в більшості це має бути
# не мультяшні звуки»): a success chime, two coins, a wrong-answer buzz, a sad trombone, a comedy boing, a bubble pop,
# an 11.7 s clock, a 65 s bass drone and an 11 s tension rise. Their files stay on disk, unused.
EXCLUDED = {'938', '1999', '1992', '946', '472', '2894', '2357', '1059', '685', '786'}
MAX_SECONDS = 4.0
LEVELED = 'sfx-library-v2'


# CapCut's «Sound effects → Trending» list as of 25 November 2026 (user: «в CapCut є Sound Effects трендінг… всі їх скачай
# в SFX, постав в нашу студію»): the 86 that CapCut marks for commercial use and that last at most 4.0 s (the studio levels SFX to 4 s at most), so none is cut.
# A row keeps its CapCut id in `mixkit_id`, the key every SFX choice and route already uses.
CAPCUT = 'capcut-trending-20261125'   # beside ROOT


def catalog():
    found = []
    for root in (ROOT, ROOT.parent / CAPCUT):
        path = root / 'catalog.json'
        if not path.is_file():
            continue
        rows = json.loads(path.read_text(encoding='utf-8'))
        found += [{**r, 'name': str(root / (r['mixkit_id'] + '.wav')), 'duration_seconds': min(MAX_SECONDS, float(r['duration_seconds'])),
                   'source_group': 'capcut' if 'capcut_id' in r else 'mixkit',
                   'preview_url': '/api/sfx-library/' + r['mixkit_id'] + '.wav?v=3'}
                  for r in rows if (root / (r['mixkit_id'] + '.wav')).is_file() and r['mixkit_id'] not in EXCLUDED]
    return found


def leveled(row) -> Path:
    """The file at the common SFX loudness and at most 4 s (kit audio/sfx.py level), made once and kept in the cache."""
    import subprocess
    import numpy as np
    import sound_settings
    import store
    out = store.DATA_ROOT / 'cache' / LEVELED / (row['mixkit_id'] + '.wav')
    if not out.is_file():
        out.parent.mkdir(parents=True, exist_ok=True)
        raw = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', row['name'], '-f', 'f32le', '-ac', '2', '-ar', '48000', '-'],
                             capture_output=True, check=True).stdout
        module = sound_settings.audio_module('sfx')
        samples = np.frombuffer(raw, dtype=np.float32).reshape(-1, 2)
        pending = out.with_suffix('.pending.wav')
        module.write_wav(str(pending), module.level(samples))
        pending.replace(out)
    return out


def allowed(sound):
    if 'library' in sound:
        choice = sound['library']
        if not choice['enabled']:
            return []
        ids = set(choice['ids']) if 'ids' in choice else None
        return [row['name'] for row in catalog() if ids is None or row['mixkit_id'] in ids]
    if not sound['effects']['enabled']:
        return []
    import sound_settings
    categories = set(sound['effects']['categories'])
    # the files keep the category names of the list before 21 November 2026
    return [row['name'] for row in catalog() if sound_settings.OLD_CATEGORIES.get(row['category'], row['category']) in categories]


def find(name):
    return next((row for row in catalog() if row['name'] == name), None)


def instructions(sound):
    rows = [r for r in catalog() if r['name'] in set(allowed(sound))]
    if not rows:
        return ''
    return ('\nАВТОРСЬКА ДОБІРКА SFX. Для нових анімацій використовуй саме ці завантажені файли. '
            'У cue.name записуй повний шлях із каталогу. Обирай доречні звуки під видимі події: '
            'поява тексту, рух, результат, жарт, напруга. Не озвучуй кожен рух; голос має лишатися чітким. '
            'Кожен ефект звучить цілим, своєю природною довжиною (до 4 с), dur його не обрізає; гучність студія вирівнює сама. '
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
        events.append({'name': cue['name'], 't': at, 'dur': max(.1, min(MAX_SECONDS, duration)), 'gain': gain})
    for offset in range(0, len(events), 200):
        project = studio.project(pid)
        studio.call('POST', f'/api/projects/{pid}/ops', {
            'expected_revision': project['revision'],
            'ops': [{'op': 'soundtrack', 'cues': events[offset:offset + 200]}]})
    return len(events)
