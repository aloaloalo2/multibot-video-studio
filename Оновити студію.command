#!/bin/zsh
# One-time recovery for an older updater. Normal future updates use the Studio button.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
echo 'Знаходимо студію…'
repair_folder=$(/usr/bin/python3 - "${0:A:h}" <<'FIND_STUDIO'
import json
import pathlib
import subprocess
import sys

OFFICIAL = {'https://github.com/aloaloalo2/multibot-video-studio',
            'git@github.com:aloaloalo2/multibot-video-studio'}

def capture(arguments):
    try:
        result = subprocess.run(arguments, capture_output=True, timeout=4)
        return result.stdout.decode('utf-8', 'replace') if result.returncode == 0 else ''
    except (OSError, subprocess.TimeoutExpired):
        return ''

def official_root(path):
    try:
        root = pathlib.Path(path).expanduser().resolve()
        if not (root / '.git').exists() or not (root / 'backend/app.py').is_file():
            return None
        origin = capture(['git', '-C', str(root), 'remote', 'get-url', 'origin']).strip().removesuffix('.git')
        return root if origin in OFFICIAL else None
    except (OSError, ValueError, TypeError):
        return None

def running_root():
    roots = set()
    for pid in set(capture(['lsof', '-tiTCP:8770', '-sTCP:LISTEN']).split()):
        if not pid.isdigit():
            continue
        for line in capture(['lsof', '-a', '-p', pid, '-d', 'cwd', '-Fn']).splitlines():
            if line.startswith('n'):
                root = official_root(line[1:])
                if root:
                    roots.add(root)
    if len(roots) > 1:
        raise SystemExit('Відкрийте одну потрібну студію та повторіть запуск оновлення.')
    return next(iter(roots), None)

def find_root(beside):
    active = running_root()
    if active:
        return active
    home = pathlib.Path.home()
    try:
        config = json.loads((home / 'Library/Application Support/VideoKey Studio/config.json').read_text(encoding='utf-8'))
        registered = official_root(pathlib.Path(config['command']).parent)
        if registered:
            return registered
    except (OSError, ValueError, KeyError, TypeError):
        pass
    adjacent = official_root(beside)
    if adjacent:
        return adjacent
    names = ('VideoKey Studio', 'MultiBot Video Studio', 'multibot-video-studio', 'multibot-video-studio-main')
    bases = (home / 'Applications', home / 'Documents', home / 'Desktop', home / 'Downloads', home / 'Documents/YOUTUBE')
    candidates = {base / name for base in bases for name in names}
    indexed = capture(['mdfind', '-onlyin', str(home), 'kMDItemFSName == "Запустить студию.command"'])
    candidates.update(pathlib.Path(item).parent for item in indexed.splitlines()[:100] if item)
    found = {root for path in candidates if (root := official_root(path))}
    if len(found) == 1:
        return found.pop()
    if found:
        raise SystemExit('Знайдено кілька копій. Відкрийте потрібну студію як завжди та повторіть запуск оновлення.')
    raise SystemExit('Спочатку відкрийте студію звичайним способом, потім запустіть цей файл ще раз.')

if __name__ == '__main__':
    print(find_root(sys.argv[1]))
FIND_STUDIO
)
if [[ $? != 0 || -z "$repair_folder" ]]; then
  read -r '?Натисніть Enter, щоб закрити це вікно.'
  exit 1
fi
repair_python='/usr/bin/python3'
[[ -x "$repair_folder/.venv/bin/python3" ]] && repair_python="$repair_folder/.venv/bin/python3"
"$repair_python" - "$repair_folder" <<'PY'
import os
import pathlib
import subprocess
import sys
import tempfile

root = pathlib.Path(sys.argv[1]).resolve()
if not (root / 'backend/app.py').is_file() or not (root / '.git').exists():
    raise SystemExit('Відкрийте студію звичайним способом і запустіть цей файл ще раз.')

def git(*arguments):
    try:
        result = subprocess.run(['git', *arguments], cwd=root, capture_output=True, timeout=60,
                                env={**os.environ, 'GIT_TERMINAL_PROMPT':'0', 'GCM_INTERACTIVE':'never'})
    except (OSError, subprocess.TimeoutExpired):
        raise SystemExit('Не вдалося отримати оновлення. Перевірте доступ до GitHub.')
    if result.returncode:
        raise SystemExit('Не вдалося отримати нову версію. Перевірте доступ до GitHub.')
    return result.stdout

origin = git('remote', 'get-url', 'origin').decode().strip().removesuffix('.git')
if origin not in {'https://github.com/aloaloalo2/multibot-video-studio',
                  'git@github.com:aloaloalo2/multibot-video-studio'}:
    raise SystemExit('Ця копія підключена до іншого репозиторію. Файли залишено без змін.')

print('Завантажуємо новий механізм оновлення…', flush=True)
git('fetch', '--quiet', '--no-tags', 'origin')
revision = git('rev-parse', 'origin/main').decode().strip()
with tempfile.TemporaryDirectory(prefix='videokey-update-') as temporary:
    folder = pathlib.Path(temporary)
    for source in ('backend/updater.py', 'backend/update_backup.py', 'tools/studio_restart.py'):
        (folder / pathlib.Path(source).name).write_bytes(git('show', revision + ':' + source))
    sys.path.insert(0, str(folder))
    from updater import Updater
    manager = Updater(root)
    state = manager._inspect()
    if state['status'] == 'current':
        print('Остання версія вже встановлена.')
        raise SystemExit(subprocess.run([sys.executable, str(root / 'tools/studio_restart.py')]).returncode)
    if state['status'] not in {'available', 'update_failed'}:
        raise SystemExit('Оновлення зачіпає особисті дані. Усі файли залишено на місці.')
    # The trusted restart tool checks all jobs, owns the mutation gate, and verifies this exact installation.
    stopped = subprocess.run([sys.executable, str(folder / 'studio_restart.py'), '--root', str(root), '--stop-only'])
    if stopped.returncode:
        raise SystemExit('Оновлення ще не почалося. Повторіть запуск після завершення поточних задач.')
    problem = None
    try:
        manager.apply()
        print('Оновлення встановлено. Резервна копія:', manager.state.get('backup', ''), flush=True)
    except Exception as error:
        problem = error
        print(str(error), flush=True)
        if manager.state.get('backup'):
            print('Резервна копія:', manager.state['backup'], flush=True)
    finally:
        started = subprocess.run([sys.executable, str(root / 'tools/studio_restart.py')])
    if started.returncode:
        raise SystemExit('Не вдалося запустити студію. Резервні копії збережено.')
    if problem:
        raise SystemExit(1)
    print('Готово. Надалі оновлюйте студію звичайною кнопкою «Оновити студію».')
PY
repair_result=$?
echo
if [[ "$repair_result" == 0 ]]; then
  /usr/bin/open 'http://127.0.0.1:8770/'
fi
read -r '?Натисніть Enter, щоб закрити це вікно.'
exit "$repair_result"
