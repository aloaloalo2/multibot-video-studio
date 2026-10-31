"""tools/clean_build.py — remove render leftovers from a project's build folder once the video is assembled.

  python tools/clean_build.py --project projects/<slug>            # list what would go and how much space it frees
  python tools/clean_build.py --project projects/<slug> --apply    # delete it

The project's code and inputs (scenes, story, timeline, input, assets, config) are outside build/ and never touched.
Inside build/ it removes what is only a step towards the final file: render parts, the silent film and its pieces,
and the raw/normalised mixes. It keeps music.wav (the mix is made from it), the Studio frame clips in build/studio
(the bridge reuses them), stills, review sheets and logs. A finished video (build/final.mp4, out/*.mp4) is removed only
when the episode folder linked to this project by razgon.json holds a byte-identical copy.
"""
import argparse, fnmatch, hashlib, json, os, shutil, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STEP_DIRS = ["parts", "parts-*"]
STEP_FILES = ["film.mp4", "film_part.mp4", "*_silent.mp4", "preview.mp4", "mix_raw.wav", "final_mix_raw.wav", "mix.wav"]


def size(path):
    if os.path.isfile(path): return os.path.getsize(path)
    return sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(path) for f in fs)


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""): h.update(chunk)
    return h.hexdigest()


def episode_folders(project):
    """Episode folders whose razgon.json points at this project (they sit beside the studio, one level up)."""
    found, base = [], os.path.dirname(ROOT)
    for name in os.listdir(base):
        link = os.path.join(base, name, "razgon.json")
        try:
            if os.path.realpath(json.load(open(link, encoding="utf-8"))["project"]) == os.path.realpath(project):
                found.append(os.path.join(base, name))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return found


def kept_elsewhere(video, folders):
    n = os.path.getsize(video)
    copies = [os.path.join(f, x) for f in folders for x in os.listdir(f) if x.lower().endswith(".mp4") and os.path.getsize(os.path.join(f, x)) == n]
    if not copies: return None
    mine = digest(video)
    return next((c for c in copies if digest(c) == mine), None)


RECENT = 600   # seconds: anything touched this recently may belong to a render or an assembly that is still running


def in_use(path, name):
    """A render keeps its parts in parts-<pid>; that folder and anything written in the last minutes stay."""
    if name.startswith("parts-") and name[6:].isdigit():
        try:
            os.kill(int(name[6:]), 0)
            return True
        except ProcessLookupError:
            pass
        except PermissionError:
            return True
    newest = max([os.path.getmtime(path)] + [os.path.getmtime(os.path.join(r, f)) for r, _, fs in os.walk(path) for f in fs])
    return time.time() - newest < RECENT


def plan(project):
    build, items = os.path.join(project, "build"), []
    if not os.path.isdir(build): return items
    for name in sorted(os.listdir(build)):
        path = os.path.join(build, name)
        if in_use(path, name): continue
        if os.path.isdir(path) and any(fnmatch.fnmatch(name, p) for p in STEP_DIRS): items.append((path, "частини рендеру"))
        elif os.path.isfile(path) and any(fnmatch.fnmatch(name, p) for p in STEP_FILES): items.append((path, "проміжний файл"))
    folders = episode_folders(project)
    finished = [os.path.join(build, "final.mp4")]
    out = os.path.join(project, "out")
    if os.path.isdir(out): finished += [os.path.join(out, x) for x in sorted(os.listdir(out)) if x.lower().endswith(".mp4")]
    for video in finished:
        if not os.path.isfile(video) or in_use(video, os.path.basename(video)): continue
        copy = kept_elsewhere(video, folders)
        if copy: items.append((video, f"копія лежить у {os.path.relpath(copy, os.path.dirname(ROOT))}"))
        else: print(f"лишаю {os.path.relpath(video, project)}: у папці випуску немає такої самої копії")
    return items


def main():
    a = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    a.add_argument("--project", required=True)
    a.add_argument("--apply", action="store_true", help="delete; without it only list")
    args = a.parse_args()
    project = os.path.abspath(args.project)
    if not os.path.isfile(os.path.join(project, "config.json")):
        sys.exit(f"Not a Razgon project: {project}")
    items = plan(project)
    total = 0
    for path, why in items:
        n = size(path); total += n
        print(f"{n / 1e6:9.1f} MB  {os.path.relpath(path, project)}  ({why})")
        if args.apply:
            shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)
    verb = "Звільнено" if args.apply else "Можна звільнити (запустіть з --apply)"
    print(f"{verb}: {total / 1e9:.2f} ГБ" if items else "Прибирати нічого.")


if __name__ == "__main__":
    main()
