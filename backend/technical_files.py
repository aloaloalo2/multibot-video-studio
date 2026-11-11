"""Keep service metadata in Studio storage; archive old episode copies losslessly."""
from pathlib import Path
import json
import shutil
import time
import store

LEGACY_NAMES = ('razgon.json', 'План видео.json', 'Запит на створення.json', 'Таймінги озвучки.json')


def migrate_channel(folder):
    """Retain an exact backup before retiring a legacy channel configuration."""
    with store.LOCK:
        legacy = folder / store.PLAN_CONFIG
        if not legacy.exists():
            return []
        target = store.channel_settings_path(folder)
        if legacy.is_symlink() or target.is_symlink():
            raise store.StudioError('Налаштування каналу містять символічне посилання')
        original = legacy.read_bytes()
        value = json.loads(original)
        if not isinstance(value, dict):
            raise store.StudioError('Налаштування каналу мають бути об’єктом')
        # A newer internal configuration remains authoritative. Both versions are retained.
        if target.exists() and not isinstance(store.read_json(target), dict):
            raise store.StudioError('Внутрішні налаштування каналу пошкоджені')
        backup = target.parent / 'technical-history' / str(time.time_ns()) / legacy.name
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy, backup)
        if backup.read_bytes() != original:
            raise OSError('Не вдалося перевірити резервну копію налаштувань каналу')
        if not target.exists():
            store.atomic_json(target, value)
            if store.read_json(target) != value:
                raise OSError('Не вдалося перевірити перенесені налаштування каналу')
        if legacy.read_bytes() != original:
            raise OSError('Налаштування каналу змінилися під час перенесення')
        legacy.unlink()
        return [str(legacy)]


def migrate_channels():
    result = {}
    for folder in store.channel_folders(include_disabled=True):
        try:
            result[store.channel_id(folder)] = migrate_channel(folder)
        except (OSError, ValueError, store.StudioError) as error:
            result[store.channel_id(folder)] = {'error': str(error)}
    return result


def save_link(pid, data):
    with store.LOCK:
        store.load_project(pid)
        if not isinstance(data, dict) or not all(isinstance(data.get(key), str) and data[key] for key in ('razgon_root', 'project')):
            raise store.StudioError('Вкажіть папку анімації та її проєкт')
        root, project = Path(data['razgon_root']).resolve(), Path(data['project']).resolve()
        frames = store.read_json(project / 'story/studio_frames.json', {})
        if not (root / 'render.mjs').is_file() or not store.under(project, root / 'projects') or frames.get('project_id') != pid:
            raise store.StudioError('Анімація належить іншому проєкту або недоступна')
        link = {'razgon_root': str(root), 'project': str(project)}
        store.atomic_json(store.project_dir(pid) / 'razgon-link.json', link)
        store._FOUND_RAZGON.pop(pid, None)
        return link


def migrate(pid):
    with store.LOCK:
        project = store.load_project(pid)
        folder = store.project_dir(pid)
        if 'project_kind' not in project:
            try:
                settings = store.read_channel_settings(store.get_channel_folder(project['channel_id'], include_disabled=True), {}) or {}
                project['project_kind'] = 'animated' if settings.get('channel_kind') == 'animated' else 'regular'
                store.save_project(project)
            except (store.StudioError, KeyError):
                pass
        if 'plan_mode' not in project:
            try:
                defaults = store.read_channel_settings(store.get_channel_folder(project['channel_id'], include_disabled=True), {}) or {}
                project['plan_mode'] = 'direct' if defaults.get('plan_mode') == 'direct' else 'director'
                store.save_project(project)
            except (store.StudioError, KeyError):
                pass
        if not project.get('episode_path'):
            return []
        episode = Path(project['episode_path'])
        legacy = [episode / name for name in LEGACY_NAMES if (episode / name).is_file()]
        # Parse every source before making any changes. Invalid files stay where they are.
        values = {path.name: store.read_json(path) for path in legacy}
        target = folder / 'imported-plan.json'
        source = project.get('plan_source')
        active = Path(source).resolve() if source else None
        if active and active != target.resolve():
            # Missing legacy paths can recover from an already kept internal copy.
            if active.is_file():
                if not (store.under(active, folder) or store.under(active, episode)):
                    raise store.StudioError('Файл плану недоступний')
                plan = store.validate_plan(store.read_json(active))
                if target.is_file():
                    history = folder / 'plan-history' / (str(time.time_ns()) + '.json')
                    history.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, history)
                store.atomic_json(target, plan)
            elif not target.is_file():
                raise store.StudioError('Файл плану не знайдено')
            project['plan_source'] = str(target)
            store.save_project(project)
        if project.get('plan_source') and target.is_file():
            plan = store.read_json(target)
            if isinstance(plan.get('report'), dict) and plan['report'].get('json') != str(target):
                plan['report']['json'] = str(target)
                store.atomic_json(target, plan)
        link = store.razgon_link(project)
        if link and store.read_json(folder / 'razgon-link.json') != link:
            store.atomic_json(folder / 'razgon-link.json', link)
        request = project.get('production_request') or values.get('Запит на створення.json', 'Таймінги озвучки.json')
        if request and store.read_json(folder / 'production-request.json') != request:
            store.atomic_json(folder / 'production-request.json', request)
        backup = folder / 'technical-history' / str(time.time_ns())
        moved = []
        for path in legacy:
            backup.mkdir(parents=True, exist_ok=True)
            # Copy and verify before removing the user-facing duplicate, even across volumes.
            saved = backup / path.name
            shutil.copy2(path, saved)
            if saved.read_bytes() != path.read_bytes():
                raise OSError('Не вдалося перевірити резервну копію ' + path.name)
            path.unlink()
            moved.append(str(path))
        return moved


def migrate_all():
    result = {}
    if not store.PROJECTS_ROOT.is_dir():
        return result
    for folder in store.PROJECTS_ROOT.iterdir():
        metadata = folder / 'project.json'
        if metadata.is_file() and not store.read_json(metadata).get('deleted_at'):
            try:
                result[folder.name] = migrate(folder.name)
            except (OSError, ValueError, store.StudioError) as error:
                result[folder.name] = {'error': str(error)}
    return result
