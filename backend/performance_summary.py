"""Compact work-time and saved-cost projection. Reads local receipts without replaying logs or jobs."""
from pathlib import Path

import project_costs
import store

LABELS = {
    'openings': 'Зачини', 'script': 'Сценарій', 'metadata': 'Метадані',
    'narration': 'Озвучка', 'analysis': 'Розпізнавання озвучки',
    'planning': 'План кадрів', 'production': 'Створення кадрів', 'export': 'Експорт',
    'translation': 'Переклад', 'language_voice': 'Озвучка перекладів',
}
ALIASES = {'language_sample': 'language_voice', 'language_save': 'language_voice', 'language_refit': 'language_voice'}
LOCAL = {'analysis', 'export'}
TOKEN_KEYS = ('input', 'output', 'cache_read', 'cache_write')


def workflow(value):
    value = ALIASES.get(value, value)
    return value if value in LABELS else None


def active_ms(row):
    elapsed = row.get('elapsed_ms', 0)
    if not project_costs.number(elapsed):
        return 0.
    stages = row.get('stages') or {}
    idle = sum(value.get('ms', 0) for key, value in stages.items()
               if key in {'queue', 'pause'} and isinstance(value, dict) and project_costs.number(value.get('ms')))
    return max(0., elapsed - idle)


def event_workflow(identity, event):
    explicit = event.get('workflow')
    if explicit:
        return workflow(explicit)
    category = event.get('category')
    if category in {'thumbnail', 'legacy_thumbnail', 'language_thumbnail'}:
        return None
    name = Path(identity.split(':', 1)[-1]).name
    if name.startswith(('openings-', 'hooks-')):
        return 'openings'
    if name.startswith('metadata-'):
        return 'metadata'
    if name.startswith('director'):
        return 'planning'
    if name.startswith('production'):
        return 'production'
    if category in {'script', 'script_editing', 'script_revision'}:
        return 'script'
    if category == 'narration':
        return 'narration'
    if category in {'voice', 'language_voice', 'language_sample'}:
        return 'language_voice'
    if category in {'languages', 'translation'}:
        return 'translation' if event.get('provider') == 'openrouter' else 'language_voice'
    return workflow(category)


def read_small(path, default=None, limit=262144):
    try:
        if path.stat().st_size > limit:
            return default
        return store.read_json(path, default)
    except (OSError, ValueError, TypeError):
        return default


def saved_costs(root):
    def key_for(value):
        if not value.startswith('claude_code:'):
            return value
        log = Path(value.split(':', 1)[1])
        if log.suffix not in {'.log', '.jsonl'}:
            return value
        return 'claude_code:' + str((log if log.is_absolute() else root / log).resolve())

    index = read_small(root / 'project-costs.json', {}, limit=8 * 1024 * 1024)
    raw = index.get('events') if isinstance(index, dict) else {}
    events = {}
    for key, value in raw.items() if isinstance(raw, dict) else []:
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        key = key_for(key)
        previous = events.get(key)
        stamp = value.get('modified', 0)
        if previous is None or project_costs.number(stamp) and stamp >= previous.get('modified', 0):
            events[key] = dict(value)
    latest = {}
    # Reports already contain the per-run billing result. Never reparse a live CLI log here.
    for path in sorted((root / 'spend').glob('*.json'), reverse=True)[:256]:
        report = read_small(path)
        if not isinstance(report, dict) or not isinstance(report.get('log'), str):
            continue
        key = key_for('claude_code:' + report['log'])
        stamp = report.get('log_modified', 0)
        if not project_costs.number(stamp):
            continue
        if key not in latest or stamp > latest[key].get('log_modified', 0):
            latest[key] = report
    tokens = {}
    for key, report in latest.items():
        event = events.get(key, {})
        modified = event.get('modified', 0)
        if report.get('log_modified', 0) >= (modified if project_costs.number(modified) else 0):
            event = {**event, 'provider': 'claude_code', 'amount': report.get('cost_usd'),
                     'estimated': not report.get('cost_measured'), 'modified': report.get('log_modified', 0)}
        kind = {'director': 'planning', 'production': 'production'}.get(report.get('kind'))
        if kind:
            event = {**event, 'workflow': kind}
        events[key] = event
        group = event_workflow(key, event)
        if group:
            target = tokens.setdefault(group, {})
            source = report.get('tokens') if isinstance(report.get('tokens'), dict) else {}
            for name in TOKEN_KEYS:
                value = source.get(name)
                if project_costs.number(value):
                    target[name] = target.get(name, 0) + value
    buckets = {}
    for identity, event in events.items():
        group = event_workflow(identity, event)
        if group:
            buckets.setdefault(group, {})[identity] = event
    rate = read_small(store.DATA_ROOT / 'eleven-credit-usd.json', {})
    rate = rate if isinstance(rate, dict) else {}
    result = {}
    for group in LABELS:
        costs = buckets.get(group, {})
        result[group] = {'recorded': bool(costs) or group in LOCAL,
                         'providers': project_costs.totals({'events': costs}, rate.get('credit_usd_rate'))['providers'],
                         'tokens': tokens.get(group, {})}
    return result


LOST = {'failed', 'cancelled', 'interrupted', 'unknown'}
ORDER = {name: index for index, name in enumerate(LABELS)}


def project(runs, root):
    """Useful time counts finished, running and paused runs. Failed, cancelled and interrupted attempts stay separate."""
    groups = {}
    running = False
    for row in runs:
        kind = workflow(row.get('workflow'))
        if not kind:
            continue
        live = row.get('status') == 'running'
        running |= live
        group = groups.setdefault(kind, {'id': kind, 'workflow': kind, 'label': LABELS[kind],
                                         'active_ms': 0., 'running': False, 'lost_ms': 0., 'lost_runs': 0})
        spent = active_ms(row)
        if row.get('status') in LOST:
            group['lost_ms'] += spent
            group['lost_runs'] += 1
        else:
            group['active_ms'] += spent
        group['running'] |= live
    try:
        costs = saved_costs(root)
    except (OSError, ValueError, TypeError, AttributeError):
        costs = {}
    rows = []
    for group in groups.values():
        group['active_ms'] = round(group['active_ms'], 2)
        group['lost_ms'] = round(group['lost_ms'], 2)
        if group['active_ms'] + group['lost_ms'] <= 1000:
            continue
        group['cost'] = costs.get(group['workflow'], {'recorded': False})
        rows.append(group)
    rows.sort(key=lambda row: ORDER[row['workflow']])
    return {'processes': rows, 'running': running,
            'total_ms': round(sum(row['active_ms'] for row in rows), 2),
            'lost_ms': round(sum(row['lost_ms'] for row in rows), 2)}
