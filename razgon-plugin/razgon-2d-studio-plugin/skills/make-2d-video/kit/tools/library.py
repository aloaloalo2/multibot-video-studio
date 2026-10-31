"""tools/library.py — the shared library of props (transparent PNG objects) for every Razgon project.

Props are cut from generated sheets into one project's assets/. The library keeps one copy of each distinct prop,
the sheet it came from and the prompt that drew it, so a later video can reuse a rocket or a bathtub instead of
generating it again. Files are APFS clones where the disk allows it, so a prop in the library and in a project
takes the space of one file.

  python3 tools/library.py collect                                  # add every project's props (safe to repeat)
  python3 tools/library.py search rocket capsule                    # find props by name or description
  python3 tools/library.py use --project projects/<slug> soyuz_rocket bathtub   # put props into a project

Layout: library/props/<name>.png, library/sheets/<project>__<sheet>.png and .txt (the prompt), library/props.json.
A different picture under a name already taken gets a suffix: bed, bed-2.
"""
import argparse, ctypes, datetime, hashlib, json, os, re, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "library"
CATALOG = LIBRARY / "props.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clone(source, target):
    """APFS clone (no extra space, independent afterwards); a plain copy elsewhere."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name("." + target.name + ".tmp")
    if tmp.exists(): tmp.unlink()
    done = False
    if sys.platform == "darwin":
        try: done = ctypes.CDLL("/usr/lib/libSystem.dylib").clonefile(os.fsencode(source), os.fsencode(tmp), 0) == 0
        except OSError: done = False
    if not done: shutil.copyfile(source, tmp)
    os.replace(tmp, target)


def load():
    try: return json.loads(CATALOG.read_text(encoding="utf-8"))
    except (OSError, ValueError): return {"props": []}


def save(catalog):
    LIBRARY.mkdir(exist_ok=True)
    catalog["props"].sort(key=lambda p: p["name"])
    tmp = CATALOG.with_suffix(".tmp"); tmp.write_text(json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8"); os.replace(tmp, CATALOG)


def prompt_lines(prompt):
    """The numbered object lines of a sheet prompt, in reading order."""
    try: text = prompt.read_text(encoding="utf-8")
    except OSError: return []
    return [m.group(1).strip() for m in re.finditer(r"^\s*\d+\.\s+(.+)$", text, re.M)]


def sources(project):
    """name -> (sheet path, prompt path, description) for props cut from this project's sheets."""
    found = {}
    for crops in sorted((project / "assets" / "src").glob("*.crops.json")):
        try: data = json.loads(crops.read_text(encoding="utf-8"))
        except ValueError: continue
        stem = crops.name[: -len(".crops.json")]
        prompt = crops.with_name(f"prompt_{stem}.txt")
        lines = prompt_lines(prompt)
        for i, item in enumerate(data.get("props", [])):
            found[item["name"]] = (crops.with_name(data.get("sheet", stem + ".png")), prompt, lines[i] if i < len(lines) else "")
    return found


def attach_origin(entry, project, sheet, prompt, text):
    """Record which sheet and prompt drew this prop; a copy in another project may be seen first."""
    if text and not entry.get("description"): entry["description"] = text
    if not sheet.is_file(): return
    kept = LIBRARY / "sheets" / f"{project.name}__{sheet.name}"
    if not kept.exists(): clone(sheet, kept)
    entry["sheet"] = str(kept.relative_to(LIBRARY))
    if prompt.is_file():
        note = kept.with_suffix(".txt")
        if not note.exists(): shutil.copyfile(prompt, note)
        entry["prompt"] = str(note.relative_to(LIBRARY))


def add_project(project, catalog=None, quiet=False):
    """Put every prop of one project into the library; returns how many were new."""
    own = catalog is None
    catalog = catalog or load()
    by_hash = {p["sha256"]: p for p in catalog["props"]}
    taken = {p["name"] for p in catalog["props"]}
    origin = sources(project)
    added = 0
    for png in sorted((project / "assets").glob("*.png")):
        h = digest(png)
        entry = by_hash.get(h)
        if entry is None:
            name, n = png.stem, 2
            while name in taken: name, n = f"{png.stem}-{n}", n + 1
            clone(png, LIBRARY / "props" / f"{name}.png")
            entry = {"name": name, "sha256": h, "description": "", "projects": [], "added": datetime.date.today().isoformat()}
            catalog["props"].append(entry); by_hash[h] = entry; taken.add(name); added += 1
        if png.stem in origin and not entry.get("sheet"):
            attach_origin(entry, project, *origin[png.stem])
        if project.name not in entry["projects"]: entry["projects"].append(project.name)
    if own: save(catalog)
    if not quiet: print(f"{project.name}: нових предметів {added}")
    return added


def search(words):
    catalog = load()
    terms = [w.lower() for w in words]
    hits = [p for p in catalog["props"] if all(t in (p["name"] + " " + p.get("description", "")).lower() for t in terms)]
    for p in hits:
        print(f"{p['name']:<28} {p.get('description', '')[:90]}  [{', '.join(p['projects'])}]")
    print(f"Знайдено {len(hits)} з {len(catalog['props'])}.")


def use(project, names):
    catalog = {p["name"]: p for p in load()["props"]}
    missing = [n for n in names if n not in catalog]
    if missing: sys.exit("Немає в бібліотеці: " + ", ".join(missing))
    assets = project / "assets"
    for name in names:
        target = assets / f"{name}.png"
        if target.exists() and digest(target) != catalog[name]["sha256"]:
            sys.exit(f"{target} уже є і відрізняється від бібліотечного; перейменуйте один із них")
        clone(LIBRARY / "props" / f"{name}.png", target)
    (assets / "index.json").write_text(json.dumps(sorted(p.stem for p in assets.glob("*.png"))))
    add_project(project, quiet=True)
    print(f"У {project.name} додано: {', '.join(names)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("collect")
    s = sub.add_parser("search"); s.add_argument("words", nargs="+")
    u = sub.add_parser("use"); u.add_argument("--project", required=True); u.add_argument("names", nargs="+")
    args = ap.parse_args()
    if args.cmd == "collect":
        catalog = load()
        for project in sorted((ROOT / "projects").iterdir()):
            if (project / "assets").is_dir(): add_project(project, catalog)
        save(catalog)
        print(f"У бібліотеці {len(catalog['props'])} предметів: {LIBRARY / 'props'}")
    elif args.cmd == "search":
        search(args.words)
    else:
        use(Path(args.project).resolve(), args.names)


if __name__ == "__main__":
    main()
