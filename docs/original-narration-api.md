# Original narration

No paid requests run when selecting a source or estimating cost.

1. GET /api/projects/<id>/narration returns `source`, `choices`, `source_endpoint`, and current `job`.
2. POST /api/projects/<id>/narration/source with {"source":"script"} or {"source":"file"} saves the author's choice.
3. For script: POST /api/projects/<id>/narration/quote with {"text":"..."}. Response includes total/cached phrase counts, estimated_credits (ElevenLabs), estimated_usd, and tax_included. Dollar cost is an estimate. ElevenLabs includes the configured 20% tax and uses the saved account credit conversion. Fish uses its selected model's byte rate. Missing account conversion returns null, never an invented price.
4. Start paid synthesis only after the author authorizes the displayed cost: POST /api/projects/<id>/narration/start with {"text":"..."}. The saved channel voice and settings are used. Poll GET narration. A completed job contains asset_id. Send that asset to POST /api/projects/<id>/plan/analyze with asset_id and script to recognize and build the plan.
5. For file: POST /api/projects/<id>/assets/upload (raw file body, X-File-Name header), then POST /api/projects/<id>/plan/analyze with asset_id and optional script.

The narration cache is keyed by phrase text, reference voice, provider, model and voice settings. Unchanged phrases reuse exact cached audio. Failed paid calls are not retried automatically. Existing source audio remains preserved. Choosing a mode alone does not replace audio.
