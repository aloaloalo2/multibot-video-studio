# Studio director contract

For an animated Studio project, use its current supplied app path and project id:

1. `python3 <app>/tools/direction.py prepare <project>`
2. Read the exact `director-context.txt` path printed. It contains the narration once, complete measured sentence timing, source signature, current sound policy and the full short data schema.
3. Author `story/direction.json` at the printed workspace path. Choose contiguous ranges of whole sentences by meaning, episodes, actual sets, staging, motivated camera and visual transitions. A continuous action may cover many sentences. Put cast/sets, episode development, visual motifs, tricky movements and any justified warnings in `bible`. Plan all appropriate sound events in the same pass.
4. `python3 <app>/tools/direction.py apply <project> <absolute-direction.json>`

The helper writes canonical `shots.json`, `beats.json` and `bible.md`, uses existing direction and timeline checks, then imports through the normal bridge. It starts no render or paid service. A dry run adds `--dry-run`; it changes no direction or timeline. Existing directed projects and active production are preserved. Reusing the same accepted table reuses its receipt. Changed source/settings invalidate a stale table.

For a sound event, `sentence` is one-based, `word` selects the spoken word or phrase, and `occurrence` disambiguates repeats. Digit anchors use Studio's spoken-number mapping. Alternatively use an explicit `offset` in seconds inside the named sentence. The helper rejects missing/ambiguous anchors without guessing. `python3 <app>/tools/direction.py words <project> --sentence N` provides only the needed word times.

The packet documents supported transitions, music moods, units and author-selected sound names, so routine direction needs no old generator, bridge/player/mixer source or whole word dump. Correct all reported genuine defects together before one more apply. A specific unexpected technical error can justify a targeted source read. Preserve the selected model/effort and the author's visual quality.

The standalone pipeline and author-requested frame repairs keep their own routes. Existing directions do not require conversion or rebuilding.
