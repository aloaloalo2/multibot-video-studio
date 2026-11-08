# Planning ownership

## Production efficiency (5 November 2026)

Project cards show compact OpenRouter, Claude Code and ElevenLabs spending icons in one compact row near the bottom only on hover/focus. Hide every provider badge, including Claude Code, when the recorded amount is zero and there are no unknown charges. Read `/api/projects/<id>/costs` lazily and cache it; do not read every project's full logs on the overview request. Persist the cumulative receipt index in `project-costs.json`, deduplicate OpenRouter request IDs, stable paid voice take IDs (including samples/retries/history), and refreshed Claude reports by log. Cached reused audio adds no charge. Keep unknown amounts unknown and estimates marked `≈`. Claude Code card dollars show the author-selected rough subscription allocation: recorded API-equivalent USD divided by 35, always marked ≈. Keep original API-equivalent receipts unchanged and show the raw amount and divisor in the tooltip. This coefficient is the author's display convention, not an official billing conversion. ElevenLabs dollars are an approximate allocation using the published subscription credit package, including the user-specified 20% tax, excluding promotions; never divide by the current balance including rollover. Retain the sanitized conversion basis locally so card hover never contacts ElevenLabs. The muted sum beside «Мови» includes translations and estimated narration; voice credits remain available in the source receipts. No paid work is started by cost reporting.

Language UI reads use `store.read_snapshot()` to reuse identical JSON within one read-only request. The compact language overview omits obsolete review text and full reference transcripts. Exact number-aware assessments and local language checks are reused only for matching inputs, including detector version and phrase timings. Keep all quality checks for changed text. UI catalogue reads use `eleven_api.ui_catalog()` and one background refresh; opening a tab must not wait for remote history pages. The montage voice switcher opens immediately and reads only `/api/projects/<id>/languages/voices`, never the full overview. Cache its options briefly per project and ignore a late response after a project switch or menu close.

Use the compact derived handoff `production-context.txt` and `tools/studio.py work P` before scene work. Preserve the accepted Studio frame ids/times and Razgon shots; see [docs/PRODUCTION_EFFICIENCY.md](docs/PRODUCTION_EFFICIENCY.md). Repair requests and pause/limit continuations start fresh Claude sessions with a compact disk checkpoint, author wishes and remaining frame ids; never replay the old conversation. Each repair keeps a separate cost log. Review new/changed frame dependencies and adjacent cuts once through `frame_review.py`, retaining unchanged stills/verdicts and requiring a current whole-film status. Keep checks for genuine visual defects, including detached neon contours. Asset selection uses saved picks, one bounded library search/contact sheet, then generation when no candidate fits. Do not lower the user's chosen model/effort or start paid production for a workflow test.

## Video production workflow

Before planning or editing a video with this Studio, read [docs/AI_VIDEO_WORKFLOW.md](docs/AI_VIDEO_WORKFLOW.md) and the applicable channel instructions. Use the Studio's saved channel settings and verify the plan and project through its local API.

## Optional frame planning (3 November 2026)

Read the project's own `plan_mode` before starting work; the channel supplies only the default for new projects. `director` is the default and follows the voice-first planning rules below. `direct` is the author's «Без плану» mode: open the ordinary editable montage immediately, including an empty project. Keep the «Озвучка» tab with source audio, script, transcription and measured phrase timings. Store those in `source-timing.json`, without inventing a frame plan; use `store.load_project_narration` for narration consumers. `GET /api/projects/<id>/plan` returns this source in `source`. Never launch the director or require plan proportions, opening formats, a frame table or plan approval in this mode. Channel proportions and visual preferences remain useful guidance.

For direct montage, agents use the normal asset and timeline action APIs, including scene groups, clip timing, motion, text and transitions. Source audio is optional for editing and export; a valid visible film timeline is required for export. Keep ordinary media validation, export locks and output checks. The numbered-frame `place`, `frames` and legacy Razgon bridge workflows still require a director frame plan; do not fabricate one to use them in direct mode. Existing Razgon projects and prior frame plans stay intact when changing a channel's mode. The mode switch must not erase or rebuild any montage, source, translation or paid media. Returning to `director` restores that workflow's plan as the active source. An explicit episode restart archives both plan and source metadata.

## Native timeline regression checks

Visual clip times must quantize their absolute start and end with the same deterministic frame-index function. Never independently round duration and start, as that creates one-frame gaps or overlaps at touching boundaries. Keep spoken audio and ASR times unchanged. Check every decoded frame in a fractional-boundary render.

Razgon export must accept untouched code blocks saved by the former Python banker-rounding rule. Canonicalize only exact old/current endpoints from the matching project, script, audio and FPS in the export snapshot. Keep the real-move check strict; never use a blanket one-frame tolerance or alter rendered media. Test both the engine manifest and an actual exported seam before changing this compatibility path.

The final composition may extend by one output frame to cover a fractional audio end. Keep interior edit boundaries and speech timestamps unchanged; never introduce an empty rounding frame at the end. Exported circular and rounded masks must retain antialiased edges at their final size.

Keep preview media DOM nodes keyed by clip/source. Removing an outgoing transition clip must not reload the incoming image or video. Preload upcoming media and its source offset. CSS stacking values must be integers; graphic covers sit above scene media and below permanent branding. Test transition application, moving an existing transition, invalid drops, hover previews, and both sides of the final frame in the real browser.

Transition favorites are local editor preferences. A cut is the default absence of a join and is omitted from the library. Applied joins can be removed with their context menu. Visual effects share one preset definition between preview and export, must be reversible, and must not alter source media or voice audio.

Use cached small thumbnails and lazy image loading in the library. Do not load source-sized review sheets or every original video just to draw library cards.

Prefer the Studio's local script or HTTP API for plan creation, regeneration, and other supported production operations to save time and tokens. Verify plans through code/API/JSON and return plan_url for the user to review. The agent's browser remains available when useful, including for visual verification and operations the API does not support.

The scene planner belongs to this Studio. Keep the planning implementation in `backend/planner.py` and execute it through `store.generate_project_plan`. Read the channel's saved settings at execution time. A project's older settings snapshot and client-supplied settings cannot replace them.

`tools/video_plan.py` is a compatibility HTTP client. Keep it free of planning logic and local fallback generation. Channel settings are edited in Studio; the former standalone settings editor is retired.

Store each generated plan's settings snapshot, settings signature, generator identity and script hash. Show a stale-plan notice when saved channel settings have changed. Preserve the project identity, existing montage and previous plan when regenerating.

Ignore retired `opening_seconds`, `opening_clip_count` and `opening_clip_types` in new plans. Opening formats follow `first_clip_format` and `first_clip_count`; automatic mode prefers an enabled video format first and otherwise uses the normal weighted plan. `first_clip_seconds=0` uses normal timing; a positive value sets the first frame duration without choosing its format. Show actual format shares by duration separately from target settings. Hints are explicit exceptions.

For planning changes run `python3 -m unittest discover -s backend/tests -v` and the compatibility client tests in `tools/tests/test_video_plan.py`. Cover current saved settings, zero first clip with legacy keys, stale detection, preserved montage and offline failure. Verify UI changes in a real browser.

## Post-Whisper number text

After real phrase timings or a successful local Whisper comparison, format written-out quantities as digits in the actual saved script, phrase text and text inserts for every channel. Use backend/number_text.py. Keep spoken_script, its hash and an immutable spoken-source TXT separately; preserve ASR word boundaries when collapsing multiword numbers. Save the numeric script to the matching episode source, preserving unrelated local text. Keep exact fractions distinct from ranges. Draft scripts retain their pre-voice form. Test Russian, Ukrainian, English and German cases, value mismatches, genuine ASR boundaries and idempotent regeneration.

The formatter only finds numbers; the agent decides how each sentence reads (user, 5 November 2026: «знаходити їх скриптом, але переводити… вручну»). `python3 tools/studio.py numbers P` lists every sentence the formatter changed; `numbers P FILE.json [--dry-run]` saves `{spoken sentence: studio text}` as the plan's `number_fixes` (`store.number_fixes`, `GET/POST /api/projects/<id>/number-fixes`). Keep quantities, percentages, years, dates, money, measures and list numbers as digits; keep words such as an indefinite «один», ordinal adjectives, «полгода», «половину», German «erst»/«als Erstes»/«einer Sekunde». A fix may change only how numbers are written (`planner.check_number_fix`); fixes survive plan rebuilds and director passes and are written to the episode's «Сценарий.txt». Test: `backend/tests/test_number_fixes.py`.

## Every channel: voice first, the director's frames, a light plan page (31 October 2026)

The user: «без озвучки план не може бути згенерований. І план завжди робить клод-код, тобто режисер… на основі тих
пропорцій, які були вказані в каналі». `generate_project_plan` without audio or timings answers `awaiting_voice` on every
channel (`store.await_voice`). Once the voice is recognised, `director.after_voice` starts Claude Opus 5.5 (high) on every
channel; a photo episode already cut on an older plan keeps it (`director.montage_started`). For a photo or video channel
the director only plans the frames (`director.frames_brief`): `tools/studio.py sentences P` gives the numbered sentences
with times and the channel's format shares, the director groups whole sentences by meaning, gives each frame a format
and an idea, and `tools/studio.py frames P FILE [--dry-run]` hands them in. `backend/director_plan.py` checks every
sentence once and in order, at most `max_sentences_per_scene` a frame, only the channel's formats, its opening format,
at most five frames of one format in a row (Razgon scenes excepted) and each format's share within ±5 points of the
channel's, and saves the frames as a director plan (`frame_source` stays `razgon-direction`, the marker of a director's
frames; `visual` holds the idea and survives re-recognition). The plan page is described in «The plan page and the
frame agent» below; it has no cost estimate, stage tag or notes. Tests:
`backend/tests/test_director_plan.py`, `test_director.py`.

## Animated films: voice first, director frames, start production

A new episode opens on the plan with a voice drop zone and an optional voice text; without text the transcript becomes the script (`analysis_jobs.start(..., script=None)`). An animated channel never gets a plan split from the script alone: `generate_project_plan` without audio or timings calls `store.await_voice`, which keeps the script on the project as `voice_script` (shown in the voice text field and used by the recognition), moves a script-only draft to `plan-history`, refuses to replace a voice or director plan, and answers `awaiting_voice` (test: `test_animated_channel_waits_for_voice_instead_of_splitting_the_script`). The editor stays closed until the timeline holds a frame of the film (see «The plan page» below). A plan with `frame_source: razgon-direction` keeps its director's sentence groups through every rebuild (`planner.keep_director_frames`); changed sentences mark it `director_stale`. Such plans show «Почати створення ролика» instead of plan regeneration; the request (`POST /api/projects/<id>/production-request`) is stored on the project and kept in internal `backend/data/projects/<id>/production-request.json`. Speech comparison keeps script words with ASR time in `aligned_words`. Text fields have no focus ring. Restart or start the server only with `python3 tools/studio_restart.py` from this folder: it refuses while exports, speech, director, production, thumbnail or agent jobs run, and starts the server in its own session so it does not die with the agent's shell (on 30 October 2026 a server started with `nohup … &` from an agent session went down with that session).

Frames of an animated film are code until the author presses «Експорт MP4» (user, 30 October 2026): the frame agent (`backend/production.py`) writes the scenes and leaves «Кадр N» code blocks (`razgon_bridge.py slots --frames`), its run is done when `frame_progress.drawn` covers the requested frames and each is a block, and a frame drawn as code counts as made on the plan and the timeline; a request for frames already drawn is refused with 409. Agents the Studio starts run with `MULTIBOT_RENDER_ON_EXPORT=1`, so the bridge refuses `push` and `final` (its `sound` renders no picture and stays allowed); stopping a run (`director.kill`) also stops the commands Claude Code ran in their own process groups. A cancelled export kills its whole process group after `STOP_GRACE` seconds, even when the bridge is already gone. On a Mac the frames are rendered on the GPU and encoded on the hardware H.264 encoder (`render.mjs` defaults `--gl gpu` and `--encoder videotoolbox` on darwin; the bridge also passes `--gl gpu`): about 10 times faster than the software drawing with x264. The export's progress counts every frame of the film, with the frames already rendered from the same code done from the start. The export's project lock leaves the live preview (`/razgon-live`) free, and the page shows no banner for it. The thumbnail takes stills of code frames through `render.mjs --stills` (`thumbnail_gen.code_stills`). Tests: `test_production.py`, `test_director.py`, `test_export_control.py`, `tools/tests/test_razgon_bridge.py`.

A Razgon episode (`razgon-link.json` in Studio project storage) exports the same film as `tools/razgon_bridge.py push` + `final`: `backend/razgon_export.py` hands the bridge's `export` command each frame's rendered timeline clip, or null for a code block; the bridge renders those frames longest first, one Chromium worker each and as many at a time as keep the Mac's RAM under 80% (`razgon_bridge.RAM_LIMIT`, about 2.2 GB a Chromium at 1080p; six at once froze a 16 GB Mac on 31 October 2026), reusing build/studio clips stamped with the same times and picture sources (`razgon_bridge.picture_fingerprints`, per frame since 1 November 2026: the frame's shots with their neighbours, the scene files that register them and its words, plus the shared config, assets, helper scenes and engine, by content; one changed scene re-renders only its frames), glues them with the channel plate and Razgon's −14 LUFS mix. A Razgon timeline with other clips, Studio transitions or effects (a mixed episode: photos, stock and text frames around some Razgon frames, as Alexey Gorbunov's) exports through the engine: first `razgon_bridge.py frames` renders only its code blocks (the same build/studio cache, each with a 0.5 s held tail for the transition out), then the engine draws each block from its clip (`razgon_export._mixed`, `app._render_razgon_blocks`). The live preview of a mixed episode draws only its `razgon_2d` frames (`frontend/razgon-live.js`). The live view says what went wrong over the preview instead of an empty frame (user, 2 November 2026: «всеодно сіре, хоча код є»): the kit's `live.html` posts `{razgon: 'error'}` for a scene that fails to load or throws, a page that never says «ready» after one fresh start reads «не відповідає», and «Перезапустити перегляд» stops this project's live server and starts it again (`razgon_live.start(pid, restart=True)`; a failed start names the last line of `build/live.log`). A Razgon music-and-effects clip whose studio copy is gone plays the project's `build/studio/music_sfx.wav`, else its `build/music.wav` (`store.resolve_asset`). Test: `backend/tests/test_razgon_export.py`.

The voice at 100% is the studio's standard level (`backend/audio_level.py`, user 31 October 2026): the timed voice (the plan's audio asset, or a copy with the same bytes) is measured once (EBU R128) and played and exported with a gain to −16 LUFS, peaks at most −1.5 dBTP; the export mix ends in a −1 dBFS limiter. In the engine an image without a circle mask keeps its shape in the middle of its box (`render.contained`), and a text clip with motion keyframes carries its timed words along (tests in `engine/tests/test_render.py`).

## The plan page and the frame agent, the same for every channel (31 October 2026)

The plan page (`frontend/director.js`, `renderEpisode`) is one column, the same for photo and animated channels, with no
numbered steps: the voice stage as one line (file, length, «розпізнано, збіг N%» and the bin that starts the episode
over) that opens on a click to «Ваш сценарій», «Розпізнаний текст» (what the recognition heard, with its report), «Таблиця кадрів» (the director's report is not shown since 1 November 2026) (user, 31 October
2026: that stage is passed, the next one stands open; a recognition that needs a look opens it by itself), the
director's state only while it works or needs the author (a stop, a limit pause, a changed text), then «Створення
ролика»: the film as a strip of its frames (on a photo channel each frame in its format's colour from
`planFormatVisuals`), the count picked by a drag across the strip (all frames by default), «Макс» and «Почати створення
ролика». The strip reads like a timeline: a tip over the frame under the pointer names its format, number and time;
pointing at a format in the legend lights its frames (a click keeps them lit); a pinch on the trackpad (ctrl + wheel,
Safari's gesture events) or − and + zoom it up to 40 times around the pointer, two fingers sideways move along it.
The button stays disabled while `production.plan_ready` is false, while an animated film waits for its
director and while the script is newer than the direction (`director_stale`). «Звіт агента» closes «Створення
ролика». Every plan comes from the director after the voice, so the page has no plan regeneration.

Under the voice line stands the voice itself to listen to (`voicePlayer` in `frontend/director.js`, the plan's
`timing.audio.asset_id`): play and pause, a seek bar, the time and the volume (a mute button and a slider, remembered in the browser), inside the page; it stops when the page changes.

«Монтаж» opens with the first frame of the film on the timeline: any clip but sound, the clips of `role: overlay`
groups and clips titled «Логотип» or «Плашка» (`editorUnlocked`/`filmClips` in `frontend/plan.js`, `store.film_clips`);
until then its tab says «Монтаж відкриється з першими кадрами ролика».

«Почати створення ролика» posts the request and goes back to the channel's projects (`showProjectList`). Each project
in `GET /api/projects` carries `production_request` (`status`, `frames`, `limit`, and `made` while the agent works,
`store.production_state`); the card shows «Створюємо кадри · N з M» and opens while the agent works too, so the author can watch the frames come in
(user, 5 November 2026). The list is read again every 8 s while any card is in work. A frame counts as
made (`store.made_frames`) when a film clip covers its middle; a Razgon code block counts once its scene is written;
an animated film counts its frames drawn as code (`frame_progress.drawn`). A request for frames already made is refused
with 409, a second request while one runs too. A request that says the agent works while no agent of this Studio
runs (a restart, a run that never started; 31 October 2026 a finished film read «Створюємо кадри» for good) is settled
by `production.settle` whenever a project or the list is read and at start-up: done when every requested frame is made,
otherwise stopped (a fresh request gets 30 s to start).

`production.start` runs for every channel. A photo channel's agent (`production.photo_brief`, Claude Opus 5.5 at
`high`) reads the plan and makes each frame by its format: the author's own pictures from the episode folder first,
stock through `studio.py stock` (a numbered contact sheet of Pixabay previews, `backend/stock_sheet.py`, looked at
instead of lists of tags) and `studio.py stock-pick` (downloads the chosen one into the project and places it), pictures drawn by Codex through
`What If/razgon-2d-studio/tools/codex_image.py`, text frames itself and `razgon_2d` frames as code through
`razgon_bridge.py`, and puts each frame at its time with `python3 tools/studio.py place P N FILE|--text` (the montage op
`place`: the plan frame's start and length, a slow zoom on a photo, the group «Кадр N»). How people look follows the channel's «Люди в кадрах» (`people_style` in `video-plan.json`, `production.people_rules`):
`stickman` (default) keeps every person a stick figure apart from the host and stock without people; `real` (Karl Brenners
Werkstatt) asks for real people in natural phone-like photos and allows stock with people; `real_older` (Valentin Chichvarkin
and Alexey Gorbunov, user 5 November 2026) asks the same with people over 60. The channel setting «Акценти на кадрах» (`accents` in
`video-plan.json`, photo and video channels only, off by default) tells the agent to add an arrow, a ring or a short
caption with `studio.py accent` on about every third or fourth picture frame where it helps (`production.accents_step`),
or none at all. The run is done when each requested frame is made. Tests:
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

## A channel's video format and the export's quality (1 November 2026)

Each channel's settings hold «Формат відео»: the size (`video_size`: HD 1280×720, Full HD 1920×1080, 2K 2560×1440, 4K
3840×2160), the frame rate (`video_fps`: 24, 25, 30, 50, 60) and the quality the export window starts from
(`video_quality`: standard, high, max). A new episode takes the size and frame rate at creation (`store.create_project`);
a channel that chose nothing gets Full HD at 25 frames a second and the standard quality (the author's defaults).
They are not changed on an episode later: frame edges, transitions and Razgon's code frames are laid out at that rate.
The studio's global settings keep only the export subfolder. The export window shows the episode's size and frame rate
and three bitrates with the file each makes (duration × (bitrate + 192 kbit/s audio)); the bitrates grow with the
picture (`store.video_bitrates`: 1/4/6 Mbit/s for HD, 2/8/12 for Full HD, 4/14/20 for 2K, 8/32/48 for 4K, half as much
again above 30 frames). `POST /export` takes `video_bitrate` (only those three), the manifest carries it, the GPU path
encodes with it and keys its cache on it, the CPU path uses it for VideoToolbox and x264 (`render.video_bitrate`). The
Mac's fast GPU export works up to Full HD and 30 frames; 2K, 4K, 50 and 60 export on the processor, several times
slower, and the settings say so. An all-Razgon film keeps the bridge's own encoding and shows no choice. «Рух анімації»
is no longer in the settings: photos move with the saved `motion_easing`, «Плавно» (ease_in_out) by default. Tests:
`backend/tests/test_agent_tools.py`, `backend/tests/test_updater.py`, `engine/tests/test_still_window.py`.

## Updates say why they stop (31 October 2026)

The studio updates itself from GitHub (`backend/updater.py`: a fetch every 2 minutes, «Оновити студію» when the
folder's branch on GitHub is ahead, a fast-forward and a restart on the click; «Запустить студию.command» updates before
it starts). An update that cannot run no longer hides: the button reads «Оновлення зупинене» and its dialog
(`frontend/updates.js`, `updateReasonHtml`) says why and what to do. `local_changes` names the changed or stray files
of the folder (ignored ones aside, up to eight and a count), `diverged` means local commits GitHub lacks,
`unsafe_update` names the untracked file the update would replace, `other_branch` names the branch the folder stands
on while GitHub's main has commits it lacks (an agent switched the folder and left it). Changed files while nothing new
waits on GitHub read as `current`: no notice for an author or agent at work. A new version that does not load on this
Mac (`Updater.starts` imports the server; a package missing, a syntax error) is taken back with `git reset --keep` and
reads `update_failed` with the error until a newer version comes; the button never restarts the studio while any work
of `agent_view.studio_status` runs (director, frame agent, thumbnail, the studio's agent, not only exports and speech).
The fetch runs outside the updater's lock. `requirements.txt` lists the Python packages and `tools/doctor.py
[--install]` checks a Mac end to end (packages, ffmpeg, node, the Whisper model, Claude, Codex, the Pixabay key,
Razgon's node_modules, the update state, that the server loads). `backend/waveforms.py` reads PCM peaks with `array`
(audioop is gone from Python 3.13). Tests: `backend/tests/test_updater.py`, `tools/tests/test_doctor.py`.

## A channel's topics in one file (1 November 2026)

The user: «попередні сценарії не варто передивлятися… просто зберігати теми, заголовки… в текстовому файлі». Each channel
folder holds «Теми каналу.txt», a title a line (`backend/topics.py`): at every start, on a new project and when a project
takes its video's title the Studio appends the titles the file lacks (projects of the channel and episode folders with
«Метаданные.txt»); lines written by hand stay and nothing is removed. A new script reads this file to choose a new topic
or a new telling of an old one; agents never read the scripts of other episodes (the director's and frame agent's
briefs say so). Test: `backend/tests/test_topics.py`.

## The Studio's own Razgon styles (1 November 2026)

`style_copy.BUILTIN` holds styles the Studio ships to every channel as whole definitions: «Темна студія»
(`studio-dark`, user: «як неоновий, тільки… чорніший… темно-зелено-чорний… як стиль нашої студії»). They lead the
gallery, cannot be deleted, and reach a film through its config (`razgon_bridge.py` puts `styleDef` in for `custom-` and
`studio-` styles), so no Razgon copy's `engine/styles.js` is touched. «Крейда» (`chalk`) left the gallery the same day;
films already in it still render.

Style cards follow the channel's kind (`style_lab.card_scene`): a regular channel sees an infographic with no characters
(kit `examples/style-card-info` at 2 s: a carrot, a brain and an eye joined by glowing arrows, Ukrainian labels and a
title), an animated channel the café of `examples/reaction-time` at 8 s. The settings page asks for the kind it shows
(`POST /style-cards {kind}`) and reloads the cards when the kind is switched. Only styles with volume are offered
(user: flat styles show no volume); a retired style a channel still uses stays in its list. Razgon text falls back to
Nunito, loaded with Cyrillic, when a title font has no Cyrillic letters. A style's `figure` ({limb, torso, head, joints,
ends}) shapes its characters (`rig2d.parts`).

## An episode's files live in its folder (1 November 2026)

The user: «картинки згенеровані, відео викачені… має бути в папці YouTube… щоб я міг видалити ту папку і все»; the
rendered animation stays in the studio «як кеш». A new episode gets its folder in the channel at once
(`store.create_project`). Pictures, videos and sounds the studio brings in (imports, uploads, stock, generated pictures,
accents) go to `<episode>/VideoKey/Матеріали` (`store.media_dir`); the studio's cache of the episode stays in
`backend/data/projects/<id>` (`store.cache_dir`): Razgon frame renders (`RAZGON_RENDER` names), export chunks
(`renders/`), the engine's render cache (`render-cache/`, `MULTIBOT_RENDER_CACHE` per export and still), stills and stock
sheets. Older media in `projects/<id>/media` stays valid (`store.media_roots`). The episode's media list skips the
VideoKey folder. «Звільнити місце» frees that cache too (`space.CACHE`) and shows only when it frees at least 100 MB
(`space.freeable`, measured at most every 30 minutes a project); deleting a project in the studio removes its VideoKey folder, the author's own files stay.
A project stays in the studio when its episode folder is deleted: its code, preview and title are there (user, 1 November
2026, after a version that hid such projects for deletion; `store.restore_hidden_projects` takes those marks off at
every start). The studio never deletes a project or its data by itself. An old episode still plays after its folder is gone (user,
2 November 2026): `store.razgon_link` reads the Studio's `razgon-link.json` (old episode copies are migration inputs), so the code
frames, live view and export find their Razgon project; an episode deleted before that finds it by the studio id in
the Razgon project's `story/studio_frames.json` (`store.find_razgon_project`), and its voice in that project's
`input/` (`store.razgon_voice`); `backend/keep.py` keeps an AAC copy of every sound clip and of
the plan's voice (`projects/<id>/kept/<asset>.m4a`, made at start and after a recognition), and `store.resolve_asset`
falls back to it. Pictures and videos are not kept: the preview marks a clip whose file is gone «Файл видалено разом
із папкою випуску». Tests: `backend/tests/test_episode_store.py`, `test_space.py`.

## The thumbnail library (1 November 2026)

The «Прев'ю» tab shows every thumbnail made for the episode (`thumbnail_gen.versions`, served by
`GET /api/projects/<id>/thumbnails/<name>`), newest first, the cover marked and the prompt's author tagged (DeepSeek, or
«Правка vN» for an edit). A click on another one makes it the cover (`POST /thumbnail/choose`); «Згенерувати ще одне»
adds a new version and keeps the others. «Правка» on a version sends the author's remark to Codex with that picture
attached (`POST /thumbnail` with `base`; `thumbnail_gen.editing`), and the result is the next version. The window closes
once a run starts, so the card shows «Малюємо прев'ю». «Згенерувати з DeepSeek» is a trial: DeepSeek (OpenRouter)
writes the prompt from the same brief, the frames attached as pictures (`thumbnail_gen.write_prompt_deepseek`).

The project-card creation dialog says «Створити нове прев’ю» and contains only the optional idea field, creation actions and any active/error status. Do not show the current cover, version library or explanatory library paragraph in this dialog: those make a new-image request look like an edit. Keep existing images in the Preview tab. A creation request sends wishes without a `base` image; its textarea is separate from the tab's own field.

«Трендове прев’ю» is a third creation action (`writer: trending`): send the English creative rules in `backend/prompts/trending_thumbnail.md`, video title, narration, author wishes and style references directly to Codex. Codex develops the idea itself. Keep visible image text in the video's language; create a new version without a base image. Do not run an extra Claude/DeepSeek prompt-writing stage.

On project cards, clicking the title opens rename; remove the separate pencil action. Hover changes the title colour to light mint and adds a soft glow to its letters. Omit tooltip, underline, background and extra border. The rename popup has only Save; its cross closes it. Preserve normal card navigation and export locks.

On project cards, omit the thumbnail creation action until the episode has enough made frames for `thumbnailReady`. Do not render a grey unavailable button. Once ready, show the normal creation action; keep export locks unchanged.

## Razgon lives in the studio's folder (1 November 2026)

The user: «цю папку з What If прибрати й засунути саме в VideoKey Studio». The working copy is
`<studio>/razgon-2d-studio` (in `.gitignore`). At the first start of this version `razgon_sync.move_home` renames
`What If/razgon-2d-studio` there (same disk only, never over an existing folder) and `relink` rewrites the paths in every
episode's `razgon.json` and in the channels' `AGENTS.md`/`CLAUDE.md`. `razgon_sync.home()`, `razgon_bridge.DEFAULT_STUDIO`
and `store.razgon_rel()` (the agents' briefs) find it in either place. Test: `tools/tests/test_razgon_home.py`.

## The browser button (1 November 2026)

The Multi Bot extension (its own repositories, multibot-extension and multibot-extension-public) has a fifth item,
«VideoKey Studio»: it opens the studio or brings its open tab forward; only when the studio does not answer it asks the
native messaging helper to start it. `install.py` copies `browser-helper/host/videokey_host.py` with a `config.json`
to `~/Library/Application Support/VideoKey Studio` (macOS keeps Chrome out of protected folders such as Documents);
the helper starts the server directly, with no Terminal (`start_directly`; macOS may ask once to let Chrome into
the studio's folder), and only when that fails asks macOS to open «Запустить студию.command» (`open -g -j`, a hidden
Terminal), leaving a marker so the command opens no second tab and hides its window, waits for `/api/health` and answers; it accepts only
`{"command": "start"}`. «browser-helper/Встановити.command» (`install.py`) registers it in each Chrome-based browser for
the extension named «Multi Bot» only, its id read from the browser profiles' Preferences.
The studio's settings («Розширення Multi Bot», `backend/extension.py`, `GET /api/extension`, `POST /api/extension/update`)
find the folder Multi Bot is loaded from (the browsers' profile Preferences), show its version and whether GitHub has a
newer one, and update it with one button: a fast-forward of the folder's own branch (never over its own changes or
commits), puts the «VideoKey Studio» item into a Multi Bot that lacks it (`extension.add_item`: the style, markup
and script from `browser-helper/multibot/`, `nativeMessaging`, the version one step up, a commit and a push to the
folder's own GitHub; the private version keeps its own features), then `browser-helper/install.py`. Chrome reloads the unpacked extension only by hand at chrome://extensions.
Test: `backend/tests/test_extension.py`.

## A picture row's eye (2 November 2026)

Every timeline row with pictures has an eye beside the sound button (user: «глазик… щоб виключити цю лінію»):
`set_layer_hidden` marks the layer `hidden`; the preview (`renderUniversalPreview`) and the export manifest
(`app.py`, the clips loop) leave its pictures out, the timeline fades it. A row of frame groups switches all its layers
in one batch. Test: `backend/tests/test_layer_eye.py`.

## The «Мови» tab: the voice and thumbnail in other languages (2 November 2026)

The user: «вкладку в проекті після превью мультиязик… озвучуємо через апі з тим самим голосом… ціну… послухати превью»,
then «відео ролик перекладати я поки не хочу, лише аудіо і превью можна текст», and a button that translates the
thumbnail, before and after. `backend/languages.py` and `frontend/languages.js`; the address ends in `/languages`.
Each language is a card of three steps: the text (script and title translated by DeepSeek through OpenRouter in
paragraph chunks, editable; saving drops the old sample), the voice (the author's voice cloned once per provider and
episode from the first 90 s of the plan's voice, `clones` in `languages.json`; a sample of about 320 characters first, one for each voice (`sample-<voice_key>.mp3`: the provider, and Fish's engine), so switching plays that voice's own sample and the button shows only while it has none;
the whole text voiced in parts of ≤2400 characters with the neighbours as context, glued, −16 LUFS / −1.5 dBTP, sped up by
at most `FIT_MAX` when longer than the video, padded with silence when shorter; the price is shown before and asked in
a confirmation) and the thumbnail (Codex redraws the current cover with only its words translated; the «after» window itself is the button, a magic wand in the middle; the captions read «Оригінал (<language>)» and the language with its flag; once made, both pictures carry the episode cards' round buttons in their corner on hover: «Перекласти ще раз» and «Завантажити» (`?download=` names the file, `Content-Disposition`; the original from `GET …/languages/original/thumbnail`), and the wand (the empty window or «Перекласти ще раз») opens, under the translated picture only, an optional «Побажання» line with «Перекласти», which starts Codex with them). Providers:
ElevenLabs (`eleven_multilingual_v2`, every language, cloning needs a paid plan) and Fish Audio with a choice of
engine (`FISH_ENGINES`: S2.1 Pro Free by default, free under fair use; S2.1 Pro billed by UTF-8 bytes; Drama 3, the expressive one, $50 per million UTF-8 bytes with a launch price of $10 until 12 November 2026 17:00 UTC (`promo`, applied by date); S1 left the list as an old model; the paid engines say «платний, потрібен баланс API Fish», and Fish's 402 «Insufficient API credit… s2.1-pro-free» reads as top up or take S2.1 Pro Free). Fish
clones inline: every request carries, as MessagePack (`languages.msgpack`), about 22 s of the voice's start cut after a
whole word with exactly the words said in it (`languages.reference`, from the recognition's `aligned_words`), so no
voice model is made (a free account may make none: «model creation limit reached (0/0)»); their keys are «Ключі сервісів» (`credentials.DEFAULTS`). Voxtral on OpenRouter has no Ukrainian or Russian.
Work files stay in `data/projects/<id>/languages/<code>`; text, title, voice and thumbnail are copied to
`<episode>/Мови/<language>/`. Jobs run side by side (user: «перекладалось текст, я нажав перекласти прев'ю, і воно зупиняє переклад?»): each language has two lanes, its text and voice (`translate`, `sample`, `voice`) and its thumbnail, and other languages run at once (`languages.ACTIVE` holds `<pid>|<code>|<group>`, `group_of`, `busy`; state in `jobs["<code>|<group>"]`, `job` mirrors the latest; `POST …/languages/cancel {slot}` stops one lane; all are in the busy list); a running lane locks only its own steps, and only a lane whose «Скасувати» was pressed reads «Скасовуємо…» (`langAsked`); the tab works during an export.
The languages stand on top as capsules with their flags (`langFlags`; user: «мови… зверху… капсулами… прапор… плюсик… хрестик»): a click opens that language's card below (one at a time, remembered in the browser as `langTab:<project>`), «+» opens a menu of the languages with flags and adds one (only its card; «Перекласти» stands in its text step), also while a job runs, × on a capsule removes it after a confirmation, and the capsule of the language at work shows a pulsing dot; the voice service is chosen in a
card's voice step. «Скасувати» on the job's line, which sits in the step it works on inside the language's card, stops it (`languages.cancel`): a translation or a voice at its
next part, the thumbnail at once (Codex killed); nothing half made is saved. The «Оригінал» card leads the page as one compact line: the name, the script's characters and the episode's own voice to listen to (its length is in the player)
(its language in brackets, found once: Whisper's `engine.language` of the latest recognition, else `guess_language` from the script, kept as `original_language`; the add select leaves it out) (`languages.original_file`, `voice_file`: the plan's asset, the levelled voice of `audio_gain`, the sound clip that
starts the film, a path in the timings, the Razgon project's voiceover). A round «Перекласти заново» icon beside «Текст» (once a text is there) translates the language again by the current rules after a confirmation (user: «кругла кнопка без тексту — оновити… бо правила нові»). Text and title edits save by themselves a
moment after typing stops (no save button, no «translate again»); the tab's messages stand in the step where the button was pressed
(`langNote`), not in the studio's banner. Every language is voiced from an example in that very language (user: «переклад будемо брати завжди від прикладу ролика на мові… або запис, або закинути приклад носія»; the original's voice carried its accent), and only without one from the original's first ~22 s cut after a whole word with its recognised words (`original_example`, `REFERENCE_SECONDS`; user: «хай кнопка працює навіть якщо… лише оригінал є»; the voice block says it will carry the original's accent): the channel keeps one example a language for all its episodes in `<channel>/Голоси для перекладу/<language>.mp3` (+ `.txt` words, `.json` heard), set in the channel's settings, section «Голоси для перекладу» (`bindChannelVoices`; `GET /api/channels/<cid>/voices`, `POST …/voices/<code>` raw body, `…/<code>/remove`, `…/<code>/file`), and an episode may drop in its own (`own-voice.mp3`, «Інший голос лише для цього випуску»), which wins (`voice_for`). An example is the author recorded in the page (MediaRecorder, `langRecord`) or any speaker's file, cut to `OWN_SECONDS`, its words recognised by the studio's Whisper (`heard`; the passage of the translation stands when nothing is heard and the card warns). Only an episode with no voice at all leaves «Послухати зразок» and «Озвучити» off (`NO_VOICE`). Samples are keyed by the example too (`voice_key`: provider, Fish's engine, episode or channel and the file's time), ElevenLabs clones by `elevenlabs-<code>-<from>-<stamp>`. A saved Fish voice model is made from the example on its first use (`fish_model`: `POST /model`, train_mode fast, the example's words as `texts`; user: «а по апі хіба не можна скопіювати норм голос?… поповнив»), kept in the example's own `.json` with the file's time (a channel's example gives one model to every episode), and then used by `reference_id`; Fish refuses on an account without API credit, and then the inline example stands and the attempt waits `FISH_RETRY` seconds. The card says whether the model is saved; samples are keyed by it (`m`); while a model is made the job line says so (`announce_model`). The voice step is compact (user: «не виділяй її так… основа акценту на створенні аудіо»; «кнопки… значки… сучасніше, компактніше»): engine and likeness as small chips, the example as a line with a compact player and icons (record, upload, remove or back to the channel's), the model mark beside its label, the sample (about a minute, `SAMPLE_CHARS`) and «Озвучити · price» in one row, the ready voice with a download icon. A sample takes as many sentences as the author picks beside it (3, 5, 10 or 20, remembered in the browser; `sample_text(text, sentences)`; user: «тест вибирати, скільки речень тестити») and says what made it (engine and likeness) and belongs to its voice key, so another engine, likeness or example hides it; a ready voice keeps what made it (`made_with`: voice key, text hash, «Fish Audio · engine · likeness») and leaves the card once any of that changes (`voice_current`; user: «щоб воно дівалось після будь-яких змін, бо не ясно, хто це згенерив»). «Схожість на приклад» beside the engine (`FISH_STYLES`: «Точно як приклад», temperature 0.5 and top_p 0.6; «Звичайно» 0.7/0.7; «Живіше» 0.9/0.8, the default since the user heard it voice Russian best; user: «голос поганий… може там є настройки?») goes with each Fish request and keys the samples. An example (a file, a video, a recording, or the original's start) is folded to mono in floating point and brought to −18 LUFS, peaks −2 dBTP (`EXAMPLE_FILTER`; user: «закинув мп4 ролика як приклад… перегруз… рипить»): `-ac 1` summed a loud stereo video's channels over full scale, the MP3 clipped and Fish cloned the crackle. The page records the example with the browser's processing off (no noise suppression, no automatic gain, 48 kHz, 256 kbit/s): processed sound made the clone sound processed. For now the page offers Fish Audio only (user: «будемо працювати лише з фіш-аудіо»); ElevenLabs stays in the code. A finished job shows only in the card: the job line speaks of failures and cancels. In time with the original (user: «все, що він говорить, говоритиме… в той самий час… це перше, найважливіше»): `segments_of` groups the plan's timed sentences into lines (joined when less than `SEGMENT_GAP` apart, up to `SEGMENT_MAX`), `translate_lines` sends them in batches as JSON with original seconds as context, without a character limit and takes back each line by its id (`line_answers`; user: «Перекладач двічі повернув не ту кількість фраз»): the lines an answer lost or merged are asked again once, and a line still missing is translated alone, so one bad answer no longer stops the translation; the parts go to the translator four at a time (`TRANSLATE_AT_ONCE`, each with the original lines before it as context), and the translator answers with reasoning off (`REASONING_OFF`; user: «довгувато діпсік працює», «Перекладач не повернув переклад однієї фрази»: DeepSeek V4.1 Flash reasoned first, slowly, and a small budget left its answer empty), again with reasoning when a model refuses that, and again with more room when an answer came back empty and cut, the text keeps one line per line (`segments.json`; an edit that merges or splits lines is refused), and `whole_synced` voices each line alone and puts it at its original's start; each line is voiced once, fitted locally with pitch preserved (0.85 through 1.15), with silence between and after to the video's length. Do not buy automatic shorter or faster takes. Record timing issues when a line still cannot fit; the card shows how fast and how late it got. Texts translated before stay whole and are fitted as before. Every translation, shortening and fix carries `SPEECH_RULES` (user: «1999-го — такі речення погані… краще слова тисяча дев'ятсот… щоб було плавно, адаптовано на голос»): numbers, years, dates, percentages, money and measures in words in their right grammatical form, no digits, symbols, shorthand, brackets, lists or emoji, short sentences of one idea, spoken words, clear stresses (ё in Russian), foreign names in the language's own spelling; a line that still holds a digit or symbol is rewritten once more (`speakable`, `UNSPOKEN`). Each capsule shows grey marks for what its language has: the text, the thumbnail, the voice (`langMarks`). The voice row in «Монтаж» has a language button (`addLayerDubControl`; user: «дай змогу міняти озвучку, щоб глянути, як вийде»): «Оригінал» or a language whose voice is ready and current, and the preview then plays that voice in place of the original clip (`dubbedVoiceUrl`, no gain, it is at −16 LUFS already); preview only, kept per episode in the browser (`dub:<project>`), the export keeps the original. The video is not changed. API: `GET /api/projects/<id>/languages`, `POST …/languages/provider`, `POST
…/languages/<code>` (add), `…/<code>/remove`, `…/<code>/text`, `…/<code>/translate|sample|voice|thumbnail`, `POST …/languages/cancel`, `GET …/languages/original`, `POST …/<code>/own-voice[/remove]`, `GET
…/<code>/file/sample|voice|thumbnail`. Test: `backend/tests/test_languages.py`.

## Natural localization for dubbing (3 November 2026)

DeepSeek localizes narration into natural spoken language for the target audience. It may restructure sentences and replace expressions with contextual equivalents while preserving facts, duties, cultural setting, intent and tone. Professions and objects use the target language's natural terms for the role in the scene; the park-ranger example is contextual guidance. Preserve every dubbing line's id, order, meaning and allotted time. Keep terminology consistent across the video. `LOCALIZATION_RULES` in `backend/languages.py` applies to narration, timed translation, retries, shortening, spoken-form repairs and titles. Existing translations change only when the author requests translation again.

## Fish sampling and voice quality (3 November 2026)

The voice selector says «Подача»: temperature and top_p control variation and expressiveness, with no guarantee of speaker similarity. Each Fish engine remembers its own selection (`fish_styles`); migrating the former shared `fish_style` preserves it for the engine it belonged to. Drama 3 starts at the hosted API defaults, 0.7 / 0.7 («Звичайно»), while S2 retains its existing default. A change of engine must not carry S2's «Живіше» into Drama. An explicit choice for an engine remains saved. Samples are raw Fish responses, with no montage or time stretching. Loudness and peak measurements cannot certify that a generated voice has no audible rasp; compare actual samples before claiming a quality fix. Never regenerate a full paid voice merely to diagnose a sample.

## ElevenLabs in Languages (3 November 2026)

The author re-enabled ElevenLabs alongside Fish. Keep the service and the Eleven model selected per project, and Fish's model and delivery settings separately. `backend/eleven_api.py` discovers TTS models, languages, limits and account credit multipliers through `/v1/models` with a five-minute cache. Offer only Eleven v4 and v4 Turbo: the author removed the older generations. Without verified metadata the UI marks its documented fallback catalogue and has no invented price. Eleven v4 and v3 use `/v1/text-to-dialogue/stream`; v4 Turbo and v3 Conversational use the Text to Dialogue WebSocket, registered with one cloned voice and flushed with `close_socket`, and only save complete audio. Other TTS models use the ordinary speech endpoint for historical projects. v4 has stability 0.5 and similarity 0.75; do not send unsupported style, speed or speaker boost. Do not re-request a faster v4 take when fitting speech: shorten naturally, then use the existing bounded time stretch. Split long inputs at each model's supported length. Key sample files by provider, model and voice reference, allow the underscores in Eleven model ids in the serving route, and preserve every saved Fish sample. Costs for Eleven are estimates in credits from the account's model rates, never a fixed USD price. Show sample estimates in the sentence-choice menu, calculated with the same selected text as synthesis; keep the idle Play label free of prices. Keys live in macOS Keychain and must not appear in chat, code, screenshots or logs. Test both dialogue transports with mocked responses, including incomplete streams and unsupported languages, and verify the visible model selector.

Translated narration must finish its grammatical thought and make comparisons and quantities clear, including a contextually needed noun after a compound number. Replace opaque metaphors with their concrete meaning for a native listener. The lightning examples in `LOCALIZATION_RULES` illustrate these rules; they preserve the source's values, intent and uncertainty. Existing translations change only on request.

## Uploaded voice references keep their full length (3 November 2026)

The author removed the former 45-second cap. `store_example` keeps the entire uploaded or microphone recording for an episode or a channel, normalizes its level and transcribes its full duration. `prepared_example` also retains the full source. Level version 2 rebuilds a shortened v1 normalized sidecar from its preserved full source, while upgrading already-complete v1 references without re-encoding or invalidating their saved clone. A recording already truncated before its original was discarded needs the author to upload the complete file again. Provider limits must be reported clearly, with no silent trimming. Do not confuse uploaded examples with the automatic short reference extracted from the original episode.


## Dubbing pause repair and saved takes (3 November 2026)

Keep paid narration takes under each language's `parts`, including original, shorter and faster candidates plus `request.json` and `manifest.json`. Move prior takes into `voice-history` and back up the accepted voice, text and segments before another run. Do not delete paid audio after joining. `dubbing_fit.fit_speed` fits short lines towards their original spoken span at no less than 85% tempo, pitch preserved; no global timeline shift. Only shorten a line when it cannot fit within the existing 1.1 speed cap. Reject a rewrite that is excessively short or worsens duration fit. Keep every detail in timed translation instead of aggressively summarizing. Analyse actual encoded pauses over 1.5 s and show remaining gaps for review. Never claim all pauses fixed based only on concat lengths. Legacy recovery splits only at confirmed quiet boundaries, preserves a guard after speech, and refuses uncertain cuts or overlaps. Back up before applying a local repair; no paid regeneration for diagnostics. Test: `backend/tests/test_dubbing_fit.py`.


## ElevenAPI price estimates (3 November 2026)

The public API list price verified at https://elevenlabs.io/pricing/api is $0.08 per 1,000 characters for Eleven v4 and $0.04 for v4 Turbo. Keep the price source and verification date in API metadata; omit the former price disclaimer paragraph in the UI. The author restored credit estimates in the UI. Prefer per-model rates inferred from recent individual history debits when the observations fit consistently, falling back to catalogue estimates; never represent estimates as an invoice. The USD list prices remain a reference. Preserve old jobs' cost units. Model catalogue credit multipliers are not reliable actual API debits: on 3 November the account's history differed from the catalogue. History character counters may include unlisted streaming chunks; do not add only the last-chunk deltas and call it a full bill. Subscription access may be denied even when models and history are readable. Never expose the key.


## Automatic language soundtrack delivery (3 November 2026)

After full narration, regeneration or local refitting succeeds, the same language worker automatically saves its complete soundtrack before reporting done. `language_mix` replaces the timeline's original narration with the selected translation and includes enabled audio/video sound at the current trim, position and volume. Hidden video sound and muted rows are omitted. An explicitly muted narration must be enabled first. Save the complete stereo 192 kbit/s MP3 to `Мови/<language>/Озвучка зі звуком - <language>.mp3` in the linked episode folder. Keep raw narration and paid takes in Studio, and prior mixes in `mix-history`. Check the linked folder before starting paid full speech. The UI reports saved with a check and filename, without a redundant save button. A missing/outdated mix or a failed save has a local-only save/retry action through `POST /api/projects/<id>/languages/<code>/save-audio`; never regenerate speech to retry delivery. A failed or cancelled mix retains the finished narration and reports that distinction. Sound signatures and output stamps invalidate delivery independently of visual-only edits. Missing source media is an error; never silently drop it. Recheck the sound signature before atomic publication so concurrent montage changes cannot produce a falsely current file. Saving uses no speech service or credits. Samples never publish a soundtrack. Hide the sample player as soon as full voicing starts and once a full voice exists; an explicit new sample request may show it again. Tests: `backend/tests/test_language_mix.py`.


## Saved narration defaults and thumbnail workspace (3 November 2026)

The small «За замовчуванням» button on the right of the «Озвучка вашим голосом» heading saves the current project's selected languages, provider, per-engine settings and explicit voice references as defaults for its channel. A green check means the current choices match the saved defaults. `language_defaults` copies references and existing clone ids into newly created projects through `store.create_project`; it never overwrites old projects' explicit choices, copies their translations or generates speech. Existing projects automatically find a saved channel voice when they have no explicit reference or opt-out. Preserve their explicit model selections, translations and generated files. There is one save-current button and no apply-saved menu. Both the reference audio and its narration settings belong to the saved defaults. Preserve reference timestamps and normalized state; a project without an explicit reference uses its own original narration. Default saves are explicit. Pin the selected voice reference and settings at narration start; unrelated jobs never block saving defaults. Test inheritance, clone reuse, existing-project preservation and channel isolation.

The sample action opens one small 3/5/10/20-sentence menu with estimates; choosing an option starts that sample. Completed narration uses a grey secondary regenerate button. The thumbnail tab has one gallery for original versions and existing language thumbnails, language filters, a large preview and an optional new-image field. Selecting an image previews it; choosing an original as the cover is a separate action. Downloads are on the image and appear on hover/focus. Do not add a count pill, an extra subtitle above «Прев’ю», or a finished-generation status in the new-image panel. Existing translated thumbnails are listed from local file metadata without preparing voices or starting paid work.


Narration settings defaults belong to the «Озвучка вашим голосом» heading, including both explicit reference audio and its settings. The single button saves the current choices directly; no menu or separate apply action. It is quiet and checked while choices match, and active after settings or reference deletion change them. A removed reference opts that episode into its original voice until a new example is uploaded, so channel fallback cannot restore it immediately. Reuse saved ElevenLabs clone ids when applying or creating a project; no duplicate upload or cloning when the remote voice is already known. Remove «свій для цього випуску» from reference labels and omit Eleven model descriptions such as «діалогова озвучка» from the selector. ElevenLabs prices are shown in credits. Character counts include spaces and punctuation; the Studio's text counter also includes line breaks, while the actual billed request follows the outgoing text.

Show the reference audio and provider/model settings even before translation exists or while it is being translated. Only sample/full synthesis waits for translated text; a saved-default check must never be the only visible sign of its voice. Project-wide provider/model controls are read-only during that project's narration/translation jobs. Saving defaults remains available after inherited job settings are pinned.


## Studio-managed assets stay inside Studio (3 November 2026)

The author corrected the former episode-local media policy. New imported and generated assets belong to `backend/data/projects/<id>/media` inside VideoKey Studio. Never create `VideoKey/Матеріали` in a YouTube episode for working media. Keep legacy locations readable and relocate explicitly through `POST /api/projects/<id>/assets/relocate` with the expected revision. Retain asset ids, timeline references and a migration journal; remove only empty old managed directories. Prevent duplicate media discovery after a path changes. Cache cleanup must preserve persistent imported media. Final language soundtracks go to the episode's language folder automatically after full narration/refitting or after an explicit local-only retry.


## No automatic paid timing retakes (3 November 2026)

An earlier synchronized narration bought extra shorter takes that were omitted from the one-pass estimate. Preserve private account audit evidence locally; never publish balances or billing history in the repository. Every new synchronized voice now submits each phrase only once for every provider. Fit its saved take locally within the existing tempo bounds, preserve words and report unresolved timing issues. Never silently call paid TTS again to shorten or speed a phrase. Persist every submitted text, characters, estimated cost, completion state and chosen file in `parts/requests.json`; preserve this alongside `request.json`, `manifest.json` and all takes. Job estimates sum submitted takes, including unsuccessful/uncertain transports, and remain estimates rather than provider debits. Upfront prices count actual outgoing lines without stored line breaks. No paid generation for testing.


## Balanced pauses and listening markers (3 November 2026)

The author permits centring translated phrases within the available time and borrowing neighbouring silence. Fit the saved audio within the existing pitch-preserving tempo bounds, then use `dubbing_fit.centered_schedule` to balance pauses while retaining order and preventing overlaps. If the complete voice cannot fit, keep all paid takes and the previous accepted audio, report the excess and stop local assembly. Never truncate spoken words or buy a retry. Save per-phrase starts, ends, tempo and original timing. The ready voice has a compact expandable «Перевірити звучання» list, with a time, actual percentage of acceleration/slowdown and timing shift. Its play buttons seek the existing voice and play the marked excerpt only. `POST .../languages/<code>/refit` rebuilds retained takes without any translation or TTS calls, backs up the previous voice/manifest/state, and invalidates a saved soundtrack normally. Tests are silent. No paid generation for diagnosis or verification.


## Country flag adaptation in translated thumbnails (3 November 2026)

The wishes panel under Languages > Preview has «Додати прапор». Remember its last explicit choice per channel in `backend/data/language-thumbnail-options/<channel>.json`, through `POST /api/projects/<id>/languages/thumbnail-options`; it is independent of narration defaults. The initial choice is off. Use the conservative `THUMBNAIL_FLAGS` allowlist (uk/UA, pl/PL, ja/JP, cs/CZ, id/ID, kk/KZ); shared or ambiguous languages including English, Spanish, French, German, Portuguese, Russian and Chinese have a disabled unchecked option. An ineligible language never changes the remembered preference or inherits a flag. The backend rejects an explicitly requested ambiguous flag before starting work. Each thumbnail job captures its option; changing a preference cannot change an already running prompt.

With the option enabled, Codex translates the existing words and integrates one accurate national flag into a suitable existing sign, clothing detail, held object surface or background element, matching perspective, lighting and the artwork. If there is no suitable place, use a small round flag badge in a quiet corner. Preserve legibility, the main subject and the story setting. Textless images still receive the flag. With it off, keep the usual translation-only brief. Retain the actual prompt and the used country/option with the result. Do not run paid image generation to test the wiring; validate job snapshots and the brief with a mocked worker, and check the real wishes panel without pressing Generate.


## Voice reuse, names and tempo limits (3 November 2026)

ElevenLabs clones are reused by API account fingerprint, channel, language and the SHA-256 of the exact prepared audio, in `backend/data/voice-clones/elevenlabs.json`. Never persist the API key. A thread and file lock prevents two parallel projects from uploading the same reference twice. Seed the registry from existing known clone ids. Copying or touching the same file does not justify another clone; changing its audio may. New clone names use the channel and full language name, with a sample number for later distinct references; send the supported language label. Metadata-only corrections of existing Studio voices omit files and preserve other labels. Keep previous voices available.

The maximum local narration tempo change is now twelve percent: 0.85 through 1.15, shared by synced dubbing and whole-track fitting. Centre phrases and borrow available silence within these limits. If the full text cannot fit, keep the paid takes and the previous accepted audio, report the excess and require review. Show exact speed/shift listening markers. No paid regeneration for changing these limits.


## Language thumbnail publication and safe restart (3 November 2026)

Languages shows the selected current translated thumbnail. The global Preview gallery shows immutable v1/v2 versions for every language. A successful language thumbnail is published through `language_thumbnails` into `languages/<code>/thumbnails/vN.png` and an atomic `thumbnails.json` pointer. Preserve a legacy `thumbnail.png` as v1 before publishing v2. Keep the actual prompt and flag options for each version. The compatibility file and explicitly copied episode thumbnail follow the selected version. Main-gallery language keys include the version, and files are served through `.../languages/<code>/thumbnails/vN.png`. The wishes action says «Згенерувати». Errors stay visible until resolved.

A worker interrupted after drawing can leave `thumbnail-new.png`. `POST .../languages/<code>/thumbnail/recover` validates its PNG and time against the failed job, publishes it idempotently and settles that job without another Codex/image call. Inspect the actual candidate before recovering it. A file's existence alone does not authorize recovery of an unrelated stale result.

Language jobs record their owner PID. A separate CLI process reading or updating language state must preserve a job owned by the live server; its empty local ACTIVE set is not evidence that the server stopped. Studio status also checks active language workers independently of persisted job status. `studio_restart.py` prepares restart through `POST /api/studio/restart/prepare`, atomically closing the mutation gate after checking active jobs and in-flight writes, so another generation cannot start between the check and termination. The gate expires after 30 seconds if the restart caller disappears. Never interrupt paid work for an update. Tests: `test_language_thumbnails.py`, `test_restart_guard.py`, `test_languages.py`, `tools/tests/test_studio_restart.py`.


## Translation language integrity before paid speech (3 November 2026)

Spanish and Polish translations contained complete Russian batches of 30 phrases. The historical raw model responses were not retained, so do not assert that parallel routing or DeepSeek alone caused them. Every translation, number rewrite and final publication now passes `backend/language_quality.py`, using script checks and the local langid model. Keep short names and acronyms valid; language ID scores are heuristic, not a guarantee of meaning or acoustic accuracy. Validate the whole saved text before a sample/full narration, before cloning or speech calls, and validate each outgoing request when its target is known. A missing detector blocks narration. Wrong-language batches get at most one bounded translation retry, never a paid TTS retry. Preserve the previous translation when validation fails.

Prompts use target-specific localization examples. Never put Russian/Ukrainian examples in a Spanish, Polish or other target's prompt. Every batch gets its explicit target ISO code. `translation-attempts/<run>` retains exact messages, returned model/provider/request id and responses without credentials. This target context is thread-local; concurrent jobs cannot mutate a shared target. Test out-of-order multilingual batches and number-cleanup language drift with mocked requests. No paid generation for diagnostics.

Audit existing text and the actual text of paid takes independently. Fixing text.txt cannot make an older wrong-language recording valid. Show affected phrase ranges and listening times, keep the old audio available for diagnostic playback, and block paid synthesis of unsafe text and delivery/download of unsafe voice. Preserve all takes for a future targeted repair; never buy a full repeat to fix a small wrong-language block. Detailed project audits stay in local task artifacts. Tests: test_language_quality.py and test_languages.py.

## Noticeable country localization in thumbnails (3 November 2026)

The former flag checkbox now says «Адаптувати під країну» and keeps the same channel preference and country eligibility. For every eligible country, adapt the visual as well as the written text. Make one or two national/local cues clearly noticeable at thumbnail size: a cap or clothing panel in national colours, a patch, an appropriate familiar local shop sign/logo, a held object or a background detail. Two complementary cues are permitted. Keep accurate flags, natural perspective/light, readable text, the main subject and the story's facts. A small round badge is a fallback for a tight composition; look for another natural cue if it fits. Do not silently regenerate existing paid thumbnails merely because the prompt changed.


## Reuse paid narration and show current settings (3 November 2026)

The heading action is a neutral grey «Зберегти налаштування» button with a save icon, present only when the open language differs from the channel default. Omit the saved-state button entirely. Compare the actual reference audio bytes and the selected provider/model/style for that language; extra language tabs and dormant engines do not make an unchanged selection dirty. Inherit missing settings from the channel while retaining explicit project choices. Saving unchanged selections through the API is idempotent. Translation, thumbnail and unrelated narration jobs do not block saving defaults. Workers pin their own inherited reference and settings before starting; an upload of the same reference blocks saving only until that upload finishes.

The language card saves with `POST /api/projects/<id>/languages/defaults` and `{code: <open language>}`. Merge that language's voice into the channel defaults, keeping every other saved language, reference file, filename and existing provider clone ID. Never replace the whole channel's voice collection with one project's stale or incomplete collection. Legacy requests without a code may update their project's languages but must still retain languages absent from that project. Opening or saving another language must not make an unchanged saved voice appear dirty. Existing episodes retain their explicit references and paid narration; only new episodes inherit the resulting combined defaults.

The channel's «Голоси для перекладу» panel shows its persisted narration service, model and applicable Fish delivery style from `GET /api/channels/<id>/voices` (`narration_defaults`). These are shared channel settings inherited by new episodes; do not present an unsaved episode selection as the channel default. Read saved metadata locally without a remote model lookup or synthesis merely to display it.

A changed saved translation hides its obsolete finished narration/player and its old language warning from the current card. Keep all paid audio on disk. The file/waveform API refuses stale narration. Check the actual old voiced words separately for audits; corrected text does not validate old speech. Missing original proof must not count as a current recording.

`backend/voice_cache.py` reuses exact spoken phrases by project, language, reference audio content, provider, model and synthesis settings. Preserve successful raw takes immediately, before timing/assembly, and preserve prior parts/requests in voice-history. A changed neighbour or timing does not rebuy an unchanged phrase. Keep context-independent reuse explicit; seam/tempo review remains necessary. Migrate legacy takes only with recorded matching voice identity; same filename or similar wording is insufficient. Never reuse uncertain/incomplete audio. A failed local fitting step preserves paid takes. With all phrases cached, no clone or TTS request is made. Prices and confirmations count only missing unique phrases, with reused/new counts; actual paid request ledgers remain separate. No automatic paid generation for verification. Tests: test_voice_cache.py, test_languages.py, test_language_defaults.py.


When narration defaults match, do not render a heading action or a button-shaped status. After a reference or active setting changes, show «Зберегти налаштування» with a save icon. The sample is part of the provider/model row: a small round grey Play and «Зразок». Before a sample exists, show only Play and «Зразок», without a credit estimate below the label. Play opens the 3/5/10/20 menu with prices; show sample estimates only in that menu. A ready sample plays or pauses directly and displays elapsed/total time; its adjacent chevron opens the sentence menu. Keep choices hidden until opened. Remove the former separate sample panel and the always-visible sentence selector. Pause and hide the compact sample while full narration runs. The original, reference and sample Play buttons use the same grey colour, icon and 34 px circle. Starting any player pauses other speech players and the timeline preview.

Sample estimates and assembly use the same cached units. If a selected sentence boundary falls inside a complete already-paid phrase, finish that cached phrase for free instead of buying its prefix. Show the expanded choice with a plus and its actual sentence count in the tooltip; retain actual words/count/duration with the sample. Prefer an existing exact prefix when present. Never label a partial recording as a complete narration unit, or buy extra sentences beyond a chosen sample. Verify playback and pause in the real browser using existing audio, without paid synthesis.

An attached voice reference shows a grey Play, its uploaded filename and duration, without a seek slider. Its only editing action is the bin. Once removed, show recording and upload actions again. Preserve the original upload filename in reference metadata and when copying channel defaults; legacy references without that metadata show their stored filename. Do not re-upload or clone audio to recover a filename.


## Narration estimates, pacing and ready state (3 November 2026)

For ElevenLabs V4 Turbo, use the author's planning allowance of 0.26 credits per uncached character (4 November 2026), for both samples and full narration. This does not alter provider catalogue rates or claim the actual tariff is 0.26. Store each run's estimated cost separately from confirmed per-request charges. HTTP `character-cost` receipts may confirm spending; missing receipts, including dialogue WebSocket synthesis, remain explicitly estimated. Never attribute an account-wide balance delta to one run when concurrent work is possible. Display the completed run's cost beside the ready voice, with an estimate label when unconfirmed. Cache-only assembly costs zero.

Actual account history can imply a discounted V4 Turbo credit rate that differs from `/models`. Never hardcode an observed discount for other accounts. Infer a tariff only from enough consistent same-model history records; whole-credit rounding on short stream chunks can make naive regression incorrect. The first history page can contain only tiny stream fragments: read a bounded number of pages before falling back to the catalogue. Persist validated rates in the Studio's private data folder, scoped to the API-key fingerprint, model, subscription tier and catalogue rate, so restarting does not lose them. Keep a recent observed tariff during insufficient/offline history for at most a day and only while account and catalogue metadata match. Measure freshness from the evidence timestamps; rereading old records cannot renew it. Never persist keys, narration text or voice IDs in this rate cache. Freeze the selected estimate throughout one narration run. Streaming history is not a complete invoice. Read account balance through `/user/subscription` separately, cache briefly, refresh after a voice job and keep stale values labelled. Never run paid speech to test prices.

A current full voice with a current saved soundtrack shows «Озвучку збережено ✓». Omit the redundant free-assembly button. When text or selected voice settings change, show the action again and retain paid takes. An outdated soundtrack has a local-only save action. Late responses and polls from a previous project must never populate the current project's voice, jobs or settings.

Measure narration pacing after five actual phrases, then in groups of ten. Reuse matching cached recordings in the measurement. Predict from the selected voice's measured rate in the target language, not the ratio of source/translation character counts. Keep the accepted translation fixed during ordinary narration. Never automatically rewrite unpaid phrases or update the published text to meet a character forecast. Keep paid text and recordings immutable; any wording repair requires a separate explicit translation/edit action before narration. V4/Turbo does not support a numeric API speed control. Fit locally within 0.85 to 1.15, balance available silence and show review markers. If the remaining text cannot fit safely, stop before more paid speech, preserving every take. No automatic paid retakes. An existing voice that remains too long at 1.15 needs a separately reviewed repair.

Uploaded video references are retained locally as full-duration normalized MP3. While uploading, show byte progress inside the reference block, then an honest processing state. For ElevenLabs instant cloning, resolve the shared existing voice ID before preparing any upload. At the author's request (4 November 2026), automatically prepare one compact sample for a new clone: approximately 70 seconds, mono 96 kbps MP3 below 900 KB, normalized with headroom. Compare bounded windows in the first five minutes for silence/clipping; do not claim speaker separation. Small references up to two minutes already below the limit can pass unchanged. Preserve the full local reference and use its full content hash for clone reuse. Never send more than 25 samples. Do not create another clone merely because preparation changed. A former short reference and a new full recording have different hashes; only register an alias after verifying audio provenance. Generated samples share the exact full-narration cache, so narration buys only missing unchanged units. Test compact sample size, duration, decoding, original preservation and ID reuse without calling paid synthesis.

## Whole-script translation length (3 November 2026)

Display a separate number-aware character comparison in Languages. `numeric_comparison.paired_forms` discounts number-word expansion only for an explicit digit in the original phrase paired with the same numeric value written in words in its translation. Match occurrences one-to-one within that phrase. If the original has no digit, count all translated words normally. Keep unmatched values, ordinary words such as «одном» and source numbers already written in words unchanged in this comparison. Whole-script totals aggregate these same phrase discounts while counting only letters. The general number parser remains separate for semantic year validation. Preserve all other text and show the normalized counts plus `(target - source) / source * 100`. Recalculate from saved text, including legacy translations; hide stale numbers while editing. This read-only metric must never rewrite a translation, change paid character estimates, invalidate voice caches or trigger compression/narration. Mark unsupported language pairs unavailable. Character agreement still does not establish spoken duration or translation quality.

Translation acceptance prioritizes faithful meaning and natural native narration. The number-aware targets are ±8.5% per phrase and ±7% for the complete script. On an explicit translation run, Studio code identifies individual outliers using source digits matched to equivalent target number words, with only letters counted. Send each problem phrase to DeepSeek exactly once with its original, current translation and a concrete percentage/target. Combine meaning, length and measured pacing issues in that one request. Permit removal of optional filler and repetition; retain essential facts, names, quantities, units, negation, chronology, date nouns and complete native grammar. Never pad short phrases. Do not send the full script back to a model to find candidates or repeat successful audits. Independently audit changed pairs only, with cached good neighbours excluded. If an optional correction fails meaning validation or worsens its length, restore the previously approved wording. Natural, source-checked deviations are approved after this single pass and remain measured truthfully; character targets alone never pause translation. Unresolved factual/language errors still require explicit review and cannot be labelled validated. Keep resumable drafts on cancellation or service failure, with one persistent correction ledger per source phrase to prevent repeat paid requests. Local tempo adjustment up to ±15% remains separate from text counts; measured seconds determine actual synchronization.

`languages.before_translate` checks language, spoken number forms and meaning against the original before `save_translation`. Preserve intermediate drafts and resume only missing or rejected units. Accept supported JSON objects, arrays and JSONL responses only with exact, unique requested phrase IDs. Check every final unit for proper names, units, complete meaning and natural phrasing; language detection alone cannot establish fidelity. Repair identified failures selectively. Cancellation, unavailable services or persistent lack of progress must retain a resumable draft and explain the actual cause. Preserve the previously accepted translation and all cached narration until a complete validated replacement is ready. Never synthesize or pay for voice as part of translation validation. Tests: `test_translation_budget.py`, `test_translation_recovery.py`, `test_translation_length_integration.py`.

MiniMax M3.1 Flash performs initial translation and ordinary audits. DeepSeek V4.1 Flash performs selective corrections and their final audit with reasoning disabled. GLM is retired. Keep historical provenance and accepted translations unchanged.

Full localization includes the target language's natural date, quantity and unit grammar. Ukrainian narration retains «року/році» and Russian retains «года/году» where required, for example «у грудні дві тисячі сімнадцятого року». Apply other languages' own conventions. Never drop these nouns or facts to hit a character budget. Use a reliably established localized film title, otherwise retain the original title; never invent a literal title. Include these rules in initial translation, semantic repairs and explicit wording edits.

The Languages UI has no translation model selector. New runs use `minimax/minimax-m3.1-flash` through OpenRouter for initial translation and ordinary independent audits. Explicit corrective requests for meaning, length and pacing use `deepseek/deepseek-v4.1-flash-1017` with reasoning disabled. A phrase already disputed by MiniMax gets its independent second check from DeepSeek. Keep DeepSeek out of the primary translation selector and record both models and actual costs. Keep the running job's model snapshot and historical attribution; old translations and jobs without model metadata used DeepSeek. Opening a page does not regenerate text or invalidate audio. Keep the actual historical model and translation cost available in the script popup. The ElevenLabs balance refreshes automatically without a manual refresh icon.

Ordinary narration always preserves the accepted text, including legacy requests with `preserve_text: false`. Reuse all matching cached takes. Complete every requested phrase once, using cached recordings wherever compatible. The 0.85 to 1.15 tempo bounds and actual decoded-duration checks remain mandatory. Timing forecasts and measured alignment issues are advisory during a requested full narration; preserve every paid take and publish the complete voice with review markers if local fitting cannot meet the target. A completed translation is not reprocessed when the page opens, refreshes or starts narration; only an explicit translation or text-edit action changes it.

FFmpeg `atempo` output duration is not exactly input duration divided by speed. Measure each locally fitted result. If accumulated output and pauses exceed the film, use `dubbing_fit.fit_measured` to adjust remaining tempo headroom from measured durations, at most three local passes, always from the preserved raw takes and within the same fifteen-percent limit. Both full narration and cache-only rebuilding use this check before scheduling. Never buy speech again or cut words to compensate for this rounding/DSP difference.

Narration forecasts reserve uncertainty only for ungenerated phrases. Compute their available raw-audio budget as `film_seconds * MAX_SPEED - measured_raw_seconds`, using the same 1.15 cap as final fitting. Unmeasured join padding belongs only to the advisory forecast: raw takes already include their own pauses. Never substitute the 1.03 forecast reserve for the allowed tempo; that falsely stops nearly finished narration. Do not divide already measured audio by a statistical reserve. Keep nominal and reserved predictions separate and test fit-capable narration at both early and late checkpoints. Forecast warnings identify how many phrases remain and the predicted shortfall, while the requested run continues. Saved takes are reused without new payment; there are no automatic paid retakes or hidden text changes.

Measure the leading/trailing quiet samples of each fitted take and retain that measurement with its tempo. `dubbing_fit.join_gaps` counts existing boundary silence towards the 50 ms breath, conservatively allowing for the 1.15 limit and a 10 ms guard at each edge. Add only the missing pause. Remeasure after tempo changes; share the resulting gaps between global fitting, measured fitting and scheduling. Never trim or overlap the recorded speech. Generate even sub-10 ms added pauses at sample precision so hundreds of small gaps cannot disappear during concatenation. A 100 ms fitting reserve must not reject a voice that fits at the permitted tempo.

For a failed full narration whose exact current phrases are all cached, `POST /api/projects/<id>/languages/<code>/voice` with `provider` and `cache_only: true` assembles those saved recordings through the normal worker and automatically saves the soundtrack. This mode verifies complete compatible cache coverage before archiving, blocks cloning and synthesis at a cache miss, and requires saved phrase timings. It retains the previous accepted audio until publication and records zero new takes/cost. Test missing cache, unchanged raw hashes, real FFmpeg boundary pauses and final duration before reporting recovery.

## Measured narration and quiet padding (4 November 2026)

`narration_audio.inspect` decodes paid takes at 48 kHz and measures their actual sample count. Remove only outer quiet below -50 dBFS while retaining 30 ms guards on both ends. Do not remove internal breaths or word samples. Keep the original take unchanged, and cache measurements by its content hash and preparation version. Forecasts and all local rendering passes must use the same prepared sample boundaries, with the shared measured join-gap calculation. Preserve raw duration and trimming metadata in the manifest. A file that contains no usable sound needs review and must not silently trigger another paid request.

Record measured speech pace from samples and full narration in `narration-profiles`, isolated by reference content, language, provider, model and synthesis settings. Reusing a take must not duplicate its observation. Only an explicit translation action may use this profile to refine the longest overruns before synthesis, followed by the same independent source-meaning audit. Never change accepted wording on page load, playback or ordinary narration. Preserve every fact, name, number and grammatical completion; a character-count lower bound must not add filler to a measured speech budget. Combine pacing and length goals in the one corrective request for that phrase. If targets cannot both be met, preserve natural source-validated wording and expose its timing for review without another rewrite or paid narration. Profiles improve the estimate, but only decoded final audio proves a fit. Continue enforcing the fifteen-percent tempo bound and measure the final duration against the film. Unresolved timing must remain visible in the completed narration review.

Check measured translation budgets for the full film, consecutive blocks of ten source phrases and the complete phrase chain. A block can borrow two seconds on either side within the original film; the complete chain must respect each original phrase's seven-second bounds. Select its longest timing overruns for concise phrasing, request the exact locally calculated percentage once per phrase and independently audit every changed phrase. Retain seekable markers for actual tempo changes and phrase shifts in finished audio.

## Phrase alignment and comparison (4 November 2026)

After getting a feasible local fit, optimize neighbouring phrase tempos and pauses jointly with `narration_alignment.propose`. Minimize both source-boundary errors with a small preference for natural tempo, preserving the ±15% tempo bounds, ±7 s boundary bounds, order and full film length. One earlier phrase's tempo can improve an entire packed chain; early speech can slow down or wait in a pause. Centre on each original spoken phrase, not on the silence before the following phrase. Rerender changed tempos from preserved raw takes, measure the actual output, and accept only a better measured fit without worse synchronization or materially worse maximum displacement. Restore fitted audio buffers/files as well as their metadata if a proposal fails. No paid resynthesis or text changes. Existing finished recordings change only on an explicitly requested local repair. Test neighbour influence, early/late speech, untouched isolated phrases and measured rollback.

Target both boundaries of every translated phrase within seven seconds of the original, preserving order and avoiding overlap. `dubbing_fit.alignment_windows` propagates these bounds and `centered_schedule` places measured takes. Local tempo stays between 0.85 and 1.15. On an explicitly requested full narration, use `allow_review` to complete all phrases even when those timing targets are infeasible (author, 4 November 2026). Keep the strict default for separate local repair helpers. The relaxed path never relaxes tempo limits or drops speech: retain the full overlong tail, report actual boundary shifts, `overrun_seconds` and `timing_status: review`, and expose the playable result with a warning. Auto-saved soundtrack mixes retain that tail too; the video montage is unchanged. A packed chain's report names the minimal largest measured overruns that contribute to it, without suggesting every phrase needs rewriting. Decode/cache validation and real service failures still stop the job with an accurate cause. No automatic paid retakes or hidden text edits.

Write `voice-timing.json` together with the completed voice, carrying `made_at`, `text_hash` and all placed phrases. `GET /api/projects/<id>/languages/<code>/alignment` reads that exact completed version. A partial retry manifest cannot describe an older finished voice. Inside the selected language's narration popup, show only the original and that translated language on one zoomable scale, with matching numbers, dark pauses, paired selection and separate phrase playback. Never add other languages' rows to this popup. Clicking empty space or outside the comparison clears only the timeline highlight; keep the last phrase details, timings and playback controls visible, including through zoom and redraws. An obsolete or absent voice has no invented translated row. Existing out-of-bounds recordings are marked for review and retained until an explicitly authorized repair succeeds.

Show each translated phrase's actual saved local tempo below its number: a turtle icon for slowing, a running figure with motion streaks for acceleration and the unsigned percentage beside it. Show `0%` without an icon when unchanged. The original row only has phrase numbers. At a scale too small for text, keep the value in the tooltip and selected phrase details. Show measured duration and the start/end displacement in those details. A tempo label comes from the completed recording's manifest, never from comparing translated and original speech durations.

Solve the full-chain timing problem with the tridiagonal interior-point solver. Independent local projection sweeps previously stopped before convergence on 341 phrases, leaving the baseline capped tempos. Check long packed chains and decoded output, alongside small neighbour cases. A proposed change to one early phrase must be evaluated across the following sequence; it may improve nearby boundaries while worsening a later constrained passage. The current raw durations, permitted tempo and source anchors determine the attainable result.

The comparison playhead is a thin, quiet grey line inside the currently sounding phrase rectangle, using that audio element's clock. It has no handle and disappears on pause, end or a silent gap. Both phrase excerpts and the full original/translated players drive it; switching players stops the previous recording. Follow the cursor horizontally and preserve its phrase through zoom changes. Beside each selected phrase's language, show its number-normalized letter count excluding spaces, digits and punctuation and the translated count's normalized percentage difference, using `numeric_comparison.comparison` for the exact corresponding texts and the source-digit-to-target-word rule. Keep the unnormalized letter count in the tooltip. If number normalization is unavailable, show no raw percentage as a substitute. These read-only counts never change the spoken text, timing or paid caches.

Show an automatic synchronization percentage beside the translated language and its flag in the phrase comparison. Use the actual completed phrase timings: for each matching phrase take the larger absolute start/end displacement, calculate `100 * max(0, 1 - drift / MAX_SHIFT) ** 2`, then average equally over all phrases. The score measures timing only; it is not semantic accuracy or simply the share inside the permitted window. Expose the formula, largest displacement and out-of-limit count in the tooltip. Omit the score when audio/timings are absent, stale or incomplete. Remove the explanatory footer about tempo signs and dark pauses.

The Text section is a compact grid of completed script files, with a flag, language name and title. Omit the redundant completed status text. Put a muted translation icon and a grey checkmark for completed translations at the foot of each script file. Keep one translation icon beside the main «Мови» heading and omit the duplicate numbered heading inside the grid. Clicking a file opens its title and script in a popup with autosave. The add-language card opens a multi-select checkbox picker with light readable text. Selecting languages alone has no side effects; its explicit «Перекласти» button starts independent translations concurrently. Show a full language column as soon as a language is added, including its script progress, narrator, narration and thumbnail. Keep translation progress inside the script card; never move unfinished languages below the grid. Thumbnail generation is independent and remains available while text translation runs. Failed starts remain individually retryable without restarting successful languages. Never launch voice synthesis from this picker. Keep source row IDs/counts during text edits. Saving defaults is hidden when the reference and provider/model/style already match. For legacy 45-second references, decoded exact excerpt matching may recognize the same longer source for this UI status only; never use that equivalence to change paid-take or remote-clone identity.

## Per-language narrator cards (4 November 2026)

The main page is labelled «Мови», with one translation icon beside its heading. Keep the compact language grid without top language capsules or a duplicate inner heading. Each language column has its own continuous rounded background and border around its script, narrator, narration and thumbnail cards. Do not enclose all languages in one shared panel. Each narrow script card has a separate «Голос диктора» card beneath it, with a grey microphone icon, a compact grey reference player, filename and saved provider/model. Hide the reference duration on this card. The player remains independently clickable; clicking the card opens that language's voice settings in a popup. Do not combine all languages into a shared reference/settings form. The original full-audio player is hidden from the top of this tab. The language picker is labelled «Виберіть мови перекладу».

Each language column also has a separate «Озвучка перекладу» card with a grey waveform icon, a compact grey player for completed audio, saved status and measured synchronization percentage. Use an exclamation icon for failed narration and preserve the existing generation confirmation and cache estimates for missing audio. Clicking ready, failed or running narration opens its details and two-row phrase comparison in a popup. Hide the former spend summary and review accordion there; actual phrase tempo and shifts remain in the comparison. Below it, a «Прев’ю» card has a 16:9 thumbnail or generation placeholder and opens the existing original/translated preview, wishes and country-adaptation controls. Polling must not reset a playing card player. Do not start paid synthesis or image generation merely by opening these cards.

`POST /api/projects/<id>/languages/provider` accepts `code` for language-specific provider/model/style choices. Channel defaults keep `language_settings` by code, and saving one language preserves the others. Synthesis, estimates and paid-cache identity resolve the selected language's settings. A running job locks only its own voice setup; unrelated languages/projects do not block editing or saving defaults. Inherited matching settings hide the save button.

## Pause frame creation and current channel logos (4 November 2026)

`POST /api/projects/<id>/production-pause` stops this project's production worker and children while preserving the existing frames and session ID. Set `paused: true` on the saved request and include it in project-list responses so both the card and plan show a resume control. `POST .../production-resume` waits until the stopped worker exits and starts a fresh session from the compact saved handoff, keeping finished assets and original author wishes. A queued paused worker must not launch. Never resume a user's paused project as part of UI testing.

`logo_layer.bind` resolves managed channel-logo clips from the channel's current source and placement on project reads. Legacy copies named `channel_logo.png` are relinked; unrelated host/name plates stay unchanged. Prepared overlays have immutable versioned paths under the channel's Studio data, shared by preview and new exports. Previously prepared exports retain their snapshot. Do not rewrite montage history or increment the project revision merely to resolve a newer logo. `GET /api/projects/<id>/branding?version=...` lets an open editor refresh its logo while preserving the playhead and selection. Disabling/removing a channel logo removes its managed overlay from the current view.


## Translation cancellation and bounded requests (4 November 2026)

A cancellation flag is monotone within the same job run. Worker progress and stale UI polling must not clear it or re-enable Cancel. Stop queued provider requests, drain already submitted responses into the resumable draft, and distinguish a new run by its start time. Empty or malformed MiniMax audit responses are not evidence of bad meaning: split the audit into smaller batches, bound repeated single-phrase attempts and preserve the draft. Never expand an empty reasoning response to an unbounded token allowance.

Each language column has its flag and name above the script card, with a hover/focus trash icon aligned to the heading's right edge. Disabled trash icons stay hidden too until hover; generic disabled-button opacity must not reveal them. The script card says «Переклад» with a grey translation icon and no duplicate flag. Narrator and translated-audio headings use grey microphone and waveform icons without duplicate flags. Keep the language flag above the column and beside «Прев’ю», including the original.

The first language column is always the original. Use the actual detected/saved source language, episode title/script, original audio and current cover. Its script card says «Оригінал» and opens a read-only source view; its narrator and «Озвучка оригіналу» players use the existing original-audio endpoint. Keep the source outside the removable translation collection and never start synthesis or translation when opening it. Hide reference duration on narrator cards while retaining duration on finished narration. Source cover opens for viewing and downloading; the existing thumbnail gallery handles editing and generation.

The author raised the local narration tempo bound to ±15% on 4 November 2026. Keep pitch, use only the necessary correction and keep the seven-second phrase boundary target. This is independent of the number-normalized translation character band. Expose the active bound as `tempo_percent` in the Languages API, use it in the confirmation, and preserve three decimals in saved speed multipliers so fractional speed changes retain their actual value. Existing audio is unchanged until an explicitly requested local rebuild.

Translation pacing profiles resolve this language's effective saved provider, model and reference, including inherited channel settings. A legacy global provider must not select another service's pace profile. Number-count corrections only recalculate comparisons; they never edit accepted wording or invalidate paid narration.

New explicit translations aim for a number-aware whole-script difference within ±7% and ±8.5% per phrase. Use one selective correction per outlier and accept natural, meaning-checked exceptions after that pass with actual deviations recorded. Never loop or pause solely on counts. Existing text is assessed without automatic edits or paid regeneration. Keep selected phrase details and tempo labels in synchronization; omit the standalone boundary commentary row. Keep current underline highlighting unchanged.

## Compact translation progress and punctuation (4 November 2026)

Keep source and translated script cards the same fixed height while working. Show only a short phase and one consistent length-agreement counter in the card. Audit progress, wait duration and batch details belong in the tooltip and script popup. Never alternate audit counts with length-agreement counts in the same main counter. Keep cancellation as a small accessible icon inside the card area. Ready thumbnails expose download and regenerate actions on hover/focus; regeneration opens wishes and country adaptation without launching a paid job.

For all source/translation length comparisons, phrase and whole-script budgets and synchronization text percentages, exclude Unicode punctuation, including periods, commas, colons, question/exclamation marks, quotes, brackets, apostrophes and dashes. Match numeric values before excluding punctuation so decimal/group separators cannot change number identity. Count only letters and preserve the source-digit-to-target-word rule. Keep saved text, paid cache identity, raw TTS character counts and credit estimates unchanged. The actual synchronization score still measures audio timing. Existing text and audio are not automatically regenerated.

## Efficient corrective translation requests (4 November 2026)

MiniMax handles the initial translation. Delegate only requested corrective units to DeepSeek through OpenRouter, with reasoning disabled as supported by its current catalog. Keep the original phrase, accepted translation and exact validation issue together. A previously rejected phrase is independently checked by DeepSeek before another rewrite. Preserve cached successful audits, partial rewrites and all paid voice takes. Keep each request model isolated in thread-local trace context and restore the outer MiniMax context for the title and next language. Attribute corrective work separately while summing actual OpenRouter costs. Do not run paid TTS as part of a text repair.

Under length pressure, optional praise, decorative adjectives, repeated emotional wording and audience-facing padding may be omitted or simplified. Preserve concrete facts, full names, exact numeric values, units, chronology, causal links, negation and essential intent. Both the correction prompt and independent checker share these permissions, so allowed concise adaptation is not repeatedly treated as a missing fact. Never add filler to meet a lower character boundary.

Below each script title show its letter-only count with a small single-T icon and compact K notation, for example «5,6K». Keep the exact count in a tooltip. Source and translated files use the same treatment. This display count never replaces the full character count used for ElevenLabs billing.


## One-pass translation correction (4 November 2026)

The author requested one concise corrective prompt per problem sentence, without repeated whole-script context or revision loops. Persist `single_pass_repairs` across resumes. A request that timed out has uncertain provider billing and is not automatically repeated. Cache audits by exact source/target pair; use DeepSeek for the final audit of corrected phrases. Combine all known issues before requesting a correction, return only its ID and wording, and cap output for that sentence. Retain factual validation and do not turn a missing/invalid audit into approval. Never trigger TTS from translation optimization.

The displayed translation price is the combined actual OpenRouter cost of initial MiniMax work, DeepSeek corrections, audits and title translation, including saved draft costs when resuming. Show «Переклад · $0.123» rounded to three decimals, without splitting or repeating provider names. Historical provenance stays in stored API fields.

A translation file with a predominantly wrong-language sentence shows a bright yellow warning triangle beside its combined cost, with exact phrase numbers in its accessible label and tooltip. Keep the cost visible while the warning is shown. Detect locally per phrase, including sufficiently long same-alphabet sentences; isolated foreign terms or one/two names in correct native speech are not sentence-level proof. Check again on the backend before sample/full synthesis and refuse before cloning or any paid speech call. The UI also blocks the action. Rechecking language never invokes a translator or consumes paid AI tokens.


## Letters-only linguistic counts (4 November 2026)

The author defines every displayed or compared linguistic character count as letters only in every language. Use `numeric_comparison.comparison_chars` for script cards including the original, editable counters, whole/phrase comparison, translation targets, synchronization details and measured speech-rate observations. Exclude spaces, line breaks, digits, punctuation, apostrophes (including modifier apostrophes), symbols and emoji. Match exact source digit values to target number words before counting the normalized pair; factual numeric validation remains separate. Do not use obsolete punctuation/space-inclusive voice-rate observations with letter counts: profile version 2 uses measured seconds per letter. Keep raw provider-billed characters and request size limits separate in `billing_chars` fields. Never change spoken text, paid cache identity or regenerate accepted text/audio merely to refresh these read-only metrics.

Language warnings must expose each exact sentence text and detected language alongside its phrase number. Expand the sole issue automatically. Closely related Russian/Ukrainian classifier guesses need corroborating orthographic/function-word evidence; a high classifier score alone must not block a clearly Russian sentence such as «Люди чувствовали вину за то, что у них так много, когда у их друзей так мало». Preserve the wrong-language block for actual foreign sentences and its pre-synthesis API guard.


## Completed script counts, cost details and horizontal language columns (4 November 2026)

File-card letter totals and percentages use the same number-aware basis: exact original digits are paired with equivalent target number words before counting letters. Keep literal unnormalized letters in `literal_letter_chars` and provider billing in `billing_chars`. The script editor hides a stale metric while autosave recomputes it. Show the percentage in parentheses directly beside T and its count, for example «T 43,3K (+4,34%)». Do not add a separate explanatory line; its tooltip gives both comparable counts and the ±7% target. The synchronization phrase details use the same paired number-aware letters and never fall back to unadjusted counts when normalization is unavailable.

Clicking the translation price opens an accessible cost dialog with a column of actual initial translation, title, checks and repairs costs, then MiniMax/DeepSeek subtotals and the cumulative total for this language in the project. Read saved OpenRouter usage only through the lazy cost endpoint; do not request provider data or parse all logs on every overview refresh. Deduplicate provider request IDs and label missing legacy attribution explicitly.

The language columns form one horizontal row at every screen width. Allow native horizontal trackpad/touch scroll, without arrow buttons. Preserve narrow existing column widths. Incomplete or resumable scripts have an inactive narration tile labelled «Спершу завершіть переклад». Enforce the same gate on sample/full synthesis API calls before provider or clone work.

Partial semantic audits preserve explicitly reported failing/passed IDs without approving omitted neighbours. Send only omitted IDs for one independent DeepSeek check, retaining known errors and exact-pair audit caches. Never discard a useful error merely because MiniMax put only failing IDs in its coverage list. Never turn omitted coverage into approval or rerun the complete translation.

Keep the original language column fixed on the left of a separate translated-language carousel. Only translated languages and the add-language card scroll. The carousel has a subtle divider and edge fades, with native horizontal trackpad scrolling and no arrow buttons (latest author preference). Prevent descendant grid min-content widths from widening the page.

The final layout pins the original column on the left, with only translated languages in a swipe carousel. Omit arrow buttons. Keep the vertical divider very low contrast. Move «Додати мову» out of the carousel into one small round plus button beside the main «Мови» heading.

The source display count normalizes only recognized number expressions that contain original digits, independently of which target is selected. Normalize target number words only when their numeric values match original digits. This keeps all displayed original denominators stable while retaining semantic number validation.

«Продовжити перевірку» means resume automatic validation and selective repair from the saved draft, never user approval and never paid speech synthesis. If an already corrected phrase receives a disputed final verdict, get one independent MiniMax verdict for only that exact source/target pair, cache it, and do not buy a second rewrite. Genuine unresolved source errors remain blocked; no foreign-language competence or approval is required from the user.

Completed translated audio must match the original duration within 0.1 seconds of encoder rounding. Longer or shorter output remains available locally for review and all paid phrase takes remain cached, but never automatically export a mix to the episode folder or label it saved. Show a bright yellow warning triangle and «Тривалість перевищена» or «Тривалість закоротка». Guard manual mix saving too; preserve any previous valid episode file. A timing shift within the film is separate from duration mismatch. Never start paid synthesis to fix this status automatically.

Russian narration permits local tempo changes within ±18% (5 November 2026). Other languages retain ±15%. Select limits per language/job using an isolated context, including measured fastest-take caches, forecasts, joint fitting and local refits. Never mutate shared global bounds while parallel jobs run. Confirmation uses the selected item's `tempo_percent`. This permission changes neither accepted text nor paid voice identity and does not request new paid takes or automatic rebuilds of existing accepted narration.

When a local refit of retained takes exceeds the source-anchor shift limit, try reducing only extra synthetic join padding from 50 ms to 30 ms, then 10 ms. Propagate the chosen gap through estimated fitting, measured fitting and placement. Keep native pauses, all source audio samples, phrase order, tempo bounds and source duration intact. Publish only a measured valid result, retaining the previous file on failure. These local retries never invoke speech services.

## Spend reports of agent runs (4 November 2026)

The user: «отчет по витраченим токенам… можливо, контекст якийсь старий ми читаємо лишній раз… прям в проект хай записується». When a run of `director.claude` ends (director or frame agent), `spend_report.record_later` reads its stream-json log and saves `projects/<id>/spend/<log>-<time>.json`; at start-up `spend_report.backfill_all` reports logs that still lack one. A report holds the run's cost from Claude Code's `modelUsage` (for a resumed session, the totals at the end less the result it printed before its first step; a resumed session without that baseline is an estimate), tokens, start and average context, shares of work by group (scene code, checks and stills, reading, directing, assets, studio, thinking), the tool results re-read on the most turns, files read again, helpers that started with a copy of the conversation, cache rewrites after long waits and short advice. Each turn's price is put on the action it starts; prices $3/$15/$0.30 and $6/$3.75 for 1h/5m cache writes per million tokens match the reported costs. `GET /api/projects/<id>/spend` (`?format=text&limit=1`) and `tools/studio.py spend P [--all]` read them; a report never touches its run. Findings and what to save: docs/LIMITS_SPEND.md. Test: `backend/tests/test_spend_report.py`.

## Razgon text reads on any background (5 November 2026)

The user: «текст, цифри… на фоні чогось, де не видно нічого… зливаються з фоном», then «по дефолту… контрастні циферки
і букви… мало кредитів не тратить». The kit's `engine/core.js` `text(g, …, { contrast: true })` does it in the engine, so
no new check or agent step is needed. `label()`, `badge`, `readout`, `callout`, `dimension`, `bigLine`, `titleCard`, `meter`,
`compareBars`, the end screen and film `label` overlays use it (scenes already written get it too); `kText` letters get
the shadow alone (`contrast: 'shadow'`). It puts a soft two-layer shadow under the letters (dark under light text,
light under dark; no plate, outline or halo, What If's rule) and picks the tone on the GPU: the picture under the
letters is drawn down to 16×4 through an SVG filter that marks samples within 0.27 of the letters' luma or past it,
halved to 1×1, and when such samples cover 42–48 % of the box, light letters cross-fade to a dark tone of their own
colour (dark ones to a light tone). No pixel is read back, so the export is not slower (07: 42 ms a frame before and
after, 1.3 % over all takes). Mid-tone text (a saturated red) keeps its colour with the dark shadow. Since 5 November 2026 the tone is off by
default (user: «блимає то чорний, то білий… в більшості текст може бути білий з тінню… забудь про такий метод»): the
shadow alone stays, and `config.json` `"textTone": true` turns the tone on for a film. The kit's `core.js` and `ui2d.js` now carry the working copy's text
cache and `compareBars` `labelW` as well, so the copy and the kit are the same files again. The skill's `render-qc.md`,
`SKILL.md` and the frame agent's brief say in one line to put text and numbers on a calm part of the picture.

## Music and effects of an animated film without a render (5 November 2026)

Episode 07 of What If had the voice alone in «Наживо» and in the «Мови» soundtracks: the director wrote no sound cues
(0 for 107 shots), and since the render moved to «Експорт MP4» nothing laid the «Razgon · музика й ефекти» clip, which
only `razgon_bridge.py push` did and the agents may not push. Now the Studio does both by itself.

The director's brief (`director.razgon_brief`, step 3) asks for the film's sound after the shots, following the kit's
`references/sound-design.md`: story-level `sfx` cues at absolute times `t` taken from `timeline/words.json`, on the
shots' visible events, about one per 15–25 s and never two within 0.3 s, and an `amb` bed on most shots (−18 to −28).
A second script, `story/gen_sound.py`, writes them into `story/shots.json`, and `gen_shots.py` carries them over when it
runs again (`sfx=old.get("sfx", [])`, `amb=old_amb.get(id)` by shot id, as 07's gen_shots.py does). The frame agent's
brief leaves the sound alone. The kit's `tools/direction_check.py` reports the sound: FAIL for unknown names, missing
sound files and cues outside the film (the mix would stop at the export), WARN for no cues, fewer than one per 40 s,
more than one per 8 s, cues within 0.3 s of each other and ambience on fewer than half the shots.

`python3 tools/razgon_bridge.py sound --razgon <project>` lays the sound without a video render: the project check, a
film Razgon draws whole (a mixed episode is refused), the plan unchanged since prepare, a wait while any `render.mjs`
runs (up to `RENDER_WAIT`, then on anyway), `render_bed` (Razgon's mix without the voice), AAC 192 kbit/s M4A of the
film's exact length (`build/studio/music_sfx.m4a`), then the M4A is imported and laid as the one `BED_TITLE` clip on its own layer right under
the channel plate and logo (`plate_layer`), the old clip and its layer removed; a 409 from an edit meanwhile is met
with a fresh project, a bed equal to the one on the timeline (the same M4A bytes) is left, and `/tidy` prunes the
replaced file (`store.RAZGON_RENDER` takes `.m4a`). It holds the project's bridge lock and is allowed under
`MULTIBOT_RENDER_ON_EXPORT`.

`backend/razgon_sound.py` runs it, at `nice -n 10`, when a director run ends done and when a frame agent's run ends
done, for an animated film with a Razgon project in the director mode (`due`). A request while one runs queues one
more run. The state is `projects/<id>/sound.json` (a run cut by a restart reads failed), the bridge's output
`sound.log`; it is in the busy list as «музика й ефекти», so `studio_restart.py` and updates wait for it. A new bed
changes the timeline's sound, so the saved language soundtracks read «outdated» through their signature
(`language_mix.snapshot`). Existing episodes are not touched: 06 and 07 keep their beds until a new director or frame
agent run there, and 07's hand-named `music_sfx-billionaire-20261105.m4a` is outside the pruned names.

The kit's mix works block by block (`BLOCK`, 10 s): `audio/mix.py` gives its sound a part at a time (`beds()`: the
ducked music, then SFX and ambience window by window, the same additions in the same order), reads the voice straight
into one array (`load_any`), measures it and its envelope per block (`voice_level`, `envelope`), and `dsp.minus_lp`,
`dsp.write_wav`, `dsp.rms_db` and `music.render_score` hold no float64 or extra copies of the whole film. The 54-minute
07 needed about 26 GB for its bed before. On a 30-minute test film the export's mix went from 6.3 GB to 3.4 GB and the bed from 6.3 GB to
2.8 GB, with the export's `mix_raw.wav` and the bed equal to the old ones sample for sample. `render_bed` takes the
same parts and keeps the old capture of the whole mix for a working copy whose mix.py has no `beds()` yet (until
`razgon_sync` brings the kit at the next start). Tests: `backend/tests/test_razgon_sound.py`,
`tools/tests/test_razgon_bridge.py` (`SoundTest`, `KitBedTest`).


## User-facing episode folders

Папка випуску призначена для користувача: сценарії, вихідні матеріали, прев’ю, готові відео й аудіо. Усі службові JSON, плани кадрів, запити агента, таймінги, журнали та проміжні файли зберігай усередині VideoKey Studio. Не створюй їх у папці випуску. План отримуй через API студії; зв’язок Razgon читай і записуй через GET/POST /api/projects/<id>/razgon-link. razgon_bridge.py prepare сам зберігає цей зв’язок усередині студії.

Studio startup migrates legacy episode service JSON into `backend/data/projects/<id>/technical-history/<timestamp>/` with byte-verified backups. Plans, animation links and production requests are authoritative in Studio project storage. Readers retain compatibility with unmigrated older episodes. Never mirror service metadata back to the episode folder. An explicit user-requested plan export is allowed.


## Paused Claude runs and bounded frame work (5 November 2026)

Treat a streamed Claude `result` as the end of the requested model turn. Flush its receipt immediately, stop reading the stream, and allow only a short bounded CLI exit grace before terminating leftover tools. A background render holding stdout open must not leave a finished project spinning until the six-hour timeout or trigger more model turns. Preserve the returned result, error/limit verdict and costs; do not report incomplete visual/performance checks as passed. Live creation status shows inactivity after two minutes without a new action. After completion hide the creation action and place the short export hint below the report. Regression: `backend/tests/test_director.py`, `frontend/tests/production-status.test.cjs`.

Claude stream logs may end without a result after pause or quota exhaustion. `spend_report` recovers the native session cost-state only when the first main message matches the log, including thinking and helper usage, and refreshes saved reports when that receipt changes. Keep one ledger event per log. Never count a resumed session cumulative total twice. Cost card requests check local receipt stamps; no paid request is made. The user-selected divisor of 35 remains an approximate display allocation.

Frame creation and direction use High. Agent/Task tools are explicitly disabled in Claude CLI. One agent takes batches of exactly five unfinished frames (only the final remaining batch may be smaller), saves every completed frame immediately, checks the batch and continues to the next. Reuse existing sets, helpers and registered takes; production-context lists missing takes for partially finished frames. Do not build large kits for the entire film in advance or launch nested Claude sessions. Preserve saved scene files on every pause. No automatic paid run is started to repair billing or check this workflow.


## Project plan switch

The switch beside «План ролика» sets the individual project mode through POST /api/projects/<id>/actions with type set_plan_mode and payload {mode: director|direct}. Channel plan_mode is a creation default only. Persist project choices and preserve plans, source audio and montage when switching. Reject changes while its director or production runs. Startup snapshots the current effective channel mode for legacy projects. The UI waits for plan_mode_editable from the backend before enabling the new switch.


## Project type defaults and timeline history

Channel settings label the creation default «Тип нових проєктів»: regular is «Універсальний» and animated means a film entirely composed of animation. Store project_kind at creation and read it for production and editor controls. Legacy projects snapshot their effective current type at safe startup. Changing channel defaults must not change existing project types.

Cmd/Ctrl-Z undoes timeline edits; Cmd/Ctrl-Shift-Z and Ctrl-Y redo. Use physical key codes for Cyrillic keyboards, preserve native text-field undo, skip open dialogs, and wait for a pending drag save before undoing it.


Enabled accents are a montage priority for meaningful animated arrows, circles and short captions on all kinds of photos. Use them on video when helpful, never as extra overlays on finished animation, host or text-only frames. Do not select frames mechanically by a fixed one-in-three quota. Both frame-agent briefs and get_project for the Studio agent must expose the saved accents flag.

## Designed text frames, moving pictures and springing accents (5 November 2026)

The user: «фон, блюр… анімацію появлення букв… професійно», «Якщо нема руху, це є проблема», «якщо диктора ми вибираємо… приближення… або віддалення… 10-15%», «акценти… з анімацією, з динамікою». `montage_ops.place --text` designs a full-frame text frame (`_designed_text`, `TEXT_LOOKS`): a neighbouring frame's picture of the episode blurred under a dark, navy or light veil, contrasting words that appear with the voice (`text_words`, varied `word_entrance`), the look turning from frame to frame. `place` moves every picture: wide photos take turns to zoom in, drift sideways and zoom out by about 12% with a cover scale, a vertical or 4:3 photo sits on its own blurred copy (`K### фон`) and zooms, a host frame zooms 12%. The `motion` op gives placed frames the same moves (frames with accents keep theirs). Accents spring in (55% → 112% → 100%) and pulse once a second later (`pop`); `animate_accents` updates older ones. The frame agent's brief adds the transitions step (`transitions --share 0.7`) and takes how people look from the channel (`people_style`). Tests: `backend/tests/test_designed_text.py`, `test_people_style.py`, `test_number_fixes.py`.

## Accents come in with an animation; the setting carries the rules (6 November 2026)

The user: «красивое появление… стрелочки, которая указывает на то место… кружочек, который появляется… текст… по словам… только там, где нужно подчеркнуть какую-то фразу», then «щоб ця галочка сама по собі інформацію давала… на іншому комп'ютері». The engine moves a clip by x, y, scale and opacity under one easing, so each arrow, ring, card and underline is two clips: the glued one (the photo's curve, invisible until its entrance ends) and an entrance clip on top, «K012 акцент N поява стрілка», linear, a keyframe each 0.04 s, ending 0.08 s after the glued clip shows (`montage_ops.animated`, `_entrance_action`, `ENTRANCE`). An arrow grows out of its tail towards the point and jabs at it twice (1.5 s; `_arrow_ends` finds the head by the width of the ink near each end), a ring closes in from 1.7× and pulses (1.4 s), a card springs open before its first word, an underline is drawn from its left end. `reglue` (also `reanimate`, `animate_accents`) glues the accents again and remakes every entrance, so it can run any number of times. Caption words keep their voice timing. `clear_accents` with `"kind": "text"` removes only the captions with their cards. The quality rules of «Акценти на кадрах» live in `production.ACCENT_RULES` and reach both the frame agent's brief and the Studio agent's system prompt: arrow head exactly on the detail being spoken about, ring around a small detail, a caption rarely and only for a phrase to stress (a warning, the main advice, a number, a sum, a law, a conclusion) of 2–6 words said in that frame, about one per 4–6 minutes, never a label of what is visible, a name such as УЗД/МРТ or a list. Tests: `backend/tests/test_agent_tools.py`.

## Language soundtracks follow the timeline's sound (6 November 2026)

The user: «переклади… йдуть без музики… без спецефектів… щоб більше такого не повторювалось». Episode 08 had its four soundtracks saved with the voice alone; the Studio laid the film's music and effects afterwards and nothing mixed them again. `language_mix.refresh(pid)` saves again every language whose full voice is current and whose soundtrack is outdated or missing, through the local «save-audio» job (FFmpeg only, no speech service). It runs when `razgon_sound` has laid a new bed, after every finished export, and for all projects at start-up (`refresh_all`). A language whose text fails the language check stays unavailable and is reported, not mixed. Test: `backend/tests/test_language_mix.py`.


## Channel effort, universal props and activity (6 November 2026)

Channel setting `claude_effort` accepts low, medium, high and xhigh, default high. Read it through `store.channel_effort` for a new director, production or Claude thumbnail prompt run, record the actual chosen value, and pass it to `--effort`. Changes do not interrupt an already running job. `animation.assets` also governs PNG props inside universal projects' Razgon scenes. The universal production brief must explicitly include the bounded library selection/generation and drawing of those props. The regular style card has real PNG props for the enabled state and vector fallbacks for disabled, cached separately; keep animated-card caches intact. Studio status exposes structured project activities. Show an animated indicator for recognition and direction in their project and channel, including on overview cards; remove it when their actual jobs finish. Do not launch paid jobs to test the indicators.

An optional channel host reference lives in Studio data as `channels/<id>/thumbnail-hero.png`, through `/api/channels/<id>/thumbnail-hero`. Show the checked «Головний герой» choice only when that image exists. Pass its explicit per-run `use_hero` choice to every original thumbnail writer and localized thumbnail job. Attach a snapshot of the identity image to prompt writing and drawing when enabled; an opt-out must omit the image and explicitly exclude the channel host. Ordinary edits of an existing thumbnail preserve their previous behavior unless the author supplies a host choice. Logo placement controls offer the four corners in one compact row; keep legacy saved non-corner placements readable without silently moving existing logos.

## Export queue (6 November 2026)

Accept confirmed exports into one FIFO queue across channels. Only one render may run at a time. Keep each waiting project's existing export guard and frozen manifest. Persist its queue position, show it with a spinner on the project card, export button and progress window, and keep the channel indicator active for queued work. Cancelling a waiting job must release its guard without starting an encoder; completion, cancellation and failure of the active render all release the slot for the next job. Duplicate submissions of the same project reuse its active job. Never interrupt a current export to activate a code change. Test the queue with local fixture projects and a controlled encoder, including cancellation, failure and continued FIFO progress.

## Combined animation workspace (7 November 2026)

For projects whose effective type is animated, combine the plan and montage in one «Анімація» tab, available before frames exist. Replace the media library with the plan workflow in a left column twice its old width: initial audio/script entry, recognition, director state and frame creation. Keep the preview and ordinary editing timeline alongside it; hide the separate plan tab and inspector. Reuse the existing plan controls, omit the creation frame-selection strip and redundant count/time readout, and place pause beside the creation progress. Starting or resuming here stays in the workspace. Production polling updates request metadata without overwriting the author's timeline or selection. Preserve the regular project's separate plan, montage, library and inspector. Tests: `frontend/tests/animation-workspace.test.cjs`.

The live creation control is muted gray with a rotating spinner, the latest plain-language action and a compact ready/total frame count. Keep pause alongside it. Hide the running activity history instead of listing timestamps, roles and technical work notes. Use clear labels such as «Готує матеріали», «Створює кадри» and «Перевіряє переходи»; do not show helper-file jargon or a gold sweeping/glowing creation button. Preserve paused/failure explanations and saved reports.

Do not display a completed «Звіт агента» block; retain the report internally. Hide the completed creation button and put the short export hint last. Single-clicking a frame group or an individual clip only changes selection, preserving the playhead; explicit navigation and scrubbing remain separate. Check this behavior while the playhead is away from the selected frame's start.

Frame edits use «Внести правки» for the selected frame(s), with Command-click preserving the first selected group. Send explicit validated frame numbers, never infer scope from a vague note. Keep this action available during production. Store FIFO requests in internal production-edits.json, deduplicate client IDs and allow waiting requests to be removed. The server drains one request at a time under the restart/mutation gate, waiting for active production, exports, quota pauses and author pauses. Persist start reservations; an uncertain interrupted paid start is not automatically replayed. A selected edit gets a fresh short scoped brief and a handoff containing only selected frames and read-only neighbours. It must not rebuild the film, run full-film checks, change audio or launch export; check changed frames and affected joins. Pending edits survive restart. Tests: test_production_edits.py, test_production_context.py, timeline-selection.test.cjs.

The completed creation display is a compact informational card with ready/total frames, a separate short review warning if present, and a muted export-availability footer. It is not a disabled action button. Keep preview header, transport and video margins compact; calculate available picture height from actual CSS insets rather than fixed spare padding.

## Linguist supervision of disputed translations (7 November 2026)

DeepSeek is the native-language «Лінгвіст»: it performs the existing source/meaning audit in bounded batches, checking faithful, simple and natural speech instead of adding another whole-script pass. Accepted unchanged neighbours keep their cached audits. For phrases still disputed after the ordinary bounded repair, it may keep faithful idiomatic wording, repair it directly, or request one fresh MiniMax translation of that phrase and review/correct its result. Send only the disputed source/translation, issue and short source neighbours. Keep numerical and target-language guards; never approve an incorrect year to finish a job. Persist every request reservation and final decision, include every model's cost, reuse accepted neighbours and never replay an uncertain paid call on resume. Contradictory checker comments concluding «No error» are inconclusive evidence and go to independent checking/supervision. Reuse an unambiguous existing target-language spoken number form when a useful repair writes the same value as digits. Do not silently discard the semantic repair. Tests: `backend/tests/test_translation_linguist.py`, `backend/tests/test_translation_recovery.py`.

When a linguist replacement fails a concrete local language/number guard, send that exact failure and phrase for at most one corrective decision, preserving its request reservation and answer. A cached semantic approval never bypasses current exact-year checks. Recognize complete Russian compound ordinal years, including «двухтысячного» and «две тысячи двухсотого»; the latter is 2200, not 2000. Before a recovery CLI starts translation, verify that the exact source/timing identity has an incomplete saved draft with the expected phrase count. The explicit translate action on a completed draft starts a new translation; use a deliberate recovery/recheck route instead when only verification was intended.


## Editable animation without pre-rendering (8 November 2026)

The `animation` format uses native editable layers and keyframes, played live by Studio. Create or replace one frame with `/ops` operation `animation` (`native_animation.py`); `replace: true` updates only that scene while preserving its group and neighbours. Do not encode animation frames to MP4/WebM/GIF or rerun Pillow/moviepy/FFmpeg video scripts for repairs. `place` and `replace` refuse this frame format. Reuse existing images as individual layers and inspect stills. Only the author's Export MP4 action renders video. Preserve previously created media and accepted projects; changing these workflow rules does not authorize a bulk rebuild of old frames.


## Channel sound choices (8 November 2026)

Channel settings group «Звук ролика» stores `sound.music.enabled`, `sound.music.generate`, `sound.effects.enabled` and `sound.effects.categories`. The 15 categories cover short editing accents such as whooshes, switching, appearance and a camera shutter, without ambient/foley categories. Categories and their built-in sound names live in `backend/sound_settings.py`; local audition WAVs are cached and use no paid service. Read the current saved channel choices in director, production and Studio-agent context. Respect them when writing music, cue and ambience plans. The bridge and the canonical Razgon audio mixer enforce the enabled flags and sound-name allowlist; music.generate=false permits only an explicit existing music file. Missing settings preserve legacy mixer config. Saving settings alone never rebuilds accepted audio.

For ordinary projects `/ops` operation `soundtrack` places locally generated music and allowed timed cues as ordinary audio clips, outside scene groups, under the same undo/revision guard. Generation is bounded to a reusable music segment, repeated on the timeline, and existing music or identical cue clips are reused. Disabled choices never start synthesis. The transitions operation uses the separate transition preferences described below, reuses matching cues and removes its own sounds when a join becomes a cut. Frame repairs preserve existing sound.

The compact timeline presents owned soundtrack and transition effect clips on one horizontal «Звук ролика» row. Music segments share one «Музика» row, and narration stays separate. Preserve each clip's real timing, overlap, volume, source and independent selection; this is display grouping, not a remix or a new render. Muting the shared row batches its audio layers in one undoable action and leaves narration alone. This presentation applies to existing and future projects.

Once a project has a production request or any made frames, the idle/paused creation button reads «Продовжити створення ролика». A first launch reads «Почати створення ролика». Original narration without an effective channel voice shows «Зразок голосу» and «Немає голосу каналу», with no misleading default provider/model. Disable its generation button until a reference (or selected HeyGen voice) is configured. Running narration must always retain its stop action. Omit the explanatory cache paragraph; preserve actual caching.

When reattaching accents, captions in the side fields and their cards/underlines share the caption's fixed coordinates. Do not attach a side-field underline to the moving photograph. Rebuild the entrance from those same coordinates so it meets the steady underline without a jump.


## Separate transition sounds for universal projects (8 November 2026)

`sound.effects` controls accents within a shot. Separate `sound.transitions` has `enabled` and a `styles` allowlist of 15 locally synthesized transition designs, with its own previews and saved choices. Missing transition settings default to disabled; preserve the author's existing accent choices. Animated projects ignore these transition sounds and hide this control in channel settings. Razgon mixer config must omit their names for an animated project.

For universal projects, the transitions operation chooses restrained sounds from the separate transition pool, matching stronger moves and leaving ordinary crossfades quiet. Without explicit direction, use about 40 percent of designed joins, at least 8 seconds apart, and vary the selected designs. The director can specify `sound_frames` (incoming frame numbers); an empty list keeps the joins silent. `/ops` `transition_sounds` updates only sound at existing joins. Do not reuse the accent allowlist for joins or add sound to every cut. Keep owned cues idempotent, remove them when a join becomes a cut, and preserve narration/music.

## New episode writing (8 November 2026)

`GET/POST /api/channels/<id>/episode-ideas` implements persisted ideas, openings and script stages. DeepSeek proposes fresh native-language topics from a bounded title history and short script samples. Recommend full-script words from actual prior scripts, editable by the author. For languages other than Ukrainian/Russian include a Ukrainian reading translation. Selecting a topic passes its exact title, target words and channel rules to Claude Opus, which writes five openings. Only the selected opening starts the full script. Preserve it verbatim. Cache successful stages, reserve running work before calling a model, never auto-repeat a paid failure, and account for both providers. Closing the dialog leaves work running; reopening resumes the saved stage. Saving the script enters the existing voice workflow without starting voice, recognition, director, frames or export automatically. New writing jobs must block restart and show channel activity.

Once the saved full-script job starts, close the episode wizard and return to the channel overview immediately. Its project card shows a spinner and «Opus пише сценарій». Never cancel the server job on close. A successful full script records the normal gray unread completion mark; refresh the card once when writing ends. Idle narration shows a compact row with its quote and a labeled «Озвучити сценарій» button, without an empty status row.

The author removed native browser confirm/alert/prompt dialogs throughout Studio (8 November 2026). Explicit buttons execute their actions directly; show narration quotes, cache counts, progress and errors inline. Modal close, backdrop click and Escape close immediately. Preserve functional forms and their explicit save/start buttons, project locks, cache reuse and the existing server authorization checks. Do not reintroduce browser confirmations when adding a workflow.

After a script is finished, «Новий випуск» opens an empty title and the remaining cached unused topics. Keep the completed script on its project card, not as the new-episode dialog's default screen. Choosing a subsequent topic creates a distinct writing run and project only on «Створити зачини · Opus»; archive the old run, preserve its script/receipts, and reject reused topic indexes. Opening the dialog starts no new paid topic request for a completed run. The refresh button explicitly requests fresh topics when needed.

«Новий випуск» always opens an empty title and the channel topic catalog, even while another episode has saved hooks. `GET /api/channels/<id>/episode-ideas?view=topics` never returns project hooks. `episode-topics.json` preserves the latest topics and the daily request reservation independently of project writing. Save hooks and their exact title/target on the episode in `episode-draft.json`; `GET/POST /api/projects/<id>/episode-draft` reads them, explicitly regenerates openings, selects a hook or cancels the draft. Clicking that project's card reopens its unfinished hooks. Close leaves the draft intact. Cancellation preserves project files; a missing/deleted project cannot block new topics. Archive earlier variants before regeneration, preserve receipts, deduplicate retried POSTs by request_id, and never automatically retry a failed paid request. Opening an older draft must not replace the current topic catalog or its daily reservation.

Writing concurrency is scoped to one project, with a separate channel topic job. Allow different episodes in the same channel to prepare hooks/scripts simultaneously. `episode_ideas.ACTIVE` maps project IDs (or the channel ID for topics) to active job data; use `active_work()` for restart gates and all project/channel spinners. A finishing job saves its own draft without replacing another episode as the current one. Topic request reservations and latest topics remain independent. Reject overlapping steps only within the same episode, and verify reverse completion order.

## Native animation seam and label acceptance (8 November 2026)

Native animation API checks each output frame for nonzero content beyond its generated backing colour before applying timeline actions. Scene-spanning layers ending one output frame early are held to the exact common seam. Intentional shorter events remain shorter; they cannot leave the scene without content. Never subtract one frame from all layer durations. Native text and PNG labels marked foreground=true draw above decorative bars and shapes. Reserve label/branding space and inspect motion extrema plus adjacent seams, including the final frame before each cut. A shape crossing a readable label is a defect even if the still at another time is fine.

The new-episode dialog keeps an empty title field and «Створити випуск», followed by exactly five «Нові теми» with a DeepSeek icon and refresh control. Titles must contain no colon, dash or hyphen. While Studio runs, generate fresh suggestions automatically once per Kyiv calendar day per channel; reserve that day before the call, retain the cache and do not retry a failed/uncertain call automatically. Preserve a selected topic and unfinished Opus work across daily refreshes. Manual refresh is an explicit new request. PNG assets is one mandatory channel rule for both animation and razgon_2d; director plans their meaningful use, frame agents place them, geometric diagrams may stay procedural.

Choosing a proposed topic first opens a local confirmation step with the exact title and editable recommended word count. Do not call Opus or create a project merely on selecting the card. «Створити зачини · Opus» explicitly starts the five openings; adjacent «Скасувати» returns to the list without a model request. Use the same highlighted Claude icon/button as preview generation. Omit the recommendation explanation. Keep the title field empty on the initial list and show word-count editing only in the selected-topic step.

Topic cards contain plain titles and Ukrainian reading translations, with no list-number prefixes. Strip enumeration markers such as `1. ` or `2) ` while preserving meaningful leading title counts such as `7 Geräusche`. Normalize cached suggestions and duplicate comparisons with the same rule. Export remains an explicit author action after project review.

## Preview loading and readable labels (8 November 2026)

Media file requests reuse a bounded, project-file-versioned read-only snapshot in `media_delivery.py`. Resolve and validate the actual file path on every request. Timeline edits/deletion invalidate it immediately; a new derived channel-logo ID refreshes metadata. Visual files must never enter voice matching, load narration or compute audio fingerprints. Prioritize the current picture above upcoming images.

Use the same half-up output-frame index in the Razgon bridge, mixed export and native montage. At 25 fps the shared 207.7-second seam is frame 5193, never frame 5192. Correct old code-block ends against the actual plan rather than hiding real timeline gaps.

Plain contrast labels have no automatic shadow or halo. Caption text and cards use the same selected palette; legacy dark cards must not remain behind a light style's dark text. Light palette label colors meet a stable 4.5 contrast ratio against its card. This is a palette choice, never a moving-background color switch. Screen-space titles stay at a fixed anchor with no continuous zoom/drift. Object labels may move with their object in one group. `animation_preferences.TEXT_RULES` reaches planning and frame agents for both PNG modes. Preserve explicit authored dim text effects and picture shadows.

Camera and element movement belong to the director for every channel. The director writes the composition and intended movement into each frame idea; execution checks the actual image and adjusts that frame deliberately. Keep infographic text, data and important objects visible at every extreme of the chosen trajectory, respecting the logo zone. Do not choose movement by frame number or prescribe a generic zoom percentage for infographics. Dynamic elements may move while the camera remains still. Shared planning/execution guidance is in backend/motion_direction.py. Placement without an explicit motion choice stays still, including vertical-photo backing and host footage; invalid motion names fail instead of falling back to a zoom.
