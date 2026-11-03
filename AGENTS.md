# Planning ownership

## Video production workflow

Before planning or editing a video with this Studio, read [docs/AI_VIDEO_WORKFLOW.md](docs/AI_VIDEO_WORKFLOW.md) and the applicable channel instructions. Use the Studio's saved channel settings and verify the plan and project through its local API.

## Optional frame planning (3 November 2026)

Read the current channel's `plan_mode` before starting work. `director` is the default and follows the voice-first planning rules below. `direct` is the author's «Без плану» mode: open the ordinary editable montage immediately, including an empty project. Keep the «Озвучка» tab with source audio, script, transcription and measured phrase timings. Store those in `source-timing.json`, without inventing a frame plan; use `store.load_project_narration` for narration consumers. `GET /api/projects/<id>/plan` returns this source in `source`. Never launch the director or require plan proportions, opening formats, a frame table or plan approval in this mode. Channel proportions and visual preferences remain useful guidance.

For direct montage, agents use the normal asset and timeline action APIs, including scene groups, clip timing, motion, text and transitions. Source audio is optional for editing and export; a valid visible film timeline is required for export. Keep ordinary media validation, export locks and output checks. The numbered-frame `place`, `frames` and legacy Razgon bridge workflows still require a director frame plan; do not fabricate one to use them in direct mode. Existing Razgon projects and prior frame plans stay intact when changing a channel's mode. The mode switch must not erase or rebuild any montage, source, translation or paid media. Returning to `director` restores that workflow's plan as the active source. An explicit episode restart archives both plan and source metadata.

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

For planning changes run `python3 -m unittest discover -s backend/tests -v` and the compatibility client tests in `tools/tests/test_video_plan.py`. Cover current saved settings, zero first clip with legacy keys, stale detection, preserved montage and offline failure. Verify UI changes in a real browser.

## Post-Whisper number text

After real phrase timings or a successful local Whisper comparison, format written-out quantities as digits in the actual saved script, phrase text and text inserts for every channel. Use backend/number_text.py. Keep spoken_script, its hash and an immutable spoken-source TXT separately; preserve ASR word boundaries when collapsing multiword numbers. Save the numeric script to the matching episode source, preserving unrelated local text. Keep exact fractions distinct from ranges. Draft scripts retain their pre-voice form. Test Russian, Ukrainian, English and German cases, value mismatches, genuine ASR boundaries and idempotent regeneration.

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

A new episode opens on the plan with a voice drop zone and an optional voice text; without text the transcript becomes the script (`analysis_jobs.start(..., script=None)`). An animated channel never gets a plan split from the script alone: `generate_project_plan` without audio or timings calls `store.await_voice`, which keeps the script on the project as `voice_script` (shown in the voice text field and used by the recognition), moves a script-only draft to `plan-history`, refuses to replace a voice or director plan, and answers `awaiting_voice` (test: `test_animated_channel_waits_for_voice_instead_of_splitting_the_script`). The editor stays closed until the timeline holds a frame of the film (see «The plan page» below). A plan with `frame_source: razgon-direction` keeps its director's sentence groups through every rebuild (`planner.keep_director_frames`); changed sentences mark it `director_stale`. Such plans show «Почати створення ролика» instead of plan regeneration; the request (`POST /api/projects/<id>/production-request`) is stored on the project and mirrored to `Запит на створення.json`. Speech comparison keeps script words with ASR time in `aligned_words`. Text fields have no focus ring. Restart or start the server only with `python3 tools/studio_restart.py` from this folder: it refuses while exports, speech, director, production, thumbnail or agent jobs run, and starts the server in its own session so it does not die with the agent's shell (on 30 October 2026 a server started with `nohup … &` from an agent session went down with that session).

Frames of an animated film are code until the author presses «Експорт MP4» (user, 30 October 2026): the frame agent (`backend/production.py`) writes the scenes and leaves «Кадр N» code blocks (`razgon_bridge.py slots --frames`), its run is done when `frame_progress.drawn` covers the requested frames and each is a block, and a frame drawn as code counts as made on the plan and the timeline; a request for frames already drawn is refused with 409. Agents the Studio starts run with `MULTIBOT_RENDER_ON_EXPORT=1`, so the bridge refuses `push` and `final`; stopping a run (`director.kill`) also stops the commands Claude Code ran in their own process groups. A cancelled export kills its whole process group after `STOP_GRACE` seconds, even when the bridge is already gone. On a Mac the frames are rendered on the GPU and encoded on the hardware H.264 encoder (`render.mjs` defaults `--gl gpu` and `--encoder videotoolbox` on darwin; the bridge also passes `--gl gpu`): about 10 times faster than the software drawing with x264. The export's progress counts every frame of the film, with the frames already rendered from the same code done from the start. The export's project lock leaves the live preview (`/razgon-live`) free, and the page shows no banner for it. The thumbnail takes stills of code frames through `render.mjs --stills` (`thumbnail_gen.code_stills`). Tests: `test_production.py`, `test_director.py`, `test_export_control.py`, `tools/tests/test_razgon_bridge.py`.

A Razgon episode (`razgon.json` in the episode folder) exports the same film as `tools/razgon_bridge.py push` + `final`: `backend/razgon_export.py` hands the bridge's `export` command each frame's rendered timeline clip, or null for a code block; the bridge renders those frames longest first, one Chromium worker each and as many at a time as keep the Mac's RAM under 80% (`razgon_bridge.RAM_LIMIT`, about 2.2 GB a Chromium at 1080p; six at once froze a 16 GB Mac on 31 October 2026), reusing build/studio clips stamped with the same times and picture sources (`razgon_bridge.picture_fingerprints`, per frame since 1 November 2026: the frame's shots with their neighbours, the scene files that register them and its words, plus the shared config, assets, helper scenes and engine, by content; one changed scene re-renders only its frames), glues them with the channel plate and Razgon's −14 LUFS mix. A Razgon timeline with other clips, Studio transitions or effects (a mixed episode: photos, stock and text frames around some Razgon frames, as Alexey Gorbunov's) exports through the engine: first `razgon_bridge.py frames` renders only its code blocks (the same build/studio cache, each with a 0.5 s held tail for the transition out), then the engine draws each block from its clip (`razgon_export._mixed`, `app._render_razgon_blocks`). The live preview of a mixed episode draws only its `razgon_2d` frames (`frontend/razgon-live.js`). The live view says what went wrong over the preview instead of an empty frame (user, 2 November 2026: «всеодно сіре, хоча код є»): the kit's `live.html` posts `{razgon: 'error'}` for a scene that fails to load or throws, a page that never says «ready» after one fresh start reads «не відповідає», and «Перезапустити перегляд» stops this project's live server and starts it again (`razgon_live.start(pid, restart=True)`; a failed start names the last line of `build/live.log`). A Razgon music-and-effects clip whose studio copy is gone plays the project's `build/studio/music_sfx.wav`, else its `build/music.wav` (`store.resolve_asset`). Test: `backend/tests/test_razgon_export.py`.

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
stock through `studio.py stock` (a numbered contact sheet of Pixabay previews, `backend/stock_sheet.py`, looked at
instead of lists of tags) and `studio.py stock-pick` (downloads the chosen one into the project and places it), pictures drawn by Codex through
`What If/razgon-2d-studio/tools/codex_image.py`, text frames itself and `razgon_2d` frames as code through
`razgon_bridge.py`, and puts each frame at its time with `python3 tools/studio.py place P N FILE|--text` (the montage op
`place`: the plan frame's start and length, a slow zoom on a photo, the group «Кадр N»). People in every frame and every
prompt are stick figures, apart from the host. The channel setting «Акценти на кадрах» (`accents` in
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
2 November 2026): `store.razgon_link` keeps the episode's razgon.json in the studio (`razgon-link.json`), so the code
frames, live view and export find their Razgon project; an episode deleted before that finds it by the studio id in
the Razgon project's `story/studio_frames.json` (`store.find_razgon_project`), and its voice in that project's
`input/` (`store.razgon_voice`); `backend/keep.py` keeps an AAC copy of every sound clip and of
the plan's voice (`projects/<id>/kept/<asset>.m4a`, made at start and after a recognition), and `store.resolve_asset`
falls back to it. Pictures and videos are not kept: the preview marks a clip whose file is gone «Файл видалено разом
із папкою випуску». Tests: `backend/tests/test_episode_store.py`, `test_space.py`.

## The thumbnail library (1 November 2026)

The thumbnail window and the «Прев'ю» tab show every thumbnail made for the episode (`thumbnail_gen.versions`, served by
`GET /api/projects/<id>/thumbnails/<name>`), newest first, the cover marked and the prompt's author tagged (DeepSeek, or
«Правка vN» for an edit). A click on another one makes it the cover (`POST /thumbnail/choose`); «Згенерувати ще одне»
adds a new version and keeps the others. «Правка» on a version sends the author's remark to Codex with that picture
attached (`POST /thumbnail` with `base`; `thumbnail_gen.editing`), and the result is the next version. The window closes
once a run starts, so the card shows «Малюємо прев'ю». «Згенерувати з DeepSeek» is a trial: DeepSeek (OpenRouter)
writes the prompt from the same brief, the frames attached as pictures (`thumbnail_gen.write_prompt_deepseek`).

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
(`langNote`), not in the studio's banner. Every language is voiced from an example in that very language (user: «переклад будемо брати завжди від прикладу ролика на мові… або запис, або закинути приклад носія»; the original's voice carried its accent), and only without one from the original's first ~22 s cut after a whole word with its recognised words (`original_example`, `REFERENCE_SECONDS`; user: «хай кнопка працює навіть якщо… лише оригінал є»; the voice block says it will carry the original's accent): the channel keeps one example a language for all its episodes in `<channel>/Голоси для перекладу/<language>.mp3` (+ `.txt` words, `.json` heard), set in the channel's settings, section «Голоси для перекладу» (`bindChannelVoices`; `GET /api/channels/<cid>/voices`, `POST …/voices/<code>` raw body, `…/<code>/remove`, `…/<code>/file`), and an episode may drop in its own (`own-voice.mp3`, «Інший голос лише для цього випуску»), which wins (`voice_for`). An example is the author recorded in the page (MediaRecorder, `langRecord`) or any speaker's file, cut to `OWN_SECONDS`, its words recognised by the studio's Whisper (`heard`; the passage of the translation stands when nothing is heard and the card warns). Only an episode with no voice at all leaves «Послухати зразок» and «Озвучити» off (`NO_VOICE`). Samples are keyed by the example too (`voice_key`: provider, Fish's engine, episode or channel and the file's time), ElevenLabs clones by `elevenlabs-<code>-<from>-<stamp>`. A saved Fish voice model is made from the example on its first use (`fish_model`: `POST /model`, train_mode fast, the example's words as `texts`; user: «а по апі хіба не можна скопіювати норм голос?… поповнив»), kept in the example's own `.json` with the file's time (a channel's example gives one model to every episode), and then used by `reference_id`; Fish refuses on an account without API credit, and then the inline example stands and the attempt waits `FISH_RETRY` seconds. The card says whether the model is saved; samples are keyed by it (`m`); while a model is made the job line says so (`announce_model`). The voice step is compact (user: «не виділяй її так… основа акценту на створенні аудіо»; «кнопки… значки… сучасніше, компактніше»): engine and likeness as small chips, the example as a line with a compact player and icons (record, upload, remove or back to the channel's), the model mark beside its label, the sample (about a minute, `SAMPLE_CHARS`) and «Озвучити · price» in one row, the ready voice with a download icon. A sample takes as many sentences as the author picks beside it (3, 5, 10 or 20, remembered in the browser; `sample_text(text, sentences)`; user: «тест вибирати, скільки речень тестити») and says what made it (engine and likeness) and belongs to its voice key, so another engine, likeness or example hides it; a ready voice keeps what made it (`made_with`: voice key, text hash, «Fish Audio · engine · likeness») and leaves the card once any of that changes (`voice_current`; user: «щоб воно дівалось після будь-яких змін, бо не ясно, хто це згенерив»). «Схожість на приклад» beside the engine (`FISH_STYLES`: «Точно як приклад», temperature 0.5 and top_p 0.6; «Звичайно» 0.7/0.7; «Живіше» 0.9/0.8, the default since the user heard it voice Russian best; user: «голос поганий… може там є настройки?») goes with each Fish request and keys the samples. An example (a file, a video, a recording, or the original's start) is folded to mono in floating point and brought to −18 LUFS, peaks −2 dBTP (`EXAMPLE_FILTER`; user: «закинув мп4 ролика як приклад… перегруз… рипить»): `-ac 1` summed a loud stereo video's channels over full scale, the MP3 clipped and Fish cloned the crackle. The page records the example with the browser's processing off (no noise suppression, no automatic gain, 48 kHz, 256 kbit/s): processed sound made the clone sound processed. For now the page offers Fish Audio only (user: «будемо працювати лише з фіш-аудіо»); ElevenLabs stays in the code. A finished job shows only in the card: the job line speaks of failures and cancels. In time with the original (user: «все, що він говорить, говоритиме… в той самий час… це перше, найважливіше»): `segments_of` groups the plan's timed sentences into lines (joined when less than `SEGMENT_GAP` apart, up to `SEGMENT_MAX`), `translate_lines` sends them in batches as JSON with original seconds as context, without a character limit and takes back each line by its id (`line_answers`; user: «Перекладач двічі повернув не ту кількість фраз»): the lines an answer lost or merged are asked again once, and a line still missing is translated alone, so one bad answer no longer stops the translation; the parts go to the translator four at a time (`TRANSLATE_AT_ONCE`, each with the original lines before it as context), and the translator answers with reasoning off (`REASONING_OFF`; user: «довгувато діпсік працює», «Перекладач не повернув переклад однієї фрази»: DeepSeek V4.1 Flash reasoned first, slowly, and a small budget left its answer empty), again with reasoning when a model refuses that, and again with more room when an answer came back empty and cut, the text keeps one line per line (`segments.json`; an edit that merges or splits lines is refused), and `whole_synced` voices each line alone and puts it at its original's start; each line is voiced once, fitted locally with pitch preserved (0.93 through 1.07), with silence between and after to the video's length. Do not buy automatic shorter or faster takes. Record timing issues when a line still cannot fit; the card shows how fast and how late it got. Texts translated before stay whole and are fitted as before. Every translation, shortening and fix carries `SPEECH_RULES` (user: «1999-го — такі речення погані… краще слова тисяча дев'ятсот… щоб було плавно, адаптовано на голос»): numbers, years, dates, percentages, money and measures in words in their right grammatical form, no digits, symbols, shorthand, brackets, lists or emoji, short sentences of one idea, spoken words, clear stresses (ё in Russian), foreign names in the language's own spelling; a line that still holds a digit or symbol is rewritten once more (`speakable`, `UNSPOKEN`). Each capsule shows grey marks for what its language has: the text, the thumbnail, the voice (`langMarks`). The voice row in «Монтаж» has a language button (`addLayerDubControl`; user: «дай змогу міняти озвучку, щоб глянути, як вийде»): «Оригінал» or a language whose voice is ready and current, and the preview then plays that voice in place of the original clip (`dubbedVoiceUrl`, no gain, it is at −16 LUFS already); preview only, kept per episode in the browser (`dub:<project>`), the export keeps the original. The video is not changed. API: `GET /api/projects/<id>/languages`, `POST …/languages/provider`, `POST
…/languages/<code>` (add), `…/<code>/remove`, `…/<code>/text`, `…/<code>/translate|sample|voice|thumbnail`, `POST …/languages/cancel`, `GET …/languages/original`, `POST …/<code>/own-voice[/remove]`, `GET
…/<code>/file/sample|voice|thumbnail`. Test: `backend/tests/test_languages.py`.

## Natural localization for dubbing (3 November 2026)

DeepSeek localizes narration into natural spoken language for the target audience. It may restructure sentences and replace expressions with contextual equivalents while preserving facts, duties, cultural setting, intent and tone. Professions and objects use the target language's natural terms for the role in the scene; the park-ranger example is contextual guidance. Preserve every dubbing line's id, order, meaning and allotted time. Keep terminology consistent across the video. `LOCALIZATION_RULES` in `backend/languages.py` applies to narration, timed translation, retries, shortening, spoken-form repairs and titles. Existing translations change only when the author requests translation again.

## Fish sampling and voice quality (3 November 2026)

The voice selector says «Подача»: temperature and top_p control variation and expressiveness, with no guarantee of speaker similarity. Each Fish engine remembers its own selection (`fish_styles`); migrating the former shared `fish_style` preserves it for the engine it belonged to. Drama 3 starts at the hosted API defaults, 0.7 / 0.7 («Звичайно»), while S2 retains its existing default. A change of engine must not carry S2's «Живіше» into Drama. An explicit choice for an engine remains saved. Samples are raw Fish responses, with no montage or time stretching. Loudness and peak measurements cannot certify that a generated voice has no audible rasp; compare actual samples before claiming a quality fix. Never regenerate a full paid voice merely to diagnose a sample.

## ElevenLabs in Languages (3 November 2026)

The author re-enabled ElevenLabs alongside Fish. Keep the service and the Eleven model selected per project, and Fish's model and delivery settings separately. `backend/eleven_api.py` discovers TTS models, languages, limits and account credit multipliers through `/v1/models` with a five-minute cache. Offer only Eleven v4 and v4 Turbo: the author removed the older generations. Without verified metadata the UI marks its documented fallback catalogue and has no invented price. Eleven v4 and v3 use `/v1/text-to-dialogue/stream`; v4 Turbo and v3 Conversational use the Text to Dialogue WebSocket, registered with one cloned voice and flushed with `close_socket`, and only save complete audio. Other TTS models use the ordinary speech endpoint for historical projects. v4 has stability 0.5 and similarity 0.75; do not send unsupported style, speed or speaker boost. Do not re-request a faster v4 take when fitting speech: shorten naturally, then use the existing bounded time stretch. Split long inputs at each model's supported length. Key sample files by provider, model and voice reference, allow the underscores in Eleven model ids in the serving route, and preserve every saved Fish sample. Costs for Eleven are estimates in credits from the account's model rates, never a fixed USD price. Show the sample estimate in its create/update button, calculated with the same sentence selector and text as synthesis. Keys live in macOS Keychain and must not appear in chat, code, screenshots or logs. Test both dialogue transports with mocked responses, including incomplete streams and unsupported languages, and verify the visible model selector.

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

The maximum local narration tempo change is now seven percent: 0.93 through 1.07, shared by synced dubbing and whole-track fitting. Centre phrases and borrow available silence within these limits. If the full text cannot fit, keep the paid takes and the previous accepted audio, report the excess and require review. Show exact speed/shift listening markers. No paid regeneration for changing these limits.


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

A changed saved translation hides its obsolete finished narration/player and its old language warning from the current card. Keep all paid audio on disk. The file/waveform API refuses stale narration. Check the actual old voiced words separately for audits; corrected text does not validate old speech. Missing original proof must not count as a current recording.

`backend/voice_cache.py` reuses exact spoken phrases by project, language, reference audio content, provider, model and synthesis settings. Preserve successful raw takes immediately, before timing/assembly, and preserve prior parts/requests in voice-history. A changed neighbour or timing does not rebuy an unchanged phrase. Keep context-independent reuse explicit; seam/tempo review remains necessary. Migrate legacy takes only with recorded matching voice identity; same filename or similar wording is insufficient. Never reuse uncertain/incomplete audio. A failed local fitting step preserves paid takes. With all phrases cached, no clone or TTS request is made. Prices and confirmations count only missing unique phrases, with reused/new counts; actual paid request ledgers remain separate. No automatic paid generation for verification. Tests: test_voice_cache.py, test_languages.py, test_language_defaults.py.


When narration defaults match, do not render a heading action or a button-shaped status. After a reference or active setting changes, show «Зберегти налаштування» with a save icon. The sample is part of the provider/model row: a small round grey Play and «Зразок». Keep sentence choices hidden until Play opens the 3/5/10/20 menu with prices. An existing matching sample has a free playback entry; choosing a generation option starts that paid sample. Remove the former separate sample panel and the always-visible sentence selector. Pause and hide the compact sample while full narration runs. The original, reference and sample Play buttons use the same grey colour, icon and 34 px circle.

An attached voice reference shows a grey Play, its uploaded filename and duration, without a seek slider. Its only editing action is the bin. Once removed, show recording and upload actions again. Preserve the original upload filename in reference metadata and when copying channel defaults; legacy references without that metadata show their stored filename. Do not re-upload or clone audio to recover a filename.


## Narration estimates, pacing and ready state (3 November 2026)

Actual account history can imply a discounted V4 Turbo credit rate that differs from `/models`. Never hardcode an observed discount for other accounts. Infer a tariff only from enough consistent same-model history records; whole-credit rounding on short stream chunks can make naive regression incorrect. The first history page can contain only tiny stream fragments: read a bounded number of pages before falling back to the catalogue. Persist validated rates in the Studio's private data folder, scoped to the API-key fingerprint, model, subscription tier and catalogue rate, so restarting does not lose them. Keep a recent observed tariff during insufficient/offline history for at most a day and only while account and catalogue metadata match. Measure freshness from the evidence timestamps; rereading old records cannot renew it. Never persist keys, narration text or voice IDs in this rate cache. Freeze the selected estimate throughout one narration run. Streaming history is not a complete invoice. Read account balance through `/user/subscription` separately, cache briefly, refresh after a voice job and keep stale values labelled. Never run paid speech to test prices.

A current full voice with a current saved soundtrack shows «Озвучку збережено ✓». Omit the redundant free-assembly button. When text or selected voice settings change, show the action again and retain paid takes. An outdated soundtrack has a local-only save action. Late responses and polls from a previous project must never populate the current project's voice, jobs or settings.

Measure narration pacing after five actual phrases, then in groups of ten. Reuse matching cached recordings in the measurement. Predict from the selected voice's measured rate in the target language, not the ratio of source/translation character counts. Keep the accepted translation fixed during ordinary narration. Never automatically rewrite unpaid phrases or update the published text to meet a character forecast. Keep paid text and recordings immutable; any wording repair requires a separate explicit translation/edit action before narration. V4/Turbo does not support a numeric API speed control. Fit locally within 0.93 to 1.07, balance available silence and show review markers. If the remaining text cannot fit safely, stop before more paid speech, preserving every take. No automatic paid retakes. An existing voice that remains too long at 1.07 needs a separately reviewed repair.

Uploaded video references are converted to full-duration normalized MP3; never truncate to 45 seconds. While uploading, show byte progress inside the reference block, then an honest processing state during conversion/recognition. For ElevenLabs cloning, split oversized MP3 references losslessly into complete ordered parts below the per-file upload limit and send one multipart clone request. Keep existing clone-id reuse. Generated sample phrases share the exact full-narration cache, so full narration buys only missing unchanged units. Tests cover interrupted samples, project switching, rounded credits, pacing, cache reuse, ready status, defaults and soundtrack delivery.

## Whole-script translation length (3 November 2026)

Translation acceptance prioritizes faithful meaning and natural native-language narration. Character counts are advisory only. An original may use digits such as `2004` or `25`, while the narration spells them out in the target language; that expansion is expected and must not cause a rejection or automatic compression. A three- or five-percent raw-character difference is not a quality criterion or a duration estimate. `translation_budget.assessment` records exact raw counts and numeric-token differences without an acceptance threshold. Actual audio duration and measured voice pacing, including the seven-percent local tempo limit, remain separate checks. Preserve every timed phrase id and order, all facts, full names, quantities and their units, natural grammar and complete meaning. Never remove information or insert filler to meet a character count.

`languages.before_translate` checks language, spoken number forms and meaning against the original before `save_translation`. Preserve intermediate drafts and resume only missing or rejected units. Accept supported JSON objects, arrays and JSONL responses only with exact, unique requested phrase IDs. Check every final unit for proper names, units, complete meaning and natural phrasing; language detection alone cannot establish fidelity. Repair identified failures selectively. Cancellation, unavailable services or persistent lack of progress must retain a resumable draft and explain the actual cause. Preserve the previously accepted translation and all cached narration until a complete validated replacement is ready. Never synthesize or pay for voice as part of translation validation. Tests: `test_translation_budget.py`, `test_translation_recovery.py`, `test_translation_length_integration.py`.

GLM is retired from translation choices at the user's request. Offer DeepSeek and MiniMax; use MiniMax for an old saved GLM selection without changing historical translation provenance or starting work automatically. Do not call GLM for new translations, repairs or audits.

Full localization includes the target language's natural date, quantity and unit grammar. Ukrainian narration retains «року/році» and Russian retains «года/году» where required, for example «у грудні дві тисячі сімнадцятого року». Apply other languages' own conventions. Never drop these nouns or facts to hit a character budget. Use a reliably established localized film title, otherwise retain the original title; never invent a literal title. Include these rules in initial translation, semantic repairs and explicit wording edits.

Translation model selection belongs to each project's language. Allow DeepSeek V4.1 Flash 1017 and MiniMax M3.1 Flash through OpenRouter. Snapshot the selected model for the entire translation job, including worker batches and audits; changing a selector alone does not regenerate or invalidate existing audio. Respect each model's supported reasoning settings and do not silently fall back to another model. Keep actual model and translation cost available in the UI. The ElevenLabs balance refreshes automatically without a manual refresh icon.

Ordinary narration always preserves the accepted text, including legacy requests with `preserve_text: false`. Reuse all matching cached takes. Measured-duration stopping, the 0.93 to 1.07 tempo bounds and final full-duration checks remain mandatory. Preserve every paid take if measured timing still fails. A completed translation is not reprocessed when the page opens, refreshes or starts narration; only an explicit translation or text-edit action changes it.

FFmpeg `atempo` output duration is not exactly input duration divided by speed. Measure each locally fitted result. If accumulated output and pauses exceed the film, use `dubbing_fit.fit_measured` to adjust remaining tempo headroom from measured durations, at most three local passes, always from the preserved raw takes and within the same seven-percent limit. Both full narration and cache-only rebuilding use this check before scheduling. Never buy speech again or cut words to compensate for this rounding/DSP difference.
