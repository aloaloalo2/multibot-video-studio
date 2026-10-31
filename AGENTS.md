# Planning ownership

## Video production workflow

Before planning or editing a video with this Studio, read [docs/AI_VIDEO_WORKFLOW.md](docs/AI_VIDEO_WORKFLOW.md) and the applicable channel instructions. Use the Studio's saved channel settings and verify the plan and project through its local API.

## Native timeline regression checks

Visual clip times must quantize their absolute start and end with the same deterministic frame-index function. Never independently round duration and start, as that creates one-frame gaps or overlaps at touching boundaries. Keep spoken audio and ASR times unchanged. Check every decoded frame in a fractional-boundary render.

The final composition may extend by one output frame to cover a fractional audio end. Keep interior edit boundaries and speech timestamps unchanged; never introduce an empty rounding frame at the end. Exported circular and rounded masks must retain antialiased edges at their final size.

Keep preview media DOM nodes keyed by clip/source. Removing an outgoing transition clip must not reload the incoming image or video. Preload upcoming media and its source offset. CSS stacking values must be integers; graphic covers sit above scene media and below permanent branding. Test transition application, moving an existing transition, invalid drops, hover previews, and both sides of the final frame in the real browser.

Transition favorites are local editor preferences. A cut is the default absence of a join and is omitted from the library. Applied joins can be removed with their context menu. Visual effects share one preset definition between preview and export, must be reversible, and must not alter source media or voice audio.

Use cached small thumbnails and lazy image loading in the library. Do not load source-sized review sheets or every original video just to draw library cards.

Prefer the Studio's local script or HTTP API for plan creation, regeneration, and other supported production operations to save time and tokens. Verify plans through code/API/JSON and return plan_url for the user to review. The agent's browser remains available when useful, including for visual verification and operations the API does not support.

The scene planner belongs to this Studio. Keep the planning implementation in `backend/planner.py` and execute it through `store.generate_project_plan`. Read the channel's saved settings at execution time. A project's older settings snapshot and client-supplied settings cannot replace them.

`tools/video_plan.py` is a compatibility HTTP client. Keep it free of planning logic and local fallback generation. Channel settings are edited in Studio; the former standalone settings editor is retired.

Store each generated plan's settings snapshot, settings signature, generator identity and script hash. Show a stale-plan notice when saved channel settings have changed. Preserve the project identity, existing montage and previous plan when regenerating.

Ignore retired `opening_seconds`, `opening_clip_count` and `opening_clip_types` in new plans. Opening formats follow `first_clip_format` and `first_clip_count`; automatic mode prefers an enabled video format first and otherwise uses the normal weighted plan. `first_clip_seconds=0` uses normal timing; a positive value sets the first frame duration without choosing its format. Show actual format shares by duration separately from target settings. Hints are explicit exceptions.

For planning changes run `python3 -m unittest discover -s backend/tests -v` and the compatibility client tests in `../tools/tests/test_video_plan.py`. Cover current saved settings, zero first clip with legacy keys, stale detection, preserved montage and offline failure. Verify UI changes in the embedded Codex browser.

## Post-Whisper number text

After real phrase timings or a successful local Whisper comparison, format written-out quantities as digits in the actual saved script, phrase text and text inserts for every channel. Use backend/number_text.py. Keep spoken_script, its hash and an immutable spoken-source TXT separately; preserve ASR word boundaries when collapsing multiword numbers. Save the numeric script to the matching episode source, preserving unrelated local text. Keep exact fractions distinct from ranges. Draft scripts retain their pre-voice form. Test Russian, Ukrainian, English and German cases, value mismatches, genuine ASR boundaries and idempotent regeneration.

## Video production workflow

Before planning or editing a video with this Studio, read [docs/AI_VIDEO_WORKFLOW.md](docs/AI_VIDEO_WORKFLOW.md) and the applicable channel instructions. Use the Studio's saved channel settings and verify the plan and project through its local API.

## Animated films: voice first, director frames, start production

A new episode opens on the plan with a voice drop zone and an optional voice text; without text the transcript becomes the script (`analysis_jobs.start(..., script=None)`). An animated channel never gets a plan split from the script alone: `generate_project_plan` without audio or timings calls `store.await_voice`, which keeps the script on the project as `voice_script` (shown in the voice text field and used by the recognition), moves a script-only draft to `plan-history`, refuses to replace a voice or director plan, and answers `awaiting_voice` (test: `test_animated_channel_waits_for_voice_instead_of_splitting_the_script`). The editor stays closed until the timeline holds a frame of the film (see «The plan page» below). A plan with `frame_source: razgon-direction` keeps its director's sentence groups through every rebuild (`planner.keep_director_frames`); changed sentences mark it `director_stale`. Such plans show «Почати створення ролика» instead of plan regeneration; the request (`POST /api/projects/<id>/production-request`) is stored on the project and mirrored to `Запит на створення.json`. Speech comparison keeps script words with ASR time in `aligned_words`. Text fields have no focus ring. Restart or start the server only with `python3 tools/studio_restart.py` from this folder: it refuses while exports, speech, director, production, thumbnail or agent jobs run, and starts the server in its own session so it does not die with the agent's shell (on 30 October 2026 a server started with `nohup … &` from an agent session went down with that session).

Frames of an animated film are code until the author presses «Експорт MP4» (user, 30 October 2026): the frame agent (`backend/production.py`) writes the scenes and leaves «Кадр N» code blocks (`razgon_bridge.py slots --frames`), its run is done when `frame_progress.drawn` covers the requested frames and each is a block, and a frame drawn as code counts as made on the plan and the timeline; a request for frames already drawn is refused with 409. Agents the Studio starts run with `MULTIBOT_RENDER_ON_EXPORT=1`, so the bridge refuses `push` and `final`; stopping a run (`director.kill`) also stops the commands Claude Code ran in their own process groups. A cancelled export kills its whole process group after `STOP_GRACE` seconds, even when the bridge is already gone. On a Mac the frames are rendered on the GPU and encoded on the hardware H.264 encoder (`render.mjs` defaults `--gl gpu` and `--encoder videotoolbox` on darwin; the bridge also passes `--gl gpu`): about 10 times faster than the software drawing with x264. The export's progress counts every frame of the film, with the frames already rendered from the same code done from the start. The export's project lock leaves the live preview (`/razgon-live`) free, and the page shows no banner for it. The thumbnail takes stills of code frames through `render.mjs --stills` (`thumbnail_gen.code_stills`). Tests: `test_production.py`, `test_director.py`, `test_export_control.py`, `../tools/tests/test_razgon_bridge.py`.

A Razgon episode (`razgon.json` in the episode folder) exports the same film as `tools/razgon_bridge.py push` + `final`: `backend/razgon_export.py` hands the bridge's `export` command each frame's rendered timeline clip, or null for a code block; the bridge renders those frames longest first, one Chromium worker each and as many at a time as keep the Mac's RAM under 80% (`razgon_bridge.RAM_LIMIT`, about 2.2 GB a Chromium at 1080p; six at once froze a 16 GB Mac on 31 October 2026), reusing build/studio clips stamped with the same times and picture sources, glues them with the channel plate and Razgon's −14 LUFS mix. A Razgon timeline with other clips, Studio transitions or effects (a mixed episode: photos, stock and text frames around some Razgon frames, as Alexey Gorbunov's) exports through the engine: first `razgon_bridge.py frames` renders only its code blocks (the same build/studio cache, each with a 0.5 s held tail for the transition out), then the engine draws each block from its clip (`razgon_export._mixed`, `app._render_razgon_blocks`). The live preview of a mixed episode draws only its `razgon_2d` frames (`frontend/razgon-live.js`). Test: `backend/tests/test_razgon_export.py`.

The voice at 100% is the studio's standard level (`backend/audio_level.py`, user 31 October 2026): the timed voice (the plan's audio asset, or a copy with the same bytes) is measured once (EBU R128) and played and exported with a gain to −16 LUFS, peaks at most −1.5 dBTP; the export mix ends in a −1 dBFS limiter. In the engine an image without a circle mask keeps its shape in the middle of its box (`render.contained`), and a text clip with motion keyframes carries its timed words along (tests in `engine/tests/test_render.py`).

## The plan page and the frame agent, the same for every channel (31 October 2026)

The plan page (`frontend/director.js`, `renderEpisode`) is one column, the same for photo and animated channels, with no
numbered steps: the voice stage as one line (file, length, «розпізнано, збіг N%» and the bin that starts the episode
over) that opens on a click to «Ваш сценарій», «Розпізнаний текст» (what the recognition heard, with its report), «Таблиця кадрів» and «Звіт режисера» (user, 31 October
2026: that stage is passed, the next one stands open; a recognition that needs a look opens it by itself), the
director's state only while it works or needs the author (a stop, a limit pause, a changed text), then «Створення
ролика»: the film as a strip of its frames (on a photo channel each frame in its format's colour from
`planFormatVisuals`), the count picked by a drag across the strip (all frames by default), «Макс» and «Почати створення
ролика». The button stays disabled while `production.plan_ready` is false, while an animated film waits for its
director and while the script is newer than the direction (`director_stale`). «Звіт агента» closes «Створення
ролика». A photo channel's plan from the planner keeps
«Перегенерувати план» in the heading.

Under the voice line stands the voice itself to listen to (`voicePlayer` in `frontend/director.js`, the plan's
`timing.audio.asset_id`): play and pause, a seek bar and the time, inside the page; it stops when the page changes.

«Монтаж» opens with the first frame of the film on the timeline: any clip but sound, the clips of `role: overlay`
groups and clips titled «Логотип» or «Плашка» (`editorUnlocked`/`filmClips` in `frontend/plan.js`, `store.film_clips`);
until then its tab says «Монтаж відкриється з першими кадрами ролика».

«Почати створення ролика» posts the request and goes back to the channel's projects (`showProjectList`). Each project
in `GET /api/projects` carries `production_request` (`status`, `frames`, `limit`, and `made` while the agent works,
`store.production_state`); the card shows «Створюємо кадри · N з M», does not open while the agent works and opens
again once it is done, paused or failed. The list is read again every 8 s while any card is in work. A frame counts as
made (`store.made_frames`) when a film clip covers its middle; a Razgon code block counts once its scene is written;
an animated film counts its frames drawn as code (`frame_progress.drawn`). A request for frames already made is refused
with 409, a second request while one runs too. A request that says the agent works while no agent of this Studio
runs (a restart, a run that never started; 31 October 2026 a finished film read «Створюємо кадри» for good) is settled
by `production.settle` whenever a project or the list is read and at start-up: done when every requested frame is made,
otherwise stopped (a fresh request gets 30 s to start).

`production.start` runs for every channel. A photo channel's agent (`production.photo_brief`, Claude Opus 5.5 at
`xhigh`) reads the plan and makes each frame by its format: the author's own pictures from the episode folder first,
stock through `tools/pixabay.py` (search, download into the episode), pictures drawn by Codex through
`What If/razgon-2d-studio/tools/codex_image.py`, text frames itself and `razgon_2d` frames as code through
`razgon_bridge.py`, and puts each frame at its time with `python3 tools/studio.py place P N FILE|--text` (the montage op
`place`: the plan frame's start and length, a slow zoom on a photo, the group «Кадр N»). People in every frame and every
prompt are stick figures, apart from the host. The run is done when each requested frame is made. Tests:
`backend/tests/test_agent_tools.py`, `backend/tests/test_production.py`, `tools/tests/test_studio.py`.

## Razgon follows the Studio's kit (31 October 2026)

The Razgon plugin with its studio kit lives in this repository (`razgon-plugin/…/make-2d-video/kit`), and Claude copies
the kit into `<YOUTUBE>/…/razgon-2d-studio` on first use. At every start the Studio brings each such copy up to date
(`tools/razgon_sync.py`, `app.razgon_kit_at_start`), so an update of the Studio from GitHub reaches the animation tools
too. A manifest in the copy (`.videokey-kit.json`) records what the Studio wrote: missing files are added, files nobody
changed since are replaced, a file changed by hand is kept and reported, files dropped from the kit are removed only if
unchanged; `projects/`, `node_modules/`, `build/` and `assets/` are never touched, and a changed `package.json` runs
`npm install`. A change to Razgon reaches others only through the kit: change the files in the kit (or copy them there
from the working copy) and push to `main`. Tests: `tools/tests/test_razgon_sync.py`.

## Timeline row order

The higher a timeline row, the higher its layer in the picture (user, 30 October 2026): the last entry of `tracks` is the top layer in the preview and the export, and it is the top row. Rows that hold only sound go under all picture rows. `timelineRowOrder` in `frontend/universal.js` and the row sort in `frontend/groups.js` keep this; a layer that must stay on top (plate, logo) goes to the end of `tracks`.

## Agent tools: one entry point, short answers (31 October 2026)

The user asked that any Claude Code agent can run the studio fast and with few tokens. `tools/studio.py` is the entry
point (commands in CLAUDE.md): `status`, `summary`, `still`, `accent`, `clear-accents`, `replace`, `transitions`, `ops`,
`export`. Behind it: `GET /api/studio/status` (the busy list `studio_restart.py` now reads in one request),
`GET /api/projects/<id>/summary` (`backend/agent_view.py`: a line per frame and its problems; `?format=text`),
`POST /api/projects/<id>/ops` (`backend/montage_ops.py`: high-level operations turned into one batch, one undo step,
checked against `expected_revision`, `dry_run` to look first), `POST /api/projects/<id>/still` (`engine/still.py`: the
export's own renderer draws a window of the render manifest, `STUDIO_GPU_WINDOW_START` in `gpu_prepare.py`) and
`GET /api/projects/<id>/exports`. Accents are glued to the frame's photo: their keyframes repeat the photo's pan and
zoom at the photo's keyframe moments with the photo's easing (`add_clip` takes `easing`), so a point on the picture stays
on it; a label in the black field beside a vertical photo stands still. Caption words take the voice's time through
`backend/word_timing.py` (digit text joined to the spoken words). Accent clips are titled «K012 акцент …».
`transitions` keeps about 70% designed seams: a cut into a full-frame text frame, no transition other than a
crossfade twice in a row, a video going out must have the frames the transition needs. A still never draws Razgon
code frames and says so. Tests: `backend/tests/test_agent_tools.py`, `tools/tests/test_studio.py`.

Every project answer carries `production` and `audio_gain`; `app.derived_state` computes them once per version of what
they read (revision, the plan file, each audio file) instead of on every request (0.2 s on GORBUNOV-23). The summary is
cached the same way. `index.html` is served with each script and stylesheet stamped by its content hash
(`app.versioned_index`): nobody bumps `?v=` by hand any more.

## The preview and the export draw the same picture (31 October 2026)

`engine/tests/test_preview_parity.py` runs the preview's own functions (`frontend/*.js`, through
`engine/tests/preview_js.py` in node) against the engine, and renders what only a film can show. Closed differences:
a vertical video in a 16:9 box was drawn at its box's left edge by both renderers (now contained and centred like an
image, `render.contained` measures videos too); a property whose first keyframe is later than 0 started from that
keyframe in the export and from the clip's own value in the preview (the engine now inserts the clip's value at 0,
the preview's `keyframeValue` reads keyframes the engine's way, and a keyframe at 0 no longer loses to the clip's value
on the first frame); words of a text clip that moves or fades entered with a plain fade in the export and lost the
clip's opacity keyframes (`render.carried_word_keyframes` samples the clip's motion, opacity and the word's entrance
from `render.entrance_state`, a copy of `applyWordEntrance`); a clip still moving at its end keeps its speed through an
outgoing transition in both, one that stopped holds (a single keyframe used to throw the scale far off); transitions
run on whole video frames in the preview too (`joinFrames`: 0.35 s at 25 fps is 9 frames); a rounded mask without a
radius is 8 px in both and rounds the contained picture. Equal already and now held by tests: slide, zoom and
cinematic transitions, transition covers (`graphicShapes` against `transition_graphics.shapes`), contained pictures. The FFmpeg renderer takes some 60 keyframes in one expression (100 failed), so sampled curves stay
under that and `render.window_keyframes` keeps only the keyframes of the scene's moments.
