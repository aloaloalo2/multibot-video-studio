# MultiBot Video Studio frontend

Static frontend served by the local studio backend at `/`. It has no build step or external network dependency. Open `index.html` through the backend so the relative API routes are available.

## User flow

1. Select a channel in the sidebar. The right side shows that channel's project list. A gear appears beside each channel on hover or keyboard focus.
   Channel settings configure automatic scene planning. Select another channel and click Import proportions to copy its format percentages into the form, then Save to persist them. Other channel settings remain independent. The summary uses numbered, saturated segments with black separators and a text legend.
2. Create a project or open an existing project card. The editor shows local media, preview, inspector and track timeline. Every media item has one universal layer; a new empty project starts with one empty layer. Video, images, text, animation and audio use the same layer model. Adding another item creates its layer, and splitting a clip creates a second layer.
   While a project is open, channel navigation is hidden and the editor fills the window. The logo, Home button, and project title remain in the header. Returning to the project list restores channel navigation. The sidebar contains channels with generic channel icons; projects appear only in the main area. Plan import is available internally through the API for the automated production workflow.
   Project cards have rename and trash controls. The gray project name in the header is also a rename button. Deletion hides the managed project and offers immediate restoration while preserving episode files.
   Each channel and project has a stable browser address. Refresh and browser back/forward restore the selected channel, project and plan/editor view.
   The Plan tab shows the attached scene map, timing summary, and full script in an expandable section. A draft has a compact red badge and cannot enter montage. Add voiceover / timings accepts audio, video, or a timing JSON. Media is recognized locally by Whisper and compared with the script. Progress and a persistent comparison report show matched words, complete phrase matches, transcript differences and uncertain boundaries. Clean results apply timings automatically; disputed results preserve the previous plan. Complete phrase times and full voiceover duration unlock montage; actual audio is required on the timeline before export. A total duration alone keeps the draft status. Plan approval is discussed in the chat. Regenerate can set project-specific proportions without changing channel settings. Every generated plan starts with video and allows at most five consecutive frames of the same format. The generator at `tools/video_plan.py` submits to `/api/projects/generate-plan`; repeating it updates the same episode without replacing montage clips.
   The plan timeline opens at 338% zoom, with minus/plus controls and horizontal scrolling. Its overview shows saturated, patterned format segments and black boundaries, without frame numbers. Format hover and focus highlight matching scenes. The browser tab uses the studio's SVG favicon.
   The timeline has one draggable playhead spanning all layers, with a handle above the time labels. Editor zoom is relative to the available panel width: 100% fits the full duration, including short clips, and smaller percentages shrink it further. Zoom steps range from 25% to 6400%; clicking the percentage returns to 100%. Resizing recalculates the fit, ruler labels adapt to the scale, and zoom keeps the visible playhead in place. The plan timeline retains its separate 338% default.
   Preview mute sets monitor volume to zero and restores its previous level on unmute. Volume, mute and the previous audible level are remembered in this browser after a reload. Undo and redo are enabled and highlighted only while their respective history stacks contain actions. Channel motion settings show four curve cards labeled Linear, Ease In, Ease Out, and Ease In Out.
   The preview keeps the project's exact aspect ratio and determines the width of the central panel; side panels fill the remaining space. Search is shown only in Pixabay. Transitions are a library tab.
   The transition library has a «Кіно» filter with 15 cinematic dissolves. Warm and cool animated light leaks and bloom share their preset definitions with the renderer. These transitions do not alter a clip's own scale or position. Hover a card to preview it, drag it to the join between adjacent frames, and use the star to save a favorite. Clicking an applied join opens its properties. A slider shows duration in seconds, increasing from left to right, with the preset's normal duration at the center when both shorter and longer durations are available. Duration and type changes save automatically; moving a join preserves its configured duration.
   Removal actions show a trash icon alongside their label. Closing a composition tab and toggling a favorite retain their own icons.
   Clicking a library file opens a separate preview without adding or replacing montage clips. Audio and video previews start paused and muted, and stop when the dialog closes. Drag a file onto a layer or clip to add or replace media; Pixabay video cards also have an explicit timeline button. Full-length narration uses its actual duration, up to the backend's 10-hour limit.
   The editor header and timeline controls wrap on smaller screens. Media tabs have independent spacing, and long filenames remain available on hover. The former library help footer and visible status footer are removed; status announcements remain accessible and errors appear in the banner. The timeline uses the released footer space.
3. Select a scene. Use the inspector to trim, set transition or volume. Drag a scene onto another scene to reorder; drag an asset onto a scene to replace it. These actions save through the backend and show an error if saving fails.
4. Export opens a confirmation panel and sends `confirm_export: true` only after the user clicks Start. The panel shows job progress and output path.

The browser interface does not silently claim that a render, download or mutation succeeded. It waits for a successful API response. Failed requests leave a visible error.

Global settings provide separate password fields for Pixabay, Pexels, and Unsplash, plus optional custom service fields. Secrets are written to macOS Keychain and never returned by the API. An existing key is represented by a fixed mask; leaving it unchanged does not overwrite it. The existing Pixabay key uses the same Keychain entry as the media client. Pexels, Unsplash, and custom entries currently store keys for future adapters; media search remains available through Pixabay. Each default service links to its official license. A stored key indicates presence, not a successful provider authentication check.

## API

- `GET /api/channels` returns `{channels:[{id,name,settings}]}`.
- `POST /api/channels/pick` returns `{channel}` after a local folder selection.
- `PATCH /api/channels/:id` accepts `{settings}` and returns `{channel}`.
- `DELETE /api/channels/:id` only removes the channel from the studio list.
- `GET /api/projects?channel=:id` returns `{projects:[{id,name,status?,updated_at?,scene_count?}]}`.
- `POST /api/projects` accepts `{channel_id,name}` and returns `{project}`.
- `GET /api/projects/:id` returns `{project:{id,name,channel_id,duration,revision,scenes,tracks,assets?,settings?}}`.
- `GET /api/projects/:id/assets` returns `{assets:[{id,name,kind,path?,preview_url?,source?,duration?}]}`.
- `POST /api/projects/:id/assets/pick` returns `{asset}`.
- `GET /api/pixabay/search?kind=video&q=...` returns `{results:[{id,pixabay_id?,name,kind,preview_url,source}]}`.
- `POST /api/projects/:id/assets/from-pixabay` accepts `{kind,pixabay_id}` and returns `{asset}`.
- `POST /api/projects/:id/actions` accepts `{type,payload,expected_revision}` and returns `{project}`.
- `POST /api/projects/:id/export` accepts `{confirm_export:true,quality:"delivery"|"preview"}` and returns `{job:{id,status,progress?}}`.
- `GET /api/jobs/:id` returns `{job:{id,status,progress?,output_path?}}`.

Supported action names and payloads: `trim_scene` with `{scene_id,start,duration}` where `start` is the source trim in-point; `move_scene` with `{scene_id,to_index}`; `split_scene` with `{scene_id,at}`; `replace_scene_asset` with `{scene_id,asset_id}`; `set_transition` with `{scene_id,transition_type,duration}`; `set_clip_volume` with `{clip_id,volume}` where volume is a multiplier such as `1`; `add_text` with `{start,duration,text}`; `undo`; `redo`.

Scene shape: `{id,start,duration,title,asset_id,type,transition:{type,duration},volume,trim_start?}`. Track shape: `{id,name,type,clips:[{id,asset_id,start,duration,volume}]}`. The backend is the source of truth for ordering, timing, undo history and persistence.

## Verification

Run `node --check app.js`. Serve the frontend through the local backend and verify channel overview, project opening, asset replacement, timeline edits, settings save, and export job state in a browser. The UI intentionally does not execute direct filesystem writes.

Project cards show no creation date (user, 30 October 2026): the cover, the title and the length are enough.
