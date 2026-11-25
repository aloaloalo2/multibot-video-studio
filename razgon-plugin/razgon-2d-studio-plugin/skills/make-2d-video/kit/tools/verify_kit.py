"""tools/verify_kit.py — confirm every studio file was written exactly (run right after installing).

  python tools/verify_kit.py
Prints MISMATCH/MISSING for any file that differs from the tested version; copy those files again from the plugin kit folder.
(Line endings and leading/trailing blank lines are ignored. Files you customise later, e.g. engine/styles.js, will of course differ.)
A copy the VideoKey Studio keeps up to date (tools/razgon_sync.py) is checked against the record the Studio left in it,
.videokey-kit.json: the table below only describes the kit as it was when this file was last written.
"""
import hashlib, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPECTED = {
    "audio/dsp.py": "bc13e5932083884a",
    "audio/mix.py": "4980df544c65a0af",
    "audio/music.py": "33fec67e9edc0625",
    "audio/sfx.py": "db36da654bf93ade",
    "engine/core.js": "3311d64301225668",
    "engine/fx2d.js": "d09f93f6d44366fa",
    "engine/overlays.js": "a9abf111cbd11a3f",
    "engine/player.js": "cac499f1da4a7a8e",
    "engine/motion.js": "f5b911715e563cef",
    "engine/rig2d.js": "9fce539912d618f4",
    "engine/scenekit.js": "68471c3799744fee",
    "engine/styles.js": "acfb1c1057532869",
    "engine/three-kit.js": "02e249e302b95420",
    "engine/ui2d.js": "6ae6cdfd56da3ea8",
    "examples/reaction-time/config.json": "9ee341c65b3cfe9a",
    "examples/reaction-time/scenes/cast.js": "e4faad3c508a5cf5",
    "examples/reaction-time/scenes/sets/cafe.js": "9b54c8432834f805",
    "examples/reaction-time/scenes/sets/lab.js": "a2da3ca0fff2d8c4",
    "examples/reaction-time/scenes/shots/01_cafe.js": "931e9c360ba052b3",
    "examples/reaction-time/scenes/shots/02_orbit3d.js": "77897bcae80a501e",
    "examples/reaction-time/scenes/shots/03_explain.js": "c22f0e7a8f505c78",
    "examples/reaction-time/story/bible.md": "e22b689a54461b41",
    "examples/reaction-time/story/shots.json": "9b1921e8e42c2498",
    "live.html": "8a41124c6e96e8ec",
    "package.json": "1aff39c91eaad305",
    "player.html": "5ffdd7da4a48cd4b",
    "render.mjs": "e188b78b38880927",
    "tools/beats.py": "eb42a8aef4d87584",
    "tools/common.py": "e237321f2f12416e",
    "tools/direction_check.py": "7c9cbc1e61844bef",
    "tools/doctor.py": "a16207eea3196e73",
    "tools/live.mjs": "7c2031d848c715cc",
    "tools/new_project.py": "940758644aa95289",
    "tools/parse_script.py": "5163cf3162b2579b",
    "tools/transcribe.py": "ecd48d05a6655d13",
}
RECORD = os.path.join(ROOT, ".videokey-kit.json")
if os.path.isfile(RECORD):
    import json
    written = json.load(open(RECORD, encoding="utf-8"))
    bad = 0
    for rel, want in sorted(written.items()):
        p = os.path.join(ROOT, *rel.split("/"))
        if not os.path.exists(p):
            print(f"MISSING   {rel}"); bad += 1
        elif hashlib.sha256(open(p, "rb").read()).hexdigest() != want:
            print(f"CHANGED   {rel}"); bad += 1
    print(f"{len(written) - bad}/{len(written)} files as the Studio wrote them." + ("" if not bad else "  Changed files are kept and reported by the Studio at its next start."))
    sys.exit(1 if bad else 0)
bad = 0
for rel, want in EXPECTED.items():
    p = os.path.join(ROOT, *rel.split("/"))
    if not os.path.exists(p):
        print(f"MISSING   {rel}"); bad += 1; continue
    got = hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n").strip()).hexdigest()[:16]
    if got != want:
        print(f"MISMATCH  {rel}"); bad += 1
print(f"{len(EXPECTED) - bad}/{len(EXPECTED)} files verified." + ("" if not bad else "  Copy the files listed above again from the plugin's kit folder, then run this again."))
sys.exit(1 if bad else 0)
