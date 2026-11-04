"""Strict translation replies and resumable drafts; never publishes or voices text."""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
from pathlib import Path


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key.')
        result[key] = value
    return result


def answers(answer, ids):
    """Return valid requested lines plus a diagnostic. Unknown/duplicate IDs reject the reply.

    Accept a mapping, an array of records, an ordered string array, or JSONL
    records. Missing IDs may be repaired independently; invented extra IDs may not.
    """
    if not isinstance(answer, str):
        return {}, 'The model returned no text.'
    text = answer.strip()
    if text.startswith('```') and text.endswith('```'):
        text = text.split('\n', 1)[-1].rsplit('```', 1)[0].strip()
    decoder = json.JSONDecoder(object_pairs_hook=_unique_object)
    try:
        documents = []
        remaining = text
        while remaining:
            value, end = decoder.raw_decode(remaining)
            documents.append(value)
            remaining = remaining[end:].strip()
        if not documents:
            return {}, 'The model returned an empty reply.'
        value = documents[0] if len(documents) == 1 else documents
        if isinstance(value, dict) and 'id' in value:
            pairs = [(value['id'], value.get('text') or value.get('translation'))]
        elif isinstance(value, dict):
            pairs = list(value.items())
        elif isinstance(value, list) and value and all(isinstance(x, dict) for x in value):
            pairs = [(x.get('id'), x.get('text') or x.get('translation')) for x in value]
        elif isinstance(value, list) and len(value) == len(ids) and all(isinstance(x, str) for x in value):
            pairs = list(zip(ids, value))
        else:
            return {}, 'Expected a mapping, JSONL records, or an array of translated lines.'
        seen, result = set(), {}
        for key, line in pairs:
            if isinstance(key, str) and key.isdecimal():
                key = int(key)
            if type(key) is not int or key not in ids:
                return {}, 'The reply contains an unexpected phrase id.'
            if key in seen:
                return {}, 'The reply contains a duplicate phrase id.'
            seen.add(key)
            if isinstance(line, str) and line.strip():
                result[key] = ' '.join(line.split())
        missing = sorted(set(ids)-set(result))
        return result, ('Missing or empty phrase ids: '+', '.join(map(str, missing))) if missing else None
    except (ValueError, TypeError, KeyError):
        return {}, 'The model returned malformed JSON.'


class InvalidAudit(RuntimeError):
    """The reply did not supply a complete, consistent validation result."""


def audit(answer, ids, *, strict=False):
    """Strict audit contract: contradictory or incomplete evidence cannot approve text."""
    invalid = {i: 'Перевірка змісту не підтвердила цю фразу. Звірте її з оригіналом.' for i in ids}
    def invalid_reply():
        if strict:
            raise InvalidAudit('Модель не повернула повну відповідь перевірки.')
        return invalid
    try:
        value = json.loads(answer, object_pairs_hook=_unique_object)
        checked = value.get('ids')
        issues = value.get('issues', [])
        if (not isinstance(checked, list) or any(type(i) is not int for i in checked)
                or len(checked) != len(ids) or set(checked) != set(ids) or not isinstance(issues, list)):
            return invalid_reply()
        if value.get('ok') is True:
            return {} if not issues else invalid_reply()
        if value.get('ok') is not False or not issues:
            return invalid_reply()
        result = {}
        for issue in issues:
            if (not isinstance(issue, dict) or type(issue.get('id')) is not int or issue['id'] not in ids
                    or issue['id'] in result or not isinstance(issue.get('reason'), str) or not issue['reason'].strip()):
                return invalid_reply()
            result[issue['id']] = issue['reason']
        return result
    except (ValueError, TypeError, AttributeError):
        return invalid_reply()


class Draft:
    """Only an exact source/model/language/timing match may resume a draft."""
    def __init__(self, folder, identity):
        self.path = Path(folder)/'translation-draft.json'
        self.identity = fingerprint(identity)
        self.size = len(identity['source_units'])
        self.data = {'version': 1, 'identity': self.identity, 'lines': [],
                     'initial_parts': {}, 'audited': {}, 'rewrite': {}, 'cost_usd': 0.0}
        try:
            saved = json.loads(self.path.read_text())
            if (isinstance(saved, dict) and saved.get('version') == 1
                    and saved.get('identity') == self.identity and not saved.get('completed')
                    and self.valid_lines(saved.get('lines', []), empty=True)):
                self.data['lines'] = saved.get('lines', [])
                parts = saved.get('initial_parts')
                if isinstance(parts, dict):
                    self.data['initial_parts'] = {k: v for k, v in parts.items()
                        if isinstance(k, str) and k.isdecimal() and int(k) < self.size
                        and isinstance(v, list) and all(isinstance(x, str) and x.strip()
                            and '\n' not in x and '\r' not in x for x in v)}
                audited = saved.get('audited')
                if isinstance(audited, dict):
                    self.data['audited'] = {k: v for k, v in audited.items()
                        if isinstance(k, str) and k.isdecimal() and int(k) < self.size
                        and isinstance(v, str) and len(v) == 64}
                rewrite = saved.get('rewrite')
                if isinstance(rewrite, dict) and isinstance(rewrite.get('identity'), str):
                    values = rewrite.get('values')
                    if isinstance(values, dict):
                        self.data['rewrite'] = {'identity': rewrite['identity'], 'values':
                            {k: v for k, v in values.items() if isinstance(k, str) and k.isdecimal()
                             and int(k) < self.size and isinstance(v, str) and v.strip()}, 'issues': {}}
                cost = saved.get('cost_usd')
                if isinstance(cost, (int, float)) and not isinstance(cost, bool) and math.isfinite(cost) and cost >= 0:
                    self.data['cost_usd'] = float(cost)
                for key in ('origin', 'issue', 'repair_model'):
                    if isinstance(saved.get(key), str):
                        self.data[key] = saved[key]
                rejected = saved.get('rejected')
                if isinstance(rejected, dict):
                    self.data['rejected'] = {k: [entry for entry in entries[-3:]
                        if isinstance(entry, dict) and isinstance(entry.get('translation'), str)
                        and isinstance(entry.get('issue'), str)]
                        for k, entries in rejected.items() if isinstance(k, str) and k.isdecimal()
                        and int(k) < self.size and isinstance(entries, list)}
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    def valid_lines(self, lines, empty=False):
        return (isinstance(lines, list) and (len(lines) == self.size or empty and not lines)
                and all(isinstance(x, str) and x.strip() and '\n' not in x and '\r' not in x for x in lines))

    def save(self, **changes):
        self.data.update(changes)
        self.data['updated_at'] = time.time()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name+'.tmp')
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2)+'\n')
        os.replace(temporary, self.path)

    def seed(self, lines, origin=None):
        if not self.valid_lines(lines):
            raise ValueError('The recovery draft must retain every nonempty source phrase in order.')
        self.save(lines=list(lines), initial_parts={}, audited={}, rewrite={}, rejected={}, completed=False,
                  origin=origin, issue=None)

    def charge(self, cost):
        if not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost < 0:
            raise ValueError('Invalid translation cost.')
        self.save(cost_usd=round(float(self.data.get('cost_usd', 0))+float(cost), 8))
