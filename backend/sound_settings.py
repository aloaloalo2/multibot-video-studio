"""Channel sound choices shared by settings, agents and the local audio mixer."""
from __future__ import annotations

import copy
import importlib.util
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KIT_AUDIO = ROOT / 'razgon-plugin/razgon-2d-studio-plugin/skills/make-2d-video/kit/audio'
CATEGORIES = (
    ('whoosh', 'М’який помах', ('whoosh',)),
    ('swish', 'Швидкий помах', ('swish',)),
    ('appearance', 'Поява елемента', ('pop',)),
    ('switch', 'Перемикання елемента', ('blip',)),
    ('tick', 'Клацання', ('tick',)),
    ('counter', 'Підрахунок чисел', ('counter',)),
    ('notification', 'Сповіщення', ('ding',)),
    ('sparkle', 'Сяйво', ('shimmer',)),
    ('movement', 'Короткий удар', ('hit',)),
    ('impact', 'Глибокий акцент', ('impact', 'stinger')),
    ('tension', 'Наростання', ('riser',)),
    ('freeze', 'Стоп-кадр', ('freeze', 'slowmo')),
    ('digital', 'Цифровий збій', ('glitch',)),
    ('devices', 'Затвор камери', ('flash',)),
    ('ambience', 'Звуковий підйом', ('powerup',)),
)
TRANSITIONS = (
    ('air', 'Повітряний whoosh'), ('silk', 'М’який шовковий'), ('whip', 'Різкий whip'),
    ('camera', 'Затвор камери'), ('snap', 'Сухий snap'), ('sweep', 'Висхідний sweep'),
    ('down', 'Низхідний swoosh'), ('rise', 'Коротке наростання'), ('reverse', 'Зворотний вдих'),
    ('bass', 'Басовий поштовх'), ('glitch', 'Цифровий glitch'), ('pixel', 'Піксельний перехід'),
    ('neon', 'Неоновий перелив'), ('warp', 'Об’ємний warp'), ('shimmer', 'Кришталеве сяйво'),
)
TRANSITION_IDS = {row[0] for row in TRANSITIONS}
IDS = {row[0] for row in CATEGORIES}
LOCK = threading.RLock()


def merge(current, patch):
    result = normalize(current)
    if not isinstance(patch, dict):
        raise ValueError('Невірні налаштування звуку')
    for key, value in patch.items():
        result[key] = {**result.get(key, {}), **value} if isinstance(value, dict) else value
    return normalize(result)


def normalize(value=None):
    if value is None:
        value = {}
    if not isinstance(value, dict) or set(value) - {'music', 'effects', 'transitions'}:
        raise ValueError('Невірні налаштування звуку')
    result = {}
    for key, flags in (('music', {'enabled': True, 'generate': True}), ('effects', {'enabled': True})):
        part = value.get(key, {})
        if not isinstance(part, dict) or set(part) - (set(flags) | ({'categories'} if key == 'effects' else set())):
            raise ValueError('Невірні налаштування ' + key)
        result[key] = {}
        for flag, default in flags.items():
            current = part.get(flag, default)
            if type(current) is not bool:
                raise ValueError('Вибір звуку має бути увімкнено або вимкнено')
            result[key][flag] = current
    categories = value.get('effects', {}).get('categories', [row[0] for row in CATEGORIES])
    if not isinstance(categories, list) or any(not isinstance(key, str) or key not in IDS for key in categories) or len(set(categories)) != len(categories):
        raise ValueError('Невідома або повторена категорія звуку')
    result['effects']['categories'] = list(categories)
    transition = value.get('transitions', {})
    if not isinstance(transition, dict) or set(transition) - {'enabled', 'styles'}:
        raise ValueError('Невірні налаштування звуків переходів')
    enabled = transition.get('enabled', False)
    styles = transition.get('styles', [row[0] for row in TRANSITIONS])
    if type(enabled) is not bool or not isinstance(styles, list) or any(not isinstance(k, str) or k not in TRANSITION_IDS for k in styles) or len(set(styles)) != len(styles):
        raise ValueError('Невідомий звук переходу або некоректний вибір')
    result['transitions'] = {'enabled': enabled, 'styles': list(styles)}
    return result


def saved_for_project(project):
    import store
    try:
        settings = store.read_channel_settings(store.get_channel_folder(project['channel_id'], include_disabled=True), {})
    except (store.StudioError, OSError, KeyError):
        settings = {}
    return settings.get('sound')


def for_project(project):
    return normalize(saved_for_project(project))


def allowed_names(sound):
    selected = sound['effects']['categories'] if sound['effects']['enabled'] else []
    return [name for key, _, names in CATEGORIES if key in selected for name in names]


def transition_names(sound):
    selected = sound['transitions']['styles'] if sound['transitions']['enabled'] else []
    return ['tr_' + key for key, _ in TRANSITIONS if key in selected]


def apply_config(config, value, *, animated=False):
    """A copy, so channel switches never destroy the director's saved cues or music file."""
    result = copy.deepcopy(config)
    if value is None:
        return result
    sound = normalize(value)
    result['music'] = {**(result.get('music') or {}), **sound['music']}
    result['sfx'] = {**(result.get('sfx') or {}), 'enabled': sound['effects']['enabled'] or (sound['transitions']['enabled'] and not animated), 'allowed_names': allowed_names(sound) + ([] if animated else transition_names(sound))}
    return result


def filter_story(story, config):
    """Also supports a working kit that has not been updated yet."""
    result = copy.deepcopy(story)
    sfx = config.get('sfx') or {}
    if not sfx.get('enabled', True) or 'allowed_names' in sfx:
        allowed = set(sfx.get('allowed_names', [])) if sfx.get('enabled', True) else set()
        result['sfx'] = [cue for cue in result.get('sfx', []) if cue.get('name') in allowed]
        for shot in result.get('shots', []):
            shot['sfx'] = [cue for cue in shot.get('sfx', []) if cue.get('name') in allowed]
            if (shot.get('amb') or {}).get('name') not in allowed:
                shot.pop('amb', None)
    return result


def catalog():
    return [{'id': key, 'label': label, 'names': list(names), 'preview_url': f'/api/sound-effects/{key}.wav?v=2'} for key, label, names in CATEGORIES]


def transition_catalog():
    return [{'id': key, 'label': label, 'name': 'tr_' + key, 'preview_url': f'/api/transition-sounds/{key}.wav?v=1'} for key, label in TRANSITIONS]


def audio_module(name):
    # Load the checked-in kit, without requiring a renderer or changing a working project.
    with LOCK:
        key = '_videokey_audio_' + name
        if key not in sys.modules:
            spec = importlib.util.spec_from_file_location(key, KIT_AUDIO / (name + '.py'))
            module = importlib.util.module_from_spec(spec)
            sys.modules[key] = module
            try:
                spec.loader.exec_module(module)
            except BaseException:
                sys.modules.pop(key, None)
                raise
        return sys.modules[key]


def preview(category, *, transition=False):
    import store
    rows = [(key, label, ('tr_' + key,)) for key, label in TRANSITIONS] if transition else CATEGORIES
    row = next((row for row in rows if row[0] == category), None)
    if row is None:
        raise store.StudioError('Звук не знайдено', 404)
    path = store.DATA_ROOT / 'cache' / 'sound-previews-v2' / (('transition-' if transition else '') + category + '.wav')
    with LOCK:
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            module = audio_module('sfx')
            samples = module.make(row[2][0], seed=7, **({} if transition else {'dur': 1.5}))
            # One consistent, moderate preview level. No service call.
            import numpy as np
            peak = float(np.abs(samples).max(initial=0))
            samples *= .22 / max(peak, .22)
            module.write_wav(str(path), samples)
    return path


def instructions(project, *, scoped=False, include_workflow=True):
    sound = for_project(project)
    music = sound['music']
    text = '\nЗВУК РОЛИКА. Актуальний вибір автора для цього каналу:\n'
    text += ('Музика вимкнена. Не створюй і не додавай фонову музику.\n' if not music['enabled'] else
             'Використовуй фонову музику. Її можна створити локально.\n' if music['generate'] else
             'Використовуй лише вже додану музику. Нову музику не генеруй.\n')
    names = allowed_names(sound)
    text += ('Дозволені короткі монтажні ефекти: ' + ', '.join(names) + '. Використовуй їх для акцентів і появи елементів усередині кадру. Зберігай чіткість голосу.\n' if names else
             'Звукові ефекти й атмосферу вимкнено. Не додавай їх.\n')
    import store
    animated = store.project_animated(project)
    transitions = [] if animated else transition_names(sound)
    text += ('Окремі звуки переходів: ' + ', '.join(transitions) + '. Обирай лише доречні стики, чергуй типи. Більшість м’яких склейок залишай тихими.\n' if transitions else 'Звуки переходів вимкнено. Монтажні акценти мають окремий вибір.\n')
    if scoped:
        return text + 'Це правка кадрів: наявний звук збережи, заново його не створюй.\n'
    if not include_workflow or not project.get('id'):
        return text
    if not animated:
        text += 'Операція transitions озвучує вибрані доречні стики. Для авторського вибору передай sound_frames з номерами вхідних кадрів; порожній список лишає всі переходи тихими. Операція transition_sounds оновлює тільки звук на існуючих стиках. Не дублюй ці події окремими cues.\n'
    text += ('Для Razgon запиши ці обмеження в config.json: music.enabled, music.generate, sfx.enabled і sfx.allowed_names; '
             'cue та amb мають використовувати тільки дозволені імена. Вимкнений пункт не потребує генерування.\n'
             'Для звичайного монтажу після створення кадрів один раз використай /ops операцію soundtrack: '
             '{"op":"soundtrack","music":true,"mood":"calm","cues":[{"name":"whoosh","t":12.5}]}. '
             'Передай music:true лише коли музика дозволена до генерації та її ще немає; cues містять лише потрібні події. '
             'Це локальний синтез звуку, без платного API й без рендеру відео. Наявний звук не дублюй.\n')
    return text
