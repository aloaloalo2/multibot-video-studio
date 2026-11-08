"""YouTube metadata returned alongside an Opus script, kept out of spoken text."""
import hashlib
import os
import re
import uuid
from pathlib import Path

import store


PROMPT = '''Also write publication metadata in the channel language, using the finished script.
Return metadata with exactly 3 distinct A/B titles (titles array), including the selected title verbatim.
Alternative titles must contain no colon, dash, hyphen or list numbering. Do not invent claims.
description: 2 short paragraphs, usually 2-4 sentences total. First thank viewers and invite them to
subscribe in the channel voice; second state the informational/educational/entertainment purpose.
For health topics add a brief note about individual professional consultation. No script summary,
links, sources, hashtags, timestamps or SEO lists. tags: exactly 3 distinct relevant strings.
These metadata requirements override older metadata instructions in the reference material.
Keep metadata entirely separate from the ready-to-speak script.'''


def path(project):
    return Path(project['episode_path']) / 'Метаданные.txt'


def exists(project):
    file = path(project)
    return file.is_file() and bool(file.read_text(encoding='utf-8').strip())


def validate(value, title):
    if not isinstance(value, dict):
        raise ValueError('Opus не повернув метадані. Сценарій збережено; можна окремо дописати метадані.')
    titles, description, tags = (value.get(k) for k in ('titles', 'description', 'tags'))
    def strings(items, count):
        return (isinstance(items, list) and len(items) == count
                and all(isinstance(s, str) and s.strip() and '\n' not in s.strip() for s in items)
                and len({s.strip().casefold() for s in items}) == count)
    if not strings(titles, 3) or title not in [s.strip() for s in titles]:
        raise ValueError('Потрібні три різні заголовки, включно з вибраним. Сценарій збережено.')
    if any(len(s.strip()) > 100 or (s.strip() != title and re.search(r'[:\-‐‑‒–—]|^\d+[.)]\s', s.strip())) for s in titles):
        raise ValueError('Некоректні заголовки метаданих. Сценарій збережено.')
    if (not isinstance(description, str) or len(re.split(r'\n\s*\n', description.strip())) != 2
            or len(description.split()) > 120 or re.search(r'https?://|#', description)):
        raise ValueError('Потрібен короткий опис із двох абзаців. Сценарій збережено.')
    if not strings(tags, 3) or any(',' in s for s in tags):
        raise ValueError('Потрібні рівно три окремі теги. Сценарій збережено.')
    return {'titles': [s.strip() for s in titles], 'description': description.strip(), 'tags': [s.strip() for s in tags]}


def save(project, value, script):
    # Accepted metadata, including hand-written files, is never replaced by a writing job.
    if exists(project):
        return str(path(project))
    value = validate(value, project['name'])
    text = ('Тайтлы для A/B-теста\n' + '\n'.join(f'{i}. {s}' for i, s in enumerate(value['titles'], 1))
            + '\n\nОписание\n' + value['description'] + '\n\nТеги\n' + ', '.join(value['tags']) + '\n')
    destination = path(project)
    tmp = destination.with_name('.metadata-' + uuid.uuid4().hex + '.tmp')
    try:
        tmp.write_text(text, encoding='utf-8')
        # Linking a complete file provides atomic creation without overwriting a concurrent edit.
        try:
            os.link(tmp, destination)
        except FileExistsError:
            if not exists(project):
                raise ValueError('Файл метаданих порожній. Перевірте його перед повторним збереженням.')
            return str(destination)
    finally:
        tmp.unlink(missing_ok=True)
    store.atomic_json(store.project_dir(project['id']) / 'publication-metadata.json', {
        **value, 'author': 'Opus', 'script_sha256': hashlib.sha256(script.strip().encode()).hexdigest(),
        'file': str(destination)})
    return str(destination)
