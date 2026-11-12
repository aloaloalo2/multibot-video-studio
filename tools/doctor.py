#!/usr/bin/env python3
"""Check that this Mac has everything VideoKey Studio needs, and say in plain words what is missing.

    python3 tools/doctor.py            # a line per check: ✓ fine, ✗ missing (with what to do), · optional
    python3 tools/doctor.py --install  # also puts in what can be put in without the author: Python packages,
                                       # the speech model, the Razgon studio's packages

Run it on a new Mac after cloning, or when a new version cannot start.
"""
from __future__ import annotations

import argparse
import importlib.util
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "tools")]

APPLE_ = sys.platform == "darwin" and platform.machine() == "arm64"
# huggingface_hub fetches the speech model for the Mac's GPU; reportlab only draws the plan as a PDF
PACKAGES = [("PIL", "Pillow", True), ("numpy", "numpy", True), ("huggingface_hub", "huggingface_hub", APPLE_),
            ("reportlab", "reportlab", False), ("websockets", "websockets", True), ("langid", "langid==1.1.6", True),
            ("text_to_num", "text2num==3.1.0", True)]
APPLE = sys.platform == "darwin" and platform.machine() == "arm64"
CODEX = Path("/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex")


class Report:
    def __init__(self):
        self.missing = 0

    def line(self, ok, what, fix="", needed=True):
        mark = "✓" if ok else ("✗" if needed else "·")
        print(f" {mark} {what}" + ("" if ok or not fix else f"\n     → {fix}"))
        if not ok and needed:
            self.missing += 1


def run(command, **kw):
    return subprocess.run(command, capture_output=True, text=True, **kw)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--install", action="store_true", help="встановити те, чого бракує і що можна поставити без автора")
    args = parser.parse_args(argv)
    report = Report()
    print("Студія:", ROOT)

    print("\nPython і пакети")
    report.line(sys.version_info >= (3, 9), f"Python {platform.python_version()}", "потрібен Python 3.9 або новіший")
    absent = [pip for module, pip, _ in PACKAGES if importlib.util.find_spec(module) is None]
    speech = "mlx_whisper" if APPLE else "faster_whisper"
    if importlib.util.find_spec(speech) is None:
        absent.append("mlx-whisper" if APPLE else "faster-whisper")
    if absent and args.install:
        run([sys.executable, "-m", "pip", "install", "--user", "-r", str(ROOT / "requirements.txt")], timeout=1800)
        absent = [name for name in absent if importlib.util.find_spec(name.split("==")[0].replace("-", "_").replace("Pillow", "PIL")) is None]
    for module, pip, needed in PACKAGES + [(speech, speech.replace("_", "-"), True)]:
        ok = pip not in absent and importlib.util.find_spec(module) is not None
        report.line(ok, pip, f"{sys.executable} -m pip install --user {pip}", needed)

    print("\nПрограми")
    for name, why, fix in (("ffmpeg", "відео й звук", "brew install ffmpeg"), ("ffprobe", "тривалість медіа", "brew install ffmpeg"),
                           ("git", "оновлення студії", "xcode-select --install"),
                           ("node", "2D-анімація Razgon", "brew install node")):
        report.line(bool(shutil.which(name)), f"{name} ({why})", fix)

    print("\nРозпізнавання озвучки")
    try:
        import speech as speech_module
        model = speech_module.mlx_model_path() if APPLE else None
        if APPLE and not model and args.install and importlib.util.find_spec("huggingface_hub"):
            from huggingface_hub import snapshot_download
            snapshot_download(speech_module.MLX_REPOS[speech_module.MODEL_NAME])
            model = speech_module.mlx_model_path()
        if APPLE:
            report.line(bool(model), f"модель Whisper «{speech_module.MODEL_NAME}» для відеокарти Mac",
                        "python3 tools/doctor.py --install завантажить її (близько 500 МБ)")
        else:
            report.line(True, "Whisper на процесорі (не Mac з Apple Silicon: розпізнавання повільніше)", needed=False)
    except Exception as error:   # the speech module itself needs the packages above
        report.line(False, "модуль розпізнавання", str(error)[:200])

    print("\nАгенти")
    try:
        import director
        director.executable()
        report.line(True, "Claude Code (режисер і агент кадрів)")
    except Exception:
        report.line(False, "Claude Code (режисер і агент кадрів)", "встановіть застосунок Claude і увійдіть у свою підписку")
    report.line(CODEX.is_file(), "Codex у застосунку ChatGPT (картинки для кадрів)",
                "встановіть застосунок ChatGPT для Mac і увійдіть у свою підписку", needed=False)
    if sys.platform == "darwin":
        key = run(["security", "find-generic-password", "-s", "pixabay-youtube-api"]).returncode == 0
        report.line(key, "ключ Pixabay у Зв'язці ключів (стокові фото й відео)",
                    "отримайте ключ на pixabay.com/api/docs і збережіть його кнопкою «Пошук Pixabay.command»", needed=False)

    print("\n2D-анімація Razgon")
    try:
        import razgon_sync
        copies = razgon_sync.copies()
    except Exception:
        copies = []
    if not copies:
        report.line(False, "Razgon-студія ще не встановлена", "її поставить Claude під час першої анімації", needed=False)
    for copy in copies:
        modules = (copy / "node_modules").is_dir()
        if not modules and args.install and shutil.which("npm"):
            run(["npm", "install", "--no-audit", "--no-fund"], cwd=copy, timeout=1800)
            modules = (copy / "node_modules").is_dir()
        report.line(modules, f"{copy.parent.name}/{copy.name}: пакети Node", f'cd "{copy}" && npm install')

    print("\nОновлення")
    try:
        import updater
        manager = updater.Updater(ROOT)
        state = manager.refresh()
        words = {"current": "остання версія", "available": "є нова версія: натисніть «Оновити студію»",
                 "offline": "GitHub зараз недоступний", "not_configured": "папка не прив'язана до GitHub",
                 "local_changes": "у папці студії є змінені файли", "diverged": "є свої зміни, яких немає на GitHub",
                 "other_branch": f"папка стоїть на гілці «{state.get('branch')}», а не на main",
                 "unsafe_update": "оновлення зачіпає особисті дані або ключі", "update_failed": "нова версія не запустилася на цьому Mac"}
        good = state["status"] in {"current", "available", "offline"}
        report.line(good, f"оновлення з GitHub: {words.get(state['status'], state['status'])}",
                    "перевірте технічну причину; локальні правки коду зберігаються автоматично")
    except Exception as error:
        report.line(False, "оновлення з GitHub", str(error)[:200])

    print("\nПеревірка запуску")
    started = run([sys.executable, "-c", 'import sys; sys.path[:0] = ["backend", "engine"]; import app'], cwd=ROOT, timeout=120)
    report.line(started.returncode == 0, "сервер студії завантажується", started.stderr.strip()[-300:])

    print("\n" + ("Усе готово до роботи." if not report.missing else
                  f"Бракує: {report.missing}. " + ("" if args.install else "Запустіть python3 tools/doctor.py --install, а решту поставте за підказками вище.")))
    return 1 if report.missing else 0


if __name__ == "__main__":
    sys.exit(main())
