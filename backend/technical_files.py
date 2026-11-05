"""Keep service metadata in Studio storage; archive old episode copies losslessly."""
from pathlib import Path
import shutil
import time
import store

LEGACY_NAMES = ('razgon.json', 'План видео.json', 'Запит на створення.json', 'Таймінги озвучки.json')


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
