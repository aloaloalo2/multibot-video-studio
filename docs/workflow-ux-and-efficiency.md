# Preview controls and workflow efficiency

The preview dialog has one Create or Clone action and a compact DeepSeek / Codex / Claude choice. The last valid choice is stored per channel in browser preferences. It selects the existing backend writer route; it does not change the image generator, model effort or channel wishes. Opening, switching modes and selecting a writer start no paid work. A pending start locks out a duplicate submission. A late reference read cannot start generation after its dialog was replaced or its URL changed.

The gallery compares a clone's source and result, or an edited version and its exact prior image. The selected current comparison opens automatically, with a compact comparison toggle. Original and translated edits resolve their base in the same language. New clone versions retain a content-addressed local source snapshot and per-version metadata inside Studio. A later reference URL never changes an older result's comparison. Legacy edits use their saved prompt header; an unidentifiable source has no fabricated comparison. Generation still receives the text prompt and optional channel hero through the existing isolated clone drawing path.

## Shared controls

`ui-controls.js` owns standard action decoration, compact choices, validated UI preferences and keyboard support for segmented controls. The common modal builder applies shared primary, secondary and destructive styles. `ui-controls.css` defines their geometry and paint using existing theme tokens. Native fields retain a low-specificity shared rule so a compact choice can use its own functional shape. Media players, timeline handles and cards retain their geometry. Busy locks and modal ownership stay with the existing common modal handler.

## Completed efficiency items

| Original item | Implementation |
| --- | --- |
| 13. Large topic/writer context | `writer_context` sends exact repeated rule paragraphs once and combines overlapping title/subject histories into one complete exclusion ledger. Current wishes, blacklist, unique instructions and historical subjects remain intact. Context statistics are local and best effort. |
| 14. Long Opus sessions | `production_sessions` scopes long work to at most 20 frames per fresh session, retaining ordinary batches of five. Each scope must finish and pass the existing local checks before another starts. A checkpoint supports explicit continuation without replaying verified work. Failed, quota-limited, cancelled or incomplete sessions never retry automatically. Model and effort remain frozen for the run. |
| 15. Large recognition status | `GET /analysis?compact=1` projects status and readiness without transcript/word arrays. Parsed summary caching follows the exact report file version. The full report is requested when the author opens its details or needs a failed comparison. |
| 16. Independent status reads | `studio-reads.js` shares in-flight status/settings requests and briefly reuses a result across views. Consumers get independent data objects. Related mutations invalidate the pool; failures remain retryable. Existing UI ownership, cancellation and polling lifecycles remain authoritative. |
| 17. Large preview polling | Card discovery and preview polling use `GET /thumbnail?compact=1`, which skips script/frame/gallery preparation. Gallery/dialog reads still receive the full creation context when needed. Legacy prompt headings are read with a bounded 200-character read. |
| 18. Repeated global settings | The folder and word-list editors join one `/api/settings` read. No credential values enter the shared pool. |
| 19. Repeated channel profiles | `channel_profile` caches sample extraction by project/source file versions and word counts by exact script hash. A montage-only change does not recount the script. Script/source changes, renamed/removed projects and candidate order are respected. Caches are bounded. |
| 20. Large modules | The preceding module split remains in place. New controls, comparisons, status projections, prompt compaction, profiles and session orchestration have separate modules. |
| 21. Invisible elapsed work | The preceding local workflow timing recorder and clock panel remain in place; fresh session calls use the existing service timing spans. |

The compact query is compatible with an older running backend: it may return the full existing response until a safe restart. Public full routes and CLI clients remain available. No quality checks, source media or accepted scripts are removed by these optimizations. GET summaries write no files.

Global activity checks read recognition job state without opening its report. Create-video status reuses the compact cached assessment. Fresh author scopes share the existing whole-job timeout; splitting a job cannot multiply that deadline.

## Verification and measured limits

Unit/HTTP tests cover per-version comparison sources, exact language bases, compact/full API contracts, report cache invalidation/retention, complete topic exclusions, preserved unique rules, profile invalidation, independent shared reads, and scoped session completion/cancellation/failure/checkpoint behavior. A mocked worker verifies 45 frames use fresh scopes of 20, 20 and 5 with the same model/effort and retained total costs. No paid model call was used for these tests.

Isolated browser checks cover comparison, editing bases, one preview action, writer persistence, clone loading and all channel settings tabs at 1470, 780 and 390 px. No horizontal page overflow or JavaScript errors were observed. Global folder and blacklist initialization issued one settings GET. Provider starts were intercepted.

On saved context packages, exact duplicate removal saved 15,687 characters for Valentin, 15,147 for Alexey and 14,270 for Karl. Other examined packages had few exact duplicates and changed very little. These are character counts, not token billing measurements. On an isolated fixture, recognition status fell from 668,113 to 291 response bytes and preview status from 29,944 to 135 bytes. Real throughput and Opus quota savings require comparison of subsequent production runs using the retained timing/cost receipts; the fixture and mocked sessions do not measure provider billing or perceived video quality.
