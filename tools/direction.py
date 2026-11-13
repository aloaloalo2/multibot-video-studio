#!/usr/bin/env python3
"""Prepare one director packet and apply one authored shot/sound table. No paid calls."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'tools'))
import direction_contract as contract
import razgon_bridge as bridge
import store


def workspace(project):
    link = store.read_json(store.project_dir(project['id']) / 'razgon-link.json', {}) or {}
    path = Path(link.get('project') or '')
    if not link.get('project') or not path.is_absolute() or not path.is_dir():
        raise ValueError('Підготуйте робочу папку командою prepare.')
    return path


def packet_for(project, plan, path):
    config = bridge.read_json(path / 'config.json')
    # Recheck current saved sound choices without changing the existing workspace.
    import sound_settings
    config = sound_settings.apply_config(config, sound_settings.saved_for_project(project), animated=True)
    settings = store.read_channel_settings(store.get_channel_folder(project['channel_id'], include_disabled=True), {}) or {}
    # Channel edits need not have propagated into this workspace yet. Bind the
    # draft to the live style/people/assets choice as well as the copied config.
    config['_channel_animation'] = settings.get('animation') or {}
    data = store.read_json(path / 'timeline/words.json', {}) or {}
    words = data.get('words', []) if isinstance(data, dict) else data
    return contract.source(plan, config, words, project_id=project['id']), words


def prepare(studio, pid):
    project, plan = studio.project(pid), studio.plan(pid)
    if not store.project_animated(project) or store.project_plan_mode(project) == 'direct':
        raise ValueError('Цей пакет призначений для режисури анімаційного проєкту.')
    if plan.get('frame_source') == 'razgon-direction' and not plan.get('director_stale'):
        raise ValueError('У проєкті вже є чинний режисерський план. Його збережено без перебудови.')
    if (project.get('production_request') or {}).get('status') == 'in_progress':
        raise ValueError('Створення кадрів уже працює. Збережіть чинну режисуру.')
    with contextlib.redirect_stdout(io.StringIO()):
        bridge.prepare(SimpleNamespace(project_id=pid, studio_url=studio.url,
            studio_dir=str(store.YOUTUBE_ROOT / store.razgon_rel()), slug=None, style=None))
    project = studio.project(pid)
    path = workspace(project)
    packet, _ = packet_for(project, plan, path)
    target = store.project_dir(pid) / 'director-context'
    store.atomic_json(target.with_suffix('.json'), packet)
    store.atomic_text(target.with_suffix('.txt'), contract.context_text(packet))
    print('Пакет режисера: ' + str(target.with_suffix('.txt')))
    print('Робоча папка: ' + str(path))
    print('Таблицю запишіть: ' + str(path / 'story/direction.json'))
    return target.with_suffix('.txt')


def words_for(studio, pid, number):
    project = studio.project(pid)
    path = workspace(project)
    packet, words = packet_for(project, studio.plan(pid), path)
    if not 1 <= number <= len(packet['sentences']):
        raise ValueError('Невідоме речення.')
    row = packet['sentences'][number - 1]
    print(f'Речення {number}: {row["text"]}')
    print(' | '.join(f'{w["start"]:.3f} {w.get("word", w.get("text", ""))}' for w in words
                     if row['start'] - .001 <= w['start'] < row['end'] - .001))


def staged_check(path, compiled):
    kit = store.YOUTUBE_ROOT / store.razgon_rel()
    with tempfile.TemporaryDirectory(prefix='.direction-', dir=path / 'build') as tmp:
        stage = Path(tmp)
        (stage / 'story').mkdir()
        for name in ('config.json', 'story/studio_frames.json'):
            shutil.copy2(path / name, stage / name)
        bridge.write_json(stage / 'story/shots.json', compiled['shots'])
        bridge.write_json(stage / 'story/beats.json', compiled['beats'])
        problems = bridge.check_project(stage)
        result = subprocess.run([sys.executable, str(kit / 'tools/direction_check.py'), '--project', str(stage)],
                                capture_output=True, text=True, timeout=60, cwd=kit)
        if problems or result.returncode:
            raise ValueError('\n'.join(problems + [(result.stdout + result.stderr).strip()])[:6000])
        return result.stdout.strip()


def commit_files(files):
    """A failed local write restores previous direction files; no partially applied table."""
    original = {p: p.read_bytes() if p.is_file() else None for p in files}
    try:
        for path, value in files.items():
            store.atomic_text(path, value)
    except BaseException:
        for path, value in original.items():
            if value is None:
                path.unlink(missing_ok=True)
            else:
                # Keep the exact old bytes, including its original whitespace.
                with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
                    f.write(value)
                    name = f.name
                Path(name).replace(path)
        raise


def apply(studio, pid, file, *, dry_run=False):
    project, plan = studio.project(pid), studio.plan(pid)
    path = workspace(project)
    if (project.get('production_request') or {}).get('status') == 'in_progress':
        raise ValueError('Створення кадрів уже працює. План не змінено.')
    if file.stat().st_size > 5_000_000:
        raise ValueError('Таблиця завелика.')
    draft = json.loads(file.read_text(encoding='utf-8'))
    saved = store.read_json(store.project_dir(pid) / 'director-context.json', {}) or {}
    packet, words = packet_for(project, plan, path)
    if saved.get('signature') != packet['signature']:
        raise ValueError('Пакет застарів: джерело, таймінги або налаштування змінилися. Жодного файлу не змінено.')
    compiled = contract.compile_direction(draft, packet, words)
    compiled['shots']['title'] = project['name']
    files = {path / 'story/shots.json': json.dumps(compiled['shots'], ensure_ascii=False, indent=2) + '\n',
             path / 'story/beats.json': json.dumps(compiled['beats'], ensure_ascii=False, indent=2) + '\n',
             path / 'story/bible.md': compiled['bible']}
    receipt_path = store.project_dir(pid) / 'director-apply.json'
    fingerprint = contract.digest(draft)
    receipt = store.read_json(receipt_path, {}) or {}
    if (not dry_run and receipt.get('draft_sha256') == fingerprint
            and receipt.get('source_signature') == packet['signature']
            and plan.get('frame_source') == 'razgon-direction' and not plan.get('director_stale')
            and all(p.is_file() and p.read_text(encoding='utf-8') == value for p, value in files.items())
            and receipt.get('plan_sha256') == contract.digest(plan['frames'])):
        print('Цю таблицю вже перевірено й збережено. Повторна перевірка та імпорт не потрібні.')
        return
    if plan.get('frame_source') == 'razgon-direction' and not plan.get('director_stale'):
        raise ValueError('Чинний режисерський план уже прийнятий. Зміни готових кадрів виконуйте через авторські правки.')
    report = staged_check(path, compiled)
    print(report)
    if dry_run:
        print('Перевірено без змін проєкту.')
        return
    # Catch a changed source during validation before committing direction files.
    fresh, _ = packet_for(studio.project(pid), studio.plan(pid), path)
    if fresh['signature'] != packet['signature']:
        raise ValueError('Джерело змінилося під час перевірки. План не змінено.')
    commit_files(files)
    # Existing bridge owns frame import, sentence coverage, plan identity and code slots.
    bridge.plan_from_direction(SimpleNamespace(razgon=str(path), studio_url=studio.url, dry_run=False))
    accepted = studio.plan(pid)
    store.atomic_json(receipt_path, {'source_signature': packet['signature'], 'draft_sha256': fingerprint,
                                     'plan_sha256': contract.digest(accepted['frames']), 'report': report})
    print(f'Режисура збережена: {len(compiled["shots"]["shots"])} шотів, '
          f'{len(compiled["shots"]["sfx"])} подій звуку. Рендер і генерації не запускалися.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--studio-url', default='http://127.0.0.1:8770')
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('prepare').add_argument('project')
    check = sub.add_parser('apply')
    check.add_argument('project')
    check.add_argument('file', type=Path)
    check.add_argument('--dry-run', action='store_true')
    words = sub.add_parser('words')
    words.add_argument('project')
    words.add_argument('--sentence', type=int, required=True)
    args = parser.parse_args()
    studio = bridge.Studio(args.studio_url)
    try:
        if args.action == 'prepare':
            prepare(studio, args.project)
        elif args.action == 'words':
            words_for(studio, args.project, args.sentence)
        else:
            apply(studio, args.project, args.file, dry_run=args.dry_run)
    except (ValueError, OSError, KeyError, bridge.BridgeError, subprocess.SubprocessError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
