# VideoKey Studio — guide for Claude Code

A local video editing studio for the user's YouTube channels: a Python server with a browser UI, an export engine on
FFmpeg and the Apple GPU, and tools for plans, voices and Razgon 2D animation. The user writes in Ukrainian or Russian;
answer in Ukrainian. The detailed rules of every subsystem are in @AGENTS.md and the production workflow in
@docs/AI_VIDEO_WORKFLOW.md — read them before changing a subsystem or making an episode.

## Where things are

- The studio folder sits inside the user's `YOUTUBE` folder; the channel folders (`Алексей Горбунов`, `What If`, …) are
  its siblings, each episode is a folder inside its channel. macOS stores some Cyrillic names decomposed (NFD): find a
  path with `glob` or `ls` instead of typing it.
- `backend/` — the server (`app.py`, HTTP on http://127.0.0.1:8770), the project store and timeline actions
  (`store.py`), the planner (`planner.py`), exports (`razgon_export.py`, `audio_level.py`), speech recognition
  (`analysis_jobs.py`, `speech.py`). Projects, jobs and caches live in `backend/data/` (not in git).
- `frontend/` — plain JS and CSS served by the server. The server stamps every script and stylesheet in `index.html`
  with a hash of its content (`app.versioned_index`), so a changed file reaches the browser on the next reload.
- `engine/` — the export renderer (`render.py`; `gpu_prepare.py` + `gpu_render.swift` on Apple Silicon).
- `tools/` — `studio.py` (the agent's entry point, below), `studio_restart.py`, `razgon_bridge.py` (Razgon 2D ↔ studio),
  `video_plan.py`, `episode.py`, `pixabay.py`, `razgon_sync.py` (brings the Razgon working copy up to the kit at every
  start; a change to Razgon goes into the kit in `razgon-plugin/` to reach other Macs).

## Running the studio

- Start or restart only with `python3 tools/studio_restart.py` (`--check` lists running work). It refuses while an
  export, speech recognition, director, production, thumbnail or agent job runs, and starts the server in its own
  session. Never `kill` the server or run `backend/app.py` from your own shell: it dies with your session. `--force`
  only when the user agreed to cut the running work.
- Frontend changes need only a page reload; backend changes need the restart; the engine runs fresh on every export.

## Working through tools/studio.py

Start here: it answers in a few lines and changes the montage in one checked batch. P is a project id or words that find
one project (`"Горбунов 23"`).

- `python3 tools/studio.py status` — what runs now (the same list `studio_restart.py --check` gives).
- `python3 tools/studio.py summary P [--frames 10-20] [--issues]` — every frame: time, format, picture and its motion,
  accents, the transition out, and problems (gaps, edges off the plan, a photo that leaves the frame uncovered, a video
  too short for its transition, keyframes or words past the clip's end, transitions into text frames, the same
  transition twice in a row, the voice off 100%, the plate not on top).
- `python3 tools/studio.py still P f12` (or `83.4`, `1:23.4`, `f12:start`, `f12:end`) — a PNG of the export at that
  moment, drawn by the export's own renderer, and a link that opens the preview at the same moment (`?t=`). Compare the
  two before saying an edit looks right; Razgon code frames are not drawn in a still.
- `python3 tools/studio.py accent P 12 text --phrase "слова голосу" --at 1290,190 --style card` (or `arrow --from x,y
  --to x,y --word слово`, `circle --at x,y --radii 190,70`, `card --at x,y --size w,h`, `image --path file --at x,y`)
  — an accent in the frame's group, glued to the photo's pan and zoom. Points are pixels of the frame at its middle
  moment, as the still of `f12` shows it; `--space photo` takes fractions of the picture. Words of `--phrase` appear in
  time with the voice. `clear-accents P 12` removes them.
- `python3 tools/studio.py replace P --frame 12 FILE` — a new picture, with the clip's title, box and motion kept.
- `python3 tools/studio.py place P 12 FILE` (or `--text`, `--asset ID`, `--motion zoom_in|zoom_out|none`) — puts frame 12 of
  the plan on the timeline at its time, in the group «Кадр 12»: a picture or a video, or the frame's words as a full-frame
  text. The frame agent of the photo channels builds the film with it.
- `python3 tools/studio.py transitions P [--share 0.7]` — about 70% designed seams by the channel rule (a cut into a
  text frame, no transition other than a crossfade twice in a row, enough video for the transition); prints the planned
  and actual counts. Existing transitions stay unless `--replace`.
- `python3 tools/studio.py ops P ops.json` — several operations at once; `--dry-run` on any change shows the actions.
- `python3 tools/studio.py export P` — the running export and the latest ones (starting one stays the user's button).

## Working through the API

Prefer the API and scripts to clicking. The main calls:

- `GET /api/channels`, `GET /api/projects/<id>` (the project with `tracks`, `scene_groups`, `join_transitions`,
  `production`, `audio_gain`), `GET /api/projects/<id>/plan`, `GET /api/projects/<id>/analysis` (`aligned_words`).
- `POST /api/projects/<id>/actions` with `{"type", "payload", "expected_revision"}`; `"type": "batch"` takes up to 1800
  actions. Clip actions: `add_clip` (each clip opens a layer of its own; `group_id` puts it into a frame group),
  `update_clip`, `move_clip`, `trim_clip`, `replace_clip_asset`, `set_clip_volume`, `delete_clip`, `move_layer`,
  `group_clips`, `set_join_transition` (`"type": "cut"` removes one). Positions are frame fractions of the clip's centre.
- `POST /api/projects/<id>/assets/pick` `{"path"}` imports a file from the episode folder.
- `POST /api/projects/<id>/plan` writes a plan; `GET /api/projects/<id>/export/active` shows a running export.
- The agent's calls behind `tools/studio.py`: `GET /api/studio/status`, `GET /api/projects/<id>/summary`,
  `POST /api/projects/<id>/ops`, `POST /api/projects/<id>/still`, `GET /api/projects/<id>/exports` (backend/README.md).
- Starting an export (`POST /api/projects/<id>/export`) is the user's button: do it only when asked.

## Rules that are easy to break

- Frames of Razgon 2D animation stay code until the user presses «Експорт MP4»: put them on the timeline as
  «Razgon · кадр NNN» blocks (`razgon_bridge.py slots`), let «Наживо» show them, never render them yourself. The export
  renders the blocks (`razgon_bridge.py export` for an all-Razgon film, `frames` for a mixed one) and builds the video.
- The voice at 100% is the studio's standard level (`audio_level.py`: −16 LUFS, peaks ≤ −1.5 dB); leave the voice clip
  at volume 1.0. The export mix has a −1 dBFS limiter.
- The preview (`frontend/*.js`) and the export (`engine/`) draw the same picture; `engine/tests/test_preview_parity.py`
  runs the preview's own functions in node against the engine. An image or a video keeps its shape in its box and sits
  in the middle (object-fit: contain); a first keyframe later than 0 starts from the clip's own value; a text clip that
  moves or fades carries its timed words, each with its own entrance; transitions run on whole video frames. Change
  both sides together, extend the parity test, and check the result with `studio.py still` against the preview.
- The last entry of `tracks` is the top layer; the channel plate stays on top.
- Keep the user's machine usable: own test renders with one Chromium and `nice`, RAM under 80%.

## Checking changes

- Backend: `bash -c 'python3 -m unittest $(ls backend/tests/test_*.py | sed "s#/#.#g; s#\.py\$##")'`
- Engine: `bash -c 'python3 -m unittest $(ls engine/tests/test_*.py | sed "s#/#.#g; s#\.py\$##")'`
- Tools: `cd tools && bash -c 'python3 -m unittest $(ls tests/test_*.py | sed "s#/#.#g; s#\.py\$##")'`
- Preview against export only: `python3 -m unittest engine.tests.test_preview_parity` (needs node and ffmpeg).
- UI: open the page in the browser, reload, look at the real screen (not only the DOM), check the console.
