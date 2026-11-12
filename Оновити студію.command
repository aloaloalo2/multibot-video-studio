#!/bin/zsh
# One-time recovery for an older updater. Normal future updates use the Studio button.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
repair_folder="${0:A:h}"
if [[ ! -f "$repair_folder/backend/app.py" || ! -e "$repair_folder/.git" ]]; then
  repair_folder=$(/usr/bin/osascript -e 'POSIX path of (choose folder with prompt "Виберіть папку VideoKey Studio")') || exit 0
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
    raise SystemExit('Оберіть папку самої студії, у якій є backend та frontend.')

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
    raise SystemExit('Ця папка підключена до іншого репозиторію. Файли залишено без змін.')

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
