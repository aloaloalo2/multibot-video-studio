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
                  "note": "Значно дешевше. Рахує байти тексту: кирилиця коштує вдвічі більше за латиницю."},
}
ELEVEN = "https://api.elevenlabs.io/v1"
ELEVEN_MODEL = "eleven_multilingual_v2"
FISH = "https://api.fish.audio"
FISH_MODEL = "s1"
TRANSLATE_CHUNK = 5000
VOICE_CHUNK = 2400
SAMPLE_CHARS = 320
CLONE_SECONDS = 90
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
    voice, duration = None, None
    if audio.get("asset_id"):
        try:
            voice = Path(store.resolve_asset(project, audio["asset_id"])["path"])
            duration = store.media_duration(voice)
        except store.StudioError:
            voice = None
    duration = duration or audio.get("duration")
    return {"script": script, "title": title, "voice": voice, "duration": float(duration) if duration else None}


def price(provider: str, text: str) -> float:
    spec = PROVIDERS[provider]
    return round(len(text.encode("utf-8") if spec["bytes"] else text) * spec["per_char"], 2)


def files(pid: str, code: str, project: dict) -> dict:
    work = work_dir(pid, code)
    return {"sample": (work / "sample.mp3").is_file(), "voice": (work / "voice.mp3").is_file() or bool(final_voice(project, code)),
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
    items = []
    for code, item in (data.get("languages") or {}).items():
        if code not in LANGUAGES:
            continue
        text = (work_dir(pid, code) / "text.txt").read_text(encoding="utf-8") if (work_dir(pid, code) / "text.txt").is_file() else ""
        items.append({"code": code, "name": LANGUAGES[code][0], "label": lang_name(code), "text": text, "title": item.get("title") or "",
                      "chars": len(text), "prices": {key: price(key, text) for key in PROVIDERS} if text else {},
                      "files": files(pid, code, project), "voice": item.get("voice") or {}, "sample_provider": item.get("sample_provider"),
                      "folder": str(episode_dir(project, code) or "")})
    configured = {item["id"]: item["configured"] for item in credentials.providers()}
    return {"languages": [{"code": code, "name": names[0], "label": names[1]} for code, names in LANGUAGES.items()],
            "providers": [{"id": key, "name": spec["name"], "note": spec["note"], "configured": configured.get(key)} for key, spec in PROVIDERS.items()],
            "openrouter": configured.get("openrouter"),
            "source": {"chars": len(src["script"]), "title": src["title"], "duration": src["duration"], "voice": bool(src["voice"]),
                       "estimate": {key: price(key, src["script"]) for key in PROVIDERS}},
            "items": sorted(items, key=lambda item: list(LANGUAGES).index(item["code"])),
            "provider": data.get("provider") or "elevenlabs", "job": data.get("job"),
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
        hint = " Перевірте ключ." if error.code in (401, 403) else " Перевірте баланс або тариф." if error.code in (402, 429) else ""
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


def translate(pid: str, code: str, job: dict) -> None:
    project = store.load_project(pid)
    src = source(project)
    if not src["script"]:
        raise RuntimeError("У випуску ще немає тексту озвучки")
    pieces, done, cost = chunks(src["script"], TRANSLATE_CHUNK), [], 0.0
    for number, piece in enumerate(pieces):
        progress(pid, job, round(100 * number / (len(pieces) + 1)), f"Перекладаємо, частина {number + 1} з {len(pieces)}")
        before = f"\n\nThe text before this part, for context only (already translated, do not repeat it):\n{pieces[number - 1][-600:]}" if number else ""
        text, spent = ask([{"role": "system", "content": translator(code) + before}, {"role": "user", "content": piece}])
        if len(text) < len(piece) * 0.3:
            raise RuntimeError("Переклад вийшов надто коротким, спробуйте ще раз")
        done.append(text)
        cost += spent
    progress(pid, job, 95, "Перекладаємо заголовок")
    title, spent = ask([{"role": "system", "content": f"Translate this YouTube video title into {ENGLISH[code]}. Keep it catchy and short, "
                                                       "as a native YouTuber would title it. Answer with the title only, no quotes."},
                        {"role": "user", "content": src["title"]}], 300)
    cost += spent
    progress(pid, job, 99, "Зберігаємо")
    work = work_dir(pid, code)
    work.mkdir(parents=True, exist_ok=True)
    text = "\n\n".join(done).strip() + "\n"
    (work / "text.txt").write_text(text, encoding="utf-8")
    for stale in ("sample.mp3",):
        (work / stale).unlink(missing_ok=True)
    def keep(data):
        item = data.setdefault("languages", {}).setdefault(code, {})
        item.update(title=title.strip().strip('"«»'), translated_at=time.time(), translate_cost=round(cost, 4))
    update(pid, keep)
    copy_out(project, code, "text")
    job["cost"] = round(cost, 4)


# ---------- voice ----------

def clone_sample(project: dict, work: Path) -> Path:
    """A minute and a half of the episode's own voice, the clone's reference."""
    voice = source(project)["voice"]
    if not voice or not voice.is_file():
        raise RuntimeError("Не знайдено озвучку випуску, з якої клонувати голос")
    target = work / "clone-sample.mp3"
    if not target.is_file():
        done = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(voice), "-t", str(CLONE_SECONDS), "-ac", "1",
                               "-ar", "44100", "-b:a", "192k", str(target)], capture_output=True, timeout=120)
        if done.returncode or not target.is_file():
            raise RuntimeError("Не вдалося вирізати зразок голосу: " + done.stderr.decode(errors="replace")[-200:])
    return target


def voice_id(pid: str, provider: str) -> str:
    """The author's voice cloned once per provider and episode; the id is kept for every language."""
    data = load_state(pid)
    known = (data.get("clones") or {}).get(provider)
    if known:
        return known
    project = store.load_project(pid)
    sample = clone_sample(project, work_dir(pid))
    name = f"VideoKey · {project['name']}"[:90]
    if provider == "elevenlabs":
        body, mime = multipart({"name": name, "remove_background_noise": "false",
                                "description": "Голос автора, клонований студією VideoKey для перекладів"}, [("files", sample, "audio/mpeg")])
        raw = request(ELEVEN + "/voices/add", body, {"xi-api-key": key(provider), "Content-Type": mime}, "ElevenLabs (клон голосу)")
        found = json.loads(raw).get("voice_id")
    else:
        body, mime = multipart({"title": name, "type": "tts", "visibility": "private", "train_mode": "fast",
                                "enhance_audio_quality": "true"}, [("voices", sample, "audio/mpeg")])
        raw = request(FISH + "/model", body, {"Authorization": "Bearer " + key(provider), "Content-Type": mime}, "Fish Audio (клон голосу)")
        found = json.loads(raw).get("_id") or json.loads(raw).get("id")
    if not found:
        raise RuntimeError("Сервіс не повернув клон голосу")
    update(pid, lambda data: data.setdefault("clones", {}).__setitem__(provider, found))
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
        payload = {"text": text, "reference_id": voice, "format": "mp3", "mp3_bitrate": 192, "normalize": True, "latency": "normal"}
        audio = request(FISH + "/v1/tts", json.dumps(payload, ensure_ascii=False).encode(),
                        {"Authorization": "Bearer " + key(provider), "Content-Type": "application/json", "model": FISH_MODEL}, "Fish Audio")
    if len(audio) < 1000:
        raise RuntimeError("Сервіс озвучки повернув порожній звук")
    target.write_bytes(audio)


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
    progress(pid, job, 10, "Клонуємо ваш голос" if not (load_state(pid).get("clones") or {}).get(provider) else "Озвучуємо зразок")
    voice = voice_id(pid, provider)
    progress(pid, job, 50, "Озвучуємо зразок")
    if pid in CANCEL:
        raise Stop()
    piece = sample_text(text)
    speak(provider, voice, piece, work_dir(pid, code) / "sample.mp3")
    job["cost"] = price(provider, piece)
    update(pid, lambda data: data.setdefault("languages", {}).setdefault(code, {}).update(sample_provider=provider))


def whole(pid: str, code: str, provider: str, job: dict) -> None:
    project = store.load_project(pid)
    text = read_text(pid, code)
    voice = voice_id(pid, provider)
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
    job["cost"] = price(provider, text)


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


def file_path(pid: str, code: str, kind: str) -> Path:
    check_code(code)
    names = {"sample": "sample.mp3", "voice": "voice.mp3", "thumbnail": "thumbnail.png"}
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


def start(pid: str, kind: str, code: str, provider: str | None = None) -> dict:
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
        if not source(project)["voice"]:
            raise store.StudioError("Не знайдено озвучку випуску, з якої клонувати голос", 409)
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
               "what": NAMES[kind], "started_at": time.time()}
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
    work = work_dir(pid, code)
    work.mkdir(parents=True, exist_ok=True)
    (work / "text.txt").write_text(text.strip() + "\n", encoding="utf-8")
    (work / "sample.mp3").unlink(missing_ok=True)
    if isinstance(title, str):
        update(pid, lambda data: data.setdefault("languages", {}).setdefault(code, {}).__setitem__("title", title.strip()[:200]))
    copy_out(store.load_project(pid), code, "text")
    return overview(pid)


def set_provider(pid: str, provider: str) -> dict:
    if provider not in PROVIDERS:
        raise store.StudioError("Невідомий сервіс озвучки")
    update(pid, lambda data: data.__setitem__("provider", provider))
    return overview(pid)
