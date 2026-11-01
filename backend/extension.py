"""The Multi Bot browser extension on this Mac, kept up to date from the studio's settings (user, 1 November 2026: «через
студію… нажав, і воно саме знайшло мою папку… і докинуло цю штуку»).

Multi Bot is loaded unpacked, so Chrome remembers its folder: `find` reads it from the Chrome-based browsers' profile
Preferences (the extension named «Multi Bot»). `state` says where it is, its version, whether GitHub has a newer one
and whether the folder holds changes of its own. `update` takes the newer version as a fast-forward of the folder's own
Git branch (never over local changes, never a merge), then sets up the helper that lets its «VideoKey Studio» button
start the studio (browser-helper/install.py). Chrome itself reloads the extension only by hand, at chrome://extensions.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import store

SUPPORT = Path.home() / "Library" / "Application Support"
BROWSERS = ["Google/Chrome", "Google/Chrome Beta", "Chromium", "Arc/User Data", "BraveSoftware/Brave-Browser",
            "Microsoft Edge", "Yandex/YandexBrowser"]
NAME = "Multi Bot"
HELPER = store.APP_ROOT / "browser-helper" / "install.py"


def find() -> Path | None:
    """The folder Multi Bot is loaded from, from any browser profile that has it."""
    for browser in BROWSERS:
        base = SUPPORT / browser
        for prefs in [*base.glob("*/Preferences"), *base.glob("*/Secure Preferences")]:
            try:
                settings = json.loads(prefs.read_text(encoding="utf-8")).get("extensions", {}).get("settings", {})
            except (OSError, ValueError):
                continue
            for entry in settings.values():
                entry = entry or {}
                path = Path(str(entry.get("path") or ""))
                if (entry.get("manifest") or {}).get("name") == NAME and path.is_absolute() and (path / "manifest.json").is_file():
                    return path
    return None


def git(folder: Path, *args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True, timeout=timeout)


def version(folder: Path) -> str | None:
    try:
        return json.loads((folder / "manifest.json").read_text(encoding="utf-8")).get("version")
    except (OSError, ValueError):
        return None


def state(fetch: bool = True) -> dict:
    folder = find()
    if not folder:
        return {"found": False}
    result = {"found": True, "path": str(folder), "version": version(folder), "git": (folder / ".git").exists(),
              "helper": helper_installed()}
    if not result["git"]:
        return result
    try:
        if fetch:
            git(folder, "fetch", "--quiet", timeout=60)
        dirty = [line[3:] for line in git(folder, "status", "--porcelain").stdout.splitlines() if line.strip()]
        behind = git(folder, "rev-list", "--count", "HEAD..@{upstream}").stdout.strip()
        ahead = git(folder, "rev-list", "--count", "@{upstream}..HEAD").stdout.strip()
        result.update(dirty=dirty[:8], behind=int(behind or 0), ahead=int(ahead or 0))
    except (OSError, subprocess.SubprocessError, ValueError):
        result["error"] = "Не вдалося перевірити оновлення розширення"
    return result


def helper_installed() -> bool:
    return any((SUPPORT / browser / "NativeMessagingHosts" / "com.videokey.studio.json").is_file() for browser in BROWSERS)


def install_helper() -> None:
    run = subprocess.run([sys.executable, str(HELPER)], capture_output=True, text=True, timeout=60)
    if run.returncode:
        raise store.StudioError((run.stdout + run.stderr).strip() or "Помічник кнопки не налаштувався", 409)


def update() -> dict:
    """Bring the folder up to its GitHub branch and set up the helper; refuses over the folder's own changes."""
    current = state()
    if not current["found"]:
        raise store.StudioError("Не знайшов Multi Bot у Chrome. Додайте його на сторінці chrome://extensions", 404)
    if current.get("git"):
        if current.get("dirty"):
            raise store.StudioError("У папці Multi Bot є власні зміни: " + ", ".join(current["dirty"])
                                    + ". Студія не стане їх затирати; попросіть агента зберегти їх у Git", 409)
        if current.get("ahead"):
            raise store.StudioError("У папці Multi Bot є коміти, яких немає на GitHub. Попросіть агента їх залити", 409)
        if current.get("behind"):
            pulled = git(Path(current["path"]), "merge", "--ff-only", "@{upstream}")
            if pulled.returncode:
                raise store.StudioError("Не вдалося оновити Multi Bot: " + (pulled.stderr or pulled.stdout).strip()[-300:], 409)
    install_helper()
    return state(fetch=False)
