---
name: make-2d-video
description: "This skill should be used when the user wants a narrated animated video in the Razgon 2D style (cinematic stick figures with rim light, moody 2.5D sets, giant face close-ups, freeze-frames, data overlays, blueprint diagrams and low-poly 3D shots), e.g. \"make a 2D video from this voiceover\", \"animate my script\", \"turn this narration into a stick figure video\", \"make a What If video\", \"create an animated explainer from my audio\", or \"do the whole video\". It runs the full pipeline: install, timestamps (Whisper), story breakdown, style choice, scene building, rendering, music, SFX and final MP4 in 16:9 or 9:16 at 720p to 4K.\n"
metadata:
  version: "0.1.0"
  author: Razgon
---

# Razgon 2D Studio: full video pipeline

Turn a voiceover (plus an optional script) into a finished MP4 where every frame is drawn by code (HTML canvas + Three.js), captured frame by frame in headless Chromium and encoded with ffmpeg. No image or video generation models are used, so characters stay consistent and text stays crisp. Invent the visuals fresh for every script; only the style is fixed.

**Bundled resources (this skill's base directory):**
- `kit/`: the tested studio (renderer, engine, tools, audio, the `examples/reaction-time` reference project). Install it into the workspace as `razgon-2d-studio/` (see `references/install.md`).
- `references/install.md`: install, dependency table, doctor, self-test.
- `references/storytelling.md`: **the story** (episodes, continuity across cuts, explanations that dive out of the story and back, variety budget, banned slideshow patterns). Read it before Stage 4 and before every Stage 6 batch.
- `references/director-pass.md`: **the motion** (camera speed waves, weight, motion blur, designed transitions, kinetic type, sound on events). Read it with the style bible before designing any shot.
- `references/style-bible.md`: **the look** (characters, sets, light, camera, editing, graphics, 9:16 rules, don'ts). Read it fully before designing any shot.
- `references/story-breakdown.md`: writing `story/bible.md` and `story/shots.json`, plus pacing rules.
- `references/engine-api.md`: the scene API, config and shots.json schemas, and the three-kit reference.
- `references/sound-design.md`: the music plan, SFX library, ambience and levels.
- `references/render-qc.md`: preview and final render, speed guide, QC checklist, troubleshooting.

Stage commands from this plugin re-run one stage: `/new-video` (stages 1–4), `/video-styles` (5), `/render-video` (6 and 8), `/video-sound` (7). When running end to end, follow this file and load references as each stage needs them.

## Golden rules
1. **Keep the narration intact.** Never rewrite, add, drop or reorder spoken words. Every shot illustrates the words spoken while it is on screen.
2. **Same style, new pictures.** Invent sets, props, characters and actions from this script. Use `examples/reaction-time` only to learn the API.
3. **Show what is said, literally and specifically.** Abstract lines become visual metaphors, diagrams or close-up reactions.
4. **Draft, look, fix, then render.** Open contact sheets and stills yourself (read the PNGs) before any full render. Rendering is slow; looking is fast.
5. **Three user checkpoints:** setup choices, style choice from rendered samples, and the preview before the final render. If the user is away, take the defaults, state what was assumed, and continue.
6. **Write the beats yourself, by meaning, and film each as a long take.** No script splits the narration; you start a new beat where the narration changes the subject (storytelling.md §0). Inside a beat the camera travels instead of cutting.
7. **Direct episodes, not sentences.** Plan the film as 10–20 continuous episodes (one place, one through-action, one camera idea, a visible change from start to end). Shots are cuts inside an episode, never one shot per sentence. See `references/storytelling.md`.
8. **Every shot is written for its moment.** Share sets and helpers, never shots: no template registry that stamps the same composition with different text. Run `tools/direction_check.py` before every long render and fix every FAIL.
9. **Nothing pops, every cut earns itself.** Every element enters and leaves with motion or a fade; text stays for its reading time and lives in film `overlays` when it would be cut off; a cut changes at least two of place, size, angle and subject, otherwise move the camera instead (storytelling.md §4).
10. **Files are the truth.** Each video lives in `razgon-2d-studio/projects/<slug>/`, and `story/shots.json` owns all timing.

## Stage 1: Intake
Ask once (AskUserQuestion when available) for:
- **Voiceover file** (required).
- **Script:** timestamped (SRT/VTT/JSON/TXT with `[mm:ss]`), plain text (best: aligned to the audio, keeping exact wording), or none (transcribed).
- **Aspect:** 16:9 or 9:16.
- **Resolution:** 720p / 1080p (recommended) / 1440p / 2160p (4K). Mention that higher resolutions take much longer to render.
- **Captions:** default on for 9:16, off for 16:9.
- **Music:** generated, the user's own file, or none. **SFX:** on or off.
- **Title.**

Don't ask about style yet. Defaults: 16:9, 1080p, 24 fps, generated music + SFX, style `dusk`.

## Stage 2: Install or check the studio
Follow `references/install.md`: copy `kit/` to `razgon-2d-studio/` in the workspace (skip if already present), install dependencies, run `python tools/verify_kit.py` and `python tools/doctor.py`, then run the example self-test. Report what was installed in one short list.

## Stage 3: Project + timeline
Run inside `razgon-2d-studio/`. Use `python3` where `python` isn't Python 3.
```bash
python tools/new_project.py --name <slug> --voice "<voiceover path>" [--script "<script path>"] --aspect 16:9 --resolution 1080p --title "<title>" [--captions]
```
- Timestamped script: `python tools/parse_script.py --project projects/<slug> --script projects/<slug>/input/script.<ext>`
- Plain script: `python tools/transcribe.py --project projects/<slug> --script projects/<slug>/input/script.txt --lang en --model small`. The match must be ≥ 90%; if it's lower, tell the user the script and audio differ.
- No script: `python tools/transcribe.py --project projects/<slug> --lang en --model small` (`base` on slow machines, `large-v3` for hard audio).

Check `timeline/transcript.txt` (its end should be near the voiceover length), then run `python tools/beats.py --project projects/<slug>` to get the beat sheet and a draft `story/shots.json`.

## Stage 4: Story breakdown
Read `references/storytelling.md`, `references/style-bible.md`, `references/director-pass.md` and `references/story-breakdown.md`. Write `story/bible.md` (logline, cast with one signature colour each, locations with moods and key lights, motifs, music plan) and, before any shot, the **episode list**: for each episode its time range, place, through-action, start state → end state, camera idea, entry/exit transition, and which lines are acted versus explained (storytelling.md §1–2). Give every shot in shots.json an `"episode"` field. Write `scenes/cast.js`. Write `story/beats.json` by meaning (storytelling.md §0), then `story/shots.json`: contiguous long takes, one per beat by default (a median of 10–25 s, 1–4 cuts per minute), a revealing camera move for each new location, and a concrete `scene` description for each. For the key shots (hook, title, freezes, climax) write 3–4 different options in the bible and pick one. Choose each non-cut transition together with both shots it joins (`whip`/`push`/`iris`/`match`/`smash`, director-pass.md §4). Run `python tools/direction_check.py --project projects/<slug>` and fix every FAIL. Send the user a 5–10 line plan summary (the episodes, not the shots) and continue unless they object.

## Stage 5: Style choice
Build the 1–2 most-used sets plus 3 representative shots (a wide shot with ≥ 2 characters, a `bigFace` close-up, a data/blueprint or 3D shot). Then render:
```bash
node render.mjs --project projects/<slug> --styles dusk,midnight,golden,neon,storybook --at <t1>,<t2>,<t3> --scale 0.5
```
Open `build/styles/style_grid.png`, then show it with one line per style: **dusk** (mauve shadows, amber key, cream rim), **midnight** (cold navy, blue-white rims, sodium practicals), **golden** (warm orange and teal), **neon** (deep blacks, magenta and teal), **storybook** (soft pastel, low contrast). Save the pick in `config.json` → `style`. For tweaks, add a custom entry to `STYLES` in `engine/styles.js` (moods overrides plus the `grade` lift/gamma/gain, sat, contrast, vignette, grain, bloom) and re-render that row.

## Stage 6: Build every shot
Read `references/engine-api.md`, `references/director-pass.md`, `references/storytelling.md` and the example scenes in `examples/reaction-time/scenes/` once. Work **one episode per batch**:
1. Write `scenes/sets/<location>.js` (reusable, anchored to `GY = E.H * V(0.8, 0.68)` and `CX = E.W/2`, with walls, floor and sky extended past the frame) and `scenes/shots/NN_<episode>.js` with one `registerShot('<id>', {...})` written for each shot of the episode. Drive the episode's camera and the hero's state from global time (`camGlobal`, helpers of `info.globalT`) so cuts inside the episode continue instead of resetting.
2. Run `node render.mjs --project projects/<slug> --sheet --scale 0.5`. Open every `build/sheets/sheet_XX.png` and check it against the QC checklist in `references/render-qc.md`. Fix any MISSING shots, errors printed by the renderer, and composition problems.
3. Before saying anything is ready, run the frame review: `python3 tools/frame_review.py --project projects/<slug> sheets` (three stills of every frame), open every `build/review/review_NN.png`, mark each frame ok or bug with `frame_review.py ... mark`, fix and repeat until `frame_review.py ... status` exits 0 (render-video §1c, render-qc.md «Frame review»).
4. Check motion with `--stills t1,t2,t3` or `--from A --to B --scale 0.5` (writes `build/preview.mp4`). Render each finished episode as a preview and run `python tools/direction_check.py --project projects/<slug> --video build/preview.mp4` on it: static holds and a jumpy cut rate show up there before the viewer sees them.

Non-negotiables from the style bible:
- Rim light on every lit figure.
- Colours from `mood()`/`S()`.
- A motivated camera move in every shot (`camPath`/`travel`, not a lone linear zoom), and a soft foreground in most medium shots.
- Weight on every arrival and contact (`spring`, `posesSpring`, `impact`); kinetic type for titles and slammed words.
- `"mb"` motion blur only on fast shots; check transitions and impacts with `--stills` inside them.
- Atmosphere (dust, rain, glows).
- Moody value structure.
- Graphics synced to words with `wordTime()`.
- Key text in film `overlays` (engine-api.md), never shorter than its reading time; no element appears or disappears in one frame; no jump cuts. `tools/direction_check.py --video` must show 0 pops, 0 jump cuts and 0 static holds.
- `V()` for every aspect-dependent value.
- No `Math.random`/`Date.now`.

## Stage 7: Sound
Read `references/sound-design.md`. Fill `story/shots.json` → `music` (contiguous mood sections) and add per-shot `sfx` cues and `amb` beds. Put a cue on every new visual event from the director pass (door stop, slammed word, landing, smash cut) at the frame it happens. Mixing happens after the final render (Stage 8), or run `python audio/mix.py --project projects/<slug>` now to audition `build/mix.wav`.

## Stage 8: Render and deliver
Read `references/render-qc.md`.
1. Preview: `node render.mjs --project projects/<slug> --from 0 --to 30 --scale 0.5` (better: the first full episode). Run `tools/direction_check.py` on shots.json and on the preview, then show the user the preview before the long render.
2. Final: `node render.mjs --project projects/<slug>`. Run it in the background for long videos and poll the log. The log prints fps and ETA, so share the estimate.
3. Run `python audio/mix.py --project projects/<slug>`, which generates music and SFX, ducks the music under the voice, normalises to −14 LUFS and muxes `out/<title>.mp4`.
4. QC the final file: duration matches, audio is present, a 1-frame-per-10-s contact sheet looks right, and the transitions and impacts look right in motion (director-pass.md §8). Deliver the MP4 (send the file), then give the location in plain words and one line on what to tweak next if needed.

## Defaults and judgement calls
- When unsure about a visual, choose the more literal, more cinematic option: a close-up for emotion, an insert for objects, a blueprint for mechanisms, 3D for big spaces.
- Long takes: about 1–4 cuts per minute, median take 10–25 s, one take per meaning beat (storytelling.md §0). Use 1–3 freeze-frames per video and a 3D move every 1–2 minutes.
- Keep each character's outfit colour fixed for the whole video, and keep screen direction consistent within a scene.
- Prefer re-rendering a fixed shot range over the whole video only when the user is comfortable splicing. Otherwise re-render everything.
