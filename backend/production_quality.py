"""Read cached visual review and check changed native labels before declaring a run done."""
import json
import subprocess
import sys

import frame_progress
import montage_ops
import native_animation
import store


def approved_razgon(project, numbers):
    """Read real persisted verdicts when a paused session ended between checkpoints."""
    linked = frame_progress.razgon_project(project)
    if not numbers or not linked or not (linked / 'build/review/review.json').is_file():
        return set()
    root = store.YOUTUBE_ROOT / store.razgon_rel()
    try:
        result = subprocess.run([sys.executable,str(root/'tools/frame_review.py'),'--project',str(linked),
                                 'status','--frames',','.join(map(str,sorted(numbers))),'--json'],
                                cwd=root,capture_output=True,text=True,timeout=30)
        if result.returncode not in (0,1):
            return set()
        return set(json.loads(result.stdout)['approved']).intersection(numbers)
    except (subprocess.TimeoutExpired, OSError, TypeError, ValueError, KeyError):
        return set()


def check(project, request):
    try:
        return _check(project, request)
    except (OSError, ValueError, TypeError, KeyError, store.StudioError) as error:
        # Recovery and project-list reads must survive malformed saved layer data.
        return {'passed': False, 'frames': [], 'errors': ['Не вдалося перевірити кадри: ' + str(error)[:400]]}


def _check(project, request):
    plan = store.load_project_plan(project['id']) or {}
    wanted = set(request['review_frames'] if 'review_frames' in request else
                 request.get('repair_frames') or range(1, int(request['frames']) + 1))
    frames = [f for f in plan.get('frames', []) if f['number'] in wanted]
    missing = wanted - {f['number'] for f in frames}
    errors = ['Кадри відсутні у плані: ' + ', '.join(map(str, sorted(missing)))] if missing else []
    native = {f['number'] for f in frames if f.get('format') == 'animation'}
    if native:
        fps = int(project.get('fps') or 25)
        groups = montage_ops.frame_groups(project, plan)
        absent = native - {f['number'] for f in groups}
        if absent:
            errors.append('Не знайдено шарів анімації кадрів: ' + ', '.join(map(str, sorted(absent))))
        for frame in groups:
            if frame['number'] not in native:
                continue
            for clip in frame['clips']:
                if clip.get('kind') == 'text' or clip.get('content_type') == 'text':
                    try:
                        native_animation.validate_label(clip, project, frame['number'], fps)
                    except store.StudioError as error:
                        errors.append(str(error))
    required = set(request.get('native_review_frames') or [])
    native_visuals = [f for f in frames if f['number'] in required and f.get('format') != 'razgon_2d']
    if native_visuals:
        import native_review
        pending = native_review.missing(project, native_visuals)
        if pending:
            errors.append('Потрібен огляд готової композиції кадрів Studio: ' + ', '.join(map(str,pending)))
    razgon_numbers = sorted(f['number'] for f in frames if f.get('format') == 'razgon_2d')
    if razgon_numbers:
        root = store.YOUTUBE_ROOT / store.razgon_rel()
        linked = frame_progress.razgon_project(project)
        if linked is None:
            errors.append('Не знайдено сцени Razgon для перевірки.')
        else:
            try:
                result = subprocess.run([sys.executable, str(root / 'tools/frame_review.py'), '--project', str(linked),
                    'status', '--frames', ','.join(map(str, razgon_numbers))], cwd=root,
                    capture_output=True, text=True, timeout=30)
                if result.returncode:
                    errors.append('Перевірка кадрів Razgon не підтверджена: ' + (result.stdout + result.stderr).strip()[-1200:])
            except (OSError, subprocess.TimeoutExpired) as error:
                errors.append('Не вдалося прочитати перевірку кадрів Razgon: ' + str(error)[:200])
    return {'passed': not errors, 'frames': sorted(wanted), 'errors': errors,
            'native_labels': len(native), 'visual_review': razgon_numbers}


INSTRUCTIONS = """
Після монтажу партії Studio звірить схвалення і наявність кадрів локально. Для зафіксованого дефекту
відкрий новий аркуш змінених кадрів. Технічний status запускає сама студія.
"""
