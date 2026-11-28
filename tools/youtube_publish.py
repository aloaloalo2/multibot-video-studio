#!/usr/bin/env python3
"""Everything a Claude session needs to publish one episode on YouTube, in one command (docs/YOUTUBE_PUBLISH.md).

User, 19 November 2026: «опублікувати ролик на YouTube… назву YouTube канала. Одразу йдуть там метаданні… щоб просто
була функція опублікувати ролик». The first upload (Космос PRO, «Может ли тайна черных дыр…», scheduled for 24 November
15:00) found the way: the built-in browser has no file picker, so the files are served from 127.0.0.1 with CORS and put
into YouTube Studio's file inputs by a script.

    python3 tools/youtube_publish.py wait                 # waits for the card's «Опублікувати» and prints the project id
    python3 tools/youtube_publish.py prepare P            # the export, cover and metadata; starts the local file server
    python3 tools/youtube_publish.py slot P 2026-11-20    # date and time of the next video after that day, by the channel's interval («none»: none yet)
    python3 tools/youtube_publish.py step P "що зроблено"   # marks a step; quiet for 15 min = «зупинилась» on the card
    python3 tools/youtube_publish.py failed P "причина"     # the card reads «Публікація зупинилась» with «Продовжити»
    python3 tools/youtube_publish.py monetization P ok    # monetization switched on in the form (or failed "причина")
    python3 tools/youtube_publish.py stop                 # stops the file server
    python3 tools/youtube_publish.py channel P UC…        # remembers the YouTube channel id of P's studio channel
    python3 tools/youtube_publish.py done P VIDEO_ID "2026-11-24 15:00" VK-VIDEO_ID   # after __vk.verify: records it
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
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


NO_ATTRIBUTION = ("без зазначення автора", "no attribution")


def music_credits(pid: str) -> list[str]:
    """«Title, Artist» of the music-library tracks the film's music used (backend/music_library.remember). A track whose
    licence asks for attribution is always named; one «без зазначення автора» only now and then, about every other film,
    the same choice for a film each time (user, 27 November 2026: «рандомно — якщо не треба вказувати, то можна не вказувати»)."""
    import random
    ids = read_json(DATA / "projects" / pid / "music-tracks.json", []) or []
    rows = {row.get("id"): row for row in read_json(DATA / "music-library" / "catalog.json", []) or [] if isinstance(row, dict)}
    optional = random.Random(pid).random() < 0.5
    return [f"{rows[i]['title']}, {rows[i]['artist']}" for i in ids if i in rows
            and (optional or not any(m in str(rows[i].get("license", "")).casefold() for m in NO_ATTRIBUTION))]


def with_credits(description: str, credits: list[str]) -> str:
    """The film's music named in its description, in the description's language, above its hashtags (user, 26 November
    2026: «обов'язково треба ролики позначати в описанні, яку ми музику використовували»)."""
    if not credits or any(c in description for c in credits):
        return description
    word = ("Музика" if re.search(r"[іїєґІЇЄҐ]", description) else "Музыка" if re.search(r"[а-яА-ЯёЁ]", description)
            else "Musik" if re.search(r"[äöüßÄÖÜ]", description) else "Music")
    line = f"{word}: " + "; ".join(credits) + " (YouTube Audio Library)"
    lines = description.rstrip().splitlines()
    tail = len(lines)
    while tail > 0 and lines[tail - 1].strip().startswith("#"):
        tail -= 1
    head, tags = lines[:tail], lines[tail:]
    while head and not head[-1].strip():
        head.pop()
    return "\n".join(head + ["", line] + ([""] + tags if tags else []))


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


COVER_LIMIT = 2 * 1024 * 1024   # YouTube refuses a thumbnail over 2 MB


def upload_cover(project: dict, png: Path) -> Path:
    """The cover as YouTube takes it: the file itself when it is under 2 MB, else a JPG copy squeezed under the limit in the
    studio's data (the original stays among the versions untouched)."""
    if png.stat().st_size <= COVER_LIMIT:
        return png
    from PIL import Image
    target = DATA / "projects" / project["id"] / "preview" / "cover-upload.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(png) as image:
        picture = image.convert("RGB")
        for quality in (92, 88, 84, 80, 75, 70, 60, 50):
            picture.save(target, "JPEG", quality=quality, optimize=True, progressive=True)
            if target.stat().st_size <= COVER_LIMIT:
                break
    return target


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


def interval(project: dict) -> int:
    """Days between a channel's videos, from «Публікація» in the channel's settings: 1 by default (user, 20 November
    2026: «якщо на 20 число є якийсь ролик, і там стоїть інтервал 2 дня… на 22 треба опублікувати»)."""
    value = (project.get("channel") or {}).get("settings", {}).get("publish_interval_days", 1)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 1 else 1


def slot(last: str, now=None, days: int = 1) -> dict:
    """When the next video of a channel goes out: `days` (the channel's interval) after the last scheduled (or, with none scheduled, the last
    published) video, but never before today; 15:00, or on today the next quarter hour at least 30 minutes ahead within
    13:00-18:00, after 18:00 still today at that quarter hour (user, 19 November 2026: «якщо останній ролик був опублікований вчора… і
    нових… запланованих немає, то публікуємо… на сьогодні»)."""
    from datetime import date, datetime, timedelta
    now = now or datetime.now()
    day = now.date() if last in ("", "none") else max(date.fromisoformat(last) + timedelta(days=days), now.date())
    if day == now.date():
        soonest = now + timedelta(minutes=30)
        soonest = soonest.replace(second=0, microsecond=0) + timedelta(minutes=(15 - soonest.minute % 15) % 15)
        start = max(soonest, datetime.combine(day, datetime.min.time()).replace(hour=13))
        # the quarter hour after midnight is tomorrow's 00:00, not today's (26 November 2026 at 23:25 it read «26th 00:00»,
        # a moment already gone)
        if start.date() == day and (start.hour < 18 or (start.hour == 18 and start.minute == 0)):
            return {"date": day.isoformat(), "time": start.strftime("%H:%M")}
        # past the window the video's day is still today: scheduled for the next quarter hour at least 30 minutes
        # ahead, not moved to tomorrow (user, 20 November 2026: «якщо сьогодні вже 18:00… ставити на 20 чи 30 хвилин
        # пізніше, ніж теперішній час»)
        return {"date": soonest.date().isoformat(), "time": soonest.strftime("%H:%M")}
    return {"date": day.isoformat(), "time": "15:00"}


QUEUE = DATA / "youtube-queue.json"   # «Опублікувати» on a card puts the episode here (backend/published.enqueue)
LISTENER = DATA / "youtube-listener.json"


def tag_blue(folder: str | None) -> bool:
    """Finder's blue tag on the episode folder once the video is on YouTube (user, 19 November 2026: «головне, щоб
    папка відмічалася голубим»); the folder's other tags stay. Colour 4 is blue in any system language."""
    import plistlib
    import subprocess
    if not folder or not Path(folder).is_dir():
        return False
    attr = "com.apple.metadata:_kMDItemUserTags"
    try:
        raw = subprocess.run(["xattr", "-px", attr, folder], capture_output=True, text=True, timeout=5)
        tags = plistlib.loads(bytes.fromhex(raw.stdout.replace(" ", "").replace("\n", ""))) if raw.returncode == 0 and raw.stdout.strip() else []
    except Exception:
        tags = []
    if any(str(t).endswith("\n4") for t in tags):
        return True
    data = plistlib.dumps([*tags, "Синий\n4"], fmt=plistlib.FMT_BINARY).hex()
    done = subprocess.run(["xattr", "-wx", attr, data, folder], capture_output=True, timeout=5)
    return done.returncode == 0


LOCK = DATA / "youtube-queue.lock"
CLAIM_FOR = 30 * 60   # seconds an episode stays with the session that took it from the queue before another may take it
ANOTHER = ("Інша сесія публікації вже чекає на черзі студії. Ця сесія не потрібна: не запускай wait знову і не публікуй, "
           "скажи автору одним реченням, що публікацію веде інша сесія, і завершуй.")


@contextmanager
def queue_lock():
    """One reader-writer of the queue at a time: the studio adds episodes, the waiting session takes them."""
    import fcntl
    with open(LOCK, "a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def waiting(pid: int) -> bool:
    """`pid` is a live `youtube_publish.py wait` of another session."""
    try:
        os.kill(int(pid), 0)
        command = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, timeout=5).stdout
    except (OSError, ValueError, subprocess.SubprocessError):
        return False
    return "youtube_publish.py" in command and "wait" in command


def take(pid: str) -> None:
    with queue_lock():
        rows = [row for row in read_json(QUEUE, []) if row.get("project") != pid]
        QUEUE.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


def claim() -> str | None:
    """The first episode no other session has taken, marked as this one's; None when there is none. Three sessions left
    waiting at once each woke on Andromeda and uploaded it three times (user, 26 November 2026: «чому 3 сесії
    публікують роліки?… це баг публікації»): an episode now goes to one session only."""
    with queue_lock():
        rows = read_json(QUEUE, [])
        for row in rows:
            # an episode whose project was deleted while it waited is skipped (20 November 2026)
            if not (DATA / "projects" / str(row.get("project")) / "project.json").exists():
                continue
            taken = row.get("claimed") or {}
            if taken and time.time() - float(taken.get("at") or 0) < CLAIM_FOR:
                continue
            row["claimed"] = {"pid": os.getpid(), "at": time.time()}
            QUEUE.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            return row["project"]
    return None


def wait(poll: float = 5.0) -> str:
    """Blocks until an episode waits in the queue and prints its project id: the publishing session runs this in the
    background and is woken when it ends, so waiting costs no tokens (user, 19 November 2026: «я нажав і воно почало
    працювати»). Only one session waits: a second one is told to finish."""
    with queue_lock():
        other = (read_json(LISTENER, {}) or {}).get("pid")
        if other and int(other) != os.getpid() and waiting(int(other)):
            raise studio.Failure(ANOTHER)
        # the studio sees a live listener by this file's pid (backend/published.listener)
        LISTENER.write_text(json.dumps({"pid": os.getpid(), "at": time.time()}), encoding="utf-8")
    while True:
        taken = claim()
        if taken:
            return taken
        time.sleep(poll)


def cancelled(pid: str) -> bool:
    """The author pressed «Скасувати» on the card (backend/published.cancel): the session stops this episode."""
    return bool(read_json(DATA / "projects" / pid / "publishing.json", {}).get("cancelled"))


CANCELLED = ("Автор скасував публікацію цього випуску в студії. Зупинись: не плануй і не публікуй його. Якщо відео вже "
             "завантажене, лиши його чернеткою, скажи автору й переходь до wait.")


def prepare(ref: str) -> dict:
    project = studio.find_project(ref)
    if cancelled(project["id"]) and not any(row.get("project") == project["id"] for row in read_json(QUEUE, [])):
        raise studio.Failure(CANCELLED)
    folder = Path(project["episode_path"])
    data = metadata(folder)
    data["description"] = with_credits(data["description"], music_credits(project["id"]))
    mp4, png = video(project), cover(project)
    # names unique to the episode and the cover's version: a browser never hands Studio another episode's cached cover
    # (19 November 2026: Titan's upload first got the black-hole film's cover from the cache)
    video_name = f"video-{project['id']}.mp4"
    if png:
        png = upload_cover(project, png)
    cover_name = f"cover-{project['id']}-{int(png.stat().st_mtime)}{png.suffix}" if png else None
    base = serve({video_name: mp4, **({cover_name: png} if png else {})})
    (DATA / "projects" / project["id"] / "publishing.json").write_text(json.dumps({"at": time.time()}), encoding="utf-8")
    take(project["id"])   # off the queue: the card now reads «Публікація»
    channel = channels().get(project["channel_id"], {})
    return {"project": project["id"], "studio_channel": project["channel"].get("name"),
            "youtube_channel_id": channel.get("youtube_id"), "playlist": channel.get("playlist"),
            "publish_interval_days": interval(project),
            "video": str(mp4), "video_name": mp4.name, "video_mb": round(mp4.stat().st_size / 1e6),
            "video_url": f"{base}/{video_name}", "cover_url": f"{base}/{cover_name}" if png else None,
            "upload_script": str(HERE / "youtube_upload.js"),
            **data, "published": read_json(DATA / "projects" / project["id"] / "published.json", None),
            # read with every episode: a session that lives for days keeps an older guide in mind (19 November 2026: the
            # publishing session went on saying «плейлістів немає» and «заставка не ставиться» after both were fixed)
            "must": [
                "Перед цим випуском перечитай docs/YOUTUBE_PUBLISH.md заново: порядок змінився, твоя пам'ять про нього застаріла.",
                "Публікуєш сам: клікаєш у Studio й перевіряєш кожен крок на скриншоті; скрипт лише для файлів відео й прев'ю.",
                "Перед Studio відкрий cover_url в окремій вкладці вбудованого браузера, щоб він дозволив адресу сервера "
                "файлів: інакше __vk.video і __vk.cover падають з ERR_BLOCKED_BY_CLIENT.",
                (f"Плейлист обов'язковий: вибери «{channel['playlist']}» у списку плейлистів і перевір його назву в полі."
                 if channel.get("playlist") else
                 "Плейлист обов'язковий: відкрий список плейлистів і подивись сам, не роби висновків з минулих випусків. "
                 "Один є, то вибери його; кілька, то той, що за темою; потім youtube_publish.py playlist <id> \"НАЗВА\"."),
                "Монетизація обов'язкова: у формі крок «Монетизация» → «Вкл.», далі вимоги рекламодавців: у самому низу "
                "«нічого з переліченого» (мовою Studio, останній пункт), потім кнопка праворуч угорі «Отправить оценку»; "
                "перевір на екрані, потім monetization P ok.",
                "Кінцева заставка обов'язкова: щоразу став її у формі, крок «Дополнения», до розкладу. "
                "Минулі невдачі не причина пропустити. endscreen failed лише після двох справжніх спроб у цьому випуску.",
            ]}


# $ per million tokens, as backend/spend_report.PRICE (Opus 5.5, the 1-hour cache)
PRICE = {"input": 3.0, "output": 15.0, "read": 0.30, "write_1h": 6.0, "write_5m": 3.75}
TRANSCRIPTS = Path.home() / ".claude" / "projects"


def session_cost(pid: str, start: float, end: float) -> dict | None:
    """The publishing session's Claude tokens between `prepare` and `done` of this episode, read from its transcript on
    disk (the session runs in the Claude app, not in the studio; user, 19 November 2026: «публікація теж рахується в
    розходи… і в час?»). The session is the transcript that ran `prepare <pid>`; each message counts once."""
    from datetime import datetime
    marker = f"prepare {pid}"
    for path in sorted(TRANSCRIPTS.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:40]:
        if path.stat().st_mtime < start - 60:
            continue
        seen, tokens, found = set(), {"input": 0, "output": 0, "read": 0, "write_1h": 0, "write_5m": 0}, False
        with path.open(encoding="utf-8", errors="replace") as source:
            for line in source:
                if marker in line and not found:
                    # only the session that ran `prepare` itself in its shell, within this publication's time
                    try:
                        row = json.loads(line)
                        at = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")).timestamp()
                        found = start - 120 <= at <= end and any(
                            part.get("type") == "tool_use" and part.get("name") == "Bash" and marker in str((part.get("input") or {}).get("command"))
                            for part in (row.get("message") or {}).get("content") or [] if isinstance(part, dict))
                    except (ValueError, KeyError, TypeError, AttributeError):
                        pass
                if '"usage"' not in line:
                    continue
                try:
                    row = json.loads(line)
                    at = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")).timestamp()
                except (ValueError, KeyError):
                    continue
                message = row.get("message") or {}
                usage = message.get("usage")
                if row.get("type") != "assistant" or not isinstance(usage, dict) or not start - 5 <= at <= end + 5:
                    continue
                key = message.get("id") or row.get("uuid")
                if key in seen:
                    continue
                seen.add(key)
                cache = usage.get("cache_creation") or {}
                tokens["input"] += usage.get("input_tokens") or 0
                tokens["output"] += usage.get("output_tokens") or 0
                tokens["read"] += usage.get("cache_read_input_tokens") or 0
                tokens["write_1h"] += cache.get("ephemeral_1h_input_tokens") or 0
                tokens["write_5m"] += cache.get("ephemeral_5m_input_tokens") or (
                    0 if cache else usage.get("cache_creation_input_tokens") or 0)
        if found and seen:
            usd = sum(tokens[k] * PRICE[k] for k in PRICE) / 1e6
            return {"usd": round(usd, 4), "tokens": tokens, "turns": len(seen), "transcript": path.name}
    return None


def record(pid: str, status: str) -> dict:
    """The publication's run in «Час роботи» (backend/job_timing format) and its Claude cost in the episode's costs."""
    import uuid
    folder = DATA / "projects" / pid
    state = read_json(folder / "publishing.json", {})
    start, end = float(state.get("at") or time.time()), time.time()
    run = uuid.uuid4().hex
    row = {"version": 1, "id": run, "project_id": pid, "workflow": "publication", "job_id": None,
           "status": "complete" if status == "done" else "failed", "language": None, "started_at": start,
           "finished_at": end, "elapsed_ms": round((end - start) * 1000, 2), "active_stage": None,
           "stages": {"service": {"ms": round((end - start) * 1000, 2), "calls": 1}}}
    (folder / "performance").mkdir(exist_ok=True)
    (folder / "performance" / f"{int(start * 1e9):020d}-{run}.json").write_text(json.dumps(row), encoding="utf-8")
    cost = session_cost(pid, start, end)
    if cost:
        costs = folder / "project-costs.json"
        data = read_json(costs, {})
        data.setdefault("events", {})[f"claude_code:publication-{run}"] = {
            "provider": "claude_code", "amount": cost["usd"], "estimated": True, "category": "publication",
            "workflow": "publication", "run_id": run, "tokens": cost["tokens"]}
        costs.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return {"minutes": round((end - start) / 60, 1), "cost": cost}


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if args[:1] == ["prepare"] and len(args) == 2:
            print(json.dumps(prepare(args[1]), ensure_ascii=False, indent=1))
        elif args[:1] == ["wait"]:
            print(wait())
        elif args[:1] == ["slot"] and len(args) == 2:
            print(json.dumps(slot(args[1])))
        elif args[:1] == ["slot"] and len(args) == 3:
            # slot P DATE: the channel's own interval between videos
            print(json.dumps(slot(args[2], days=interval(studio.find_project(args[1])))))
        elif args[:1] == ["queue"]:
            print(json.dumps(read_json(QUEUE, []), ensure_ascii=False))
        elif args[:1] in (["step"], ["failed"]) and len(args) == 3:
            # the session marks each step («Відео у формі», «Розклад 21.11 15:00»); a card whose session goes quiet
            # for 15 minutes or says «failed» reads «Публікація зупинилась» with «Продовжити» (backend/published.py)
            project = studio.find_project(args[1])
            if cancelled(project["id"]):
                print(CANCELLED)
                return 3
            file = DATA / "projects" / project["id"] / "publishing.json"
            state = {**read_json(file, {}), "updated": time.time()}
            state.setdefault("at", time.time())
            state["failed" if args[0] == "failed" else "step"] = args[2]
            file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            if args[0] == "failed":
                record(project["id"], "failed")   # the attempt's time and cost, listed apart as a failed attempt
            print("ok")
        elif args[:1] == ["monetization"] and len(args) in (3, 4) and args[2] in ("ok", "failed"):
            # monetization on in every video (user, 20 November 2026: «монетизація… включена треба ставити
            # обов'язково»): done asks for this mark like for the end screen
            project = studio.find_project(args[1])
            if cancelled(project["id"]):
                print(CANCELLED)
                return 3
            file = DATA / "projects" / project["id"] / "publishing.json"
            state = {**read_json(file, {}), "updated": time.time()}
            state.setdefault("at", time.time())
            state["monetization"] = args[2] if args[2] == "ok" else "failed: " + (args[3] if len(args) == 4 else "")
            file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            print("ok")
        elif args[:1] == ["endscreen"] and len(args) in (3, 4) and args[2] in ("ok", "failed"):
            # the end screen and the playlist are part of every publication (user, 19 November 2026: «кінцеву
            # заставку теж не вибирається»): done asks for this mark, so no session skips them quietly
            project = studio.find_project(args[1])
            if cancelled(project["id"]):
                print(CANCELLED)
                return 3
            file = DATA / "projects" / project["id"] / "publishing.json"
            state = {**read_json(file, {}), "updated": time.time()}
            state.setdefault("at", time.time())
            state["endscreen"] = args[2] if args[2] == "ok" else "failed: " + (args[3] if len(args) == 4 else "")
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
        elif args[:1] == ["playlist"] and len(args) == 3:
            # the channel's playlist, remembered for its next publications (prepare gives it then)
            project = studio.find_project(args[1])
            saved = read_json(CHANNELS, {})
            saved[project["channel_id"]] = {**saved.get(project["channel_id"], {}), "playlist": args[2].strip(),
                                            "name": project["channel"].get("name")}
            CHANNELS.write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"{project['channel'].get('name')}: плейлист «{args[2].strip()}»")
        elif args[:1] == ["done"] and len(args) in (4, 5):
            if len(args) != 5 or args[4] != "VK-" + args[2]:
                raise studio.Failure("Спершу перевір у «Контенті»: await __vk.verify(VIDEO_ID) має дати ok і proof; "
                                     "тоді done P VIDEO_ID \"дата час\" PROOF. Чернетку не позначай опублікованою.")
            project = studio.find_project(args[1])
            if cancelled(project["id"]):
                print(CANCELLED + " Якщо ролик уже встиг стати запланованим, скажи це автору: він вирішить, видаляти його чи ні.")
                return 3
            folder = DATA / "projects" / project["id"]
            endscreen = read_json(folder / "publishing.json", {}).get("endscreen")
            if not endscreen:
                raise studio.Failure("Кінцева заставка не позначена: у формі до розкладу виконай await __vk.endScreen() і "
                                     "запиши endscreen P ok (або endscreen P failed \"причина\", якщо YouTube не дав її поставити).")
            monetization = read_json(folder / "publishing.json", {}).get("monetization")
            if not monetization:
                raise studio.Failure("Монетизація не позначена: у формі крок «Монетизация» → «Вкл.» → «Готово», перевір на "
                                     "екрані й запиши monetization P ok (або monetization P failed \"причина\").")
            mark = {"at": time.time(), "source": "youtube_publish", "video_id": args[2], "url": f"https://youtu.be/{args[2]}",
                      "scheduled": args[3], "endscreen": endscreen, "monetization": monetization}
            (folder / "published.json").write_text(json.dumps(mark, ensure_ascii=False), encoding="utf-8")
            mark["work"] = record(project["id"], "done")
            mark["blue_tag"] = tag_blue(project.get("episode_path"))   # the folder turns blue in Finder too
            (folder / "publishing.json").unlink(missing_ok=True)
            print(json.dumps(mark, ensure_ascii=False))
        else:
            print(__doc__)
            return 2
    except studio.Failure as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
