"""Compile an author's semantic shot table using the existing voice timings.

The model chooses episodes, takes, staging, camera and sound events. This module
only formats files, locates selected words and validates the technical contract.
No model, speech, image or rendering service is called here.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import unicodedata

import word_timing

TRANSITIONS = ('cut', 'fade', 'dip', 'dipWhite', 'flash', 'whip', 'push', 'iris', 'match', 'smash', 'zoom')
MOODS = ('mystery', 'tension', 'action', 'wonder', 'hopeful', 'sad', 'triumph', 'playful', 'calm', 'dark', 'epic')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def source(plan, config, words, *, project_id=None):
    timing = plan.get('timing') or {}
    if timing.get('status') != 'audio_synced':
        raise ValueError('Спочатку потрібні озвучка та її перевірені таймінги.')
    sentences = timing.get('sentences') or [s for f in plan['frames'] for s in f['sentence_timings']]
    rows = [{'number': i, 'start': float(s['start']), 'end': float(s['end']), 'text': s['text']}
            for i, s in enumerate(sentences, 1)]
    duration = finite(timing['audio']['duration'], 'тривалість озвучки', 0.001)
    if not rows:
        raise ValueError('Немає речень озвучки.')
    for i, row in enumerate(rows):
        if not row['text'] or not 0 <= row['start'] < row['end'] <= duration + .001:
            raise ValueError(f'Некоректні таймінги речення {i + 1}.')
        if i and row['start'] < rows[i - 1]['end'] - .001:
            raise ValueError('Таймінги речень перекриваються.')
    value = {'project_id': project_id, 'channel_id': plan.get('channel_id'),
             'script_sha256': plan.get('script_sha256'), 'audio': timing['audio'],
             'duration': duration, 'sentences': rows, 'words_sha256': digest(words),
             'look': {k: v for k, v in config.items() if k not in ('duration', 'voiceover', 'script')},
             'sound': {'music': config.get('music') or {}, 'sfx': config.get('sfx') or {}}}
    value['signature'] = digest(value)
    return value


def finite(value, label, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{label}: потрібне скінченне число.')
    if minimum is not None and value < minimum or maximum is not None and value > maximum:
        raise ValueError(f'{label}: значення поза дозволеними межами.')
    return float(value)


def token(value):
    return re.sub(r'[^\w]', '', unicodedata.normalize('NFC', value).casefold()).replace('ё', 'е')


def cue_time(cue, packet, words):
    number = cue.get('sentence')
    if type(number) is not int or not 1 <= number <= len(packet['sentences']):
        raise ValueError('Подія SFX: невідоме речення.')
    sentence = packet['sentences'][number - 1]
    if cue.get('word'):
        if 'offset' in cue:
            raise ValueError('Подія SFX: виберіть word або offset.')
        candidates = [{'text': w.get('word', w.get('text', '')), 'start': w['start'], 'sentence': 1}
                      for w in words if sentence['start'] - .001 <= float(w['start']) < sentence['end'] - .001]
        # Digit captions and spoken multi-word numbers use the same established timing map.
        converted = word_timing.digit_words([1], candidates)
        target = [token(t) for t in cue['word'].split() if token(t)]
        occurrence = cue.get('occurrence', 1)
        if not target or type(occurrence) is not int or occurrence < 1:
            raise ValueError(f'SFX речення {number}: некоректне слово або occurrence.')
        for values in (candidates, converted):
            matches = [v['start'] for i, v in enumerate(values)
                       if [token(w['text']) for w in values[i:i + len(target)]] == target]
            if len(matches) >= occurrence:
                return float(matches[occurrence - 1])
        raise ValueError(f'SFX речення {number}: слово «{cue["word"]}» відсутнє в таймінгах. Уточніть лише цю подію.')
    if 'offset' not in cue:
        raise ValueError(f'SFX речення {number}: вкажіть word або явний offset.')
    offset = finite(cue['offset'], 'offset', 0, sentence['end'] - sentence['start'])
    return sentence['start'] + offset


def compile_direction(draft, packet, words):
    if not isinstance(draft, dict) or draft.get('source_signature') != packet['signature']:
        raise ValueError('Змінилися джерело, таймінги або налаштування. Оновіть пакет перед збереженням.')
    rows = draft.get('shots')
    if not isinstance(rows, list) or not rows or len(rows) > 5000:
        raise ValueError('Передайте непорожню таблицю shots.')
    bible = draft.get('bible')
    if not isinstance(bible, str) or not bible.strip():
        raise ValueError('Додайте bible: коротку режисерську карту персонажів, епізодів, декорацій і ризиків.')
    duration, sentences = packet['duration'], packet['sentences']
    shots, beats, cues, seen, errors = [], [], [], set(), []
    expected = 1
    for index, row in enumerate(rows, 1):
        try:
            if not isinstance(row, dict):
                raise ValueError('потрібен об’єкт шоту')
            first, last = row.get('first_sentence'), row.get('last_sentence')
            if type(first) is not int or type(last) is not int or first != expected or not first <= last <= len(sentences):
                raise ValueError(f'речення мають іти підряд від {expected}, без пропусків і повторів')
            sid = row.get('id', f's{index:03d}')
            if not isinstance(sid, str) or not re.fullmatch(r'[\w-]{1,80}', sid) or sid in seen:
                raise ValueError('невірний або повторений id')
            for key in ('scene', 'episode', 'set'):
                if not isinstance(row.get(key), str) or not row[key].strip():
                    raise ValueError(f'потрібне поле {key}')
            if len(row['scene'].split()) < 4:
                raise ValueError('scene має описувати конкретну композицію й дію')
            transition = copy.deepcopy(row.get('in') or {'type': 'cut'})
            if not isinstance(transition, dict) or transition.get('type') not in TRANSITIONS:
                raise ValueError('невідомий тип переходу')
            if 'dur' in transition:
                finite(transition['dur'], 'dur переходу', 0, 5)
            start = sentences[first - 1]['start'] if first > 1 else 0.0
            end = sentences[last]['start'] if last < len(sentences) else duration
            if transition.get('dur', 0) > end - start:
                raise ValueError('перехід довший за шот')
            shot = {'id': sid, 'start': start, 'end': end, 'episode': row['episode'], 'set': row['set'],
                    'scene': row['scene'], 'line': ' '.join(s['text'] for s in sentences[first - 1:last]),
                    'in': transition, 'bars': None, 'sfx': [], 'amb': None, 'notes': row.get('notes', '')}
            if row.get('params'):
                if not isinstance(row['params'], dict):
                    raise ValueError('params має бути об’єктом')
                shot['params'] = copy.deepcopy(row['params'])
            row_cues = row.get('cues', [])
            if not isinstance(row_cues, list):
                raise ValueError('cues має бути списком')
            for cue in row_cues:
                if not isinstance(cue, dict):
                    raise ValueError('подія SFX має бути об’єктом')
                name = cue.get('name')
                allowed = packet['sound']['sfx']
                if not allowed.get('enabled', True) or name not in allowed.get('allowed_names', []):
                    raise ValueError('SFX не дозволений у поточних налаштуваннях каналу')
                at = cue_time(cue, packet, words)
                if not first <= cue['sentence'] <= last or not start <= at < end:
                    raise ValueError('SFX належить іншому шоту або виходить за його межі')
                item = {'name': name, 't': at, 'gain': finite(cue.get('gain', -14), 'gain', -60, 0),
                        'shot': sid, 'why': str(cue.get('why') or '')}
                if 'dur' in cue:
                    item['dur'] = finite(cue['dur'], 'dur ефекту', .01, 6)
                cues.append(item)
            seen.add(sid)
            shots.append(shot)
            beats.append({'id': sid, 'start': start, 'end': end, 'first_sentence': first - 1,
                          'last_sentence': last - 1, 'episode': row['episode'], 'scene': row['scene']})
            expected = last + 1
        except (ValueError, TypeError, KeyError) as error:
            errors.append(f'Шот {index}: {error}')
    if expected != len(sentences) + 1:
        errors.append(f'Потрібно покрити всі {len(sentences)} речень, наступне очікуване {expected}.')
    music = copy.deepcopy(draft.get('music') or [])
    policy = packet['sound']['music']
    if music and (not policy.get('enabled', True) or not policy.get('generate', True)):
        errors.append('Новий музичний план не дозволений поточним вибором каналу.')
    if not isinstance(music, list):
        errors.append('music має бути списком.')
        music = []
    for i, part in enumerate(music):
        try:
            if not isinstance(part, dict) or part.get('mood') not in MOODS:
                raise ValueError('невідомий музичний настрій')
            a, b = finite(part['start'], 'start музики', 0, duration), finite(part['end'], 'end музики', 0, duration)
            finite(part.get('intensity', .5), 'intensity', 0, 1)
            if b <= a or i and abs(a - music[i - 1]['end']) > .001:
                raise ValueError('музичні частини мають бути додатними й послідовними')
        except (ValueError, TypeError, KeyError) as error:
            errors.append(f'Музика {i + 1}: {error}')
    if errors:
        raise ValueError('\n'.join(errors))
    cues.sort(key=lambda c: c['t'])
    return {'shots': {'duration': duration, 'shots': shots, 'music': music, 'sfx': cues},
            'beats': {'beats': beats}, 'bible': bible.strip() + '\n'}


def context_text(packet):
    """One complete voice table and a small technical reference; no old episode code."""
    return '\n'.join([
        'РЕЖИСЕРСЬКИЙ ПАКЕТ. Джерело: ' + packet['signature'],
        f'Тривалість {packet["duration"]:.3f} с. Речень {len(packet["sentences"])}. Номери речень починаються з 1.',
        'Напиши один direction.json. Схема:',
        '{"source_signature":"' + packet['signature'] + '","bible":"персонажі, епізоди, декорації, камера, мотиви, ризики",'
        '"shots":[{"id":"s001","first_sentence":1,"last_sentence":4,"episode":"E01","set":"orbit",'
        '"scene":"конкретна композиція, дія, рух камери, PNG предмети", "in":{"type":"fade","dur":0.5},'
        '"cues":[{"sentence":2,"word":"слово події","occurrence":1,"name":"дозволене ім’я","gain":-14,"dur":1.5,"why":"видима подія"}]}],'
        '"music":[{"start":0,"end":' + str(packet['duration']) + ',"mood":"mystery","intensity":0.4}]}',
        'Діапазони речень вибираєш за змістом. Кожне речення рівно один раз, послідовно, від 1 до кінця. '
        'Кількість шотів визначає зміна дії, думки чи декорації. Неперервна дія в одному місці об’єднується в один шот. '
        'Усередині нього композиція може розвиватися. Не нарізай автоматично за реченнями або кількістю слів.',
        'Спочатку продумай зв’язні епізоди та розвиток, потім шоти. Орієнтир довгого плану 10-25 с, '
        'спокійні довші пояснення допустимі за змістом. Кожна нова локація відкривається зрозумілим рухом камери. '
        'Уникай повторення композицій і повернень між декораціями без причини.',
        'Переходи: ' + ', '.join(TRANSITIONS) + '. dur у секундах; push/whip: dir 1 або -1, vertical true для вертикального руху; '
        'iris: x,y від 0 до 1; match: from/to об’єкти {x,y} у частках кадру. '
        'cut усередині того самого місця потребує змістовної зміни; неперервну дію продовжуй.',
        'Cues і music залишай порожніми для вимкнених пунктів. Для SFX обери видиму подію й слово всередині її речення; '
        'можна передати явний offset у секундах від початку речення. '
        'Підготуй весь список подій одразу; додавання ефектів заради числової квоти не потрібне. '
        'Довгі файли обрізай dur максимум до 6 с. amb лишай порожнім. Наявну музику не генеруй заново.',
        'Музичні настрої: ' + ', '.join(MOODS) + '. intensity від 0 до 1; частини start/end у секундах, змінюються за змістом.',
        'Камера, перспектива, зв’язок тексту й предметів, пропорції та опора мають бути описані конкретно. '
        'Збережи слова й порядок озвучки, вибраний стиль і вільну зону логотипа. Логотип додає Studio. '
        'Сцени, картинки, відео й озвучку на цьому етапі не створюй.',
        'Поточний звуковий вибір: ' + json.dumps(packet['sound'], ensure_ascii=False, separators=(',', ':')),
        'РЕЧЕННЯ З ОЗВУЧКИ:',
        *[f'{s["number"]:03d} {s["start"]:.3f}-{s["end"]:.3f} {s["text"]}' for s in packet['sentences']],
    ]) + '\n'
