"""The release date of episodes marked published before the studio published them itself (the blue Finder tag keeps no
date), read from each channel's public YouTube feed (user, 19 November 2026: «синя галочка… але дата не стоїть…
стоїть сьогодні»). The feed (youtube.com/feeds/videos.xml?channel_id=…) is public and lists a channel's latest
videos with their publication time; an episode is matched by its title or one of its metadata titles."""
from __future__ import annotations

import re
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import store

FEED = "https://www.youtube.com/feeds/videos.xml?channel_id="
EVERY = 1800   # seconds between rounds
NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
KNOWN = {"2ddc1e61e4d6108e": "UCVdKfrFahdlMz5BomHnfzOA"}   # Космос PRO, found by hand before the studio kept ids


def fold(title: str) -> str:
    # NFC first: the feed may spell «й» as «и» and a combining breve, which the pattern below would cut off
    import unicodedata
    return re.sub(r"[^\w]+", " ", unicodedata.normalize("NFC", str(title)).casefold().replace("ё", "е")).strip()


def channel_ids() -> dict:
    saved = store.read_json(store.DATA_ROOT / "youtube-channels.json", {}) or {}
    return {**KNOWN, **{cid: row.get("youtube_id") for cid, row in saved.items() if isinstance(row, dict) and row.get("youtube_id")}}


def feed(youtube_id: str) -> dict:
    """{folded title: (video id, local 'YYYY-MM-DD HH:MM')} of the channel's latest videos."""
    request = urllib.request.Request(FEED + youtube_id, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        root = ET.fromstring(response.read(2_000_000))
    found = {}
    for entry in root.findall("a:entry", NS):
        title, video = entry.findtext("a:title", "", NS), entry.findtext("yt:videoId", "", NS)
        published = entry.findtext("a:published", "", NS)
        try:
            local = datetime.fromisoformat(published).astimezone().strftime("%Y-%m-%d %H:%M")
        except ValueError:
            continue
        found[fold(title)] = (video, local)
    return found


def titles(project: dict) -> list[str]:
    names = [project.get("name") or ""]
    file = Path(project.get("episode_path") or "") / "Метаданные.txt"
    try:
        text = file.read_text(encoding="utf-8")
        block = text.split("Описание")[0]
        names += [re.sub(r"^\d+[.)]\s*", "", line).strip() for line in block.splitlines()[1:] if line.strip()]
    except OSError:
        pass
    return [fold(name) for name in names if name.strip()]


def fill() -> int:
    """Dates for the published marks that have none; returns how many were filled."""
    ids, filled, feeds = channel_ids(), 0, {}
    for marker in store.PROJECTS_ROOT.glob("*/published.json"):
        mark = store.read_json(marker, {}) or {}
        if not mark.get("at") or mark.get("scheduled"):
            continue
        try:
            project = store.load_project(marker.parent.name)
        except store.StudioError:
            continue
        youtube = ids.get(project.get("channel_id"))
        if not youtube:
            continue
        if youtube not in feeds:
            try:
                feeds[youtube] = feed(youtube)
            except Exception:   # offline or a changed feed: try again next round
                feeds[youtube] = {}
        for name in titles(project):
            if name in feeds[youtube]:
                video, when = feeds[youtube][name]
                store.atomic_json(marker, {**mark, "video_id": video, "url": f"https://youtu.be/{video}", "scheduled": when,
                                           "date_from": "youtube-feed"})
                filled += 1
                break
    return filled


def loop() -> None:
    while True:
        try:
            fill()
        except Exception:
            pass
        time.sleep(EVERY)


def start() -> None:
    threading.Thread(target=loop, name="youtube-dates", daemon=True).start()
