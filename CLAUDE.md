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
- `frontend/` — plain JS and CSS served by the server. After changing a file there, bump its `?v=` in `index.html`,
  or the browser keeps the old one.
- `engine/` — the export renderer (`render.py`; `gpu_prepare.py` + `gpu_render.swift` on Apple Silicon).
- `tools/` — `studio_restart.py`, `razgon_bridge.py` (Razgon 2D ↔ studio), `video_plan.py`, `episode.py`, `pixabay.py`.

## Running the studio

- Start or restart only with `python3 tools/studio_restart.py` (`--check` lists running work). It refuses while an
  export, speech recognition, director, production, thumbnail or agent job runs, and starts the server in its own
  session. Never `kill` the server or run `backend/app.py` from your own shell: it dies with your session. `--force`
  only when the user agreed to cut the running work.
- Frontend changes need only a page reload; backend changes need the restart; the engine runs fresh on every export.

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
- Starting an export (`POST /api/projects/<id>/export`) is the user's button: do it only when asked.

## Rules that are easy to break

- Frames of Razgon 2D animation stay code until the user presses «Експорт MP4»: put them on the timeline as
  «Razgon · кадр NNN» blocks (`razgon_bridge.py slots`), let «Наживо» show them, never render them yourself. The export
  renders the blocks (`razgon_bridge.py export` for an all-Razgon film, `frames` for a mixed one) and builds the video.
- The voice at 100% is the studio's standard level (`audio_level.py`: −16 LUFS, peaks ≤ −1.5 dB); leave the voice clip
  at volume 1.0. The export mix has a −1 dBFS limiter.
- An image keeps its shape in its box and sits in the middle (as the preview's object-fit: contain); a text clip with
  keyframes moves its timed words along. Keep the preview and the export showing the same picture; check an export
  change on a real slice of a project (cut its render manifest in `backend/data/projects/<id>/renders/`).
- The last entry of `tracks` is the top layer; the channel plate stays on top.
- Keep the user's machine usable: own test renders with one Chromium and `nice`, RAM under 80%.

## Checking changes

- Backend: `bash -c 'python3 -m unittest $(ls backend/tests/test_*.py | sed "s#/#.#g; s#\.py\$##")'`
- Engine: `bash -c 'python3 -m unittest $(ls engine/tests/test_*.py | sed "s#/#.#g; s#\.py\$##")'`
- Tools: `cd tools && bash -c 'python3 -m unittest $(ls tests/test_*.py | sed "s#/#.#g; s#\.py\$##")'`
- UI: open the page in the browser, reload, look at the real screen (not only the DOM), check the console.
