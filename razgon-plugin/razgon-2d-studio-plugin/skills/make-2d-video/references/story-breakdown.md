# Story breakdown (the creative pass)

Read the whole transcript twice, then read `storytelling.md`. Plan **episodes first** (storytelling.md §1): split the narration into 10–20 continuous stretches, each with one place, one through-action, a visible change and one camera idea. Only then cut each episode into shots. Then write `story/bible.md` (short, practical):
- **Logline and tone** (wonder / suspense / comedy / drama), plus who "you" is if the script is in second person.
- **Cast table.** For each recurring character: id, role, outfit `{top, color, head, headColor, face, legs, gloves, kid}`, signature colour, personality, and the expressions they use most. Every recurring character gets exactly ONE distinct saturated signature item (style-bible.md, Characters). Put the outfits in `scenes/cast.js`.
- **Locations (sets).** For each: name, mood (`day|golden|dusk|night|storm|interiorWarm|interiorCool|void`), where the key light comes from, the window/view, 3–6 signature props, and the layers (sky → far → mid → floor → foreground).
- **Motifs:** recurring visual devices tied to the story, such as a frozen-droplets look for slowed time, a corner multiplier badge, a heartbeat line, or a colour that marks a power.
- **Act / music plan:** sections with a mood and intensity (sound-design.md).
- **Episode list:** `E01 0:00–1:25 street · Randy decides to stay up → friends join him · slow crane down onto the porch · entry: fade from black · exit: match moon → clock`, one line per episode, plus which lines are acted and which dive into an explanation view.

Then **rewrite `story/shots.json`** (schema in engine-api.md, story/shots.json). For every shot set:
`id, start, end, episode, line, scene` (one concrete sentence describing the picture, e.g. "OTS: blurred Jake shoulder fg, Max at the window, rain, slow push"), `set`, `bars`, `in` (transition), `sfx`, `amb`, `notes`.

Pacing rules (long takes, storytelling.md §0):
- First write `story/beats.json` by hand from the meaning of the narration (never generate it from sentence or word counts). Beats of 10–35 s, a new one where the narration changes the subject.
- Each beat is one take by default; neighbouring beats in the same place continue the take. The camera travels (pan, push, crane, fly-in) inside the take instead of cutting.
- Shots are **contiguous**; the first starts at 0 and the last ends at `duration` (the voiceover length plus about 1.5 s when Razgon owns the mix; exactly the voiceover length when an external editor owns the timeline).
- Target 1–4 cuts per minute, median shot length 10–25 s. A cut inside a beat must change place, size and angle; fast montage only as a deliberate exception of ≤ 10 s.
- Every new location opens with a camera move that reveals it (crane, push, pan), not a hard cut to a wide.
- Run `python tools/direction_check.py --project projects/<slug>` and fix every FAIL before writing shot code.

Give the user a 5–10 line summary: the cast, the locations, the number of shots, and the visual highlights per act. Continue unless they object.

