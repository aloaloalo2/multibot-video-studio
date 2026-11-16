"""tools/library.py — the library of props (transparent PNG objects) for Razgon projects.

Props are cut from generated sheets into one project's assets/. The library keeps one copy of each distinct prop,
the sheet it came from and the prompt that drew it, so a later video can reuse a rocket or a bathtub instead of
generating it again. Files are APFS clones where the disk allows it, so a prop in the library and in a project
takes the space of one file.

  python3 tools/library.py collect                                  # add every project's props (safe to repeat)
  python3 tools/library.py search rocket capsule                    # find props by name or description
  python3 tools/library.py use --project projects/<slug> soyuz_rocket bathtub   # put props into a project

  python3 tools/library.py search --project projects/<slug> rocket  # the same in that project's channel library

Layout: library/props/<name>.png, library/sheets/<project>__<sheet>.png and .txt (the prompt), library/props.json.
A different picture under a name already taken gets a suffix: bed, bed-2.

Each channel keeps its own library (user, 16 November 2026: «розділи… в кожного каналу, щоб все своє було»): a project
whose config.json names a "channel" (VideoKey Studio writes it into every project it creates) takes its props from and
gives its new props to library/channels/<channel>/, with the same layout. A project without a channel, made before
that or outside the Studio, keeps the shared library/. The props already in the shared library stay there.
"""
import argparse, ctypes, datetime, hashlib, json, os, re, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "library"
CHANNEL_NAME = re.compile(r"[A-Za-z0-9_.-]+")


def channel_of(project):
    """The channel a project belongs to, from its config.json; None for a project without one."""
    try: channel = json.loads((Path(project) / "config.json").read_text(encoding="utf-8")).get("channel")
    except (OSError, ValueError, AttributeError): return None
    return channel if isinstance(channel, str) and CHANNEL_NAME.fullmatch(channel) else None


def library_for(project=None, channel=None):
    """The channel's own library, or the shared one for a project without a channel."""
    channel = channel if channel and CHANNEL_NAME.fullmatch(channel) else (channel_of(project) if project else None)
    return LIBRARY / "channels" / channel if channel else LIBRARY


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


def load(lib=None):
    try: return json.loads(((lib or LIBRARY) / "props.json").read_text(encoding="utf-8"))
    except (OSError, ValueError): return {"props": []}


def save(catalog, lib=None):
    lib = lib or LIBRARY
    lib.mkdir(parents=True, exist_ok=True)
    catalog["props"].sort(key=lambda p: p["name"])
    path = lib / "props.json"
    tmp = path.with_suffix(".tmp"); tmp.write_text(json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8"); os.replace(tmp, path)


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


def attach_origin(entry, project, sheet, prompt, text, lib=None):
    """Record which sheet and prompt drew this prop; a copy in another project may be seen first."""
    lib = lib or LIBRARY
    if text and not entry.get("description"): entry["description"] = text
    if not sheet.is_file(): return
    kept = lib / "sheets" / f"{project.name}__{sheet.name}"
    if not kept.exists(): clone(sheet, kept)
    entry["sheet"] = str(kept.relative_to(lib))
    if prompt.is_file():
        note = kept.with_suffix(".txt")
        if not note.exists(): shutil.copyfile(prompt, note)
        entry["prompt"] = str(note.relative_to(lib))


def add_project(project, catalog=None, quiet=False):
    """Put every prop of one project into its channel's library (or the shared one); returns how many were new."""
    lib = library_for(project)
    own = catalog is None
    catalog = catalog or load(lib)
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
            clone(png, lib / "props" / f"{name}.png")
            entry = {"name": name, "sha256": h, "description": "", "projects": [], "added": datetime.date.today().isoformat()}
            catalog["props"].append(entry); by_hash[h] = entry; taken.add(name); added += 1
        if png.stem in origin and not entry.get("sheet"):
            attach_origin(entry, project, *origin[png.stem], lib=lib)
        if project.name not in entry["projects"]: entry["projects"].append(project.name)
    if own: save(catalog, lib)
    if not quiet: print(f"{project.name}: нових предметів {added}")
    return added


def search(words, limit=6, sheet=None, lib=None):
    lib = lib or LIBRARY
    catalog = load(lib)
    terms = [w.lower() for w in words]
    hits = [p for p in catalog["props"] if all(t in (p["name"] + " " + p.get("description", "")).lower() for t in terms)]
    # Exact names first, then close name matches. The agent sees a bounded list,
    # rather than loading the entire library and many individual source PNGs.
    query = "_".join(terms)
    hits.sort(key=lambda p: (p["name"].lower() != query, -sum(t in p["name"].lower() for t in terms), p["name"]))
    shown = hits[:max(1, min(24, int(limit)))]
    for p in shown:
        print(f"{p['name']:<28} {p.get('description', '')[:90]}")
    where = "бібліотеці каналу" if lib.parent.name == "channels" else "спільній бібліотеці"
    print(f"Показано {len(shown)} із {len(hits)} відповідних предметів у {where}.")
    if sheet and shown:
        from PIL import Image, ImageDraw, ImageFont
        sheet = Path(sheet)
        sheet.parent.mkdir(parents=True, exist_ok=True)
        canvas = Image.new("RGB", (3 * 240, ((len(shown) + 2) // 3) * 200), (35, 35, 40))
        draw = ImageDraw.Draw(canvas)
        for i, p in enumerate(shown):
            x, y = i % 3 * 240, i // 3 * 200
            with Image.open(lib / "props" / (p["name"] + ".png")) as source:
                im = source.convert("RGBA"); im.thumbnail((216, 155))
                canvas.paste(im, (x + (240 - im.width) // 2, y + (160 - im.height) // 2), im)
            draw.text((x + 10, y + 168), p["name"][:32], fill="white", font=ImageFont.load_default())
        canvas.save(sheet)
        print(f"Один аркуш кандидатів: {sheet}")


def use(project, names):
    lib = library_for(project)
    catalog = {p["name"]: p for p in load(lib)["props"]}
    missing = [n for n in names if n not in catalog]
    if missing: sys.exit("Немає в бібліотеці каналу цього проєкту: " + ", ".join(missing) if lib != LIBRARY else
                         "Немає в бібліотеці: " + ", ".join(missing))
    assets = project / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    for name in names:
        target = assets / f"{name}.png"
        if target.exists() and digest(target) != catalog[name]["sha256"]:
            sys.exit(f"{target} уже є і відрізняється від бібліотечного; перейменуйте один із них")
        if not target.exists():
            clone(lib / "props" / f"{name}.png", target)
    picks_path = assets / "library-picks.json"
    picks = json.loads(picks_path.read_text()) if picks_path.is_file() else {}
    picks.update({name: {"sha256": catalog[name]["sha256"], "file": f"{name}.png"} for name in names})
    picks_path.write_text(json.dumps(picks, ensure_ascii=False, indent=1))
    (assets / "index.json").write_text(json.dumps(sorted(p.stem for p in assets.glob("*.png"))))
    add_project(project, quiet=True)
    print(f"У {project.name} додано: {', '.join(names)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("collect")
    s = sub.add_parser("search"); s.add_argument("words", nargs="+")
    s.add_argument("--limit", type=int, default=6)
    s.add_argument("--sheet", help="one small contact sheet of the selected candidates")
    s.add_argument("--project", help="search the library of this project's channel (projects/<slug>)")
    s.add_argument("--channel", help="search this channel's library")
    u = sub.add_parser("use"); u.add_argument("--project", required=True); u.add_argument("names", nargs="+")
    args = ap.parse_args()
    if args.cmd == "collect":
        catalogs = {}
        for project in sorted((ROOT / "projects").iterdir()):
            if (project / "assets").is_dir():
                lib = library_for(project)
                if lib not in catalogs: catalogs[lib] = load(lib)
                add_project(project, catalogs[lib])
        for lib, catalog in catalogs.items():
            save(catalog, lib)
            print(f"У бібліотеці {len(catalog['props'])} предметів: {lib / 'props'}")
    elif args.cmd == "search":
        project = Path(args.project).resolve() if args.project else None
        if project and not project.is_dir(): sys.exit(f"Немає проєкту {args.project}")
        search(args.words, args.limit, args.sheet, library_for(project, args.channel))
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from project_lock import project_files
        with project_files(Path(args.project).resolve()):
            use(Path(args.project).resolve(), args.names)


if __name__ == "__main__":
    main()
