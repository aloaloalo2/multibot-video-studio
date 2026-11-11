# VideoKey Studio frontend

The static frontend is served by the local backend. Open it through Studio so relative API routes and local media work. It has no build step. The existing scripts share a browser global scope; inspect cross-file callers before removing a function.

## Current workflow

1. The sidebar selects a channel. The channel overview shows its episodes, saved milestones, active progress, relative dates and export checkmarks. The gear beside the channel opens its settings. The gear, New episode and Studio settings use the same quiet outlined control style.
2. New episode starts with Own title. The author can create an empty episode, explicitly open Ideas or import a YouTube reference. Opening the dialog generates nothing. Ideas request a daily refresh only when that choice is opened; explicit refresh is a separate action. A selected idea or imported reference has an editable title and target word count. Create openings starts four hooks of six sentences; choosing one starts the script. Unfinished hooks open inside that episode's script panel.
3. The script appears before the two compact source cards: synthesize the script or upload narration. The cards retain a shared script draft when switching. Missing channel voice defaults to upload. Automatic narration and automatic montage are optional channel settings. Original HeyGen narrations use one FIFO queue; waiting episodes can be cancelled.
4. Studio prepares the fixed closing pause and recognizes audio locally. A verified native take assembly supplies sentence order and measured sentence boundaries; recognition refines word timing. Uploaded or otherwise unverified audio retains the standard comparison and order checks. Temporary status failures retry reads without starting another analysis or voice generation.
5. The director plans from the voice, then frame creation updates the same montage workspace. New frame revisions and media appear without reloading, preserving the selected clip and playhead. Ordinary unchanged polls do not reload the media library. Direct montage mode keeps the manual workflow without requiring director frames.
6. The project workspace contains Montage, Preview and Languages. Preview has version history, generation, reference cloning and editing. Regular projects can create previews from title/script before frames exist; animation has its own prerequisites. Generated work continues after its dialog closes. Language work preserves the chosen voice and paid phrase cache.
7. Export is an explicit author action. Its dialog shows quality choices and size estimates. The queue reports overall progress. Actual cancellation remains available while an export runs. Project editing is locked during export, and terminal success is published only after the output is saved.

Channel narration settings contain three groups: attached voice reference, service/model and provider tuning, then sample text/result and local audio tuning. Matching completed samples show one player. Local speed, reverb and noise previews do not regenerate provider samples. Channel settings have one Save action and one mounted editor per value. Transfer in Advanced exports/imports saved channel preferences and assets; API credentials remain with the Studio installation.

Global settings contain service keys, the YouTube directory, the script/hook word blacklist and storage cleanup. Keys are masked. Copy is an explicit secret-read action; do not log or expose credentials during tests. A changed folder is staged until Save and never moves existing files. Cleanup requires its own explicit action and preserves source assets, current montage media and finished videos.

## Shared controls and async ownership

- `style.css` owns the `--ui-*` tokens, primary/secondary/outline/danger controls and dialog geometry. Layout-specific controls such as media players, timeline handles and segmented choices retain their functional shapes.
- Use the dialog cross for ordinary close. Keep cancellation when it stops actual work or abandons a pending destructive change.
- `modal()` locks a clicked action before calling it. A callback must not exit because that same button is disabled. Optional `enabled()` restores its validated state after an asynchronous response.
- Modal replacement disposes the prior editor exactly once. Async responses check their project, navigation and modal generation before changing the interface.
- GET retry must never become an automatic paid POST retry. Keep explicit mutation identifiers where the API supports them.
- A project/media refresh commits only while its starting revision and navigation remain current. Keep author drafts, including intentional empty values.
- Visible failures are reported inline or through the shared error banner. Do not silently leave a start action inert.

## API entry points

The backend owns project identity, revisions, timings, queues and persistence. Main frontend routes include:

- `/api/channels` and `/api/channels/:id` for channels and settings.
- `/api/channels/:id/episode-ideas` for the topic catalog and explicit writing starts.
- `/api/projects/:id/episode-draft` for project-bound hooks/script state.
- `/api/channels/:id/idea-reference` for public YouTube title/thumbnail references.
- `/api/projects`, `/api/projects/:id` and `/api/projects/:id/assets` for project/media reads.
- `/api/projects/:id/actions` for montage edits with `expected_revision`.
- `/api/projects/:id/narration`, `/analysis` and `/create-video` for narration and the voice-first handoff.
- `/api/projects/:id/thumbnail` and `/languages` for preview and localization workflows.
- `/api/projects/:id/export`, `/export/active` and `/api/jobs/:id` for export state.
- `/api/studio/status` for compact activity polling.

See the backend implementation and regression tests for exact payloads and compatibility routes.

## Verification

Run `node --test frontend/tests/*.test.cjs` and syntax-check changed scripts with `node --check`. Verify affected views in an isolated browser against the local backend. For routine QA, block mutations or use temporary test projects and mocked providers. Do not start paid production, save real settings, copy credentials or export an author's video solely to test a control.

The 11 November review covers the nine channel settings panels at desktop, narrow and mobile widths, the shared hover style, new episode choices, deferred requests and the combined montage update. See `docs/STUDIO_REVIEW_2026-11-11.md` and `docs/ui-design-system.md`.
