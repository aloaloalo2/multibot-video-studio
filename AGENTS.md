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

A Razgon episode (`razgon.json` in the episode folder) exports the same film as `tools/razgon_bridge.py push` + `final`: `backend/razgon_export.py` hands the bridge's `export` command each frame's rendered timeline clip, or null for a code block; the bridge renders those frames longest first, one Chromium worker each and as many at a time as keep the Mac's RAM under 80% (`razgon_bridge.RAM_LIMIT`, about 2.2 GB a Chromium at 1080p; six at once froze a 16 GB Mac on 31 October 2026), reusing build/studio clips stamped with the same times and picture sources (`razgon_bridge.picture_fingerprints`, per frame since 1 November 2026: the frame's shots with their neighbours, the scene files that register them and its words, plus the shared config, assets, helper scenes and engine, by content; one changed scene re-renders only its frames), glues them with the channel plate and Razgon's −14 LUFS mix. A Razgon timeline with other clips, Studio transitions or effects (a mixed episode: photos, stock and text frames around some Razgon frames, as Alexey Gorbunov's) exports through the engine: first `razgon_bridge.py frames` renders only its code blocks (the same build/studio cache, each with a 0.5 s held tail for the transition out), then the engine draws each block from its clip (`razgon_export._mixed`, `app._render_razgon_blocks`). The live preview of a mixed episode draws only its `razgon_2d` frames (`frontend/razgon-live.js`). Test: `backend/tests/test_razgon_export.py`.

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
engine (`FISH_ENGINES`: S2.1 Pro Free by default, free under fair use; S2.1 Pro and S1 billed by UTF-8 bytes; Drama 3, the expressive one, with no price named by Fish yet, shown as «ціна на fish.audio»). Fish
clones inline: every request carries, as MessagePack (`languages.msgpack`), about 22 s of the voice's start cut after a
whole word with exactly the words said in it (`languages.reference`, from the recognition's `aligned_words`), so no
voice model is made (a free account may make none: «model creation limit reached (0/0)»); their keys are «Ключі сервісів» (`credentials.DEFAULTS`). Voxtral on OpenRouter has no Ukrainian or Russian.
Work files stay in `data/projects/<id>/languages/<code>`; text, title, voice and thumbnail are copied to
`<episode>/Мови/<language>/`. One job a project (`languages.ACTIVE`, in the busy list); the tab works during an export.
The languages stand on top as capsules with their flags (`langFlags`; user: «мови… зверху… капсулами… прапор… плюсик… хрестик»): a click opens that language's card below (one at a time, remembered in the browser as `langTab:<project>`), «+» opens a menu of the languages with flags and adds one (only its card; «Перекласти» stands in its text step), also while a job runs, × on a capsule removes it after a confirmation, and the capsule of the language at work shows a pulsing dot; the voice service is chosen in a
card's voice step. «Скасувати» on the job's line, which sits in the step it works on inside the language's card, stops it (`languages.cancel`): a translation or a voice at its
next part, the thumbnail at once (Codex killed); nothing half made is saved. The «Оригінал» card leads the page as one compact line: the name, the script's characters and the episode's own voice to listen to (its length is in the player)
(its language in brackets, found once: Whisper's `engine.language` of the latest recognition, else `guess_language` from the script, kept as `original_language`; the add select leaves it out) (`languages.original_file`, `voice_file`: the plan's asset, the levelled voice of `audio_gain`, the sound clip that
starts the film, a path in the timings, the Razgon project's voiceover). Text and title edits save by themselves a
moment after typing stops (no save button, no «translate again»); the tab's messages stand in the step where the button was pressed
(`langNote`), not in the studio's banner. Every language is voiced from an example in that very language, never from the original (user: «переклад будемо брати завжди від прикладу ролика на мові… або запис, або закинути приклад носія»; the original's voice carried its accent): the channel keeps one example a language for all its episodes in `<channel>/Голоси для перекладу/<language>.mp3` (+ `.txt` words, `.json` heard), set in the channel's settings, section «Голоси для перекладу» (`bindChannelVoices`; `GET /api/channels/<cid>/voices`, `POST …/voices/<code>` raw body, `…/<code>/remove`, `…/<code>/file`), and an episode may drop in its own (`own-voice.mp3`, «Інший голос лише для цього випуску»), which wins (`voice_for`). An example is the author recorded in the page (MediaRecorder, `langRecord`) or any speaker's file, cut to `OWN_SECONDS`, its words recognised by the studio's Whisper (`heard`; the passage of the translation stands when nothing is heard and the card warns). Without an example «Послухати зразок» and «Озвучити» stay off and the server refuses (`NO_VOICE`). Samples are keyed by the example too (`voice_key`: provider, Fish's engine, episode or channel and the file's time), ElevenLabs clones by `elevenlabs-<code>-<from>-<stamp>`. For now the page offers Fish Audio only (user: «будемо працювати лише з фіш-аудіо»); ElevenLabs stays in the code. A finished job shows only in the card: the job line speaks of failures and cancels. In time with the original (user: «все, що він говорить, говоритиме… в той самий час… це перше, найважливіше»): `segments_of` groups the plan's timed sentences into lines (joined when less than `SEGMENT_GAP` apart, up to `SEGMENT_MAX`), `translate_lines` sends them in batches as JSON with the seconds each has and a character budget (`CHARS_PER_SECOND`) and takes back an array of the same length (asked again once), the text keeps one line per line (`segments.json`; an edit that merges or splits lines is refused), and `whole_synced` voices each line alone and puts it at its original's start, sped up at most `SYNC_SPEED` when longer than its place, later only by what is left, silence between and after to the video's length; the card shows how fast and how late it got. Texts translated before stay whole and are fitted as before. Each capsule shows grey marks for what its language has: the text, the thumbnail, the voice (`langMarks`). The video is not changed. API: `GET /api/projects/<id>/languages`, `POST …/languages/provider`, `POST
…/languages/<code>` (add), `…/<code>/remove`, `…/<code>/text`, `…/<code>/translate|sample|voice|thumbnail`, `POST …/languages/cancel`, `GET …/languages/original`, `POST …/<code>/own-voice[/remove]`, `GET
…/<code>/file/sample|voice|thumbnail`. Test: `backend/tests/test_languages.py`.
