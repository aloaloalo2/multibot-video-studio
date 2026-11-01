#!/usr/bin/python3
"""Let the Multi Bot extension start VideoKey Studio: registers host/videokey_host.py as the native messaging host
«com.videokey.studio» in every Chrome-based browser on this Mac, for the Multi Bot extension only.

Multi Bot is loaded unpacked, so its id comes from its folder's path (unpacked_id), and from each browser profile's
Preferences where they name the extension «Multi Bot». Run «Встановити.command» once, and again after Multi Bot is loaded from another folder.
"""
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "host" / "videokey_host.py"
# Chrome runs the helper from here, not from the studio's folder: macOS keeps Chrome out of protected folders such as
# Documents, where the studio may live
HOME_DIR = Path.home() / "Library" / "Application Support" / "VideoKey Studio"
HOST = HOME_DIR / "videokey_host.py"
NAME = "com.videokey.studio"
SUPPORT = Path.home() / "Library" / "Application Support"
BROWSERS = ["Google/Chrome", "Google/Chrome Beta", "Chromium", "Arc/User Data", "BraveSoftware/Brave-Browser",
            "Microsoft Edge", "Yandex/YandexBrowser"]


def extension_ids(base: Path) -> set:
    """Ids of the extensions named «Multi Bot» in every profile of one browser."""
    ids = set()
    for prefs in [*base.glob("*/Preferences"), *base.glob("*/Secure Preferences")]:
        try:
            settings = json.loads(prefs.read_text(encoding="utf-8")).get("extensions", {}).get("settings", {})
        except (OSError, ValueError):
            continue
        for ident, entry in settings.items():
            manifest = (entry or {}).get("manifest") or {}
            if manifest.get("name") == "Multi Bot":
                ids.add(ident)
    return ids


def unpacked_id(folder: Path) -> str:
    """The id Chrome gives an extension loaded unpacked from this folder: its path hashed (sha256), the first 32 hex
    digits written with the letters a to p. Preferences do not always name the extension, the path always gives it."""
    digest = hashlib.sha256(str(folder.resolve()).encode("utf-8")).hexdigest()[:32]
    return "".join(chr(ord("a") + int(char, 16)) for char in digest)


def multibot_folders(given: list) -> list:
    """Multi Bot's folders: the ones passed in (the studio passes the one it found), else ~/flow-bot and its subfolders."""
    found = [Path(item) for item in given if (Path(item) / "manifest.json").is_file()]
    if not found:
        for manifest in [*(Path.home() / "flow-bot").glob("manifest.json"), *(Path.home() / "flow-bot").glob("*/manifest.json")]:
            try:
                if json.loads(manifest.read_text(encoding="utf-8")).get("name") == "Multi Bot":
                    found.append(manifest.parent)
            except (OSError, ValueError):
                continue
    return found


def place_helper() -> None:
    HOME_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE, HOST)
    os.chmod(HOST, 0o755)
    (HOME_DIR / "config.json").write_text(json.dumps({"command": str(HERE.parent / "Запустить студию.command")},
                                                     ensure_ascii=False), encoding="utf-8")


def main() -> int:
    place_helper()
    from_path = {unpacked_id(folder) for folder in multibot_folders(sys.argv[1:])}
    done = []
    for name in BROWSERS:
        base = SUPPORT / name
        if not base.is_dir():
            continue
        ids = extension_ids(base) | from_path
        if not ids:
            continue
        folder = base / "NativeMessagingHosts"
        folder.mkdir(exist_ok=True)
        manifest = {"name": NAME, "description": "Starts VideoKey Studio", "path": str(HOST), "type": "stdio",
                    "allowed_origins": [f"chrome-extension://{ident}/" for ident in sorted(ids)]}
        (folder / f"{NAME}.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        done.append(name.split("/")[-1] if name != "Arc/User Data" else "Arc")
    if not done:
        print("Не знайшов розширення Multi Bot у браузері. Додайте його в Chrome (chrome://extensions) і запустіть це ще раз.")
        return 1
    print("Готово: кнопка VideoKey Studio у Multi Bot тепер може запускати студію (" + ", ".join(done) + ").")
    print("Оновіть Multi Bot на сторінці chrome://extensions (стрілка-кружечок), щоб він побачив нову кнопку.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
