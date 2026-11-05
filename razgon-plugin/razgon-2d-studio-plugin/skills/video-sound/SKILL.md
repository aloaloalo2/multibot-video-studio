---
name: video-sound
description: "This skill should be used when the user runs /video-sound or asks to \"add music\", \"add sound effects\", \"design the sound\", \"change the music mood\", \"use my own music\", \"the music is too loud/quiet\", \"remix the audio\", or \"redo the soundtrack\" for an Razgon 2D Studio video. It plans mood-based generated music, places SFX and ambience cues on the shot list, mixes them under the voiceover with ducking and loudness normalisation, and muxes the final MP4.\n"
metadata:
  version: "0.1.0"
  author: Razgon
---

# /video-sound: music, SFX, ambience and the final mix

Work inside `razgon-2d-studio/` on the active project. Read `../make-2d-video/references/sound-design.md` (relative to this skill's base directory) first.

## 1. Music plan
- Read `story/bible.md` and the shot list, then write `story/shots.json` → `"music"`: contiguous sections `{start, end, mood, intensity}` that change at story turns (title card, discovery, danger, climax, resolution, explanation), typically every 30–90 s.
- Moods: `mystery, tension, action, wonder, hopeful, sad, triumph, playful, calm, dark, epic`. Intensity 0–1 adds pulse, arpeggios and drums.
- Audition a mood: `python audio/music.py --mood tension --intensity 0.7 --dur 20 --out build/test_tension.wav`, and send the WAV if the user wants to listen.
- **User's own track:** copy it into `projects/<slug>/input/` and set `config.json` → `"music": {"enabled": true, "file": "input/<name>.mp3", "gainDb": -17}`. It loops or trims, and the end fades.
- **No music:** `"music": {"enabled": false}`.

## 2. SFX and ambience
- For the whole film (preferred: it stays put when the shots are cut again): `"sfx": [{"t": <s from the film's start>, "name": "<effect>", "gain": -10}]` at the top of shots.json, about one cue per 15–25 s, never two within 0.3 s.
- Per shot: `"sfx": [{"at": <s from shot start>, "name": "<effect>", "gain": -8}]` (optional `dur`, `seed`, `pitch`; `name` may be a path to the user's own WAV/MP3 inside the project). Per shot ambience: `"amb": {"name": "rain|wind|city|roomtone|murmur|hum", "gain": -20}`.
- List the library with `python audio/sfx.py --list`, or audition it with `python audio/sfx.py --demo build/sfx_demo`.
- Place cues on actions and graphics: `whoosh`/`swish` on whips and fast moves, `pop`/`blip` when graphics appear, `counter` under ticking numbers, `riser` then `impact`/`stinger` on reveals, `slowmo`/`freeze` for time effects, `hit`/`kick`/`footstep` on contact. Never stack more than ~2 cues at the same instant.

## 3. Mix and mux
For a VideoKey Studio episode, regenerate only its soundtrack with `python3 "VideoKey Studio/tools/razgon_bridge.py" sound --razgon <project>`: it builds the bed with `render_bed(project_path)`, encodes it to M4A and replaces the «Razgon · музика й ефекти» clip on the timeline (the Studio runs it by itself after the director and the frame agent). This also works after cache cleanup: the helper must create `build/studio` before writing its bed. Preserve a backup of the old configuration, cue plan and audio. Do not call `push` or render/export video for a sound-only request. Verify the returned bed exists and has the full episode duration before importing it. Keep narration and visual clips intact.

Run `python audio/mix.py --project projects/<slug>`. It ducks the music −9 dB and ambience −5 dB under the voice, normalises to `config.loudness` (−14 LUFS default), writes `build/mix.wav`, and, when `build/video_silent.mp4` exists, writes `out/<title>.mp4`.
- Levels: `config.music.gainDb` (default −17 relative to the voice) and `config.sfx.gainDb` (default −6). Change them by 2–3 dB per iteration.
- QC: listen points or `ffmpeg -i out/<file>.mp4 -af ebur128=framelog=quiet -f null -` (integrated loudness about −14 LUFS) and check that the duration matches the video.


For a new Studio soundtrack, create its own universal layer so the narrator and music can be muted independently. Measure against the Studio's levelled narration; a very quiet source recording can otherwise make the generated bed inaudible. Import a 192 kbit/s AAC/M4A delivery for a long episode instead of an extra uncompressed WAV copy. Keep the editable source and report decode/level checks separately from actual listening.
