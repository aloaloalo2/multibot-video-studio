"""The author's standing rules for every script writer and agent the studio starts, the same a Claude Code session in
the YOUTUBE folder works by (user, 8 November 2026: «AGENTS.md або CLAUDE.md не береться з папки… якщо я пишу сценарій
тут або через студію, є різниця?… пофікси… та пам'ять також… не тільки до одного каналу, а до всіх… синхронізувати»).

The studio starts Claude with `--setting-sources ''`, so nothing is read from the disk by itself: these functions put
the rules into the brief.

- `writing_rules()`: the user's own CLAUDE.md with its @-included files (the writing rules).
- `script_sections(path)`: the sections of an AGENTS.md about scripts, openings, titles, words and speech, whole
  (the big files are mostly montage; taking their first 16 000 characters lost the later script rules).
- `claude_memory(channel)`: the Claude Code memory notes of this channel and the rules every channel shares.
"""
from __future__ import annotations

import re
import unicodedata
import word_blacklist
from pathlib import Path

HOME = Path.home()
CLAUDE_MD = HOME / ".claude" / "CLAUDE.md"
MEMORY = HOME / ".claude" / "projects" / "-Users-a11-Documents-YOUTUBE" / "memory"
PROVERKA = HOME / ".agents" / "skills" / "scenariy" / "scripts" / "proverka.py"

SCRIPT_WORDS = ("сценар", "зачин", "тайтл", "заголов", "слов", "речь", "речі", "мова", "язык", "удержан", "кликбейт",
                "польз", "обещан", "обіцян", "описан", "тег", "текст для озвуч", "надежд", "интерес", "лайк", "тире",
                "голос ведущ", "подача", "автор", "живая", "повтор", "фраз", "читач", "глядач", "зритель")
NOT_SCRIPT = ("монтаж", "кадр", "png", "фото", "переход", "зум", "карта", "плашк", "браузер", "звук", "студі",
              "flow", "картин", "інфограф", "инфограф", "відео", "видео", "рендер", "whisper", "розпізнав")
GENERAL = ("усі канали", "всі канали", "всех каналов", "все каналы", "всіх каналів", "all channels", "every channel")


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def _read(path: Path) -> str:
    try:
        return nfc(path.read_text(encoding="utf-8"))
    except OSError:
        return ""


def writing_rules() -> str:
    """CLAUDE.md with every `@file` line replaced by that file (relative to CLAUDE.md)."""
    text = _read(CLAUDE_MD)
    out = []
    for line in text.splitlines():
        match = re.fullmatch(r"\s*@(\S+)\s*", line)
        if match:
            target = (CLAUDE_MD.parent / match.group(1)).expanduser()
            out.append(_read(target) or line)
        else:
            out.append(line)
    return "\n".join(out).strip()


def script_sections(path: Path, limit: int = 60000) -> str:
    """The `##` sections whose heading speaks of scripts and not of montage, newest first as the file keeps them."""
    text = _read(path)
    if not text:
        return ""
    parts = re.split(r"(?m)^(?=#{1,3} )", text)
    kept, size = [], 0
    for part in parts:
        heading = part.splitlines()[0].lower() if part.strip() else ""
        if not heading.startswith("#"):
            continue
        if any(w in heading for w in SCRIPT_WORDS) and not any(w in heading for w in NOT_SCRIPT):
            if size + len(part) > limit:
                break
            kept.append(part.strip())
            size += len(part)
    return "\n\n".join(kept)


def _stem(channel: str) -> list[str]:
    """Words that name the channel in memory notes: its surname or name, its stem, and the Latin file-name form."""
    name = nfc(channel).strip()
    words = [w for w in re.findall(r"\w+", name) if len(w) > 2]
    key = words[-1] if words else name
    latin = {"антропов": "antropov", "горбунов": "gorbunov", "чичваркин": "valentin", "werkstatt": "karl", "if": "what-if"}
    stems = {key.lower()[:6], name.lower()}
    if key.lower() in latin:
        stems.add(latin[key.lower()])
    if "what if" in name.lower():
        stems.update({"what if", "what-if"})
    if "karl" in name.lower():
        stems.update({"karl", "карл"})
    if "валентин" in name.lower():
        stems.update({"валентин", "чичвар"})
    if "горбунов" in name.lower():
        stems.update({"олексі", "алексе", "горбун"})
    return [s for s in stems if s]


PREFIXES = ("antropov", "gorbunov", "valentin", "karl", "what-if", "vetrov")
TEXT_WORDS = ("сценар", "зачин", "тайтл", "заголов", "заборонен", "слова", "речен", "мова", "мовою", "озвуч", "фраз", "текст")


def claude_memory(channel: str, limit: int = 30000, scripts_only: bool = False) -> str:
    """Memory notes of this channel and the notes that hold for every channel, frontmatter dropped. A note whose file
    name starts with another channel's prefix (antropov-, gorbunov-, …) stays with that channel. With scripts_only,
    only notes that speak of scripts, openings, titles or words."""
    if not MEMORY.is_dir():
        return ""
    stems = _stem(channel)
    own = [p for p in PREFIXES if any(p == s or p in s for s in stems)]
    chosen = []
    for file in sorted(MEMORY.glob("*.md")):
        if file.name == "MEMORY.md":
            continue
        prefix = next((p for p in PREFIXES if file.name.startswith(p)), None)
        if prefix and prefix not in own:
            continue
        text = _read(file)
        low = text.lower()
        body = re.sub(r"(?s)\A---.*?---\s*", "", text).strip()
        mine = prefix in own if prefix else any(s in low for s in stems)
        if not (mine or any(g in low for g in GENERAL)):
            continue
        if scripts_only and not any(w in low for w in TEXT_WORDS):
            continue
        chosen.append(f"[{file.stem}]\n{body}")
    out, size = [], 0
    for note in chosen:
        if size + len(note) > limit:
            break
        out.append(note)
        size += len(note)
    return "\n\n".join(out)


def for_channel(folder: Path, root: Path) -> dict:
    """Everything a script writer of this channel must follow, by source."""
    import store
    portable = store.read_json(store.DATA_ROOT / 'channels' / store.channel_id(folder) / 'portable-rules.json', {}) or {}
    if isinstance(portable.get('author'), dict):
        result = dict(portable['author'])
    else:
        result = {
            "author_writing_rules": writing_rules(),
            "youtube_script_rules": script_sections(root / "AGENTS.md"),
            "channel_script_rules": script_sections(store.channel_rules_source(folder)),
            "claude_memory_notes": claude_memory(folder.name, scripts_only=True),
        }
    entries=word_blacklist.current()
    result.pop('studio_word_blacklist',None)
    if word_blacklist.managed():
        result={key:word_blacklist.without_legacy_bans(value) if isinstance(value,str) else value for key,value in result.items()}
        result['studio_word_blacklist']=entries
    elif entries:result['studio_word_blacklist']=entries
    return result


def check(text: str, workdir: Path) -> tuple[bool | None, str]:
    """Return True/False for a completed check, or None when the checker is unavailable."""
    import subprocess
    import sys
    import tempfile
    import os
    blacklist=word_blacklist.message(text)
    if not PROVERKA.is_file():
        return (False,blacklist) if blacklist else (None,"Автоматична перевірка сценарію недоступна: proverka.py не знайдено.")
    with tempfile.NamedTemporaryFile("w", suffix=".txt", dir=workdir, delete=False, encoding="utf-8") as f:
        f.write(text)
        name = f.name
    try:
        env=dict(os.environ)
        if word_blacklist.managed():env['VIDEOKEY_MANAGED_WORD_BLACKLIST']='1'
        out = subprocess.run([sys.executable, str(PROVERKA), "--voiceover", name], capture_output=True, text=True, timeout=120,env=env)
    finally:
        Path(name).unlink(missing_ok=True)
    report = (out.stdout + out.stderr).strip()
    if blacklist:report+='\n'+blacklist
    return out.returncode == 0 and not blacklist, report.replace(name, "сценарій")
