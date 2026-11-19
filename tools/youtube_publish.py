#!/usr/bin/env python3
"""Everything a Claude session needs to publish one episode on YouTube, in one command (docs/YOUTUBE_PUBLISH.md).

User, 19 November 2026: «опублікувати ролик на YouTube… назву YouTube канала. Одразу йдуть там метаданні… щоб просто
була функція опублікувати ролик». The first upload (Космос PRO, «Может ли тайна черных дыр…», scheduled for 24 November
15:00) found the way: the built-in browser has no file picker, so the files are served from 127.0.0.1 with CORS and put
into YouTube Studio's file inputs by a script.

    python3 tools/youtube_publish.py wait                 # waits for the card's «Опублікувати» and prints the project id
    python3 tools/youtube_publish.py prepare P            # the export, cover and metadata; starts the local file server
    python3 tools/youtube_publish.py slot 2026-11-20      # date and time of the next video after that day («none»: none yet)
    python3 tools/youtube_publish.py step P "що зроблено"   # marks a step; quiet for 15 min = «зупинилась» on the card
    python3 tools/youtube_publish.py failed P "причина"     # the card reads «Публікація зупинилась» with «Продовжити»
    python3 tools/youtube_publish.py stop                 # stops the file server
    python3 tools/youtube_publish.py channel P UC…        # remembers the YouTube channel id of P's studio channel
    python3 tools/youtube_publish.py done P VIDEO_ID "2026-11-24 15:00"   # records the publication in the studio
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import studio  # noqa: E402  (call, find_project, Failure)

ROOT = HERE.parent
DATA = ROOT / "backend" / "data"
CHANNELS = DATA / "youtube-channels.json"
SERVE = DATA / "youtube-publish"
PORT = 8899
# channels found by hand before the studio kept them (19 November 2026)
KNOWN = {"2ddc1e61e4d6108e": {"youtube_id": "UCVdKfrFahdlMz5BomHnfzOA", "name": "Космос PRO", "playlist": "Космос"}}

SERVER = """import http.server, os, sys
os.chdir(sys.argv[1])
class H(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()
    def do_OPTIONS(self):
        self.send_response(204); self.end_headers()
    def log_message(self, *a):
        pass
http.server.ThreadingHTTPServer(('127.0.0.1', int(sys.argv[2])), H).serve_forever()
"""


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def channels() -> dict:
    return {**KNOWN, **read_json(CHANNELS, {})}


def metadata(folder: Path) -> dict:
    """Titles, description and tags from the episode's «Метаданные.txt» (episode_metadata.save writes it)."""
    file = folder / "Метаданные.txt"
    if not file.is_file():
        raise studio.Failure(f"Немає файла метаданих: {file}")
    text = file.read_text(encoding="utf-8")
    parts = {}
    for name, body in re.findall(r"(?ms)^(Тайтлы[^\n]*|Описание|Теги)\n(.*?)(?=^\s*(?:Тайтлы|Описание|Теги)\b|\Z)", text):
        parts[name.split()[0]] = body.strip()
    titles = [re.sub(r"^\d+[.)]\s*", "", line).strip() for line in parts.get("Тайтлы", "").splitlines() if line.strip()]
    tags = [t.strip() for t in parts.get("Теги", "").replace("\n", ",").split(",") if t.strip()]
    if not titles or not parts.get("Описание"):
        raise studio.Failure(f"У {file.name} немає тайтлів або опису")
    return {"titles": titles, "title": titles[0], "description": parts["Описание"], "tags": tags}


def video(project: dict) -> Path:
    jobs = studio.call("GET", f"/api/projects/{project['id']}/exports").get("jobs") or []
    for job in jobs:
        path = Path(job.get("output_path") or "")
        if job.get("status") == "complete" and path.is_file():
            return path
    found = sorted(Path(project["episode_path"]).glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if found:
        return found[0]
    raise studio.Failure("У випуску ще немає готового MP4: спершу «Експорт MP4»")


def cover(project: dict) -> Path | None:
    for path in (Path(project["episode_path"]) / "Превью.png", DATA / "projects" / project["id"] / "preview" / "Превью.png"):
        if path.is_file():
            return path
    return None


def stop() -> bool:
    pid = read_json(SERVE / "server.json", {}).get("pid")
    if not pid:
        return False
    try:
        os.killpg(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    (SERVE / "server.json").unlink(missing_ok=True)
    return True


def serve(files: dict) -> str:
    stop()
    folder = SERVE / "files"
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.iterdir():
        old.unlink()
    for name, path in files.items():
        (folder / name).symlink_to(path)
    script = SERVE / "serve.py"
    script.write_text(SERVER, encoding="utf-8")
    process = subprocess.Popen([sys.executable, str(script), str(folder), str(PORT)], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    (SERVE / "server.json").write_text(json.dumps({"pid": process.pid, "started_at": time.time()}), encoding="utf-8")
    time.sleep(0.8)
    return f"http://127.0.0.1:{PORT}"


def slot(last: str, now=None) -> dict:
    """When the next video of a channel goes out: the day after the last scheduled (or, with none scheduled, the last
    published) video, but never before today; 15:00, or on today the next quarter hour at least 30 minutes ahead within
    13:00-18:00, else the next day at 15:00 (user, 19 November 2026: «якщо останній ролик був опублікований вчора… і
    нових… запланованих немає, то публікуємо… на сьогодні»)."""
    from datetime import date, datetime, timedelta
    now = now or datetime.now()
    day = now.date() if last in ("", "none") else max(date.fromisoformat(last) + timedelta(days=1), now.date())
    if day == now.date():
        soonest = now + timedelta(minutes=30)
        soonest = soonest.replace(second=0, microsecond=0) + timedelta(minutes=(15 - soonest.minute % 15) % 15)
        start = max(soonest, datetime.combine(day, datetime.min.time()).replace(hour=13))
        if start.hour < 18 or (start.hour == 18 and start.minute == 0):
            return {"date": day.isoformat(), "time": start.strftime("%H:%M")}
        day += timedelta(days=1)
    return {"date": day.isoformat(), "time": "15:00"}


QUEUE = DATA / "youtube-queue.json"   # «Опублікувати» on a card puts the episode here (backend/published.enqueue)
LISTENER = DATA / "youtube-listener.json"


def take(pid: str) -> None:
    rows = [row for row in read_json(QUEUE, []) if row.get("project") != pid]
    QUEUE.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


def wait(poll: float = 5.0) -> str:
    """Blocks until an episode waits in the queue and prints its project id: the publishing session runs this in the
    background and is woken when it ends, so waiting costs no tokens (user, 19 November 2026: «я нажав і воно почало
    працювати»)."""
    # the studio sees a live listener by this file's pid (backend/published.listener)
    LISTENER.write_text(json.dumps({"pid": os.getpid(), "at": time.time()}), encoding="utf-8")
    while True:
        rows = read_json(QUEUE, [])
        if rows:
            return rows[0]["project"]
        time.sleep(poll)


def prepare(ref: str) -> dict:
    project = studio.find_project(ref)
    folder = Path(project["episode_path"])
    data = metadata(folder)
    mp4, png = video(project), cover(project)
    # names unique to the episode and the cover's version: a browser never hands Studio another episode's cached cover
    # (19 November 2026: Titan's upload first got the black-hole film's cover from the cache)
    video_name = f"video-{project['id']}.mp4"
    cover_name = f"cover-{project['id']}-{int(png.stat().st_mtime)}.png" if png else None
    base = serve({video_name: mp4, **({cover_name: png} if png else {})})
    (DATA / "projects" / project["id"] / "publishing.json").write_text(json.dumps({"at": time.time()}), encoding="utf-8")
    take(project["id"])   # off the queue: the card now reads «Публікація»
    channel = channels().get(project["channel_id"], {})
    return {"project": project["id"], "studio_channel": project["channel"].get("name"),
            "youtube_channel_id": channel.get("youtube_id"), "playlist": channel.get("playlist"),
            "video": str(mp4), "video_name": mp4.name, "video_mb": round(mp4.stat().st_size / 1e6),
            "video_url": f"{base}/{video_name}", "cover_url": f"{base}/{cover_name}" if png else None,
            "upload_script": str(HERE / "youtube_upload.js"),
            **data, "published": read_json(DATA / "projects" / project["id"] / "published.json", None)}


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if args[:1] == ["prepare"] and len(args) == 2:
            print(json.dumps(prepare(args[1]), ensure_ascii=False, indent=1))
        elif args[:1] == ["wait"]:
            print(wait())
        elif args[:1] == ["slot"] and len(args) == 2:
            print(json.dumps(slot(args[1])))
        elif args[:1] == ["queue"]:
            print(json.dumps(read_json(QUEUE, []), ensure_ascii=False))
        elif args[:1] in (["step"], ["failed"]) and len(args) == 3:
            # the session marks each step («Відео у формі», «Розклад 21.11 15:00»); a card whose session goes quiet
            # for 15 minutes or says «failed» reads «Публікація зупинилась» with «Продовжити» (backend/published.py)
            project = studio.find_project(args[1])
            file = DATA / "projects" / project["id"] / "publishing.json"
            state = {**read_json(file, {}), "updated": time.time()}
            state.setdefault("at", time.time())
            state["failed" if args[0] == "failed" else "step"] = args[2]
            file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            print("ok")
        elif args[:1] == ["stop"]:
            print("Сервер файлів зупинено" if stop() else "Сервер файлів не працював")
        elif args[:1] == ["channel"] and len(args) == 3 and re.fullmatch(r"UC[\w-]{22}", args[2]):
            project = studio.find_project(args[1])
            saved = read_json(CHANNELS, {})
            saved[project["channel_id"]] = {**saved.get(project["channel_id"], {}), "youtube_id": args[2],
                                            "name": project["channel"].get("name")}
            CHANNELS.write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"{project['channel'].get('name')}: {args[2]}")
        elif args[:1] == ["done"] and len(args) == 4:
            project = studio.find_project(args[1])
            record = {"at": time.time(), "source": "youtube_publish", "video_id": args[2], "url": f"https://youtu.be/{args[2]}",
                      "scheduled": args[3]}
            folder = DATA / "projects" / project["id"]
            (folder / "published.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            (folder / "publishing.json").unlink(missing_ok=True)
            print(json.dumps(record, ensure_ascii=False))
        else:
            print(__doc__)
            return 2
    except studio.Failure as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
