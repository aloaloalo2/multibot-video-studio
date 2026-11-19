"""A short reference of a film's shared Razgon helpers for the frame sessions.

User, 19 November 2026: «є що оптимізувати по лімітам… по швидкості?», «так, зроби». The spend reports of two films showed
every frame session reading the whole helper files (scenes/kit.js, scenes/channel/ui.js, base.js, science.js: about 180 KB)
and carrying them through dozens of steps, a quarter of the film's cost. The session now gets one line per exported helper
(its call and the comment above it) and opens the code of a single function only when the line is not enough.
"""
from __future__ import annotations

import re
from pathlib import Path

EXPORT = re.compile(r"^export\s+(?:async\s+)?(?:function\s*\*?\s*([A-Za-z_$][\w$]*)\s*\(([^)]*)\)?|"
                    r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(\([^)]*\)|[A-Za-z_$][\w$]*)?\s*(=>)?)")
COMMENT_WIDTH = 220
LIMIT = 30000   # characters; a film with more helpers than this gets the files most used first


def files(razgon: Path) -> list[Path]:
    scenes = razgon / "scenes"
    found = [scenes / "kit.js", scenes / "cast.js", scenes / "assets.js"]
    found += sorted((scenes / "channel").glob("*.js")) + sorted(scenes.glob("lib_*.js")) + sorted((scenes / "sets").glob("*.js"))
    return [path for path in found if path.is_file()]


def entries(path: Path) -> list[str]:
    """`name(args) · comment` for each export of one file, the comment being the lines right above it."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    found = []
    for index, line in enumerate(lines):
        match = EXPORT.match(line)
        if not match:
            continue
        name = match.group(1) or match.group(3)
        if match.group(1):
            call = f"{name}({(match.group(2) or '').strip()})"
        elif match.group(5) or (match.group(4) or "").startswith("("):
            call = f"{name}{match.group(4) or '()'}"
        else:
            call = name
        notes, above = [], index - 1
        while above >= 0 and lines[above].strip().startswith(("//", "*", "/*")):
            text = lines[above].strip().lstrip("/*").strip().strip("-=").strip()   # «// ----- камера» rules go
            if text:
                notes.insert(0, text)
            above -= 1
        note = " ".join(notes)
        # a comment that already names the call («say(g, str, x, y, k, o): …», after a section heading such as
        # «камера») gives the call as written there, and only what follows it is kept
        written = re.search(r"(?<![\w$])" + re.escape(name) + r"\([^)]*\)\s*:", note)
        if written:
            call, note = written.group(0).rstrip(": ").strip(), note[written.end():].strip()
        note = note[:COMMENT_WIDTH] + ("…" if len(note) > COMMENT_WIDTH else "")
        found.append(f"  {call}" + (f" · {note}" if note else ""))
    return found


def text(razgon: Path | None) -> str:
    """The reference, or "" when the film has no helper files yet."""
    if not razgon:
        return ""
    parts, size = [], 0
    for path in files(razgon):
        rows = entries(path)
        if not rows:
            continue
        block = f"{path.relative_to(razgon)}:\n" + "\n".join(rows)
        if size + len(block) > LIMIT:
            parts.append(f"{path.relative_to(razgon)}: (не вмістилось у довідник, дивись експорти: grep -n \"^export\")")
            continue
        parts.append(block)
        size += len(block)
    return "\n".join(parts)
