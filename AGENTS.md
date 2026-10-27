# Planning ownership

## Native timeline regression checks

Visual clip times must quantize their absolute start and end with the same deterministic frame-index function. Never independently round duration and start, as that creates one-frame gaps or overlaps at touching boundaries. Keep spoken audio and ASR times unchanged. Check every decoded frame in a fractional-boundary render.

Keep preview media DOM nodes keyed by clip/source. Removing an outgoing transition clip must not reload the incoming image or video. Preload upcoming media and its source offset. CSS stacking values must be integers; graphic covers sit above scene media and below permanent branding. Test transition application, moving an existing transition, invalid drops, hover previews, and both sides of the final frame in the real browser.

Transition favorites are local editor preferences. A cut is the default absence of a join and is omitted from the library. Applied joins can be removed with their context menu. Visual effects share one preset definition between preview and export, must be reversible, and must not alter source media or voice audio.

Use cached small thumbnails and lazy image loading in the library. Do not load source-sized review sheets or every original video just to draw library cards.

Plan creation and regeneration by the agent must use the local script or HTTP API directly. Verify plans through code/API/JSON and return plan_url for the user to review. Do not drive the website for these operations. Browser verification remains appropriate for explicitly requested UI changes.

The scene planner belongs to this Studio. Keep the planning implementation in `backend/planner.py` and execute it through `store.generate_project_plan`. Read the channel's saved settings at execution time. A project's older settings snapshot and client-supplied settings cannot replace them.

The parent `tools/video_plan.py` is a compatibility HTTP client. Keep it free of planning logic and local fallback generation. Channel settings are edited in Studio; the former standalone settings editor is retired.

Store each generated plan's settings snapshot, settings signature, generator identity and script hash. Show a stale-plan notice when saved channel settings have changed. Preserve the project identity, existing montage and previous plan when regenerating.

Ignore retired `opening_seconds`, `opening_clip_count` and `opening_clip_types` in new plans. `first_clip_seconds=0` follows the normal weighted plan. A positive value reserves the first generated video and fixes its duration. Show actual format shares by duration separately from target settings. Hints are explicit exceptions.

For planning changes run `python3 -m unittest discover -s backend/tests -v` and the compatibility client tests in `../tools/tests/test_video_plan.py`. Cover current saved settings, zero first clip with legacy keys, stale detection, preserved montage and offline failure. Verify UI changes in the embedded Codex browser.

## Post-Whisper number text

After real phrase timings or a successful local Whisper comparison, format written-out quantities as digits in the actual saved script, phrase text and text inserts for every channel. Use backend/number_text.py. Keep spoken_script, its hash and an immutable spoken-source TXT separately; preserve ASR word boundaries when collapsing multiword numbers. Save the numeric script to the matching episode source, preserving unrelated local text. Keep exact fractions distinct from ranges. Draft scripts retain their pre-voice form. Test Russian, Ukrainian, English and German cases, value mismatches, genuine ASR boundaries and idempotent regeneration.

## Video production workflow

Before planning or editing a video with this Studio, read [docs/AI_VIDEO_WORKFLOW.md](docs/AI_VIDEO_WORKFLOW.md) and the applicable channel instructions. Use the Studio's saved channel settings and verify the plan and project through its local API.
