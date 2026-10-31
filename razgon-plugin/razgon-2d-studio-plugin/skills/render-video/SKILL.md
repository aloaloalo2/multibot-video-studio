---
name: render-video
description: "This skill should be used when the user runs /render-video or asks to \"build the scenes\", \"check the shots\", \"show me a contact sheet\", \"preview the video\", \"render the video\", \"render in 4K / 9:16\", \"re-render after a fix\", or \"export the final MP4\" for an Razgon 2D Studio project. It writes or repairs shot code in batches with contact-sheet QC, makes preview clips, runs the full frame-by-frame render, and muxes the final video with sound.\n"
metadata:
  version: "0.1.0"
  author: Razgon
---

# /render-video: build, QC, preview and final render

Work inside `razgon-2d-studio/` on the active project (`projects/<slug>`; if several exist, ask which one). Shared references are in `../make-2d-video/references/` relative to this skill's base directory. Read `engine-api.md`, `style-bible.md`, `director-pass.md` and `render-qc.md` before writing or fixing scenes.

## 1. Build or repair shots (one episode per batch)
Read `../make-2d-video/references/storytelling.md` first. Write every shot for its own moment (no shot-template registry), continue the episode's camera and the characters' state across cuts from global time, and run `python tools/direction_check.py --project projects/<slug>` after each episode; add `--video build/preview.mp4` once the episode is previewed.
- List what's missing: `node render.mjs --project projects/<slug> --sheet --scale 0.4`. The console lists MISSING shots and shot errors, and `build/sheets/sheet_XX.png` shows one still per shot.
- Write `scenes/sets/*.js` and `scenes/shots/NN_name.js` (`registerShot(id, …)` for each shot id). Study `examples/reaction-time/scenes/` for working patterns.
- After each batch, re-run the sheet and **open every sheet PNG** against the QC checklist in `render-qc.md`. Fix and repeat until there are no MISSING or ERROR frames and every shot passes.
- Check every non-cut transition and every impact with `--stills` at 2–3 moments inside it (director-pass.md §8).
- To check motion, use `--stills t1,t2,t3` (several moments of one shot) or `--from A --to B --scale 0.5` (writes `build/preview.mp4`).

## 1a. Live preview without rendering
To review the whole film quickly, run `node tools/live.mjs --project projects/<slug> [--port 8781]` in the background and open `http://127.0.0.1:<port>/live.html`. The player draws every frame in real time under the voiceover (sound muted by default) at 0.33/0.5/0.75 scale; drag the timeline to any moment, Space plays, arrows step 1 s, Shift+arrows step one frame. The timeline is numbered by `story/studio_frames.json` when it exists, otherwise by shots. Any change to `scenes/`, `story/`, `config.json` or `engine/` reloads the page at the same moment. If `config.json` has `"overlay": "input/<file>.png"` (a transparent full-frame PNG such as a channel plashka), the live page draws it over every frame, as the final will have it. With `?embed=1` the page hides its controls and follows a host app instead: the host posts `{razgon:'seek', t}` messages and gets `{razgon:'ready'}` after each load (MultiBot Video Studio uses this to draw the film live in its editor preview). Use it to find bugs before the frame-by-frame render; the MP4 render remains the deliverable.

## 1b. Text never leaves the frame
Run `node render.mjs --project projects/<slug> --text-check 0.25 --scale 0.25 [--from A --to B]` after every batch of scene changes. It logs every visible line drawn with `text()` and fails any text held cut by the frame edge for a second or longer (text crossing the edge during a camera move is listed but passes). Fix by framing the group whole (mind the layer depth: a wall at depth 0.9 needs its aim corrected by 1/0.9), spacing groups apart, or limiting `maxWidth` to the room left before the edge. `UI.badge` keeps itself inside the frame; pass `align: 'left'` for a counter on the left side.

## 1c. Frame review: three stills of every frame before anything is handed over
Nothing is shown to the user as ready, neither the live film nor a render, before every frame has been looked at and passed. Run `python3 tools/frame_review.py --project projects/<slug> sheets`: it renders three stills of every frame (Studio frames from `story/studio_frames.json`, else shots) from the live code at 20%, 50% and 80% of it and lays them out four frames per sheet in `build/review/review_NN.png`, each row with the frame number, time, takes and narration line. **Open every sheet** and check every frame against «Frame review» in `../make-2d-video/references/render-qc.md`: logic first (people lying on a bed lie on the mattress, people sitting sit on the seat with straight backs and feet on the floor, hands hold what they hold, nothing floats, clips or passes through, the picture shows what the words say), then craft (anything primitive, cramped, empty or ugly). Record each frame with `frame_review.py ... mark <frames> ok` or `mark <frame> bug "<what is wrong>"`, fix every bug in the scene code and run `sheets` again: frames whose pixels changed lose their verdict and must be looked at again, untouched frames keep theirs. `frame_review.py ... status` must exit 0 (every frame ok on the current code) before you say the film is ready, before the final render and before the final MP4 goes to the user. Keep iterating until the picture is right; do not hand over «good enough».

## 2. Preview checkpoint
Render `node render.mjs --project projects/<slug> --from 0 --to 30 --scale 0.5` and send the user the preview, or the contact sheets, before the long render. Mention the expected render time (speed guide in `render-qc.md`: frames = seconds × 24; ~2 frames/s at 720p on a small 2-core CPU, 1080p ~2× slower, 4K ~8× slower, desktops 3–5× faster).

## 3. Final render
- To change resolution or aspect, edit `projects/<slug>/config.json` (`resolution`, `aspect`). Switching aspect needs a fresh sheet review, because 9:16 framing differs.
- Run `node render.mjs --project projects/<slug> [--workers N] [--format jpeg]` and run it in the background for anything over a minute or two: `nohup node render.mjs --project projects/<slug> > build/render.log 2>&1 &`. Poll the log and report progress and ETA at sensible intervals.
- Use fewer workers if memory is tight (about 1–1.5 GB each at 1080p, more at 4K). With no GPU, add `--gl swiftshader` (already the Linux default).
- Output: `build/video_silent.mp4`. The end of the log lists any shot errors. Fix them and re-render if there are any.

## 4. Sound, mux and deliver
Make sure the music plan and SFX are set (see `/video-sound`), then run `python audio/mix.py --project projects/<slug>`, which writes `out/<title>.mp4`. QC: `ffprobe` duration ≈ `story/shots.json` duration, an audio stream is present, and a contact sheet of the final file (`ffmpeg -i out/<file>.mp4 -vf fps=1/10,scale=320:-1,tile=6x5 -frames:v 1 build/final_sheet.png`) looks right. Send the MP4 to the user and say in plain words where it was saved.
