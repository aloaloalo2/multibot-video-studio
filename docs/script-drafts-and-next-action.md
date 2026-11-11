# Working scripts and the next episode action

The script editor saves every edit, including an intentionally empty field. Browser recovery is immediate; Studio writes follow an 800 ms typing pause. The script heading shows a compact saving state and a clock for history. A history dialog previews one version with its word count. Restore creates a new working version and preserves the replaced text.

Working drafts live under `backend/data/projects/<id>/script-draft/`. They never modify `voice_script`, narration jobs, media, plans or project revisions. The first accepted text is pinned as `baseline`; at most 20 other previous versions are retained. An explicit narration start flushes the draft and submits the visible text through the existing narration handler. Saving or restoring text starts no paid work.

## Recovery and concurrency

- The accepted script hash and project restart epoch bind each draft to its source. A newer accepted source cannot silently revive an unrelated pending draft. The old pending text remains available explicitly in history.
- Expected versions reject competing tab writes. A writer ID and increasing local sequence allow recovery from a lost acknowledgement of that same tab's earlier write. Older sequences cannot undo later edits.
- One request saves at a time. A late acknowledgement updates the server version while retaining text typed after that request. Each tab has its own local recovery key.
- Temporary save failures preserve browser text and make up to three delayed draft-write retries. Paid actions never run through those retries. Conflict recovery is explicit and retains the previous server text in history.
- An updated interface may be served while an older backend is still busy with production. Only the exact unsupported-route response enables temporary browser-only storage. Refresh after a safe backend restart transfers those edits into Studio. Deleted projects, storage exhaustion and real conflicts remain visible failures.
- Restoring a version checks the owning project, navigation, modal generation and selected version. Responses from an earlier selection or closed dialog cannot replace another view.

## Primary action

The project header has one primary next action. It follows writing, hook selection, narration, recognition, director planning, frame creation and export. Active work shows its current stage and permits no duplicate start. Relevant missing voice, timing or plan prerequisites appear beside the action with a shortcut to the existing settings. A saved working script takes precedence over an older ready narration when deciding the next step.

The decision function is independent of rendering. Dispatch reuses the current workflow buttons and their existing validation, cancellation, API calls and idempotency. Only the delegated duplicate button is hidden. Direct montage can still add materials and export a valid visual timeline without compulsory narration. The header observes changes already rendered in the workspace; it adds no polling.

## Verification

Unit and HTTP tests cover durable/empty edits, independent accepted work, version conflicts, unknown acknowledgements, bounded history, restore, source/restart changes and disk failures. Frontend tests cover immediate reload recovery, edits during reads/writes, tab recovery, offline storage, legacy-server compatibility and action selection across normal/direct workflows.

An isolated browser with temporary projects verified editing and reload, reload before the debounce, historical restore, empty text, one narration start with the edited text, missing voice and its settings link, and typing the first script without an extra source selection. Layouts at 1470, 780 and 390 px have one visible primary action and no horizontal page overflow. Provider starts were intercepted; no paid synthesis or production ran for this check. Screenshots and results are in the local Studio audits folder.
