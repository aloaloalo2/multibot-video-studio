# MultiBot Video Studio backend

Local Python standard-library server. It binds only to `127.0.0.1`, serves `frontend/` at `/`, and keeps editable project manifests under `backend/data/projects/`. Existing episode files are read-only; selected media is copied into a managed project folder. The user must confirm a final export in the interface.

Run:

```bash
/usr/bin/python3 backend/app.py --host 127.0.0.1 --port 8770
```

After backend edits, restart each active Studio server before verifying new frontend code. Old processes retain their imported Python modules while serving updated frontend files. The frontend checks API version 2 and item-layer mode to detect incompatible instances. The canonical persistent data folder is `backend/data`; the user's projects from the earlier integration server have been copied there with their source retained.

`MULTIBOT_STUDIO_DATA` can redirect managed data for development. The project renderer is invoked as:

```bash
/usr/bin/python3 engine/render.py --project <render-manifest.json> --output <temporary.mp4>
```

The backend checks the result and moves the complete MP4 into the selected episode folder or its configured export subfolder. Exports never replace an existing file.

On Apple Silicon, universal timelines up to 1080p and 30 fps use the GPU renderer when Swift is available. It emits progress, mixes audio using the existing renderer, and fully decodes the completed MP4 before publishing it. Variable-frame-rate, rotated, interlaced, HDR, blurred-video and other unsupported slices use the established renderer. GPU failure falls back to the established export and resets progress. Set `MULTIBOT_GPU_EXPORT=0` to select the established path for diagnostics. Cancellation terminates the process group and removes temporary output.

## API

All mutations use `Content-Type: application/json`, local `Host`, and same-origin browser requests. Errors return `{ "error": "..." }` with a non-2xx status.

| Method | Route | Result |
| --- | --- | --- |
| GET | `/api/health` or `/health` | `{service:"multibot-video-studio",status:"ok"}` |
| GET | `/api/channels` | `{channels:[{id,name,path,settings}]}` |
| GET | `/api/settings` | `{settings:{default_width,default_height,default_fps,export_subfolder}}` |
| PATCH | `/api/settings` | `{settings:{...}}` saves global defaults for new projects and the export folder |
| GET | `/api/service-keys` | Provider names and key-presence status; never returns secrets |
| POST | `/api/service-keys` | `{provider_id,key,name?}` writes a key to macOS Keychain; custom service names are stored separately |
| POST | `/api/channels/pick` | Native folder chooser; optional `{path,copy_from}` for desktop integration; `{channel}` |
| PATCH | `/api/channels/<id>` | `{settings:{...}}` merges into the channel's `video-plan.json`; `{channel}` |
| DELETE | `/api/channels/<id>` | Hides channel without deleting its folder |
| GET | `/api/projects?channel=<id>` | `{projects:[{id,name,status,scene_count,duration,revision,updated_at}]}` |
| POST | `/api/projects` | `{channel_id,name,episode_path?}` creates managed project; `{project}` |
| POST | `/api/projects/import` | `{channel_id,plan_path,name?}` imports `План видео.json`; `{project}` |
| POST | `/api/projects/import/pick` | `{channel_id,name?}` opens the native JSON chooser; `{project}` |
| GET | `/api/projects/<id>` | `{project}` with editable scenes, tracks, assets, revision |
| PATCH | `/api/projects/<id>` | Rename with `{name,expected_revision?}` |
| DELETE | `/api/projects/<id>` | Reversible removal from the list; preserves project and episode files |
| POST | `/api/projects/<id>/restore` | Restore a removed project |
| GET | `/api/projects/<id>/plan` | Read the scene map attached to the project |
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

Supported v2 actions: `add_layer {name?,to_index?}`, `remove_layer {layer_id}`, `move_layer {layer_id,to_index}`, `update_layer {layer_id,name}`, `add_clip {layer_id,kind,start,duration,asset_id?,title?,text?,content_type?,color?,x?,y?,width?,height?,scale?,opacity?,volume?,preset?,preset_duration?,keyframes?}`, `move_clip {clip_id,to_layer_id?,start}`, `trim_clip {clip_id,trim_start,duration}`, `split_clip {clip_id,at}` (absolute timeline time), `replace_clip_asset {clip_id,asset_id}`, `set_clip_volume {clip_id,volume}`, `set_transition {clip_id,type,duration}`, `delete_clip {clip_id}`, `update_clip {clip_id,patch:{...}}`, `undo`, and `redo`. Keyframes may set time, x, y, scale, and opacity. A clip may contain a video, image, text, animation, or audio asset on any layer.

Transitions support cut, crossfade, and swipe in both the editor and renderer. The current project schema uses universal layers with one media item per layer, and its array order determines the visual stacking order. Existing scene-based projects are converted when read, with their original scenes and tracks kept in `legacy_backup` on the first edit.

API keys are stored with native macOS Keychain calls. Pixabay reuses the existing `pixabay-youtube-api` entry. Pexels, Unsplash, and optional custom services currently support key storage, without media-search adapters. Provider metadata contains only identifiers and display names. A key-presence status does not validate provider credentials. Tests mock the vault and never write real credentials.

## Manifest

The managed `project.json` contains `{id,name,channel_id,episode_path,schema_version:2,revision,width,height,fps,duration,tracks,assets,settings}`. New projects have one empty universal layer. Each layer contains `{id,name,type:'universal',z_index,clips}`. Each clip contains `{id,kind,asset_id?,start,duration,trim_start,title,volume,transition,x,y,width,height,scale,opacity,keyframes}` and media or animation fields where relevant. Sources in existing episode folders are referenced read-only; imported files live inside the managed project's `media/` folder.

`expected_revision` guards against editing stale state. Undo and redo snapshots are kept beside the manifest. The renderer receives a converted manifest with the engine's ordered scenes, layers, transitions, and audio tracks.

## Drafts and phrase timings

The planner creates a draft even when a total duration is supplied. A synchronized plan requires a timing file with the complete voiceover duration and every script sentence in order. POST `/api/projects/<id>/plan/generate` accepts `timings: {duration, sentences: [{text,start,end}], audio_sha256?}` alongside `script`. The text must match the script, intervals must be finite, positive, ordered, non-overlapping, and within the full duration. Frame boundaries are derived from those phrase times; original phrase intervals remain available in each frame. The optional audio fingerprint binds export to a particular file. Existing automation may alternatively submit `narration: {audio_path|asset_id, sentences}` to measure and fingerprint the source locally.

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

The report distinguishes word-match percentage, complete phrase matches, differences, missing boundaries, overlapping intervals and low recognition confidence. Only complete normalized-text matches with usable actual ASR word boundaries are applied automatically. Incomplete phrase boundaries are never interpolated. A word-match percentage is not a calibrated estimate of timestamp accuracy. Reports requiring review leave the existing plan untouched. A changed source file or changed script prevents automatic application. Successful application regenerates the plan with current project/channel proportions, preserves montage and plan history, and binds export to the analyzed audio fingerprint.

Tests cover missing/replaced/repeated words, punctuation normalization, misleading 100% text matches with low confidence, actual boundary selection, background application, review without overwriting, and video extraction reuse. A separate short synthetic audio/video check runs the real installed Whisper model. Real channel episodes are not rendered as part of these checks.
