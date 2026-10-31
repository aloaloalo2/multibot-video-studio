# Storytelling: episodes, continuity, and how not to make a slideshow

Read this before Stage 4 and again before every Stage 6 batch. It exists because the easiest way to fill 10–20 minutes of narration is also the worst one: a few parametric shot templates (street, face, diagram, text card) stamped out once per sentence. Every frame is technically correct, and the result is a slideshow that jerks to a new picture every 4–5 seconds, repeats the same five compositions, and never tells a story. Viewers feel it within a minute even when they can't name it ("it's all the same", "it moves in jerks", "the story doesn't flow").

The cure is to direct **meaning beats as long takes**, grouped into episodes.

## 0. Beats and long takes (read this first)
Think of the video as a game level, not a slideshow: one world, one camera that travels through it, a story that keeps moving. Every change of picture costs the viewer attention, so the picture changes only when the *meaning* changes.
- **You write the beats yourself, by meaning, never by a script that counts sentences or words.** Read the narration and start a new beat exactly where it moves to another thought ("the plan" → "night one" → "adenosine" → "4 a.m."). A typical beat is 10–35 s and covers 2–7 sentences. Save them in `story/beats.json` (`{"beats": [{"id", "first_sentence", "last_sentence", "start", "end", "intent"}]}`, sentence indices from `timeline/sentences.json`). External editors (clip plans) follow these beats.
- **One beat = one continuous take by default.** Inside it the camera *travels* instead of cutting: it pans to the street sign, pushes into a face, cranes up, flies into the head, slides to the next room. Characters act through the whole take. Neighbouring beats in the same place should continue the same take (no cut at all).
- **Cuts are rare and only at beat boundaries:** about 1–4 cuts per minute in the whole film. A cut inside a beat needs a reason (a deliberate shock, a reaction) and must change place, size and angle. Rapid montages are an exception for ≤ 10 s.
- **Text is rare and fits its container.** One idea at a time; every string measured with `maxWidth` so it never overflows a notebook page, a card or the frame.



## 1. Episodes
An episode is a continuous stretch of the film (usually 30–120 s) with:
- **one place** (a set, or a set plus the "inside" view it dives into and comes back from),
- **one through-action** that develops while the narrator talks: the hero sits down, waits, gets sleepier, checks the clock, gives up, goes to the fridge; a car drives, slows, drifts toward the lane line,
- **a state that changes from the start of the episode to its end** (time on the clock, light in the window, the hero's posture and face, a counter, a pile growing, a crowd gathering),
- **one camera idea** that spans the whole episode: a slow push from wide to the face over 40 s, a crane up and out, a dolly along the street following the walk. Individual shots inside the episode are cuts *within* that idea (wide → over-the-shoulder → insert → face), not resets.

Plan the whole video as 10–20 episodes in `story/bible.md` before writing a single shot. For each one write: time range, place, through-action, what changes (start state → end state), camera idea, entry and exit (how we arrive and how we leave), and which narration lines are illustrated by **acting** versus which ones need an **explanation view**.

## 2. Explanations come out of the story and go back into it
Diagrams, data cards and kinetic words are the biggest source of slideshow feel when they are hard-cut in and out. Instead:
- **Dive in, come back.** The camera pushes into the hero's head (`iris` from the eye, `zoom`, or a `match` from the head outline to the blueprint brain), the explanation plays, and we return to the *same* moment of the episode with the hero one step further along. Use the same anchor both ways.
- **Diegetic first.** Put numbers where they live: on the alarm clock, the phone screen, a notebook page, a TV in the room, a road sign, a lab monitor. A floating card is the last resort.
- **One explanation view per idea**, developed over its whole stretch (particles keep piling, the curve keeps drawing), never three different diagrams in 15 s.
- Kinetic text is punctuation: at most one slam per minute, and never as a substitute for showing the action the narrator describes.

## 3. Continuity rules (the "no reset" rules)
- **Camera continues across cuts inside an episode.** Drive it from global time (`camGlobal(info, t, keys)` in `motion.js`) so every shot of the episode reads the same move; individual shots add framing offsets on top.
- **Characters continue.** Same position, same screen direction, same pose they ended the previous shot in. If a shot starts with the hero standing, the previous one must show him getting up.
- **State is a function of global time**, not of the shot: the clock time, the darkness under the eyes, the slump of the posture, the pile of particles, the dawn in the window. Write small helpers like `tiredness(globalT)` and use them everywhere.
- **No static holds.** Every second something moves with intent: the camera, a character's action, the light, particles. A breathing pose under a frozen camera is a still image.
- **Transitions are part of the design.** Between episodes use `dip`, `whip`, `push`, `match` or a sound-led cut chosen for both sides. Inside an episode, hard cuts on action or on the beat of a word.

## 4. Clean edits: nothing pops, every cut earns itself
Viewers forgive simple drawings; they don't forgive glitches. These are the glitches:
- **Pops.** An element (text, a label, a prop, a light, the sky) appears or vanishes within one frame. Every element enters and leaves with motion or a fade (`life(t, t0, t1)` from `engine/overlays.js`, `kText` with `out`, a spring scale, a slide). Changing an expression or a blink is acting, not a pop.
- **Text that flashes or is cut off.** Any text must stay on screen for its reading time (`readTime(str)`: 0.9 s + 0.3 s per word, at least 1.2 s) and leave with a fade before it is gone. Text that starts less than its reading time before a cut, or that belongs to a moment spanning two shots, goes into **film overlays** (`story/shots.json` → `"overlays"`), which live on the film's timeline, survive cuts, fade in and out by themselves and are stretched to their reading time by the engine. Keep in-shot text for text that is part of the picture (a notebook page, a screen, a clock).
- **Strobing.** A time-lapse or a flicker faster than ~2 changes per second over the whole frame reads as a glitch. Settle fast cycles to a calm mid value (director-pass.md §9 shows the pattern).
- **Jump cuts.** A cut whose two sides look almost the same (same place, same size, same angle) reads as a glitch. A cut must change at least two of: place, shot size (≥ 1.5× zoom), angle/side, subject. If you only want to get closer, **don't cut: move the camera**. Two consecutive shots of the same diagram are one shot.
- **State resets.** A counter, a badge, a light or a pose that exists at the end of shot A and is gone at the start of shot B (or restarts its animation) pops. Drive persistent things from global time, and fade them in/out by global time, so every shot shows the same value.
- **Dead air.** No frame region may stand perfectly still for more than ~1.5 s: drift the camera, float particles, let a character breathe and act.

`tools/direction_check.py --video` measures pops, jump cuts and static holds frame by frame and FAILs on them. Fix every one, then look at the preview in motion yourself.

## 5. Variety budget (check it, don't hope for it)
Across the video:
- no set for more than ~25% of the runtime; at least 6 distinct places in a 10+ minute film,
- shot sizes mixed inside every episode (wide / medium / over-the-shoulder / insert / face),
- giant faces ≤ 15% of shots and never twice in a row,
- diagrams/cards/kinetic text together ≤ 30% of the runtime,
- a 3D or freeze-frame moment roughly every 1–2 minutes,
- shot length varies: some 1 s cuts on action, some 6–10 s holds with a moving camera; a uniform 4–5 s rhythm is a red flag.

## 6. Things that are banned
- A shot-template registry that turns `params.tpl` into shots for the whole video. Shared **sets** and **helpers** are good; shared **shots** are not. Every shot gets its own `draw` written for its words and its place in the episode.
- One shot per sentence as the planning unit.
- Replacing an action with a label ("WEIGHT GAIN" over a kitchen) when the action can be shown.
- The same composition with different text more than twice in the video.
- Faces used as filler between ideas.
- Jumping between unrelated places every few seconds.
- Cuts between two near-identical frames, and text that is visible for less than its reading time.

## 7. Audit before rendering
Run `python tools/direction_check.py --project projects/<slug>` after writing shots.json and again after the shot code is done. It flags template use, uniform rhythm, set ping-pong, repeated scene descriptions, missing episodes and the variety budget above. After a preview render run it with `--video build/preview.mp4` to measure static holds and cut rate in the actual picture. Fix every FAIL before the long render, and treat WARN as a question you must answer in the bible.

## 8. Working with an external timeline (e.g. a video editor that slices the film)
Razgon renders every frame from global time, so an outside editor can cut the film into its own clips at any timestamps and the pieces meet frame-exactly. Never let the editor's clip boundaries become your shot boundaries: direct the film as one continuous piece and let the editor slice it. If the editor asks for a clip plan, derive it from your direction (clip boundaries at your real cuts and episode starts), never the other way round.
