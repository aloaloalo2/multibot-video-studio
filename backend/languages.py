"""The «Мови» tab: an episode's voice in other languages, and its thumbnail with the words translated.

The user (2 November 2026): «вкладку в проекті після превью мультиязик… перекладаємо сценарій… озвучуємо через апі з тим
самим голосом… вибрати язик… ціну… послухати превью»; «відео ролик перекладати я поки не хочу, лише аудіо і превью».

For each language the author picks:
1. the script and the video's title are translated by DeepSeek through OpenRouter (the studio's key); the author may
   correct the text before it is voiced;
2. the author's own voice is cloned once a provider from a minute of the episode's voice (ElevenLabs or Fish Audio, the
   author's key in the studio's settings) and a short sample is voiced first, to be heard before paying for the whole;
3. the whole text is voiced in parts, glued, brought to the studio's level (−16 LUFS) and fitted to the video's length
   (sped up by at most FIT_MAX when longer, silence after when shorter), so it goes to YouTube as an audio track;
4. the cover is redrawn by Codex with only its words translated.

Work files stay in the studio (data/projects/<id>/languages/<code>); the voice, the text and the thumbnail are copied
next to the video, «<episode>/Мови/<language>/», while the episode folder exists.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import credentials
import store

LANGUAGES = {
    "en": ("English", "англійська"), "uk": ("Українська", "українська"), "ru": ("Русский", "російська"),
    "de": ("Deutsch", "німецька"), "es": ("Español", "іспанська"), "fr": ("Français", "французька"),
    "pt": ("Português", "португальська"), "it": ("Italiano", "італійська"), "pl": ("Polski", "польська"),
    "tr": ("Türkçe", "турецька"), "nl": ("Nederlands", "нідерландська"), "hi": ("हिन्दी", "гінді"),
    "ar": ("العربية", "арабська"), "ja": ("日本語", "японська"), "ko": ("한국어", "корейська"), "zh": ("中文", "китайська"),
    "id": ("Bahasa Indonesia", "індонезійська"), "cs": ("Čeština", "чеська"), "ro": ("Română", "румунська"),
    "kk": ("Қазақша", "казахська"),
}
# English names for the translator's brief
ENGLISH = {"en": "English", "uk": "Ukrainian", "ru": "Russian", "de": "German", "es": "Spanish", "fr": "French",
           "pt": "Portuguese", "it": "Italian", "pl": "Polish", "tr": "Turkish", "nl": "Dutch", "hi": "Hindi",
           "ar": "Arabic", "ja": "Japanese", "ko": "Korean", "zh": "Simplified Chinese", "id": "Indonesian",
           "cs": "Czech", "ro": "Romanian", "kk": "Kazakh"}

# What one voiced character costs, as the providers' price pages said on 2 November 2026; shown as an estimate.
PROVIDERS = {
    "elevenlabs": {"name": "ElevenLabs", "per_char": 0.10 / 1000, "bytes": False,
                   "note": "Найкраща якість і клон голосу, усі мови. Клон голосу потребує платного тарифу (від Starter)."},
    "fishaudio": {"name": "Fish Audio", "per_char": 15 / 1_000_000, "bytes": True,
                  "note": "Голос клонується прямо в кожному запиті зі зразка вашої озвучки, без окремої моделі."},
}
ELEVEN = "https://api.elevenlabs.io/v1"
ELEVEN_MODEL = "eleven_multilingual_v2"
FISH = "https://api.fish.audio"
# Fish's engines (user, 2 November 2026: «там безкоштовно… є різні рушії в фіші»): S2.1 Pro Free costs nothing under
# fair use; the paid ones bill UTF-8 bytes. Every one clones the voice inline from a reference in the request
# (MessagePack), so no voice model is created: a free account's model limit is 0.
FISH_ENGINES = {"s2.1-pro-free": {"name": "S2.1 Pro Free", "per_char": 0.0, "note": "безкоштовно"},
                "s2.1-pro": {"name": "S2.1 Pro", "per_char": 15 / 1_000_000, "note": "$15 за 1 млн байтів"},
                "s1": {"name": "S1", "per_char": 15 / 1_000_000, "note": "$15 за 1 млн байтів"},
                # the expressive one (user: «чому драма не додав»); Fish's own page gave no price on 2 November 2026
                "drama-3": {"name": "Drama 3", "per_char": None, "note": "найвиразніший, ціна на fish.audio"}}
FISH_ENGINE = "s2.1-pro-free"
TRANSLATE_CHUNK = 5000
VOICE_CHUNK = 2400
SAMPLE_CHARS = 320
FIT_MAX = 1.15
TIMEOUT = 300
ACTIVE: set[str] = set()
CANCEL: set[str] = set()      # projects whose running job the author stopped
PROCS: dict[str, subprocess.Popen] = {}
LOCK = threading.Lock()


class Stop(Exception):
    pass


def lang_name(code: str) -> str:
    return LANGUAGES[code][1]


def check_code(code: str) -> str:
    if code not in LANGUAGES:
        raise store.StudioError("Невідома мова", 404)
    return code


def work_dir(pid: str, code: str | None = None) -> Path:
    base = store.project_dir(pid) / "languages"
    return base / code if code else base


def state_path(pid: str) -> Path:
    return work_dir(pid) / "languages.json"


def load_state(pid: str) -> dict:
    data = store.read_json(state_path(pid), {})
    data = data if isinstance(data, dict) else {}
    job = data.get("job")
    if isinstance(job, dict) and job.get("status") == "running" and pid not in ACTIVE:
        job.update(status="failed", error="Студію перезапустили під час роботи. Спробуйте ще раз.")
    return data


def save_state(pid: str, data: dict) -> None:
    work_dir(pid).mkdir(parents=True, exist_ok=True)
    store.atomic_json(state_path(pid), data)


def update(pid: str, change) -> dict:
    with LOCK:
        data = load_state(pid)
        change(data)
        save_state(pid, data)
        return data


def episode_dir(project: dict, code: str) -> Path | None:
    """«<episode>/Мови/<language>» next to the video, while the episode folder is there."""
    folder = Path(project.get("episode_path") or "")
    if project.get("episode_path") and folder.is_dir():
        return folder / "Мови" / LANGUAGES[code][0]
    return None


def source(project: dict) -> dict:
    """The episode's script, title, voice and its length."""
    plan = store.load_project_plan(project["id"]) or {}
    script = (plan.get("script") or plan.get("spoken_script") or "").strip()
    folder = Path(project.get("episode_path") or "")
    if not script and project.get("episode_path") and (folder / "Сценарий.txt").is_file():
        script = (folder / "Сценарий.txt").read_text(encoding="utf-8", errors="replace").strip()
    title = (store.episode_title(folder) if project.get("episode_path") and folder.is_dir() else None) or project["name"]
    audio = ((plan.get("timing") or {}).get("audio") or {})
    voice = voice_file(project, audio, plan)
    duration = (store.media_duration(voice) if voice else None) or audio.get("duration")
    return {"script": script, "title": title, "voice": voice, "duration": float(duration) if duration else None}


def voice_file(project: dict, audio: dict, plan: dict | None = None) -> Path | None:
    """The episode's own voice, looked for the way the plan's player does and further (user, 2 November 2026: «Не
    знайдено озвучку випуску»): the plan's asset; the recording the studio levels to 100% (`audio_gain`), as timings
    attached by a path name the voice by an id made before the project had the file; a file path in the timings; the
    longest sound clip on the timeline that starts the film and is not music."""
    import audio_level
    try:
        gains = project.get("audio_gain") or audio_level.voice_gains(project, plan)
    except (OSError, ValueError, store.StudioError):
        gains = {}
    ids = [audio.get("asset_id"), *gains]
    clips = sorted((clip for track in project.get("tracks", []) for clip in track.get("clips", [])
                    if clip.get("kind") == "audio" and float(clip.get("start") or 0) < 1
                    and "музик" not in (clip.get("title") or "").lower() and "music" not in (clip.get("title") or "").lower()),
                   key=lambda clip: -float(clip.get("duration") or 0))
    ids += [clip.get("asset_id") for clip in clips]
    for aid in dict.fromkeys(item for item in ids if item):
        try:
            path = Path(store.resolve_asset(project, aid)["path"])
        except (store.StudioError, KeyError, OSError):
            continue
        if path.is_file():
            return path
    for key in ("path", "source_path", "file"):
        path = Path(str(audio.get(key) or ""))
        if audio.get(key) and path.is_file():
            return path
    # an animated episode: the voice its Razgon project keeps (config.json's voiceover)
    try:
        link = store.razgon_link(project)
        config = store.read_json(Path(link["project"]) / "config.json", None) if link else None
        if isinstance(config, dict) and config.get("voiceover") and (Path(link["project"]) / config["voiceover"]).is_file():
            return Path(link["project"]) / config["voiceover"]
    except (OSError, ValueError, KeyError, TypeError, store.StudioError):
        pass
    return None


def price(provider: str, text: str, engine: str | None = None) -> float | None:
    """What voicing the text costs; None when the provider names no price for the engine."""
    spec = PROVIDERS[provider]
    rate = FISH_ENGINES.get(engine or FISH_ENGINE, FISH_ENGINES[FISH_ENGINE])["per_char"] if provider == "fishaudio" else spec["per_char"]
    if rate is None:
        return None
    return round(len(text.encode("utf-8") if spec["bytes"] else text) * rate, 2)


# How closely Fish keeps to the example (user, 2 November 2026: «голос поганий… може там є настройки?»): lower
# temperature and top_p stay nearer to the example's voice, higher ones speak more freely.
FISH_STYLES = {"exact": {"name": "Точно як приклад", "temperature": 0.5, "top_p": 0.6},
               "normal": {"name": "Звичайно", "temperature": 0.7, "top_p": 0.7},
               "lively": {"name": "Живіше", "temperature": 0.9, "top_p": 0.8}}
FISH_STYLE = "lively"           # user, 2 November 2026: «живіше варіант краще озвучує… на ру»


def fish_style(pid: str) -> str:
    style = load_state(pid).get("fish_style")
    return style if style in FISH_STYLES else FISH_STYLE


def fish_engine(pid: str) -> str:
    engine = load_state(pid).get("fish_engine")
    return engine if engine in FISH_ENGINES else FISH_ENGINE


def files(pid: str, code: str, project: dict) -> dict:
    work = work_dir(pid, code)
    return {"samples": sorted(path.stem[len("sample-"):] for path in work.glob("sample-*.mp3")), "voice": (work / "voice.mp3").is_file() or bool(final_voice(project, code)),
            "thumbnail": (work / "thumbnail.png").is_file()}


def final_voice(project: dict, code: str) -> Path | None:
    work = work_dir(project["id"], code) / "voice.mp3"
    if work.is_file():
        return work
    folder = episode_dir(project, code)
    found = folder / f"Озвучка {LANGUAGES[code][0]}.mp3" if folder else None
    return found if found and found.is_file() else None


def overview(pid: str) -> dict:
    project = store.load_project(pid)
    data = load_state(pid)
    src = source(project)
    engine = fish_engine(pid)
    items = []
    for code, item in (data.get("languages") or {}).items():
        if code not in LANGUAGES:
            continue
        text = (work_dir(pid, code) / "text.txt").read_text(encoding="utf-8") if (work_dir(pid, code) / "text.txt").is_file() else ""
        items.append({"code": code, "name": LANGUAGES[code][0], "label": lang_name(code), "text": text, "title": item.get("title") or "",
                      "chars": len(text), "prices": {key: price(key, text, engine) for key in PROVIDERS} if text else {},
                      "files": files(pid, code, project), "voice": item.get("voice") or {},
                      "lines": len(synced_segments(pid, code) or []),
                      "passage": passage(text) if text else "",
                      "own_voice": ({"text": own["text"], "duration": own["duration"], "heard": own["heard"], "stamp": own["stamp"]} if (own := own_voice(pid, code)) else None),
                      "channel_voice": ({"duration": shared["duration"], "heard": shared["heard"], "stamp": shared["stamp"]}
                                        if (shared := channel_voice(project.get("channel_id"), code)) else None),
                      "voice_key": voice_key(pid, "fishaudio", code), "sample_provider": item.get("sample_provider"),
                      "folder": str(episode_dir(project, code) or "")})
    configured = {item["id"]: item["configured"] for item in credentials.providers()}
    return {"languages": [{"code": code, "name": names[0], "label": names[1]} for code, names in LANGUAGES.items()],
            "providers": [{"id": key, "name": spec["name"], "note": spec["note"], "configured": configured.get(key),
                           **({"engines": [{"id": eid, **item} for eid, item in FISH_ENGINES.items()], "engine": engine,
                               "styles": [{"id": sid, "name": item["name"]} for sid, item in FISH_STYLES.items()], "style": fish_style(pid),
                               "free": FISH_ENGINES[engine]["per_char"] == 0} if key == "fishaudio" else {})}
                          for key, spec in PROVIDERS.items()],
            "openrouter": configured.get("openrouter"),
            "source": {"chars": len(src["script"]), "title": src["title"], "duration": src["duration"], "voice": bool(src["voice"]),
                       "language": original_language(pid, project, src["script"]),
                       "estimate": {key: price(key, src["script"], engine) for key in PROVIDERS}},
            "items": sorted(items, key=lambda item: list(LANGUAGES).index(item["code"])),
            # Fish Audio only for now (user, 2 November 2026: «будемо працювати лише з фіш-аудіо»); ElevenLabs stays in code
            "provider": "fishaudio", "job": data.get("job"),
            "channel_id": project.get("channel_id"),
            "thumbnail": bool(cover(project))}


def cover(project: dict) -> Path | None:
    import thumbnail_gen
    return thumbnail_gen.preview(project)


# ---------- keys and HTTP ----------

def key(service: str) -> str:
    try:
        return credentials.vault().read(credentials.service_name(service))
    except RuntimeError:
        name = {"openrouter": "OpenRouter", **{k: v["name"] for k, v in PROVIDERS.items()}}[service]
        raise RuntimeError(f"Додайте ключ {name} у налаштуваннях студії («Ключі сервісів»)") from None


def request(url: str, data: bytes, headers: dict, what: str) -> bytes:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, method="POST", headers=headers), timeout=TIMEOUT) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        body = error.read()[:2000].decode("utf-8", errors="replace")
        try:
            detail = json.loads(body)
            detail = detail.get("detail") or detail.get("message") or detail.get("error") or detail
            if isinstance(detail, dict):
                detail = detail.get("message") or detail.get("status") or json.dumps(detail, ensure_ascii=False)
        except ValueError:
            detail = body
        money = re.search(r"credit|balance|quota|limit|payment|subscription|plan", str(detail), re.I)
        # Fish answers 403 «model creation limit reached (0/0). Top up API credit» to a valid key with no API balance
        hint = (" Ключ правильний, але на рахунку API цього сервісу немає коштів або тариф не дозволяє цю дію: поповніть баланс "
                "API на сайті сервісу (він окремий від звичайної підписки)." if money and error.code in (401, 402, 403, 429)
                else " Перевірте ключ." if error.code in (401, 403) else " Перевірте баланс або тариф." if error.code in (402, 429) else "")
        raise RuntimeError(f"{what}: помилка {error.code}. {str(detail)[:300]}{hint}") from None
    except OSError as error:
        raise RuntimeError(f"{what} не відповів: {error}") from None


def multipart(fields: dict, files: list[tuple[str, Path, str]]) -> tuple[bytes, str]:
    boundary = "----videokey" + uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    for name, path, mime in files:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{path.name}"\r\nContent-Type: {mime}\r\n\r\n'.encode()
                     + path.read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), "multipart/form-data; boundary=" + boundary


# ---------- translation ----------

def chunks(text: str, size: int) -> list[str]:
    """Pieces of at most about `size` characters cut at paragraph ends, else at sentence ends."""
    pieces, current = [], ""
    for paragraph in re.split(r"(\n\s*\n)", text):
        units = [paragraph] if len(paragraph) <= size else re.split(r"(?<=[.!?…])\s+", paragraph)
        for unit in units:
            if current and len(current) + len(unit) + 1 > size:
                pieces.append(current.strip())
                current = ""
            current += unit if unit.startswith("\n") or not current or current.endswith("\n") else " " + unit
    if current.strip():
        pieces.append(current.strip())
    return [piece for piece in pieces if piece]


def ask(messages: list, max_tokens: int = 12000) -> tuple[str, float]:
    import agent_openrouter
    payload = {"model": agent_openrouter.MODEL, "max_tokens": max_tokens, "usage": {"include": True}, "messages": messages}
    raw = request(agent_openrouter.BASE + "/chat/completions", json.dumps(payload, ensure_ascii=False).encode(),
                  {"Authorization": "Bearer " + key("openrouter"), "Content-Type": "application/json"}, "OpenRouter")
    try:
        result = json.loads(raw)
        text = str(result["choices"][0]["message"]["content"] or "").strip()
    except (ValueError, KeyError, IndexError, TypeError):
        raise RuntimeError("OpenRouter не повернув переклад") from None
    cost = (result.get("usage") or {}).get("cost")
    return re.sub(r"^```\w*\n|\n```$", "", text).strip(), float(cost) if isinstance(cost, (int, float)) else 0.0


def translator(code: str) -> str:
    return (f"You translate the voice-over of a YouTube video into {ENGLISH[code]}. A narrator will read your text aloud "
            "with the author's own voice. Keep the meaning, the facts, the tone and the energy; sound natural and alive, "
            "as a native YouTuber would say it, not word for word. Keep the paragraphs. Do not add, drop or explain anything. "
            "Write numbers, units and abbreviations the way they are best read aloud. Answer with the translation only.")


# ---------- in time with the original (user, 2 November 2026: «все, що він говорить, говоритиме плюс-мінус в той
# самий час, коли він говорить в оригіналі… це перше, найважливіше») ----------
# The voice's sentences with their times (the plan's recognition) are grouped into lines, each spoken at its own moment:
# the translator gets every line with the seconds it has, Fish voices line by line, and each line is put where its
# original stands, sped up a little when it is longer than its place.
SEGMENT_GAP = 0.3          # sentences closer than this run on as one line
SEGMENT_MAX = 14.0         # seconds a line may take at most
SYNC_SPEED = 1.25          # how much a line may be sped up to fit its place
CHARS_PER_SECOND = {"ja": 8, "zh": 6, "ko": 8}
TRANSLATE_LINES = 30


def segments_of(plan: dict) -> list[dict]:
    """The lines of the original voice: [{start, end, source}], in order, sentences that run on joined."""
    sentences = ((plan.get("timing") or {}).get("sentences")
                 or [item for frame in plan.get("frames") or [] for item in frame.get("sentence_timings") or []])
    lines = []
    for item in sentences:
        try:
            start, end, text = float(item["start"]), float(item["end"]), str(item.get("text") or "").strip()
        except (KeyError, TypeError, ValueError):
            continue
        if not text or end <= start:
            continue
        last = lines[-1] if lines else None
        if last and start - last["end"] < SEGMENT_GAP and end - last["start"] <= SEGMENT_MAX:
            last.update(end=end, source=last["source"] + " " + text)
        else:
            lines.append({"start": round(start, 3), "end": round(end, 3), "source": text})
    return lines


def segments_path(pid: str, code: str) -> Path:
    return work_dir(pid, code) / "segments.json"


def synced_segments(pid: str, code: str) -> list[dict] | None:
    data = store.read_json(segments_path(pid, code), None)
    return data if isinstance(data, list) and data else None


def translate_lines(code: str, lines: list[dict], total: float | None, pid: str, job: dict) -> tuple[list[str], float]:
    """Every line translated to fit about the seconds it has; the answer is a JSON array of the same length."""
    rate = CHARS_PER_SECOND.get(code, 15)
    done, cost = [], 0.0
    batches = [lines[i:i + TRANSLATE_LINES] for i in range(0, len(lines), TRANSLATE_LINES)]
    for number, batch in enumerate(batches):
        progress(pid, job, round(95 * number / max(1, len(batches))), f"Перекладаємо, частина {number + 1} з {len(batches)}")
        offset = number * TRANSLATE_LINES
        items = []
        for k, line in enumerate(batch):
            index = offset + k
            place = (lines[index + 1]["start"] if index + 1 < len(lines) else (total or line["end"] + 1)) - line["start"]
            seconds = round(max(line["end"] - line["start"], min(place, (line["end"] - line["start"]) * 1.4)), 1)
            items.append({"text": line["source"], "seconds": seconds, "max_chars": max(12, int(seconds * rate))})
        before = "\n".join(done[-4:])
        system = translator(code) + (
            "\n\nThe voice-over is dubbed line by line: each line is spoken at the same moment as in the original video and has "
            "only `seconds` to be said. Translate every line so a narrator says it naturally within that time: about "
            "`max_chars` characters or fewer, shorter wording where needed, the meaning kept. Keep the lines one to one: never "
            "merge, split or move words between them. Answer with a JSON array of strings only, exactly as many as the lines, "
            "in the same order.") + (f"\n\nThe lines just before, already translated, for context only:\n{before}" if before else "")
        for attempt in range(2):
            answer, spent = ask([{"role": "system", "content": system}, {"role": "user", "content": json.dumps(items, ensure_ascii=False)}])
            cost += spent
            try:
                found = json.loads(answer[answer.index("["):answer.rindex("]") + 1])
                if isinstance(found, list) and len(found) == len(batch) and all(isinstance(text, str) and text.strip() for text in found):
                    done += [" ".join(text.split()) for text in found]
                    break
            except ValueError:
                pass
        else:
            raise RuntimeError("Перекладач двічі повернув не ту кількість фраз. Спробуйте ще раз")
    return done, cost


def translate(pid: str, code: str, job: dict) -> None:
    project = store.load_project(pid)
    src = source(project)
    if not src["script"]:
        raise RuntimeError("У випуску ще немає тексту озвучки")
    lines = segments_of(store.load_project_plan(pid) or {})
    if lines:
        texts, cost = translate_lines(code, lines, src["duration"], pid, job)
        save_translation(pid, code, project, src, "\n".join(texts), cost, job,
                         [{"start": line["start"], "end": line["end"], "source": line["source"]} for line in lines])
        return
    pieces, done, cost = chunks(src["script"], TRANSLATE_CHUNK), [], 0.0
    for number, piece in enumerate(pieces):
        progress(pid, job, round(100 * number / (len(pieces) + 1)), f"Перекладаємо, частина {number + 1} з {len(pieces)}")
        before = f"\n\nThe text before this part, for context only (already translated, do not repeat it):\n{pieces[number - 1][-600:]}" if number else ""
        text, spent = ask([{"role": "system", "content": translator(code) + before}, {"role": "user", "content": piece}])
        if len(text) < len(piece) * 0.3:
            raise RuntimeError("Переклад вийшов надто коротким, спробуйте ще раз")
        done.append(text)
        cost += spent
    save_translation(pid, code, project, src, "\n\n".join(done), cost, job, None)


def save_translation(pid: str, code: str, project: dict, src: dict, text: str, cost: float, job: dict, segments) -> None:
    progress(pid, job, 96, "Перекладаємо заголовок")
    title, spent = ask([{"role": "system", "content": f"Translate this YouTube video title into {ENGLISH[code]}. Keep it catchy and short, "
                                                       "as a native YouTuber would title it. Answer with the title only, no quotes."},
                        {"role": "user", "content": src["title"]}], 300)
    cost += spent
    progress(pid, job, 99, "Зберігаємо")
    work = work_dir(pid, code)
    work.mkdir(parents=True, exist_ok=True)
    (work / "text.txt").write_text(text.strip() + "\n", encoding="utf-8")
    if segments:
        store.atomic_json(segments_path(pid, code), segments)
    else:
        segments_path(pid, code).unlink(missing_ok=True)
    drop_samples(work)
    def keep(data):
        item = data.setdefault("languages", {}).setdefault(code, {})
        item.update(title=title.strip().strip('"«»'), translated_at=time.time(), translate_cost=round(cost, 4))
    update(pid, keep)
    copy_out(project, code, "text")
    job["cost"] = round(cost, 4)


# ---------- voice ----------

# The voice of a translation always comes from an example in that very language (user, 2 November 2026: «переклад
# будемо брати завжди від прикладу ролика на мові… або запис, або закинути приклад носія»): a clone copies the
# pronunciation of its example with the timbre, so an example in the language carries no foreign accent. The channel
# keeps one example a language for all its episodes («в настройках каналу»), and an episode may have its own instead
# («якщо ні, то можна закинути свій»), which wins. Either is the author's own voice recorded in the page or a file of any
# speaker. There is no fallback to the original's voice: it brought its accent along.
OWN_SECONDS = 45
PASSAGE_CHARS = 380
CHANNEL_VOICES = "Голоси для перекладу"


def passage(text: str) -> str:
    """The passage of the translation the author may read aloud: about twenty-five seconds of whole sentences."""
    return sample_text_at(text, PASSAGE_CHARS)


def channel_voice_dir(cid: str) -> Path:
    return store.get_channel_folder(cid) / CHANNEL_VOICES


def read_example(folder: Path, stem: str, source: str) -> dict | None:
    audio, said = folder / f"{stem}.mp3", folder / f"{stem}.txt"
    if not (audio.is_file() and said.is_file()):
        return None
    meta = store.read_json(folder / f"{stem}.json", {}) or {}
    return {"path": audio, "text": said.read_text(encoding="utf-8").strip(), "duration": store.media_duration(audio),
            "heard": meta.get("heard", True), "from": source, "stamp": int(audio.stat().st_mtime)}


def own_voice(pid: str, code: str | None) -> dict | None:
    """The episode's own example for a language, if the author dropped one in."""
    return read_example(work_dir(pid, code), "own-voice", "episode") if code else None


def channel_voice(cid: str | None, code: str | None) -> dict | None:
    if not cid or not code or code not in LANGUAGES:
        return None
    try:
        return read_example(channel_voice_dir(cid), LANGUAGES[code][0], "channel")
    except store.StudioError:
        return None


def voice_for(pid: str, code: str | None, original: bool = True) -> dict | None:
    """The example a language is voiced from: the episode's own, else the channel's, else (user, 2 November 2026: «хай
    кнопка працює навіть якщо… лише оригінал є») the start of the original voice, with its accent."""
    if not code:
        return None
    own = own_voice(pid, code)
    if own:
        return own
    try:
        cid = store.load_project(pid).get("channel_id")
    except store.StudioError:
        cid = None
    return channel_voice(cid, code) or (original_example(pid) if original else None)


REFERENCE_SECONDS = 22


def spoken_words(pid: str) -> list[dict]:
    """The words of the latest recognition with their times (script words with ASR time)."""
    pointer = store.read_json(store.project_dir(pid) / "analysis-state.json", {}) or {}
    if not pointer.get("job_id"):
        return []
    report = store.read_json(store.project_dir(pid) / "analysis" / pointer["job_id"] / "result.json", {}) or {}
    return [word for word in report.get("aligned_words") or [] if isinstance(word, dict) and "end" in word]


def original_example(pid: str) -> dict | None:
    """About twenty seconds of the original voice from its start, cut after a whole word, with exactly the words said in
    it; made once and kept. None when the episode has no voice."""
    work = work_dir(pid)
    audio_path, text_path = work / "reference.mp3", work / "reference.txt"
    if not (audio_path.is_file() and text_path.is_file()):
        try:
            src = source(store.load_project(pid))
        except store.StudioError:
            return None
        if not src["voice"]:
            return None
        said = [word for word in spoken_words(pid) if float(word["end"]) <= REFERENCE_SECONDS]
        if len(said) >= 8:
            end, text = float(said[-1]["end"]) + 0.15, " ".join(str(word["text"]) for word in said)
        else:            # no recognition kept: the script's opening at about fifteen characters a second
            end, text = float(REFERENCE_SECONDS), sample_text_at(src["script"], int(REFERENCE_SECONDS * 15))
        if not text.strip():
            return None
        work.mkdir(parents=True, exist_ok=True)
        try:
            run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(src["voice"]), "-t", f"{end:.2f}", "-ac", "1", "-ar", "44100",
                 "-b:a", "160k", str(audio_path)], "вирізати зразок голосу")
        except RuntimeError:
            return None
        text_path.write_text(text.strip(), encoding="utf-8")
    return read_example(work, "reference", "original")


NO_VOICE = ("Додайте приклад голосу цією мовою: запишіть себе або закиньте запис носія мови, тут чи в налаштуваннях "
            "каналу. Озвучка скопіює саме цей голос і вимову")


def store_example(folder: Path, stem: str, code: str, stream, size: int, said: str) -> None:
    """A recording or a file turned into the example: mono MP3 of at most OWN_SECONDS, its words recognised."""
    if not 0 < size <= 200 * 1024 * 1024:
        raise store.StudioError("Запис завеликий або порожній", 413)
    folder.mkdir(parents=True, exist_ok=True)
    raw = folder / f"{stem}.upload"
    with raw.open("wb") as out:
        left = size
        while left > 0:
            chunk = stream.read(min(left, 1024 * 1024))
            if not chunk:
                break
            out.write(chunk)
            left -= len(chunk)
    target = folder / f"{stem}.mp3"
    try:
        run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(raw), "-vn", "-t", str(OWN_SECONDS), "-ac", "1", "-ar", "44100",
             "-b:a", "160k", str(target)], "прочитати запис")
    except RuntimeError as error:
        raise store.StudioError(str(error)) from None
    finally:
        raw.unlink(missing_ok=True)
    length = store.media_duration(target) or 0
    if length < 5:
        target.unlink(missing_ok=True)
        raise store.StudioError("Запис закороткий: потрібно хоча б 10 секунд мови")
    # the speaker may say anything in the language: the recording is recognised locally, so Fish gets its own words
    found = heard(target, length, code)
    if not found and not str(said or "").strip():
        target.unlink(missing_ok=True)
        raise store.StudioError("Студія не змогла розпізнати слова в записі. Спробуйте чистіший запис без музики")
    (folder / f"{stem}.txt").write_text((found or str(said).strip()) + "\n", encoding="utf-8")
    # whether the words came from the recording itself: when not, Fish gets the passage, right only if it was read
    store.atomic_json(folder / f"{stem}.json", {"heard": bool(found)})


def drop_example(folder: Path, stem: str) -> None:
    for suffix in (".mp3", ".txt", ".json"):
        (folder / f"{stem}{suffix}").unlink(missing_ok=True)


def save_own_voice(pid: str, code: str, stream, size: int, said: str) -> dict:
    check_code(code)
    store.load_project(pid)
    with LOCK:
        if pid in ACTIVE and (load_state(pid).get("job") or {}).get("code") == code:
            raise store.StudioError("Зачекайте, доки закінчиться дія з цією мовою", 409)
    store_example(work_dir(pid, code), "own-voice", code, stream, size, said)
    drop_samples(work_dir(pid, code))
    return overview(pid)


def remove_own_voice(pid: str, code: str) -> dict:
    check_code(code)
    drop_example(work_dir(pid, code), "own-voice")
    drop_samples(work_dir(pid, code))
    return overview(pid)


def channel_voices(cid: str) -> dict:
    store.get_channel_folder(cid)
    found = []
    for code in LANGUAGES:
        example = channel_voice(cid, code)
        if example:
            found.append({"code": code, "name": LANGUAGES[code][0], "label": lang_name(code), "duration": example["duration"],
                          "heard": example["heard"], "stamp": example["stamp"]})
    return {"voices": found, "languages": [{"code": code, "name": names[0], "label": names[1]} for code, names in LANGUAGES.items()],
            "folder": str(channel_voice_dir(cid))}


def save_channel_voice(cid: str, code: str, stream, size: int, said: str) -> dict:
    check_code(code)
    store_example(channel_voice_dir(cid), LANGUAGES[code][0], code, stream, size, said)
    return channel_voices(cid)


def remove_channel_voice(cid: str, code: str) -> dict:
    check_code(code)
    drop_example(channel_voice_dir(cid), LANGUAGES[code][0])
    return channel_voices(cid)


def channel_voice_file(cid: str, code: str) -> Path:
    check_code(code)
    example = channel_voice(cid, code)
    if not example:
        raise store.StudioError("Прикладу голосу немає", 404)
    return example["path"]


def heard(path: Path, length: float, code: str) -> str | None:
    """The words of a short recording, by the studio's own recognition; None when it is not available or hears little."""
    try:
        import speech
        words, _ = speech.transcribe(path, length, lambda *args, **kwargs: None, language=code)
    except Exception:            # no model on this Mac, a busy GPU: the passage's text stands
        return None
    text = " ".join(str(word.get("text") or "").strip() for word in words).strip()
    return text if len(text.split()) >= 5 else None


def voice_id(pid: str, provider: str, code: str | None = None):
    """The voice for one language, from its example. ElevenLabs keeps a clone id per example; Fish gets the example
    with every request."""
    example = voice_for(pid, code)
    if not example:
        raise RuntimeError(NO_VOICE)
    if provider == "fishaudio":
        return {"audio": example["path"].read_bytes(), "text": example["text"], "engine": fish_engine(pid), "style": fish_style(pid)}
    slot = f"elevenlabs-{code}-{example['from']}-{example['stamp']}"
    known = (load_state(pid).get("clones") or {}).get(slot)
    if known:
        return known
    project = store.load_project(pid)
    body, mime = multipart({"name": f"VideoKey · {project['name']} · {code}"[:90], "remove_background_noise": "false",
                            "description": "Голос для перекладів студії VideoKey"}, [("files", example["path"], "audio/mpeg")])
    raw = request(ELEVEN + "/voices/add", body, {"xi-api-key": key(provider), "Content-Type": mime}, "ElevenLabs (клон голосу)")
    found = json.loads(raw).get("voice_id")
    if not found:
        raise RuntimeError("Сервіс не повернув клон голосу")
    update(pid, lambda data: data.setdefault("clones", {}).__setitem__(slot, found))
    return found


def speak(provider: str, voice: str, text: str, target: Path, before: str = "", after: str = "") -> None:
    if provider == "elevenlabs":
        payload = {"text": text, "model_id": ELEVEN_MODEL, "voice_settings": {"stability": 0.5, "similarity_boost": 0.85, "style": 0.0,
                                                                                "use_speaker_boost": True}}
        if before:
            payload["previous_text"] = before[-500:]
        if after:
            payload["next_text"] = after[:300]
        audio = request(f"{ELEVEN}/text-to-speech/{voice}?output_format=mp3_44100_128", json.dumps(payload, ensure_ascii=False).encode(),
                        {"xi-api-key": key(provider), "Content-Type": "application/json", "Accept": "audio/mpeg"}, "ElevenLabs")
    else:
        ref = voice if isinstance(voice, dict) else {}
        style = FISH_STYLES.get(ref.get("style") or FISH_STYLE, FISH_STYLES[FISH_STYLE])
        payload = {"text": text, "references": [{"audio": ref["audio"], "text": ref["text"]}], "format": "mp3", "mp3_bitrate": 192,
                   "normalize": True, "latency": "normal", "chunk_length": 200,
                   "temperature": style["temperature"], "top_p": style["top_p"]}
        audio = request(FISH + "/v1/tts", msgpack(payload),
                        {"Authorization": "Bearer " + key(provider), "Content-Type": "application/msgpack",
                         "model": ref.get("engine") or FISH_ENGINE}, "Fish Audio")
    if len(audio) < 1000:
        raise RuntimeError("Сервіс озвучки повернув порожній звук")
    target.write_bytes(audio)


def msgpack(value) -> bytes:
    """MessagePack of dicts, lists, strings, bytes, numbers, booleans and None: what Fish's inline references need."""
    import struct
    if value is None:
        return b"\xc0"
    if value is True or value is False:
        return b"\xc3" if value else b"\xc2"
    if isinstance(value, int):
        if 0 <= value < 128:
            return bytes([value])
        return b"\xd3" + struct.pack(">q", value)
    if isinstance(value, float):
        return b"\xcb" + struct.pack(">d", value)
    if isinstance(value, str):
        raw = value.encode("utf-8")
        size = len(raw)
        head = bytes([0xa0 | size]) if size < 32 else b"\xd9" + bytes([size]) if size < 256 else b"\xda" + struct.pack(">H", size) if size < 65536 else b"\xdb" + struct.pack(">I", size)
        return head + raw
    if isinstance(value, (bytes, bytearray)):
        size = len(value)
        head = b"\xc4" + bytes([size]) if size < 256 else b"\xc5" + struct.pack(">H", size) if size < 65536 else b"\xc6" + struct.pack(">I", size)
        return head + bytes(value)
    if isinstance(value, (list, tuple)):
        head = bytes([0x90 | len(value)]) if len(value) < 16 else b"\xdc" + struct.pack(">H", len(value))
        return head + b"".join(msgpack(item) for item in value)
    if isinstance(value, dict):
        head = bytes([0x80 | len(value)]) if len(value) < 16 else b"\xde" + struct.pack(">H", len(value))
        return head + b"".join(msgpack(str(k)) + msgpack(v) for k, v in value.items())
    raise TypeError(f"msgpack: {type(value).__name__}")


def sample_text_at(text: str, size: int) -> str:
    out = ""
    for sentence in re.split(r"(?<=[.!?…])\s+", text.strip()):
        if out and len(out) + len(sentence) > size:
            break
        out = (out + " " + sentence).strip()
    return out


def voice_key(pid: str, provider: str, code: str | None = None) -> str:
    """Which voice a sample was made with: the provider (and Fish's engine) and the example it was cloned from, so a
    new example or engine never plays an older one's sample."""
    example = voice_for(pid, code)
    tail = f"-{example['from']}{example['stamp']}" if example else ""
    return (f"fishaudio-{fish_engine(pid)}-{fish_style(pid)}" if provider == "fishaudio" else provider) + tail


def drop_samples(work: Path) -> None:
    """Samples of an older text (a new translation, the author's edit) are of words no longer there."""
    for path in [*work.glob("sample-*.mp3"), work / "sample.mp3"]:
        path.unlink(missing_ok=True)


def sample_text(text: str) -> str:
    sentences = re.split(r"(?<=[.!?…])\s+", text.strip())
    out = ""
    for sentence in sentences:
        if out and len(out) + len(sentence) > SAMPLE_CHARS:
            break
        out = (out + " " + sentence).strip()
    return out[: SAMPLE_CHARS * 2]


def sample(pid: str, code: str, provider: str, job: dict) -> None:
    text = read_text(pid, code)
    progress(pid, job, 10, "Озвучуємо зразок")
    voice = voice_id(pid, provider, code)
    progress(pid, job, 50, "Озвучуємо зразок")
    if pid in CANCEL:
        raise Stop()
    piece = sample_text(text)
    # each voice (a provider, and Fish's engine) keeps its own sample, so switching between them compares them
    speak(provider, voice, piece, work_dir(pid, code) / f"sample-{voice_key(pid, provider, code)}.mp3")
    job["cost"] = price(provider, piece, fish_engine(pid))
    update(pid, lambda data: data.setdefault("languages", {}).setdefault(code, {}).update(sample_provider=provider))


def line_texts(pid: str, code: str) -> list[str]:
    return [line.strip() for line in read_text(pid, code).splitlines() if line.strip()]


def whole_synced(pid: str, code: str, provider: str, job: dict, segments: list[dict]) -> None:
    """Each line voiced alone and put at its original's moment: sped up (at most SYNC_SPEED) when longer than its
    place, late only by what is left over, silence where the original is silent."""
    project = store.load_project(pid)
    texts = line_texts(pid, code)
    if len(texts) != len(segments):
        raise RuntimeError(f"У тексті має бути {len(segments)} рядків, по одному на фразу, а зараз {len(texts)}")
    voice = voice_id(pid, provider, code)
    total = source(project)["duration"] or segments[-1]["end"]
    work = work_dir(pid, code)
    parts_dir = work / "parts"
    shutil.rmtree(parts_dir, ignore_errors=True)
    parts_dir.mkdir(parents=True)
    pieces, cursor, fastest, latest = [], 0.0, 1.0, 0.0
    def silence(seconds: float) -> None:
        if seconds < 0.01:
            return
        path = parts_dir / f"{len(pieces):05d}-gap.wav"
        run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", f"{seconds:.3f}",
             "-c:a", "pcm_s16le", str(path)], "зробити паузу")
        pieces.append(path)
    for number, (line, text) in enumerate(zip(segments, texts)):
        progress(pid, job, round(90 * number / len(segments)), f"Озвучуємо фразу {number + 1} з {len(segments)}")
        spoken = parts_dir / f"{number:05d}.mp3"
        speak(provider, voice, text, spoken, texts[number - 1] if number else "", texts[number + 1] if number + 1 < len(texts) else "")
        start = max(float(line["start"]), cursor)
        place = (float(segments[number + 1]["start"]) if number + 1 < len(segments) else max(total, float(line["end"]))) - start - 0.05
        length = store.media_duration(spoken) or 0
        speed = min(max(1.0, length / place if place > 0 else SYNC_SPEED), SYNC_SPEED)
        fitted = parts_dir / f"{len(pieces) + 1:05d}-line.wav"
        filters = (f"atempo={speed:.4f}," if speed > 1.001 else "") + "aresample=48000"
        run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(spoken), "-af", filters, "-ac", "1", "-c:a", "pcm_s16le", str(fitted)],
            "підігнати фразу")
        silence(start - cursor)
        pieces.append(fitted)
        cursor = start + (store.media_duration(fitted) or length / speed)
        fastest, latest = max(fastest, speed), max(latest, start - float(line["start"]))
    progress(pid, job, 92, "Склеюємо й вирівнюємо гучність")
    silence(total - cursor)
    listing = parts_dir / "list.txt"
    listing.write_text("".join(f"file '{path.name}'\n" for path in pieces), encoding="utf-8")
    joined = work / "joined.wav"
    run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c:a", "pcm_s16le", str(joined)],
        "склеїти фрази")
    out = work / "voice.mp3"
    run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(joined), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "48000",
         "-b:a", "192k", str(out)], "звести звук")
    joined.unlink(missing_ok=True)
    shutil.rmtree(parts_dir, ignore_errors=True)
    final = store.media_duration(out)
    def keep(data):
        data.setdefault("languages", {}).setdefault(code, {})["voice"] = {
            "provider": provider, "made_at": time.time(), "duration": final, "source_duration": total, "synced": True,
            "lines": len(segments), "fastest": round(fastest, 2), "latest": round(latest, 1),
            "longer": round(max(0.0, cursor - total), 1)}
    update(pid, keep)
    copy_out(project, code, "voice")
    job["cost"] = price(provider, "\n".join(texts), fish_engine(pid))


def whole(pid: str, code: str, provider: str, job: dict) -> None:
    segments = synced_segments(pid, code)
    if segments:
        return whole_synced(pid, code, provider, job, segments)
    project = store.load_project(pid)
    text = read_text(pid, code)
    voice = voice_id(pid, provider, code)
    work = work_dir(pid, code)
    parts_dir = work / "parts"
    shutil.rmtree(parts_dir, ignore_errors=True)
    parts_dir.mkdir(parents=True)
    pieces = chunks(text, VOICE_CHUNK)
    parts = []
    for number, piece in enumerate(pieces):
        progress(pid, job, round(90 * number / len(pieces)), f"Озвучуємо, частина {number + 1} з {len(pieces)}")
        target = parts_dir / f"{number:04d}.mp3"
        speak(provider, voice, piece, target, pieces[number - 1] if number else "", pieces[number + 1] if number + 1 < len(pieces) else "")
        parts.append(target)
    progress(pid, job, 92, "Склеюємо й вирівнюємо гучність")
    listing = parts_dir / "list.txt"
    listing.write_text("".join(f"file '{path.name}'\n" for path in parts), encoding="utf-8")
    joined = work / "joined.wav"
    run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-ar", "48000", str(joined)], "склеїти частини")
    length = store.media_duration(joined) or 0
    target_length = source(project)["duration"]
    filters, fit = ["loudnorm=I=-16:TP=-1.5:LRA=11"], {}
    if target_length and length:
        ratio = length / target_length
        if ratio > 1.0:
            speed = min(ratio, FIT_MAX)
            filters.insert(0, f"atempo={speed:.4f}")
            fit["speed"] = round(speed, 3)
            length /= speed
        if length < target_length:
            filters.append(f"apad=whole_dur={target_length:.3f}")
            fit["padded"] = round(target_length - length, 1)
        fit["longer"] = round(max(0.0, length - target_length), 1)
    out = work / "voice.mp3"
    run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(joined), "-af", ",".join(filters), "-ar", "48000", "-b:a", "192k", str(out)], "звести звук")
    joined.unlink(missing_ok=True)
    shutil.rmtree(parts_dir, ignore_errors=True)
    final = store.media_duration(out)
    def keep(data):
        data.setdefault("languages", {}).setdefault(code, {})["voice"] = {
            "provider": provider, "made_at": time.time(), "duration": final, "source_duration": target_length, **fit}
    update(pid, keep)
    copy_out(project, code, "voice")
    job["cost"] = price(provider, text, fish_engine(pid))


def run(command: list, what: str) -> None:
    done = subprocess.run(command, capture_output=True, timeout=3600)
    if done.returncode:
        raise RuntimeError(f"Не вдалося {what}: " + done.stderr.decode(errors="replace")[-300:])


def read_text(pid: str, code: str) -> str:
    path = work_dir(pid, code) / "text.txt"
    text = path.read_text(encoding="utf-8").strip() if path.is_file() else ""
    if not text:
        raise RuntimeError("Спершу перекладіть текст")
    return text


# ---------- thumbnail ----------

def thumbnail(pid: str, code: str, job: dict) -> None:
    import thumbnail_gen
    project = store.load_project(pid)
    base = cover(project)
    if not base:
        raise RuntimeError("У випуску ще немає прев'ю")
    if not thumbnail_gen.CODEX.is_file():
        raise RuntimeError("Не знайдено Codex у ChatGPT.app")
    work = work_dir(pid, code)
    work.mkdir(parents=True, exist_ok=True)
    progress(pid, job, 20, "Codex перекладає прев'ю, зазвичай 1–3 хвилини")
    name = "thumbnail-new.png"
    (work / name).unlink(missing_ok=True)
    title = ((load_state(pid).get("languages") or {}).get(code) or {}).get("title")
    hint = f'\nThe video\'s title in {ENGLISH[code]} is "{title}", if it helps to choose the words.' if title else ""
    # the author's own wishes for this translation (user, 2 November 2026: «побажання… свої… щоб було додати»)
    wishes = str(job.get("wishes") or "").strip()
    if wishes:
        hint += f"\nThe author's wishes (in Ukrainian or Russian), they come first:\n{wishes[:1500]}"
    prompt = f"""Edit the attached YouTube thumbnail: translate every word written on it into {ENGLISH[code]}.
Keep the translation as short and punchy as the original, in the same font style, size, colours, outline and position.{hint}
Change nothing else: the composition, the characters, the faces, the style, the colours and the background stay exactly
as they are. If there is no text on the picture, return it unchanged.
Use the built-in image generation tool and make exactly one image. Save it in the current working directory as "{name}"
and reply only with the saved path."""
    command = [str(thumbnail_gen.CODEX), "exec", "-s", "workspace-write", "--skip-git-repo-check", "-C", str(work), "-i", str(base), "-"]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=work, text=True,
                               start_new_session=True)
    PROCS[pid] = process
    try:
        out, err = process.communicate(prompt, timeout=thumbnail_gen.TIMEOUT)
    except subprocess.TimeoutExpired:
        process.kill()
        raise
    finally:
        PROCS.pop(pid, None)
    if pid in CANCEL:
        raise Stop()
    result = subprocess.CompletedProcess(command, process.returncode, out, err)
    (work / "thumbnail-log.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
    from PIL import Image, UnidentifiedImageError
    try:
        with Image.open(work / name) as image:
            image.verify()
    except (OSError, UnidentifiedImageError):
        raise RuntimeError("Codex не зберіг картинку. " + (result.stderr or result.stdout)[-300:].strip()) from None
    (work / name).replace(work / "thumbnail.png")
    copy_out(project, code, "thumbnail")


def copy_out(project: dict, code: str, what: str) -> None:
    folder = episode_dir(project, code)
    if not folder:
        return
    name = LANGUAGES[code][0]
    source_file, target = {"text": ("text.txt", f"Текст {name}.txt"), "voice": ("voice.mp3", f"Озвучка {name}.mp3"),
                           "thumbnail": ("thumbnail.png", f"Прев'ю {name}.png")}[what]
    try:
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(work_dir(project["id"], code) / source_file, folder / target)
        if what == "text":
            title = ((load_state(project["id"]).get("languages") or {}).get(code) or {}).get("title")
            if title:
                (folder / f"Заголовок {name}.txt").write_text(title + "\n", encoding="utf-8")
    except OSError:
        pass


def guess_language(text: str) -> str | None:
    """The script's language by its letters, when the recognition did not name it."""
    sample = text[:20000].lower()
    if re.search("[іїєґ]", sample):
        return "uk"
    if re.search("[ыэъё]", sample):
        return "ru"
    if re.search("[а-я]", sample):
        return "ru"
    if re.search("[äöüß]", sample):
        return "de"
    if re.search("[ñ¿¡]", sample):
        return "es"
    if re.search("[a-z]", sample):
        return "en"
    return None


def original_language(pid: str, project: dict, script: str) -> str | None:
    """The voice's language, found once and kept (user, 2 November 2026: «один раз має розпізнатися»): the language
    Whisper heard in the latest recognition, else a guess from the script's letters."""
    data = load_state(pid)
    if data.get("original_language") in LANGUAGES:
        return data["original_language"]
    found = None
    pointer = store.read_json(store.project_dir(pid) / "analysis-state.json", {}) or {}
    if pointer.get("job_id"):
        report = store.read_json(store.project_dir(pid) / "analysis" / pointer["job_id"] / "result.json", {}) or {}
        found = str(((report.get("engine") or {}).get("language")) or "").lower()[:2] or None
    found = found if found in LANGUAGES else guess_language(script)
    if found:
        update(pid, lambda data: data.__setitem__("original_language", found))
    return found


def original_file(pid: str) -> Path:
    """The episode's own voice, for the «Оригінал» card."""
    voice = source(store.load_project(pid))["voice"]
    if not voice or not voice.is_file():
        raise store.StudioError("Не знайдено озвучку випуску", 404)
    return voice


def file_path(pid: str, code: str, kind: str) -> Path:
    check_code(code)
    names = {"voice": "voice.mp3", "thumbnail": "thumbnail.png", "own": "own-voice.mp3"}
    if re.fullmatch(r"sample-[a-z0-9.\-]+", kind):
        names[kind] = kind + ".mp3"
    if kind not in names:
        raise store.StudioError("Файл не знайдено", 404)
    path = work_dir(pid, code) / names[kind]
    if kind == "voice" and not path.is_file():
        path = final_voice(store.load_project(pid), code) or path
    if not path.is_file():
        raise store.StudioError("Файл не знайдено", 404)
    return path


# ---------- jobs ----------

def progress(pid: str, job: dict, value: int, stage: str) -> None:
    if pid in CANCEL:
        raise Stop()
    job.update(progress=value, stage=stage)
    update(pid, lambda data: data.__setitem__("job", dict(job)))


WORK = {"translate": translate, "sample": sample, "voice": whole, "thumbnail": thumbnail}
NAMES = {"translate": "переклад", "sample": "зразок озвучки", "voice": "озвучка", "thumbnail": "переклад прев'ю"}


def worker(pid: str, kind: str, code: str, provider: str | None, job: dict) -> None:
    try:
        if kind in ("sample", "voice"):
            WORK[kind](pid, code, provider, job)
        else:
            WORK[kind](pid, code, job)
        job.update(status="done", progress=100, stage="Готово", finished_at=time.time())
    except Stop:
        job.update(status="cancelled", stage="Скасовано", finished_at=time.time())
    except subprocess.TimeoutExpired:
        job.update(status="failed", error="Не встигло за відведений час", finished_at=time.time())
    except (OSError, RuntimeError, ValueError, store.StudioError) as error:
        job.update(status="failed", error=str(error), finished_at=time.time())
    finally:
        try:
            update(pid, lambda data: data.__setitem__("job", dict(job)))
        finally:
            with LOCK:
                ACTIVE.discard(pid)
                CANCEL.discard(pid)


def cancel(pid: str) -> dict:
    """Stop the running job: at the next part of a translation or a voice (the part being made is finished and paid),
    at once for the thumbnail, whose Codex is killed. Nothing half made is saved."""
    with LOCK:
        if pid not in ACTIVE:
            return overview(pid)
        CANCEL.add(pid)
        process = PROCS.get(pid)
    if process and process.poll() is None:
        import os, signal
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except OSError:
            pass
    update(pid, lambda data: (data.get("job") or {}).update(stage="Скасовуємо…"))
    return overview(pid)


def start(pid: str, kind: str, code: str, provider: str | None = None, wishes: str | None = None) -> dict:
    check_code(code)
    if kind not in WORK:
        raise store.StudioError("Невідома дія", 404)
    project = store.load_project(pid)
    if kind in ("sample", "voice"):
        if provider not in PROVIDERS:
            raise store.StudioError("Оберіть сервіс озвучки")
        try:
            key(provider)
        except RuntimeError as error:
            raise store.StudioError(str(error), 409) from None
        if not voice_for(pid, code):
            raise store.StudioError(NO_VOICE, 409)
        try:
            read_text(pid, code)
        except RuntimeError as error:
            raise store.StudioError(str(error), 409) from None
    if kind == "translate":
        try:
            key("openrouter")
        except RuntimeError as error:
            raise store.StudioError(str(error), 409) from None
        if not source(project)["script"]:
            raise store.StudioError("У випуску ще немає тексту озвучки", 409)
    if kind == "thumbnail" and not cover(project):
        raise store.StudioError("У випуску ще немає прев'ю: створіть його на вкладці «Прев'ю»", 409)
    with LOCK:
        if pid in ACTIVE:
            raise store.StudioError("Зачекайте, доки закінчиться попередня дія", 409)
        ACTIVE.add(pid)
        job = {"status": "running", "kind": kind, "code": code, "provider": provider, "progress": 0, "stage": "Починаємо",
               "what": NAMES[kind], "started_at": time.time(),
               **({"wishes": str(wishes).strip()[:1500]} if kind == "thumbnail" and str(wishes or "").strip() else {})}
        data = load_state(pid)
        data["job"] = dict(job)
        data.setdefault("languages", {}).setdefault(code, {})
        if provider:
            data["provider"] = provider
        save_state(pid, data)
    threading.Thread(target=worker, args=(pid, kind, code, provider, job), daemon=True).start()
    return job


def add(pid: str, code: str) -> dict:
    check_code(code)
    store.load_project(pid)
    update(pid, lambda data: data.setdefault("languages", {}).setdefault(code, {}))
    return overview(pid)


def remove(pid: str, code: str) -> dict:
    check_code(code)
    with LOCK:
        job = load_state(pid).get("job") or {}
        if pid in ACTIVE and job.get("code") == code:
            raise store.StudioError("Зачекайте, доки закінчиться дія з цією мовою", 409)
        data = load_state(pid)
        (data.get("languages") or {}).pop(code, None)
        save_state(pid, data)
    shutil.rmtree(work_dir(pid, code), ignore_errors=True)    # the copies next to the video stay: they are the author's
    return overview(pid)


def save_text(pid: str, code: str, text: str, title: str | None = None) -> dict:
    check_code(code)
    if not isinstance(text, str) or not text.strip():
        raise store.StudioError("Текст порожній")
    if len(text) > 400_000:
        raise store.StudioError("Текст задовгий")
    with LOCK:
        if pid in ACTIVE and (load_state(pid).get("job") or {}).get("code") == code:
            raise store.StudioError("Зачекайте, доки закінчиться дія з цією мовою", 409)
    segments = synced_segments(pid, code)
    if segments:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) != len(segments):
            raise store.StudioError(f"Кожен рядок звучить у свій час: їх має бути {len(segments)}, а зараз {len(lines)}. "
                                    "Не об'єднуйте й не розбивайте рядки")
        text = "\n".join(lines)
    work = work_dir(pid, code)
    work.mkdir(parents=True, exist_ok=True)
    (work / "text.txt").write_text(text.strip() + "\n", encoding="utf-8")
    drop_samples(work)
    if isinstance(title, str):
        update(pid, lambda data: data.setdefault("languages", {}).setdefault(code, {}).__setitem__("title", title.strip()[:200]))
    copy_out(store.load_project(pid), code, "text")
    return overview(pid)


def set_provider(pid: str, provider: str, engine: str | None = None, style: str | None = None) -> dict:
    if provider not in PROVIDERS:
        raise store.StudioError("Невідомий сервіс озвучки")
    if engine is not None and engine not in FISH_ENGINES:
        raise store.StudioError("Невідомий рушій Fish Audio")
    if style is not None and style not in FISH_STYLES:
        raise store.StudioError("Невідома схожість голосу")
    def change(data):
        data["provider"] = provider
        if engine:
            data["fish_engine"] = engine
        if style:
            data["fish_style"] = style
    update(pid, change)
    return overview(pid)
