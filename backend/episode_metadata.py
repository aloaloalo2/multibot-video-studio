"""YouTube metadata returned alongside an Opus script, kept out of spoken text."""
import hashlib
import json
import os
import re
import uuid
from pathlib import Path

import store
import audience_policy


PROMPT = '''Also write publication metadata in the channel language, using the finished script.
Return metadata with exactly 3 distinct A/B titles (titles array), including the selected title verbatim.
Alternative titles must contain no colon, dash, hyphen or list numbering. Do not invent claims.
description: always written by the channel's author himself, in the first person, speaking straight to the viewer, as if
he typed it under his own video (the author, 27 November 2026: «опис має бути завжди від автора написаний каналу, від нього
звернення, типу він писав цей опис, і дуже прямим текстом без води»): «я», «мы» for the channel, «вы» to the viewer; very
direct plain text, every sentence carries something concrete from this video, no warm-up, no filler, no general words; no
made-up personal stories or experiences, the first person speaks only about this video and its subject; not a template
(the author, 17 November 2026: «два-три речення, знизу хештеги… як звичайна людина написала»). 2-3 plain sentences in the
channel language about what this video shows and why it is worth watching, in everyday words. The description must be
concrete, never only pleasant (the author, 18 November 2026: «описання має бути конкретне… обов'язково»): name what this
video actually tells, the subject itself and one or two specific things from the script (a fact, a number, a place, what
happens and why), so a reader knows exactly what they will learn; no vague praise such as «a fascinating journey»; a short invitation to
subscribe only if it sounds natural here. No stock phrases that fit any video («Видео носит познавательный характер»,
«Спасибо, что смотрите», «This video is for informational purposes»), no claims beyond the script, no summary of the
whole script, no links, sources, timestamps or keyword lists. For a health topic one of the sentences may briefly say
that the video does not replace a doctor's advice. Then an empty line and one line of 1 to 9 hashtags for this video in
the channel language. Every hashtag is strictly ONE real word (the author, 27 November 2026: «хештеги… мусять бути 1
словом. строго 1 слово», then «від 1 до 9»): never two or more words glued together, so #космос #Юпитер #гравитация,
never #чёрныедыры or #гравитационныеволны.
tags (the author, 18 November 2026): from 4 to 15 tags in the channel language, every tag exactly ONE word (no spaces,
no phrases). The first tag is the channel's niche itself (for a space channel «космос»); the second is a synonym of that
niche («вселенная»). Then broad, common words people search for in this niche (космос, планеты, звёзды, Юпитер, Марс),
not narrow phrases about this one video; and always the main subject of this video as one word when it has one (a video
about the Moon has «Луна», about Mars «Марс»). No repeats.
These metadata requirements override older metadata instructions in the reference material.
Keep metadata entirely separate from the ready-to-speak script.'''


def recent_descriptions(cid, skip=None, limit=6):
    """The channel's latest descriptions (from each episode's publication-metadata.json, newest first), so a new one never
    repeats them (the author, 17 November 2026: «всі вони мають бути завжди різні для кожного ролика»)."""
    found = []
    try:
        projects = sorted((p for p in store.list_projects(cid) if p.get('id') != skip),
                          key=lambda p: float(p.get('updated_at') or 0), reverse=True)
    except (store.StudioError, OSError):
        return []
    for project in projects:
        data = store.read_json(store.project_dir(project['id']) / 'publication-metadata.json', {}) or {}
        text = data.get('description')
        if isinstance(text, str) and text.strip():
            found.append(text.strip())
        if len(found) >= limit:
            break
    return found


# Every description gets its own shape, picked at random for the film (the author, 27 November 2026: «так само додавати
# треба рандомно то так то ні емодзі», «шаблонність хочу прибрати, щоб кожен опис був унікальний»): emoji or none,
# two or three sentences, how it opens, how many hashtags. The same film keeps the same shape when asked again.
OPENINGS = ('Start with the most surprising fact or number from the script.',
            'Start with a short question the viewer may have asked themselves.',
            'Start with the one thing this video sorts out that people often get wrong.',
            'Start straight with the subject and what happens to it, no lead-in.',
            'Start with a concrete scene, place or moment from the script.',
            'Start with what the viewer will be able to tell or do after watching.')


def shape(seed) -> str:
    import random
    rng = random.Random(str(seed or random.random()))
    emoji = rng.choice((0, 0, 1, 1, 2))
    sentences = rng.choice((2, 3))
    hashtags = rng.randint(1, 9)
    words = {0: 'No emoji at all.', 1: 'Exactly one emoji that fits the subject, placed where a person would put it.',
             2: 'Two emoji that fit the subject, placed naturally (not both at the end, not as bullet points).'}[emoji]
    return (f'\nTHIS DESCRIPTION\'S OWN SHAPE (picked at random so no two descriptions look alike; follow it): '
            f'{sentences} sentences, in the channel author\'s own first-person voice to the viewer. {rng.choice(OPENINGS)} {words} Exactly {hashtags} hashtag'
            f'{"" if hashtags == 1 else "s"} on the hashtag line.')


def prompt(cid=None, skip=None):
    text = PROMPT + '\nCURRENT STUDIO AUDIENCE POLICY:\n' + audience_policy.text() + shape(skip)
    previous = recent_descriptions(cid, skip) if cid else []
    if previous:
        text += ('\nThe latest descriptions of this channel are below. Yours must differ from all of them: other words, '
                 'another first sentence, another build and other hashtags where the topic allows; never reuse their '
                 'phrases.\n' + json.dumps(previous, ensure_ascii=False))
    return text


def path(project):
    return Path(project['episode_path']) / 'Метаданные.txt'


def exists(project):
    file = path(project)
    return file.is_file() and bool(file.read_text(encoding='utf-8').strip())


def validate(value, title):
    if not isinstance(value, dict):
        raise ValueError('Opus не повернув метадані. Сценарій збережено; можна окремо дописати метадані.')
    titles, description, tags = (value.get(k) for k in ('titles', 'description', 'tags'))
    # The author selected the primary title. Punctuation drift from the model cannot block the whole bundle.
    if isinstance(titles, list) and len(titles) == 3 and all(isinstance(item, str) and item.strip() for item in titles):
        titles = [item.strip() for item in titles]
        if title not in titles:
            titles = [title, *titles[1:]]
    if isinstance(description, str):
        description = description.replace('\\r\\n', '\n').replace('\\n', '\n')

    def strings(items, count):
        return (isinstance(items, list) and len(items) == count
                and all(isinstance(s, str) and s.strip() and '\n' not in s.strip() for s in items)
                and len({s.strip().casefold() for s in items}) == count)
    if not strings(titles, 3) or title not in [s.strip() for s in titles]:
        raise ValueError('Потрібні три різні заголовки, включно з вибраним. Сценарій збережено.')
    if any(len(s.strip()) > 100 or (s.strip() != title and re.search(r'[:‒–—]|(?<!\w)[\-‐‑]|[\-‐‑](?!\w)|^\d+[.)]\s', s.strip())) for s in titles):
        raise ValueError('Некоректні заголовки метаданих. Сценарій збережено.')
    parts = re.split(r'\n\s*\n', description.strip()) if isinstance(description, str) else []
    text, tags_line = (parts[0], parts[-1]) if len(parts) == 2 else ('', '')
    hashtags = tags_line.split()
    sentences = [x for x in re.split(r'(?<=[.!?…])\s+', text.strip()) if x.strip()]
    # 2-3 sentences of the person who made the video, then one line of hashtags (the author, 17 November 2026)
    # 120 words: three French or Spanish sentences run past 80 (19 November 2026, an 87-word description was refused)
    if (len(parts) != 2 or not 1 <= len(sentences) <= 4 or len(text.split()) > 120 or re.search(r'https?://|#', text)
            or not 1 <= len(hashtags) <= 9 or not all(re.fullmatch(r'#[^\W_]{2,30}', h) for h in hashtags)):
        raise ValueError('Потрібен короткий опис на 2-3 речення і під ним рядок від 1 до 9 хештегів, кожен одним словом. Сценарій збережено.')
    # 4 to 15 one-word tags, the niche first (the author, 18 November 2026)
    if (not isinstance(tags, list) or not 4 <= len(tags) <= 15
            or not all(isinstance(t, str) and re.fullmatch(r'[^\s,#]{2,30}', t.strip()) for t in tags)
            or len({t.strip().casefold() for t in tags}) != len(tags)):
        raise ValueError('Потрібно від 4 до 15 різних тегів, кожен одним словом, перший про нішу каналу. Сценарій збережено.')
    return {'titles': [s.strip() for s in titles], 'description': description.strip(), 'tags': [s.strip() for s in tags]}


def save(project, value, script, *, author='Opus'):
    # Accepted metadata, including hand-written files, is never replaced by a writing job.
    if exists(project):
        return str(path(project))
    value = validate(value, project['name'])
    text = ('Тайтлы для A/B-теста\n' + '\n'.join(f'{i}. {s}' for i, s in enumerate(value['titles'], 1))
            + '\n\nОписание\n' + value['description'] + '\n\nТеги\n' + ', '.join(value['tags']) + '\n')
    destination = path(project)
    # the episode's folder may have been deleted or renamed by hand: it is made again, as at the project's creation
    # (14 November 2026: «[Errno 2] No such file or directory … .metadata-….tmp» after a finished script)
    destination.parent.mkdir(parents=True, exist_ok=True)
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
        **value, 'author': author, 'script_sha256': hashlib.sha256(script.strip().encode()).hexdigest(),
        'file': str(destination)})
    return str(destination)


def save_generated(project, value, script, complete):
    """Normalize locally first; at most one short metadata-only model call when content is absent/invalid."""
    if exists(project):
        return str(path(project))
    try:
        value = validate(value, project['name'])
    except ValueError as error:
        brief = (prompt(project.get('channel_id'), project.get('id')) + '\nReturn only {"metadata":{"titles":["...","...","..."],"description":"...","tags":["niche","niche synonym","...","..."]}}. '
                  'Do not rewrite the script. The selected title is authoritative.\n'
                  + json.dumps({'channel':project.get('channel_name',''), 'selected_title':project['name'],
                                            'topic_excerpt':script[:800], 'validation_error':str(error)}, ensure_ascii=False))
        result = complete(brief)
        return save(project, result.get('metadata'), script)
    return save(project, value, script)
