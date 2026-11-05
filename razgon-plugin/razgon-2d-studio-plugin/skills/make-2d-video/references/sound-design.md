# Sound design

`audio/mix.py` builds the soundtrack from `story/shots.json`. It ducks the music −9 dB and ambience −5 dB under the voice and normalises the master to −14 LUFS (YouTube), or `config.loudness`.

**Music plan** (`"music"` in shots.json): contiguous sections with a mood and intensity (0–1; higher adds pulse, arps and drums). Moods: `mystery, tension, action, wonder, hopeful, sad, triumph, playful, calm, dark, epic`. Change sections at story turns (the title card, a discovery, danger, the climax, the resolution, the science segment), typically every 30–90 s. Audition with `python audio/music.py --mood tension --dur 20 --out test.wav`. To use the user's own track, set `config.music.file = "input/music.mp3"` (it loops or trims and fades the end). Set `config.music.gainDb` (default −17 relative to the voice) for a louder or quieter bed. The generated music is a serviceable ambient/cinematic bed. For premium results, suggest the user's own licensed track.

**SFX cues** (per shot `"sfx": [{"at": 0.3, "name": "whoosh", "gain": -8}]`, where `at` is seconds from the shot start; optional `dur`, `seed`, `pitch`; `name` can also be a path to the user's own WAV/MP3). Library (`python audio/sfx.py --list`, audition all with `--demo build/sfx_demo`):
`whoosh, swish, impact, hit, riser, slowmo, freeze, tick, clock, heartbeat, pop, blip, counter, ding, shimmer, stinger, footstep, kick, whistle, carpass, phonebuzz, phonering, cheer, applause, murmur, rain, thunder, wind, roomtone, city, hum, powerup, glitch, flash, buzz`.
Conventions: `whoosh`/`swish` on camera whips and fast moves. `pop`/`blip` when graphics appear, `counter` under ticking numbers. `riser` 1–2 s before a big reveal, then `impact`/`stinger` on it. `slowmo` going into slow motion, `freeze` on time-stop. `ding`/`shimmer` for realisations and powers. `hit`/`kick`/`footstep` on contact. Gains: subtle UI −12 to −16, normal −6 to −10, big moments −3 to −6. Don't stack more than ~2 cues at the same instant, and leave dialogue clear.

**Story-level cues** (`"sfx"` at the top of shots.json, next to `"music"`): `[{"t": 81.4, "name": "ding", "gain": -10, "seed": 3, "shot": "e12", "why": "the words it lands on"}]`, where `t` is seconds from the start of the film; `shot` and `why` are notes for the next person and the mix ignores them. They stay at their moment of the voice when the shots are cut again, so a long film directed in several passes keeps them here. Take the time from `timeline/words.json`: the start of the word that names the visible event. About one cue per 15–25 s of film; never two within 0.3 s of each other; quieter (−12 to −16) under a dense sentence. `tools/direction_check.py` counts the cues and the ambience, fails unknown names and cues outside the film, and warns when cues are sparse, crowded or stacked.

**Keep the sound when the shots are generated again.** A script that writes shots.json (`story/gen_shots.py`) must carry the sound over from the file it replaces, or every new cut of the shots silences the film:

```python
old = json.loads((HERE / "shots.json").read_text()) if (HERE / "shots.json").exists() else {}
old_amb = {s["id"]: s.get("amb") for s in old.get("shots", [])}
# per shot: amb=old_amb.get(shot_id); for the story: sfx=old.get("sfx", []), overlays=old.get("overlays", [])
```

Write the cues themselves with a second script (`story/gen_sound.py`: it reads shots.json and timeline/words.json and writes `sfx` and `amb`), and run it after every run of gen_shots.py.

**Ambience beds** (per shot `"amb": {"name": "rain", "gain": -20}`; looped with 0.4 s fades): `rain, wind, city, roomtone, murmur, hum`. Use them on most shots for a continuous world, at −18 to −28.

**In VideoKey Studio** the film's frames stay code until «Експорт MP4», but its sound does not wait for a render: when the director's run and each frame agent's run end, the Studio runs `python3 "VideoKey Studio/tools/razgon_bridge.py" sound --razgon <project>`. It mixes music, SFX and ambience as `audio/mix.py` does under the voice (its `beds()`, block by block, a few GB of RAM for an hour of film), without the voice, and lays the result as the «Razgon · музика й ефекти» clip on its own layer under the channel plate. The live preview and the language soundtracks play it. The export mixes the whole soundtrack again from shots.json.

