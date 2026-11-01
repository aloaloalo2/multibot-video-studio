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
    # where the README installs it (~/flow-bot/heygen-grabber), should no profile say so
    for manifest in [*(Path.home() / "flow-bot").glob("manifest.json"), *(Path.home() / "flow-bot").glob("*/manifest.json")]:
        try:
            if json.loads(manifest.read_text(encoding="utf-8")).get("name") == NAME:
                return manifest.parent
        except (OSError, ValueError):
            continue
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
              "helper": helper_installed(), "item": has_item(folder)}
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


def install_helper(folder: Path | None = None) -> None:
    run = subprocess.run([sys.executable, str(HELPER), *([str(folder)] if folder else [])], capture_output=True, text=True, timeout=60)
    if run.returncode:
        raise store.StudioError((run.stdout + run.stderr).strip() or "Помічник кнопки не налаштувався", 409)


def update() -> dict:
    """Bring the folder up to its GitHub branch and set up the helper; refuses over the folder's own changes."""
    current = state()
    if not current["found"]:
        raise store.StudioError("Не знайшов Multi Bot у Chrome. Додайте його на сторінці chrome://extensions", 404)
    folder = Path(current["path"])
    if current.get("git") and current.get("dirty"):
        # the author's own unsaved work stays as it is: no update over it, no commit of it; the item is only written
        # into the same files on top of it (user, 1 November 2026: the folder held unsaved YouTube Studio changes)
        if not has_item(folder):
            add_item(folder, in_git=False)
        install_helper(folder)   # also when an earlier click put the item in and stopped at the helper
        return {**state(fetch=False), "note": "Кнопку додано. У теці Multi Bot є ваші незбережені зміни, тож студія нічого "
                "не зберігала в Git: збережіть їх разом із кнопкою (попросіть Codex «закоміть і запуш зміни в flow-bot/heygen-grabber»)."}
    if current.get("git"):
        if current.get("ahead"):
            raise store.StudioError("У папці Multi Bot є коміти, яких немає на GitHub. Попросіть агента їх залити", 409)
        if current.get("behind"):
            pulled = git(Path(current["path"]), "merge", "--ff-only", "@{upstream}")
            if pulled.returncode:
                raise store.StudioError("Не вдалося оновити Multi Bot: " + (pulled.stderr or pulled.stdout).strip()[-300:], 409)
    note = add_item(folder, current.get("git"))
    install_helper(folder)
    return {**state(fetch=False), **({"note": note} if note else {})}


ITEM = store.APP_ROOT / "browser-helper" / "multibot"


def has_item(folder: Path) -> bool:
    try:
        return 'id="studioOpen"' in (folder / "popup.html").read_text(encoding="utf-8")
    except OSError:
        return False


def add_item(folder: Path, in_git: bool) -> str | None:
    """Put the «VideoKey Studio» item into this Multi Bot (user, 1 November 2026: the private version has its own
    features, so the item goes in on top of them, not as a switch to the public one): the item's style, markup and
    script from browser-helper/multibot, the nativeMessaging permission, the version one step up. Then a commit in the
    folder's Git and a push to its GitHub, when it has one. Nothing happens to a Multi Bot that has the item."""
    if has_item(folder):
        return None
    html_path, js_path, manifest_path = folder / "popup.html", folder / "popup.js", folder / "manifest.json"
    html = html_path.read_text(encoding="utf-8")
    script_tag = '<script src="popup.js"></script>'
    if "</style>" not in html or script_tag not in html or not js_path.is_file():
        raise store.StudioError("Ця версія Multi Bot влаштована інакше: кнопку студія вставити не змогла", 409)
    style_at = html.rindex("</style>")
    html = html[:style_at] + (ITEM / "item.css").read_text(encoding="utf-8") + html[style_at:]
    tag_at = html.rindex(script_tag)
    line_start = html.rindex("\n", 0, tag_at) + 1
    html = html[:line_start] + (ITEM / "item.html").read_text(encoding="utf-8") + html[line_start:]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    permissions = manifest.setdefault("permissions", [])
    if "nativeMessaging" not in permissions:
        permissions.append("nativeMessaging")
    parts = str(manifest.get("version") or "1.0").split(".")
    if parts[-1].isdigit():
        parts[-1] = str(int(parts[-1]) + 1)
        manifest["version"] = ".".join(parts)
    js = js_path.read_text(encoding="utf-8").rstrip("\n") + "\n\n\n" + (ITEM / "item.js").read_text(encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    js_path.write_text(js, encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not in_git:
        return "Кнопку додано. Зміна лишилась лише на цьому Mac, у Git студія її не зберігала."
    git(folder, "add", "popup.html", "popup.js", "manifest.json")
    committed = git(folder, "-c", "user.name=VideoKey Studio", "-c", "user.email=studio@videokey.local", "commit", "-qm",
                    "VideoKey Studio item: open the studio, start it when it is closed")
    if committed.returncode:
        return "Кнопку додано, але зберегти її в Git не вдалося: " + (committed.stderr or committed.stdout).strip()[-200:]
    pushed = git(folder, "push", "-q", timeout=120)
    if pushed.returncode:
        return "Кнопку додано й збережено в Git цієї папки; на GitHub відправити не вдалося, спробуйте пізніше."
    return None
