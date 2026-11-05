# Rendering, QC and troubleshooting

## Render

**Preview first.** `node render.mjs --project projects/my-video --from 0 --to 30 --scale 0.5` writes `build/preview.mp4`. Watch it (or sample stills). Then send the user a preview or a contact sheet before the long final render.

**Final render:**
```bash
node render.mjs --project projects/my-video [--workers N] [--format jpeg]
python audio/mix.py --project projects/my-video        # builds music + SFX, mixes, muxes -> out/<title>.mp4
```
- Workers default to half the CPU threads (max 8). Each worker is a separate Chromium. Lower the count if RAM is short (about 0.6–1.5 GB per worker at 1080p, more at 4K).
- On machines without a GPU (most Linux servers), Chromium uses SwiftShader (`--gl swiftshader`, the default on Linux). On macOS the default is `--gl gpu`: headless Chromium with `--gl auto` falls back to software drawing on a Mac, and the GPU draws the same picture 4–7 times faster (measured on a 1080p film, PSNR 43–45 dB against software). On Windows the default stays `--gl auto`. On a Mac each part is also encoded on the hardware H.264 encoder (VideoToolbox, `--encoder videotoolbox`, `--q 75`): x264 took about 60% of a render's CPU, and with two renders side by side the hardware encoder doubled the speed (2.57 against 1.28 s of film per second at 1080p) at the same look. `--encoder x264` brings x264 back.
- **Speed guide** (frames = seconds × 24): measured at 720p on a 2-thread cloud CPU, about 2 frames/s, so a 47 s video took about 10 min. 1080p costs ~2× that, 1440p ~3.5×, 4K ~8×. A modern 8-core desktop is ~3–5× faster, and a GPU helps the 3D shots most. Budget accordingly, and for 10-minute videos at 4K plan for a long or overnight render. Long renders should run in the background (`nohup … &` or a separate terminal) while you poll the log.
- `--format jpeg` speeds up capture (~1.5×) with negligible quality loss.
- **Partial re-render after a fix:** re-run the whole video (simple and safe), or render only the changed range with `--from/--to --out build/fix.mp4` and splice it in with ffmpeg if you're comfortable.
- **Final QC:** `ffprobe` duration ≈ the shots.json duration, audio present, then make a contact sheet of the final file with ffmpeg (`-vf fps=1/10,scale=320:-1,tile=6x5`) and look at it.


## QC checklist (run on every contact sheet)
- [ ] No `MISSING SHOT` or red `ERROR` frames, and the console printed no shot errors.
- [ ] Each picture matches its `line`, and the key action lands on the key word.
- [ ] Characters are readable: rim light present, staged against brighter areas, not cut off at the edges, not overlapping text.
- [ ] Outfits and screen direction are consistent within a scene, and every character has a contact shadow or is grounded.
- [ ] Moody value structure (mostly dark, 1–3 bright accents), not flat or washed out, and colours come from the mood/style.
- [ ] Every shot has a motivated camera move (not a lone linear zoom) and some atmosphere; medium shots have a soft foreground that enters the frame without covering faces or text.
- [ ] Arrivals and contacts have weight (overshoot, settle, impact); non-cut transitions read correctly in `--stills` taken inside them.
- [ ] Every new visual event (slam, landing, smash cut) has its SFX on the same frame.
- [ ] Text is short, inside the safe area, and legible at phone size, on a calm part of the picture, in its own colour (mostly white) with a soft shadow; the tone does not flip with the background (it strobes). Numbers match the narration.
- [ ] Nothing pops: every element enters and leaves with motion or a fade; text stays for its reading time; no cut between near-identical frames; no strobing time-lapse (`tools/direction_check.py --video`).
- [ ] Variety: no more than 3 consecutive shots of the same type or framing, with close-ups and inserts sprinkled in.
- [ ] 9:16: subjects in the middle, nothing important under the captions.
- [ ] Audio: voice clear, music ducked, no SFX pile-ups, final loudness about −14 LUFS.

## Frame review (every frame, three stills, before handing over)
`python3 tools/frame_review.py --project projects/<slug> sheets` → open every `build/review/review_NN.png` → `mark <frames> ok` or `mark <frame> bug "<note>"` → fix → `sheets` again → `status` exits 0. A verdict belongs to the pixels: a frame whose stills changed goes back to «not reviewed» (a speck of drifting dust is not a change: stills are compared on 128×72 thumbnails). A scene that throws draws `ERROR …` into its frame; `sheets` lists such errors at the end and `status` fails until there are none. Look at each still as a viewer would and ask what is wrong with it:
- [ ] **Bodies make physical sense.** Someone lying on a bed lies on the mattress (not above it, not through it, head on the pillow end); someone sitting sits on the seat, back straight or naturally leaning, feet on the floor or the footrest; someone standing stands on the floor line; nobody floats unless the story says weightless.
- [ ] **Contact is real.** Hands hold the object they use (a phone, a contract, a bar, a towel) instead of the object hovering beside them; carried people are held by both carriers; props rest on tables, floors or hooks; ropes and straps connect to what they hang from.
- [ ] **Nothing overlaps wrongly.** No limb through a body, chair, bed or wall; no prop drawn over a face; no character half inside another; layers in a believable depth order.
- [ ] **The picture says what the words say.** The thing named in the line is on screen and recognisable; the action happens when it is said; counts, names, numbers and colours match the narration.
- [ ] **Scale and place are believable.** People are not giants next to a station or tiny next to a cup unless that is the joke; a person on Earth stands on the ground, not as a head sticking out of the planet.
- [ ] **Windows, screens and the logo corner stay clear.** A card, fan, checklist or bottle is not pasted over a window or porthole: it goes on free wall or into a hand. Nothing sits under the channel logo (the overlay's top-right box, e.g. x 1675–1855, y 55–149 at 1080p) or behind the top-centre title plate, including things that drift through the frame.
- [ ] **A PNG brings only what the scene needs.** A prop drawn with extra parts (clippers with their own coiled hose, a desk with a chair) is clipped to the part that is used, and the rest is drawn to fit the scene, so it does not wrap or cover a body.
- [ ] **Craft.** No primitive shape standing in for a real object (use a PNG prop); no empty, flat or cramped frame; no clipped heads or text; no text or number that merges with the picture under it (move it to a calm part); nothing ugly or unfinished; no stairs or props that lead nowhere. If it would not pass on a top channel, it is a bug.
- [ ] **Text lies where it belongs.** Text that belongs to a thing (a book page, a sign, a screen, a poster) is laid with `textOn()` (engine/core.js) on the measured corners of its face, so it slants with it and stays inside its edges; never a flat line over a slanted surface. A thing that has to carry readable text (a book, a ledger, a board) is a prop that faces the viewer squarely, so its text lies level along its own rules: on a photographed book in strong perspective with curved pages, flat text looked crooked however it was turned (episode 08). A page-turn or a sheet flying over the text is left out: it only hides what the viewer has to read. A caption (a date, a number) sits on bare wall or sky of this very scene, not at one fixed screen point for every scene; where the camera moves, draw it in the world's layer so it moves with the wall. Dark ink on a light wall, light on a dark one: never text that melts into what is under it.
- [ ] **Things stand on what carries them.** A train's wheels sit on the rail line (measure the share of the picture's height where its wheels end and put that line on the rail), a teletype on the desk's top face, a book on the table. A track, bridge or road the vehicle uses is drawn at the vehicle's line, not as a backdrop behind it.
- [ ] **Depth follows the foot line, in one layer.** What stands lower on the screen (closer) is drawn later: sort crowds by y; someone walking past a booth or a car is either in front of it (below its foot line) or hidden by it; a street lamp on the near kerb is drawn over the cars on the road. A judge behind a bench is drawn before the bench.
- [ ] **Lines end on their targets.** A beam, cable or thread starts and ends exactly on its object, never in empty air and never past the target; a broken link shows its break (a red spark on both cut ends). Draw a line and its target in the same `layer()`, or the parallax pulls them apart as the camera moves.
- [ ] **No blank rectangles.** A cut-open room, an open gate or a building shows what is in it or behind it (windows, a door, furniture, the street outside), never a flat fill.
- [ ] **Framing and camera.** A sign, panel or caption is never cut by the frame edge; to hold a framing repeat the key (a spline overshoots the target otherwise).
- [ ] **Assets keep their sharpness.** Library and sheet props are about 500 px; a prop drawn above 1.6× its pixels at 1080p is drawn in code, put in a soft `blurLayer` foreground, or generated as one large asset alone on its sheet.

## Automatic checks before the look (no tokens, about 20 s for a whole film)
`node render.mjs --project projects/<slug> --logic-check 0.5 --scale 0.25` samples the film every 0.5 s and lists what a viewer would call wrong: a farther figure or prop drawn over a closer one in the same layer (an item held by a person, a thing lying on another, wall items and soft blurred layers are skipped), text covered by a later opaque object, and a prop blown up past 1.6× its pixels. `--text-check` finds text cut by the frame edge. It also lists `text half on`: a text partly on a thing and partly off it (a heading sticking out of its page, a caption across a crane); that list must be empty. Look at every FAIL on a still: fix the real ones, and name the false ones (a view through a window, a cut-away) in the report. Then the three stills per frame above. It is a loop: stills, the list of every bug, the fixes, then the checks and stills of every changed frame again, until neither shows a bug.

## Troubleshooting
- **Bright unexplained stripes on bodies or furniture:** check rim-light width, offset silhouettes, joints and foreground occlusion at the final display size. Keep the rim subtle and continuous; it must not look like a second limb or a detached neon line. Compare the same moment before/after, plus two other poses. The Billionaire film's shared figure rim was reduced from 4 to 1.2 pixels after thick contours were reported on 5 November 2026.
- **Repeated whole-film reviews:** `frame_review.py sheets` caches sources and stills per frame. After local edits it renders the changed frames and their neighbours only. Use those sheets for logic and composition together; record verdicts once. `status` checks each frame's current fingerprint, so a partial review cannot approve untouched stale frames.
- **Fonts look like serif defaults** → the `@fontsource` packages are missing. Run `npm install` in razgon-2d-studio.
- **`ERROR <take>@<t>: x is not a function` in a still** → a helper and a local variable share a name (a cue `stairs = c.cue('stairs')` hides a helper `stairs()`); rename the helper. And never put a `//` comment in the middle of a line that still has code after it: it comments out the closing brackets.
- **`Player failed to boot`** → read the message. Usually it's a JSON syntax error in shots.json/config.json or an import path in a scene. Scene import errors are listed at the end of a render.
- **WebGL or 3D shot black** → add `--gl swiftshader`, and check the console for Three.js errors (a misspelt builder or a missing `return {stage}` in init).
- **Out of memory or crashes at 4K** → use `--workers 1` or `2`, and avoid huge blur amounts on 4K (blur cost scales with resolution).
- **Whisper slow** → use `--model base`. **Script match < 90%** → the wrong script or audio. Ask the user.
- **The video is longer or shorter than the audio** → `story.duration` must equal the last shot's `end`. Re-run `beats.py --force` or fix by hand.
- **PyAV/`av` errors from faster-whisper** → the tools decode audio with ffmpeg themselves, so just ensure ffmpeg is on PATH.
- **Windows paths** → quote paths with spaces. Use `python` (or `py -3`) instead of `python3`.
