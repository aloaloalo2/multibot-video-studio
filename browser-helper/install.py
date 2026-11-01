#!/usr/bin/python3
"""Let the Multi Bot extension start VideoKey Studio: registers host/videokey_host.py as the native messaging host
«com.videokey.studio» in every Chrome-based browser on this Mac, for the Multi Bot extension only.

Multi Bot is loaded unpacked, so its id comes from its folder; it is read from each browser profile's Preferences
(an extension named «Multi Bot»). Run «Встановити.command» once, and again after Multi Bot is loaded from another folder.
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOST = HERE / "host" / "videokey_host.py"
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


def main() -> int:
    os.chmod(HOST, 0o755)
    done = []
    for name in BROWSERS:
        base = SUPPORT / name
        if not base.is_dir():
            continue
        ids = extension_ids(base)
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
