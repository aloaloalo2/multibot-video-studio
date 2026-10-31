"""tools/verify_kit.py — confirm every studio file was written exactly (run right after installing).

  python tools/verify_kit.py
Prints MISMATCH/MISSING for any file that differs from the tested version; copy those files again from the plugin kit folder.
(Line endings and leading/trailing blank lines are ignored. Files you customise later, e.g. engine/styles.js, will of course differ.)
"""
import hashlib, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPECTED = {
    "audio/dsp.py": "589d305d94d8acc3",
    "audio/mix.py": "a48273c523b68c3b",
    "audio/music.py": "2fb3ce1df2fe5c7d",
    "audio/sfx.py": "2fa56141e2423718",
    "engine/core.js": "aff933c5f8df6edd",
    "engine/fx2d.js": "d09f93f6d44366fa",
    "engine/overlays.js": "f97bee4c3380af78",
    "engine/player.js": "34eca65e52bf1293",
    "engine/motion.js": "f6ceec93f98d7c8f",
    "engine/rig2d.js": "ec2a665e0aa8ffed",
    "engine/scenekit.js": "68471c3799744fee",
    "engine/styles.js": "66b00b1b5f87326f",
    "engine/three-kit.js": "02e249e302b95420",
    "engine/ui2d.js": "061cbdf8d34cabe1",
    "examples/reaction-time/config.json": "9ee341c65b3cfe9a",
    "examples/reaction-time/scenes/cast.js": "e4faad3c508a5cf5",
    "examples/reaction-time/scenes/sets/cafe.js": "fb9adaa553e87b74",
    "examples/reaction-time/scenes/sets/lab.js": "a2da3ca0fff2d8c4",
    "examples/reaction-time/scenes/shots/01_cafe.js": "931e9c360ba052b3",
    "examples/reaction-time/scenes/shots/02_orbit3d.js": "77897bcae80a501e",
    "examples/reaction-time/scenes/shots/03_explain.js": "c22f0e7a8f505c78",
    "examples/reaction-time/story/bible.md": "e22b689a54461b41",
    "examples/reaction-time/story/shots.json": "9b1921e8e42c2498",
    "live.html": "9d1a83b5b29513d6",
    "package.json": "a69ab6c53a47f900",
    "player.html": "5ffdd7da4a48cd4b",
    "render.mjs": "6a3505c70bf57abf",
    "tools/beats.py": "eb42a8aef4d87584",
    "tools/common.py": "e237321f2f12416e",
    "tools/direction_check.py": "f34dafeb2757ff45",
    "tools/doctor.py": "a16207eea3196e73",
    "tools/live.mjs": "1e242bb43b8546c7",
    "tools/new_project.py": "940758644aa95289",
    "tools/parse_script.py": "5163cf3162b2579b",
    "tools/transcribe.py": "ecd48d05a6655d13",
}
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
