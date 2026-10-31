"""tools/direction_check.py — catch slideshow direction before the viewer does (references/storytelling.md).

  python tools/direction_check.py --project projects/<slug>                       # plan + shot code
  python tools/direction_check.py --project projects/<slug> --video build/preview.mp4   # + measured motion

FAIL = fix before rendering. WARN = answer it in story/bible.md or fix it. Exit code 1 when anything FAILs.
"""
import argparse, collections, json, os, re, statistics, subprocess, sys

ap = argparse.ArgumentParser()
ap.add_argument("--project", required=True)
ap.add_argument("--video", help="a rendered preview to measure static holds, jump cuts and pops")
ap.add_argument("--offset", type=float, default=0.0, help="film time of the preview's first frame (the --from you rendered with)")
a = ap.parse_args()
P = a.project
story = json.load(open(os.path.join(P, "story", "shots.json"), encoding="utf-8"))
shots = story["shots"]
total = float(story.get("duration") or shots[-1]["end"])
fails, warns, notes = [], [], []
def fail(msg): fails.append(msg)
def warn(msg): warns.append(msg)

# --- template registries: shared shots instead of shared sets/helpers
tpl = [s for s in shots if isinstance(s.get("params"), dict) and s["params"].get("tpl")]
if len(tpl) > 0.2 * len(shots):
    fail(f"{len(tpl)}/{len(shots)} shots come from a params.tpl template registry. Write each shot for its own moment (storytelling.md §5).")
code = ""
shots_dir = os.path.join(P, "scenes", "shots")
for root, _, files in os.walk(shots_dir):
    for f in files:
        if f.endswith(".js"):
            code += open(os.path.join(root, f), encoding="utf-8").read()
if re.search(r"for\s*\(.*E\.shots.*\)[^\n]*registerShot", code) or re.search(r"E\.shots[^\n]*\.forEach[^\n]*registerShot", code):
    fail("Shot code registers shots in a loop over E.shots (a template registry).")
registered = set(re.findall(r"registerShot\(\s*['\"]([^'\"]+)['\"]", code))
if registered:
    missing = [s["id"] for s in shots if s["id"] not in registered]
    if missing and not tpl:
        warn(f"{len(missing)} shots have no registerShot of their own yet (first: {', '.join(missing[:5])}).")

# --- episodes
eps = [s.get("episode") for s in shots]
if any(e is None for e in eps):
    fail(f"{sum(e is None for e in eps)} shots have no \"episode\". Plan episodes first (storytelling.md §1).")
else:
    spans = collections.OrderedDict()
    for s in shots:
        spans.setdefault(s["episode"], [s["start"], s["end"]])[1] = s["end"]
    order = [s["episode"] for s in shots]
    if any(order[i] != order[i - 1] and order[i] in order[:i - 1] for i in range(1, len(order))):
        fail("An episode comes back after another one started. Episodes must be continuous stretches.")
    lengths = [b - a2 for a2, b in spans.values()]
    short = [e for e, (a2, b) in spans.items() if b - a2 < 15]
    if short:
        warn(f"Very short episodes (<15 s): {', '.join(map(str, short[:8]))}. Merge them into neighbours unless they are deliberate punctuation.")
    if total > 300 and len(spans) < 6:
        warn(f"Only {len(spans)} episodes for {total/60:.1f} min.")
    notes.append(f"episodes: {len(spans)}, median length {statistics.median(lengths):.0f} s")

# --- rhythm: long takes, few cuts (storytelling.md §0)
durs = [s["end"] - s["start"] for s in shots]
cuts = sum(1 for i, s in enumerate(shots) if i and (s.get("in") or {}).get("type", "cut") == "cut")
per_min = cuts / max(1e-6, total / 60)
med = statistics.median(durs)
notes.append(f"shots: {len(shots)}, median take {med:.1f} s, hard cuts {cuts} ({per_min:.1f}/min)")
if per_min > 6:
    fail(f"{per_min:.1f} hard cuts per minute: the picture keeps jumping. One long take per meaning beat; travel the camera instead of cutting (target 1–4/min).")
elif per_min > 4:
    warn(f"{per_min:.1f} hard cuts per minute (target 1–4).")
if med < 5:
    fail(f"Median take is {med:.1f} s: too short to follow. Merge shots into long takes (target 10–25 s).")
beats_file = os.path.join(P, "story", "beats.json")
if not os.path.exists(beats_file):
    warn("No story/beats.json. Write the meaning beats yourself (storytelling.md §0); they also drive external clip plans.")
else:
    beats = json.load(open(beats_file, encoding="utf-8")).get("beats", [])
    lens = [(b.get("end") or total) - b["start"] for b in beats]
    notes.append(f"beats: {len(beats)}, median {statistics.median(lens):.0f} s")
    if beats and statistics.median(lens) < 8:
        warn("Beats are very short; a beat is a whole thought (usually 10–35 s).")

# --- places
sets = [s.get("set") or "" for s in shots]
named = [x for x in sets if x]
if named:
    share = collections.Counter()
    for s in shots:
        if s.get("set"):
            share[s["set"]] += s["end"] - s["start"]
    top, sec = share.most_common(1)[0]
    if sec > 0.35 * total:
        warn(f"Set '{top}' fills {100*sec/total:.0f}% of the runtime (budget ~25%).")
    if total > 600 and len(share) < 6:
        warn(f"Only {len(share)} distinct sets for {total/60:.1f} min (want ≥ 6).")
    flips = sum(1 for i in range(2, len(sets)) if sets[i] and sets[i] == sets[i - 2] and sets[i] != sets[i - 1] and shots[i].get("episode") != shots[i - 1].get("episode"))
    if flips > len(shots) * 0.08:
        fail(f"Place ping-pong: {flips} times the film jumps A → B → A between episodes. Keep each place in one continuous episode.")
else:
    warn("No shot has a \"set\"; the variety budget can't be checked.")

# --- continuity: a new take in the same place is a jump cut (the camera and the people jump at the junction)
HARD = {"cut", "smash", "flash"}
jumps = [f"{shots[i - 1]['id']}→{shots[i]['id']}" for i in range(1, len(shots))
         if (shots[i].get("in") or {}).get("type", "cut") in HARD and shots[i].get("set") and shots[i].get("set") == shots[i - 1].get("set")]
if jumps:
    fail(f"{len(jumps)} hard cuts inside one place ({', '.join(jumps[:8])}{'…' if len(jumps) > 8 else ''}). If the action goes on, it is "
         "the same take: join it to the take above (one shot, one Studio frame, one camera path). A new take in the same place "
         "needs a real change of time, subject or mode and a designed transition (dip, push, zoom, iris, match).")

# --- repeated compositions
desc = collections.Counter(re.sub(r"\W+", " ", (s.get("scene") or "").lower()).strip() for s in shots)
dup = [(d, n) for d, n in desc.items() if d and n > 2]
if dup:
    fail("Same scene description used more than twice: " + "; ".join(f"'{d[:40]}' ×{n}" for d, n in dup[:5]))
blank = sum(1 for s in shots if len((s.get("scene") or "").split()) < 4)
if blank > len(shots) * 0.1:
    fail(f"{blank} shots have no real scene description (fewer than 4 words).")

# --- explanation vs story balance, faces
kinds = collections.Counter()
for s in shots:
    sc = (s.get("scene") or "").lower()
    k = "face" if re.search(r"big ?face|close-?up face|giant face", sc) else "diagram" if re.search(r"blueprint|diagram|card|chart|kinetic|title|text slam|bars", sc) else "story"
    kinds[k] += s["end"] - s["start"]
if kinds["diagram"] > 0.3 * total:
    warn(f"Diagrams/cards/text fill {100*kinds['diagram']/total:.0f}% of the runtime (budget 30%). Show more of it as action or diegetic numbers.")
faces = [i for i, s in enumerate(shots) if re.search(r"big ?face|giant face", (s.get("scene") or "").lower())]
if len(faces) > 0.15 * len(shots):
    warn(f"Giant faces are {100*len(faces)/len(shots):.0f}% of shots (budget 15%).")
if any(b - a2 == 1 for a2, b in zip(faces, faces[1:])):
    warn("Two giant-face shots in a row.")

# --- transitions between episodes
if not any(e is None for e in eps):
    hard = sum(1 for i in range(1, len(shots)) if shots[i]["episode"] != shots[i - 1]["episode"] and (shots[i].get("in") or {}).get("type", "cut") == "cut")
    if hard > max(2, len(set(eps)) * 0.5):
        warn(f"{hard} episode changes are plain cuts. Design entries/exits (dip, whip, push, match, iris).")

# --- overlays (film-timeline graphics)
ovs = story.get("overlays") or []
for ov in ovs:
    words = len(str(ov.get("str", "")).split())
    if float(ov.get("end", 0)) - float(ov.get("start", 0)) < max(1.2, 0.9 + 0.3 * words) - 0.05:
        warn(f"Overlay '{ov.get('str')}' is scheduled shorter than its reading time; the engine stretches it, so make room for it.")
busy = 0
for i, ov in enumerate(ovs):
    together = sum(1 for o2 in ovs if o2 is not ov and float(o2["start"]) < float(ov.get("end", 0)) and float(o2.get("end", 0)) > float(ov["start"]))
    busy = max(busy, together + 1)
if busy > 2:
    warn(f"Up to {busy} overlays on screen at once (max 2).")
if code and re.search(r"kText\([^;]*\)", code) and "overlays" not in json.dumps(story)[:200000] and len(re.findall(r"kText\(", code)) > len(shots) * 0.3:
    warn("Lots of kText inside shots and no film overlays: text drawn inside a shot is cut off by the next cut. Put key text in story.overlays.")

# --- measured motion in a rendered preview
if a.video:
    def ff(vf):
        r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", a.video, "-vf", vf, "-an", "-f", "null", "-"], capture_output=True, text=True)
        return r.stderr
    log = ff("freezedetect=n=0.003:d=1.5")
    holds = [float(x) for x in re.findall(r"freeze_duration: ([\d.]+)", log)]
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", a.video], capture_output=True, text=True).stdout or 0)
    cuts = len(re.findall(r"pts_time", ff("select='gt(scene,0.35)',showinfo")))
    notes.append(f"video: {dur:.0f} s, static holds ≥1.5 s: {len(holds)} ({sum(holds):.0f} s), hard scene changes: {cuts} ({cuts / max(1, dur) * 60:.0f}/min)")
    if sum(holds) > 0.1 * max(1, dur):
        fail(f"{sum(holds):.0f} s of the preview are static holds (≥1.5 s without visible motion).")
    if dur and cuts / dur * 60 > 18:
        warn(f"{cuts / dur * 60:.0f} big picture changes per minute: the eye is jerked around. Cut inside places, not between them.")
    # frame-to-frame change on a tiny grey copy: jump cuts at the edits, pops everywhere else
    try:
        import numpy as np
        fps = float(json.load(open(os.path.join(P, "config.json"))).get("fps", 24))
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", a.video, "-vf", "scale=96:54,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
        fr = np.frombuffer(raw, np.uint8).reshape(-1, 54, 96).astype(np.float32)
        d = np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2))                      # d[i] = change from frame i to i+1
        edits = {}
        for s in shots:
            k = int(np.ceil((s["start"] - a.offset) * fps - 1e-6))   # first frame that belongs to the new shot
            if 0 < k < len(fr):
                edits[k] = s
        jumps = []
        for k, s in edits.items():
            if (s.get("in") or {}).get("type", "cut") != "cut":
                continue
            dark = fr[k - 1].mean() < 10 and fr[k].mean() < 10        # a cut through black (fade out → fade in) is not a jump
            if d[k - 1] < 9 and not dark:
                jumps.append(f"{s['id']} @{s['start']:.2f}s (change {d[k - 1]:.1f})")
        if jumps:
            fail(f"{len(jumps)} jump cuts: the picture barely changes across the cut, so it reads as a glitch. Change place, size (≥1.5×) or angle, or replace the cut with a camera move: " + "; ".join(jumps[:8]))
        near = set()
        for k, s in edits.items():
            tr = s.get("in") or {}
            span = 0 if tr.get("type", "cut") == "cut" else int(np.ceil(float(tr.get("dur", 0.6)) * fps))
            near.update(range(k - 2, k + 2 + span))                          # designed transitions move a lot on purpose
        pops = []
        for i in range(2, len(d) - 2):
            if i in near:
                continue
            local = np.median(np.r_[d[max(0, i - 6):i - 1], d[i + 2:i + 7]])
            uniform = abs(fr[i + 1].mean() - fr[i].mean()) > 0.7 * d[i]      # the whole frame brightens/darkens together: a fade, not a pop
            if d[i] > 6 and d[i] > 5 * max(local, 0.5) and not uniform:
                pops.append(round(a.offset + (i + 1) / fps, 2))
        if pops:
            fail(f"{len(pops)} pops: something appears or vanishes within one frame (at {', '.join(map(str, pops[:10]))} s). Every element enters and leaves with motion or a fade.")
        notes.append(f"edits checked: {len(edits)}, jump cuts: {len(jumps)}, pops: {len(pops)}")
    except Exception as exc:
        warn(f"Frame analysis skipped: {exc}")

for n in notes:
    print("  ·", n)
for w in warns:
    print("WARN ", w)
for f in fails:
    print("FAIL ", f)
print(f"\n{len(fails)} FAIL, {len(warns)} WARN" + ("" if fails else "  — direction looks like a film, not a slideshow."))
sys.exit(1 if fails else 0)
