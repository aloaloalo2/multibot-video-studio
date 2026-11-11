# VideoKey Studio backend

Local Python standard-library server. It binds only to `127.0.0.1`, serves `frontend/` at `/`, and keeps editable project manifests under `backend/data/projects/`. Existing episode files are read-only; selected media is copied into a managed project folder. The user must confirm a final export in the interface.

Run:

```bash
python3 tools/studio_restart.py
```

After backend edits, use the same guarded restart before verifying new frontend code. It refuses while jobs are active; never force a restart over running work. Old processes retain their imported Python modules while serving updated frontend files. The frontend checks API version 2 and item-layer mode to detect incompatible instances. The canonical persistent data folder is `backend/data`; the user's projects from the earlier integration server have been copied there with their source retained.

`MULTIBOT_STUDIO_DATA` can redirect managed data for development. The project renderer is invoked as:

```bash
/usr/bin/python3 engine/render.py --project <render-manifest.json> --output <temporary.mp4>
```

The backend checks the result and moves the complete MP4 into the selected episode folder or its configured export subfolder. Exports never replace an existing file.

On Apple Silicon, universal timelines up to 1080p and 30 fps use the GPU renderer when Swift is available. It emits progress, mixes audio using the existing renderer, and fully decodes the completed MP4 before publishing it. Variable-frame-rate, rotated, interlaced, HDR, blurred-video and other unsupported slices use the established renderer. GPU failure falls back to the established export and resets progress. Set `MULTIBOT_GPU_EXPORT=0` to select the established path for diagnostics. Cancellation terminates the process group and removes temporary output.

## API

JSON mutations require an object with `Content-Type: application/json`, local `Host`, and same-origin browser requests. Non-object bodies, truncated requests, non-finite numbers and excessive JSON nesting return 400 before dispatch. Binary media and settings ZIP uploads use their existing dedicated routes. Errors return `{ "error": "..." }` with a non-2xx status.

| Method | Route | Result |
| --- | --- | --- |
| GET | `/api/health` or `/health` | `{service:"multibot-video-studio",status:"ok"}` |
| GET | `/api/channels` | `{channels:[{id,name,path,settings}]}` |
| GET | `/api/settings` | `{settings:{youtube_root,export_subfolder}}` |
| PATCH | `/api/settings` | `{settings:{...}}` saves the channel root and export subfolder |
| POST | `/api/settings/youtube-root/pick` | `{path}` selects a directory locally without applying it |
| GET | `/api/service-keys` | Provider names and key-presence status; never returns secrets |
| POST | `/api/service-keys` | `{provider_id,key,name?}` writes a key to macOS Keychain; custom service names are stored separately |
| POST | `/api/channels/pick` | Native folder chooser; optional `{path,copy_from}` for desktop integration; `{channel}` |
| PATCH | `/api/channels/<id>` | `{settings:{...}}` merges into Studio's `backend/data/channels/<id>/settings.json`; `{channel}` |
| DELETE | `/api/channels/<id>` | Hides channel without deleting its folder |
| GET | `/api/projects?channel=<id>` | `{projects:[{id,name,status,scene_count,duration,revision,created_at,updated_at}]}`, newest creation first |
| POST | `/api/projects` | `{channel_id,name,episode_path?}` creates managed project; `{project}` |
| POST | `/api/projects/import` | `{channel_id,plan_path,name?}` imports `План видео.json`; `{project}` |
| POST | `/api/projects/import/pick` | `{channel_id,name?}` opens the native JSON chooser; `{project}` |
| GET | `/api/projects/<id>` | `{project}` with editable scenes, tracks, assets, revision |
| PATCH | `/api/projects/<id>` | Rename with `{name,expected_revision?}` |
| DELETE | `/api/projects/<id>` | Permanently removes managed project data and the episode's `VideoKey` media folder; preserves the author's other episode files and Razgon source |
| POST | `/api/projects/<id>/restore` | Clears an earlier legacy soft-delete marker while its managed project still exists; cannot undo permanent removal |
| GET | `/api/projects/<id>/plan` | `{plan,source,settings_match}`: the active scene plan, or narration source in direct mode |
| POST | `/api/projects/<id>/plan` | Attach or update `{plan}` without changing montage clips |
| POST | `/api/projects/from-plan` | Upsert by `{channel_id,name,episode_path,plan}`, returning `plan_url` |
| POST | `/api/projects/<id>/actions` | `{type,payload,expected_revision}` applies one edit; `{project}` |
| GET | `/api/projects/<id>/assets` | `{assets}` from project media and episode folder |
| GET | `/api/projects/<id>/assets/<asset-id>/file` | Local media bytes with single-range support |
| POST | `/api/projects/<id>/assets/pick` | Native file chooser; optional `{path}`; copies media; `{asset}` |
| GET | `/api/pixabay/search?kind=video&q=...` | `{results}` using the existing keychain-backed client |
| POST | `/api/projects/<id>/assets/from-pixabay` | `{kind,pixabay_id,quality?}` saves one selected result and its source record; `{asset}` |
| POST | `/api/projects/<id>/export` | `{confirm_export:true}` starts verified render; `{job}` |
| GET | `/api/jobs/<id>` | `{job:{status,progress,output_path,error}}` |
| GET | `/api/studio/status` | `{busy:[lines],exports}`: running exports and every project's recognition, director, frame production, thumbnail and studio-agent job in one request |
| GET | `/api/projects/<id>/summary` | The project frame by frame: `{head,fps,revision,frames:[{n,start,end,format,group_id,line,issues}],issues}`; `?frames=10-20`, `?issues=1`, `?format=text` (plain lines) |
| POST | `/api/projects/<id>/ops` | `{ops:[...],expected_revision?,dry_run?}` montage operations (`accent`, `clear_accents`, `replace`, `transitions`, `place`, see `montage_ops.py`) as one batch and one undo step; `{revision,report,applied}` |
| POST | `/api/projects/<id>/still` | `{time,frames?,cpu?}` draws the export at that moment with its own renderer (`engine/still.py`); `{output,outputs,urls,renderer,time,notes}`. Allowed during an export |
| GET | `/api/projects/<id>/exports` | `{active,jobs}`: the running export and the latest five |

Supported v2 actions: `add_layer {name?,to_index?}`, `remove_layer {layer_id}`, `move_layer {layer_id,to_index}`, `update_layer {layer_id,name}`, `add_clip {layer_id,kind,start,duration,asset_id?,title?,text?,content_type?,color?,x?,y?,width?,height?,scale?,opacity?,volume?,preset?,preset_duration?,keyframes?}`, `move_clip {clip_id,to_layer_id?,start}`, `trim_clip {clip_id,trim_start,duration}`, `split_clip {clip_id,at}` (absolute timeline time), `replace_clip_asset {clip_id,asset_id}`, `set_clip_volume {clip_id,volume}`, `set_transition {clip_id,type,duration}`, `delete_clip {clip_id}`, `update_clip {clip_id,patch:{...}}`, `undo`, and `redo`. Keyframes may set time, x, y, scale, and opacity. A clip may contain a video, image, text, animation, or audio asset on any layer.

Transitions support cut, crossfade, and swipe in both the editor and renderer. The current project schema uses universal layers with one media item per layer, and its array order determines the visual stacking order. Existing scene-based projects are converted when read, with their original scenes and tracks kept in `legacy_backup` on the first edit.

API keys are stored with native macOS Keychain calls. Pixabay reuses the existing `pixabay-youtube-api` entry. Pexels, Unsplash, and optional custom services currently support key storage, without media-search adapters. Provider metadata contains only identifiers and display names. A key-presence status does not validate provider credentials. Tests mock the vault and never write real credentials.

## Manifest

The managed `project.json` contains `{id,name,channel_id,episode_path,schema_version:2,revision,width,height,fps,duration,tracks,assets,settings}`. New projects have one empty universal layer. Each layer contains `{id,name,type:'universal',z_index,clips}`. Each clip contains `{id,kind,asset_id?,start,duration,trim_start,title,volume,transition,x,y,width,height,scale,opacity,keyframes}` and media or animation fields where relevant. Sources in existing episode folders are referenced read-only; imported files live inside the managed project's `media/` folder.

`expected_revision` guards against editing stale state. Undo and redo snapshots are kept beside the manifest. The renderer receives a converted manifest with the engine's ordered scenes, layers, transitions, and audio tracks.

## Drafts and phrase timings

These planning gates apply to the default channel setting `plan_mode: "director"`. To use direct editing, PATCH `/api/channels/<id>` with `{"settings":{"plan_mode":"direct"}}`. The current channel setting governs its existing and new projects. Switching modes preserves all project data.

In direct mode, project responses include `plan_mode: "direct"` and `production: {plan_mode:"direct",stage:"direct",editor_ready:true,plan_ready:false,export_ready,reason}`. An empty timeline is editable. Export requires a valid visible film timeline, with the normal media validation and export lock, without a mandatory narration or scene plan. Use ordinary asset imports and `/actions` to assemble clips and scene groups. Plan-number operations still require a frame plan.

The source tab keeps narration and transcription separately. In direct mode `/plan/generate` saves a script and optional validated `timings` or `narration` into private `source-timing.json`; no frames are generated and an older plan is preserved. `/plan/analyze` applies the same source contract after speech recognition and does not start the director. `GET /plan` returns `{plan:null,source,settings_match:null}`; `source` contains `script`, its hash, and `timing: {status,audio?,sentences?}`. The backend helper `store.load_project_narration` selects this source in direct mode and the scene plan in director mode, with a compatible fallback for old projects.

The planner creates a draft even when a total duration is supplied. A synchronized plan requires a timing file with the complete voiceover duration and every script sentence in order. POST `/api/projects/<id>/plan/generate` accepts `timings: {duration, sentences: [{text,start,end}], audio_sha256?}` alongside `script`. The text must match the script, intervals must be finite, positive, ordered, non-overlapping, and within the full duration. Frame boundaries are derived from those phrase times. When first_clip_seconds is positive, the opening ends at that exact time; a sentence crossing the boundary remains unchanged and its original interval is also shown as continuation in the next frame. Original phrase intervals remain available in the plan. The optional audio fingerprint binds export to a particular file. Existing automation may alternatively submit `narration: {audio_path|asset_id, sentences}` to measure and fingerprint the source locally.

`weights` overrides only this project's proportions; `use_channel_weights:true` resets the override. Regeneration preserves montage and previous plan versions. The first frame is always video, including when first-clip duration is zero or a photo is requested by a hint. At most five frames of one format can occur consecutively. An impossible single-format run or conflicting explicit hints returns an explanation instead of violating that limit.

Project responses include derived `production: {stage,plan_ready,export_ready,reason}`. Draft import attaches a plan without creating clips. Draft plans cannot enter montage. Export additionally requires a full-length, unmuted narration clip at zero with no source trimming and a matching actual audio duration. An expected fingerprint is checked when present. These rules are enforced by the server before starting a render. The studio validates supplied timing data. A total duration never supplies missing phrase boundaries.

CLI examples use `tools/video_plan.py --timings <timings.json>` after the draft script arguments. `--audio` is optional and pairs with `--timings` to verify the source audio as well. JSON-only timing files must include `duration`; no duration is inferred from the last spoken word.

## Tests

```bash
/usr/bin/python3 -m unittest discover -s backend/tests -v
```

Tests use temporary project data and channel folders. They verify health, project creation and import, scene and audio edits, split/undo, revision conflicts, percent validation, media range delivery, export confirmation, and a real short FFmpeg export when available.

## Local audio and video analysis

POST `/api/projects/<id>/plan/analyze` accepts `{asset_id}` for an audio or video already imported through the existing media upload endpoint. GET `/api/projects/<id>/analysis` returns the latest job and report. Processing runs in a background worker, locally, through the installed `faster-whisper` package and cached multilingual `small` model in CPU int8 mode. The model is loaded with `local_files_only=True`; no media is sent to an API and no model is downloaded silently.

Video audio is extracted to a lossless PCM WAV without changing the source video. The extracted asset is reused when the source and audio fingerprints still match. Audio input is recognized directly. All original words, timestamps, recognition scores, transcript differences and the comparison report are retained in the managed project's analysis folder. Concurrent local servers identify the worker process; interrupted work can be restarted. Closing the dialog does not stop the worker.

The report distinguishes word-match percentage, phrase matches, differences, missing boundaries, overlapping intervals and low recognition confidence. Automatic acceptance requires at least 90% overall and 80% in each sentence, usable actual ASR boundaries, preserved sentence order and complete speech. Equivalent written/spoken number forms are normalized. Genuine missing, repeated or reordered speech remains blocked. Local targeted recognition retries disputed windows before a final mismatch is reported; incomplete phrase boundaries are never interpolated. A word-match percentage is not a calibrated estimate of timestamp accuracy. Reports requiring review leave the existing plan untouched. A changed source file or changed script prevents automatic application. Successful application preserves montage and plan history and binds export to the analyzed audio fingerprint. Recognition completion is published after its requested director handoff, so readers cannot observe a finished analysis before the next stage starts.

Tests cover missing/replaced/repeated words, punctuation normalization, misleading 100% text matches with low confidence, actual boundary selection, background application, review without overwriting, and video extraction reuse. A separate short synthetic audio/video check runs the real installed Whisper model. Real channel episodes are not rendered as part of these checks.


Episode folders contain user deliverables and source media. Service metadata lives in `backend/data/projects/<id>/`: `imported-plan.json`, `razgon-link.json`, `production-request.json`, source timings and histories. Startup archives legacy episode JSON under `technical-history/` after verifying an exact copy.

`GET /api/projects/<id>/razgon-link` returns the animation link. `POST` to the same endpoint accepts `{razgon_root, project}`, verifies the project ID in `story/studio_frames.json`, and stores the link internally. No episode JSON is written.

### Channel directory

`youtube_root` selects the parent directory containing channel folders. The default is the Studio installation’s parent. The native picker does not save; PATCH validates an existing readable/writable directory, persists it in backend/data/settings.json and applies it immediately when Studio is idle. New episodes and their publication outputs use the selected channel directory. Existing project paths and files are not migrated or renamed. Re-selecting a previous directory restores its channel/project list. Internal project data and caches remain in Studio. Server startup, episode/Pixabay tools and Razgon synchronization share workspace_paths.py.
