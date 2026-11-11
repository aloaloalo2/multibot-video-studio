"""Small read-only job projections. Full reports remain available on the existing routes."""
from collections import OrderedDict
import threading

import store

LOCK = threading.RLock()
CACHE = OrderedDict()
MAX_CACHE = 128
JOB_KEYS = ('id', 'project_id', 'type', 'kind', 'code', 'status', 'stage', 'progress', 'error', 'handoff_error',
            'started_at', 'finished_at', 'updated_at', 'writer', 'file', 'version', 'total', 'completed',
            'provider', 'queue_position')


def job(value):
    return {key: value[key] for key in JOB_KEYS if key in value} if isinstance(value, dict) else None


def cached_file(path, project):
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    key = (str(path), stat.st_mtime_ns, stat.st_size, stat.st_ino)
    with LOCK:
        if key in CACHE:
            CACHE.move_to_end(key)
            return CACHE[key]
        result = project(store.read_json(path))
        CACHE[key] = result
        while len(CACHE) > MAX_CACHE:CACHE.popitem(last=False)
        return result


def report(value):
    if not isinstance(value, dict):return None
    keys = ('status', 'applied', 'script_sha256', 'studio_script_sha256', 'word_match_percent',
            'phrase_count', 'matched_phrases', 'timing_source')
    result = {key: value[key] for key in keys if key in value}
    if value.get('sequence_verification'):
        proof = value['sequence_verification']
        result['sequence_verification'] = {key: proof[key] for key in ('version', 'verified') if key in proof}
    blocking = {'missing_boundary','uncertain_boundary','missing_speech','repeated_speech','out_of_order'}
    if not value.get('sequence_verification'):blocking.update(('low_phrase_match','number_difference'))
    phrases = [row for row in value.get('phrases', []) if row.get('issues')]
    phrases.sort(key=lambda row: not bool(blocking.intersection(row['issues'])))
    result['phrases'] = [{'number': row.get('number'), 'issues': row['issues']} for row in phrases[:8]]
    return {**result, 'compact': True}


def analysis_report(path):
    return cached_file(path, report)
