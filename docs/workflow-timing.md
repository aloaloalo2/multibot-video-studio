# Workflow timing and module split

The 11 November 2026 change separates channel HTTP routing, atomic file IO, shared errors and pure timeline operations from the larger app/store modules. Existing store imports and error identity stay compatible. Channel media reads reuse the same handler and request security gates.

Each new project task records local wall time for preparation, queue waiting, external author/provider work, recognition, verification, rendering and saving. Original narration, analysis, writing, director, frame production, previews, exports and language workers use the same recorder. Provider/model choices, prompts, retries, paid cache keys and source media stay owned by the existing workflows.

The clock beside the project header opens **Час роботи**. It shows stage totals and expandable individual runs. Language runs retain their language code. A completed run needs one GET; a visible running panel refreshes every three seconds. Closing/replacing the panel or navigating stops reads and rejects late responses.

## Semantics

- Elapsed time comes from a monotonic clock. Calendar changes cannot inflate or reduce it.
- Nested stages are exclusive; their times add up to their own run. Provider wrappers can nest without counting seconds twice.
- Parallel runs overlap. The panel labels the sum as time of separate tasks, with overlapping runs counted individually.
- External-call time includes waiting for the existing request/author process and its result. It does not estimate provider-side compute, token usage or subscription cost.
- Measurements start at the worker boundary. Existing completed or already-running jobs have no invented historical breakdown.
- A status is observed after the worker’s cleanup/handoff. An observer does not write the production job. An orphaned saved running record reads as interrupted.

## Storage and API

`GET /api/projects/<id>/performance` returns fixed workflow/stage labels, stage totals and up to 64 runs. It validates the project and reads only bounded local records plus in-memory active measurements. This GET never starts analysis, retries a service or settles production.

Records live in `backend/data/projects/<id>/performance/`. There are no prompts, scripts, provider answers, credentials or media paths in them. Stage totals are aggregated; no unbounded event stream is written. In-progress writes are throttled to once per two seconds, with explicit initial/final checkpoints. Normal production state remains authoritative if observation fails. Existing-directory atomic writes prevent a late observer from recreating a deleted project.

## Verification

The regression suite covers nested time accounting, wall-clock jumps, terminal failures and cancellation, disk failure without duplicate work, read-only live/interrupted reports, retention, project deletion, independent thread context and HTTP access. Frontend tests cover project/modal ownership, disposal, GET retry and finished reports without polling. Existing workflow tests cover the unchanged narration, director, export and channel contracts.

Verified on 11 November: 1112 backend, 213 frontend, 85 engine and 55 tools tests passed. Static Python/JavaScript checks passed. AST comparison confirmed 13 moved timeline/error functions and classes were unchanged. An isolated browser preview passed at 1470, 780 and 390 px, including expandable rows, shared controls and dialog close, without paid actions. The live API was verified after the guarded idle restart.

A local recorder microbenchmark measured 5000 empty stage spans in 9.19 ms with two disk writes. This measures observation overhead on this machine; it does not estimate the duration of actual production work.
