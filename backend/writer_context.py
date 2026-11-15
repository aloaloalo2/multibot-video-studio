"""Lossless prompt compaction: unique rule paragraphs and one complete topic ledger."""
import copy
import json
import re
import unicodedata

RULE_SOURCES = ('studio_audience_policy', 'author_writing_rules', 'youtube_script_rules', 'channel_script_rules', 'claude_memory_notes')


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


# Sections of the studio's rules about WHICH model writes and how the studio routes the work (Opus, ChatGPT, Codex,
# effort, excluded authors, transcripts, files) are for the coordinator, not for the writer. Sent to Opus they made a
# 34 000-character brief about AI models and their «reasoning effort», and Opus 5.5's safety filter stopped a normal
# French script as «reasoning_extraction» (user, 15 November 2026: «мені потрібно, щоб більше такого не повторювалося»).
ROUTING = re.compile(r'opus|sonnet|chatgpt|codex|minimax|deepseek|inkling|gemma|автор|в чаті|в чате|расшифровк|розшифровк|'
                     r'\btxt\b|объединение предложений|объём сценария сначала|обсяг сценарію спершу|зачин\w* .*предложени', re.I)


def writer_rules(text):
    """The writing rules without the sections about model routing and studio workflow."""
    parts = re.split(r'(?m)^(?=## )', text)
    return ''.join(part for part in parts if not (part.startswith('## ') and ROUTING.search(part.splitlines()[0])))


def compact(context):
    result = copy.deepcopy(context)
    before = len(json.dumps(context, ensure_ascii=False))
    for name in ('youtube_script_rules', 'claude_memory_notes'):
        if isinstance(result.get(name), str):
            result[name] = writer_rules(result[name])
    seen = set()
    duplicates = 0
    for name in RULE_SOURCES:
        if not isinstance(result.get(name), str):continue
        paragraphs = []
        for paragraph in re.split(r'\n\s*\n', result[name]):
            key = unicodedata.normalize('NFC', paragraph).strip()
            if len(key) >= 80 and key in seen:
                duplicates += 1
                continue
            if len(key) >= 80:seen.add(key)
            paragraphs.append(paragraph)
        result[name] = '\n\n'.join(paragraphs)
    topics = {}
    for row in [*({'title': title} for title in (context.get('previous_titles') or []) if isinstance(title, str)),
                *({'title': title} for title in (context.get('previous_suggestions') or []) if isinstance(title, str)),
                *(context.get('previous_topic_history') or [])]:
        if not isinstance(row, dict) or not isinstance(row.get('title'), str):continue
        key = ' '.join(unicodedata.normalize('NFC', row['title']).split()).casefold()
        # Retain every supplied subject label, including conflicting historical labels.
        identity = (key, row.get('subject') or '', row.get('premise') or '')
        topics[identity] = {name: row[name] for name in ('title', 'subject', 'premise') if isinstance(row.get(name), str)}
    if topics:
        for key, subject, premise in list(topics):
            if subject or premise:topics.pop((key, '', ''), None)
        result['topic_exclusions'] = list(topics.values())
        for key in ('previous_titles', 'previous_suggestions', 'previous_topic_history'):result.pop(key, None)
    after = len(encode(result))
    if after > before:
        result = copy.deepcopy(context)
        after = len(encode(result))
    return result, {'original_characters':before,'sent_characters':after,'saved_characters':before-after,
                    'duplicate_paragraphs':duplicates,'excluded_topics':len(topics)}
