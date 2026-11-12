"""Lossless prompt compaction: unique rule paragraphs and one complete topic ledger."""
import copy
import json
import re
import unicodedata

RULE_SOURCES = ('author_writing_rules', 'youtube_script_rules', 'channel_script_rules', 'claude_memory_notes')


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def compact(context):
    result = copy.deepcopy(context)
    before = len(json.dumps(context, ensure_ascii=False))
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
