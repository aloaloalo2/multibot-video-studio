# Engine reference

## Folder layout
```
razgon-2d-studio/
  render.mjs  player.html  package.json
  engine/   core.js styles.js rig2d.js fx2d.js ui2d.js three-kit.js player.js motion.js
  tools/    doctor.py verify_kit.py new_project.py transcribe.py parse_script.py beats.py common.py
  audio/    dsp.py sfx.py music.py mix.py
  examples/reaction-time/   (reference project: scenes + story)
  projects/<slug>/
     config.json   input/ (voiceover, script, music)   timeline/ (words, sentences, beats)
     story/shots.json  story/bible.md   scenes/cast.js  scenes/sets/*.js  scenes/shots/*.js
     build/ (sheets, stills, styles, parts, music.wav, mix.wav, video_silent.mp4)   out/<title>.mp4
```
Every `.js` under `scenes/` is loaded automatically (files starting with `_` are skipped). Import the engine with absolute paths (`'/engine/core.js'`) and project files relatively (`'../cast.js'`).

## config.json
`{ title, aspect: "16:9"|"9:16", resolution: "720p"|"1080p"|"1440p"|"2160p", fps: 24, style: "dusk", voiceover, script, duration, captions: bool, captionStyle?: {y,size,max}, bars: null|"wide"|"scope"|"none"|number, fadeIn: 0.5, fadeOut: 0.8, music: {enabled, gainDb, file?, seed?, key?}, sfx: {enabled, gainDb}, loudness: -14 }`

## story/shots.json
```json
{ "title": "…", "duration": 312.4,
  "shots": [ { "id": "s001", "start": 0, "end": 3.4, "line": "spoken words", "scene": "what we see", "set": "cafe",
               "bars": null, "in": {"type": "cut|fade|dip|dipWhite|flash|whip|zoom", "dur": 0.4, "dir": 1},
               "sfx": [{"at": 0.4, "name": "buzz", "gain": -10}], "amb": {"name": "murmur", "gain": -26},
               "params": {}, "vignette": true, "captions": true, "mb": 0, "notes": "" } ],
  "music": [ {"start": 0, "end": 42, "mood": "mystery", "intensity": 0.4} ],
  "sfx": [ {"t": 120.5, "name": "impact", "gain": -6} ] }
```

## Shot modules
```js
import { E, V, registerShot, mood, layer, blurLayer, veil, ease, prog, key, wordTime, talkAmount } from '/engine/core.js';
import { drawFigure, POSES, posesAt, breathe, walkPose, bigFace, headPos } from '/engine/rig2d.js';
import * as FX from '/engine/fx2d.js';  import * as UI from '/engine/ui2d.js';
import { lab } from '../sets/lab.js';  import { MAX, DOC } from '../cast.js';

registerShot('s013', { draw(g, t, info) {            // 2D: g = canvas ctx in logical units, t = seconds into the shot
  const cam = { z: 1 + 0.06 * ease.inOut(t / info.dur), x: -30 };
  const { GY, M } = lab(g, t, cam);
  layer(g, cam, 1, g => drawFigure(g, { x: E.W/2 - 40, y: GY, s: 1.4, facing: -1, outfit: DOC,
        pose: breathe(posesAt(t, [[0, 'stand'], [0.4, 'point']]), t), expr: 'smile', rim: { color: M.rim, dir: [0, -1] } }));
  FX.dust(g, t);
}});
registerShot('s008', { kind: '3d',                   // 3D: init once (T = three-kit), draw per frame, optional 2D overlay
  init(T, info) { const st = T.stage({ mood: 'golden' }); /* build */ return { stage: st }; },
  draw(s, t, info, T) { T.orbit(s.stage.camera, t, { target: [0, 1, 0], radius: 6, height: 2.5, from: -0.8, to: 0.3, dur: info.dur }); },
  overlay(g, t, info, s) { /* 2D graphics on top, logical units */ } });
```
`info = { dur, globalT, p, line, shot, ...shot.params }`. An exception inside a shot is printed to the console and drawn as red text on the frame, so check the render output.

## Core, rig, FX and UI API (logical units: 16:9 → 1920×1080, 9:16 → 1080×1920)
- **core.js:** `E` (W, H, PX, fps, vertical, cfg, words, shots), `V(h, v)`, `clamp lerp prog ease{linear,in,out,inOut,sine,outBack,outElastic} key(t, [[t,v],…], ease) mixVal rng(seed) noise(x, seed) shake(t, amp, freq, seed) talkAmount(globalT, from, to) wordTime(word, afterGlobalT)`, colour `rgb css mix alpha shade`, `mood(name) S() setStyle`, draw `rr seg poly circle ring linGrad radGrad glow fillRect backdrop veil text measure FONTS`, camera `layer(g, cam, depth, fn) blurLayer(g, amount, fn, cam?, depth?)`, `registerShot getShot`.
- **rig2d.js:** `drawFigure(g, {x, y, s, facing, pose, rot, outfit, expr, talk, blink, look:[x,y], rim:{color, dir, w}, dim, alpha, prop, shadow, trail})`. Poses: `POSES.{stand, relaxed, talk, explain, point, pointUp, wave, cheer, handsOnHead, crossArms, think, shrug, holdFront, phone, reach, sad, facepalm, ready, crouch, sit, sitBack, kneel, lie(+rot), dive(+rot), kick, jump, fall}`, plus `posesAt, blendPose, breathe, walkPose(phase, {run})`, `face(g, x, y, r, {expr, talk, blink, look, front})`, `bigFace(g, cx, cy, r, {outfit, expr, talk, blink, look, rimColor, rimSide, tilt})`, `headPos(o) → [x, y, r]`, `soccerBall(g, x, y, r, rot)`. Props: `phone, ball, paper, cup, paddle, pointer, tablet, flashlight`. Outfit: `top: hoodie|labcoat|trench|jersey|tshirt|suit|dress|tracksuit|none, color, color2, legs, head: cap|capBack|beanie|fedora|headband|visor|hood|ponytail|bun|curly|spiky|none, headColor, face: glasses|sunglasses, gloves, number, kid`. Custom poses are plain objects with the 11 points; edit a copy (`{...POSES.sit, hF:[34,-188]}`).
- **fx2d.js:** `rain drops dust snow stars fog sun moon godRays lightCone pool lensStreak sparkle lightning speedLines rings skyline hills clouds tree pine lampPost windowFrame facade door chair stool counter screen bed clock floorLines crowd`.
- **ui2d.js:** `titleCard bigLine badge readout callout dimension dataCard compareBars meter blueprint bpStroke lineFigure bubble endScreen captions`.

## Scene kit for long takes (engine/scenekit.js)
`import { word, aim, camera, L, slump, chairUnder, fig, glassHead, brainGlyph, grains, eyelids, fadeBlack, gauge, page } from '/engine/scenekit.js'`
- `word(w, after, fallback)` → global time of a spoken word. `aim(px, py, z)` → camera that centres a world point; `camera(t, [[globalT, aim(...)], …])` → one smooth move for a whole take (camPath without end-easing + drift).
- `L(t, s0, s1, in, out)` → 0..1..0 envelope. `slump(k)` → seated pose that sinks forward with tiredness k (never stands up). `chairUnder(g, x, y, s, facing, M)`, `fig(g, outfit, opts, M)` (drawFigure with rim from the mood).
- `glassHead(g, cx, cy, r, alpha, drawInside)` → an x-ray head over a character: show what happens inside without leaving the scene. `brainGlyph`, `grains` draw inside it.
- `lieOnBedY(GY, s)`, `lieOnSofaY(GY, s)` → the y that puts a lying figure (rot ±π/2) ON the mattress or sofa seat; a figure sitting on a bed keeps `y = GY` (the seat height of `POSES.sit` matches the mattress). Floating figures are the most visible bug in a frame.
- `brainGlyph` draws a side-view brain (lobes, gyri, sulci, cerebellum, stem); `virus(g, x, y, r, c, t)` and `whiteCell(g, x, y, r, t)` for immune scenes. Prefer recognisable drawings over abstract dots and lines.
- `eyelids(g, k)` → screen-space eyelids (heavy eyes, microsleeps; animate slowly). `gauge(g, x, y, r, v, label, color)`, `page(g, x, y, w, h, [[t0, 'line'], …], t)` (typed lines that fit the page), `fadeBlack(g, k)`.

## Film overlays (engine/overlays.js) — text that must never pop or be cut off
`story/shots.json` → `"overlays": [{ "type": "text"|"label"|"badge", "str": "264 HOURS", "start": 27.16, "end": 32.2, "x": 0.5, "y": 0.2, "mode": "slam"|"rise"|"drop"|"spread"|"type", "size": 96, "color": "gold"|"cream"|"accent"|"#hex", "font": "title"|"ui", "fadeIn": 0.3, "fadeOut": 0.4 }]`
Drawn after the grade on top of every shot, so they cross cuts untouched. Each overlay fades in and out by itself and stays at least `readTime(str)` (0.9 s + 0.3 s per word, ≥ 1.2 s). Start them at the word (`wordTime`), keep at most 2 on screen. In shot code, `import { life, readTime } from '/engine/overlays.js'`: `life(t, t0, t1, {in, out})` → 0..1 envelope for anything with a lifetime.

## motion.js (director pass — see director-pass.md)
```js
import { camPath, camGlobal, episodeP, travel, drift, camAdd, spring, impact, squashAt, posesSpring, smear, fg, kText } from '/engine/motion.js';
```
- `camPath(t, [[t, {z, x, y, r}], …])` → cam; flows through middle keys (continuous velocity), soft ends.
- `camGlobal(info, t, [[globalT, {z, x, y, r}], …])` → cam for a whole episode keyed in global seconds; every shot of the episode uses the same keys so cuts continue the move. `episodeP(info, t0, t1)` → 0..1 progress of the episode by global time (drive tiredness, clocks, light, piles with it).
- `travel(t, t0, t1, {accel, brake})` → 0..1 with short acceleration and long braking. `drift(t, amp, seed)` → tiny organic offset. `camAdd(a, b)`.
- `spring(t, t0, {freq, damp})` → 0, then overshoots 1 and settles. `impact(t, tHit, {amp, decay, len, squash})` → `{x, y, r, sq}`. `squashAt(g, x, y, sq, fn)`.
- `posesSpring(t, [[0, POSES.shrug], [0.6, POSES.point]], {freq, damp})` → pose with overshooting blends.
- `smear(g, dx, dy, fn, n)` → directional blur of one element. `fg(g, cam, fn, {depth, blur})` → soft parallax foreground.
- `kText(g, t, str, x, y, {start, mode: 'drop'|'rise'|'slam'|'spread'|'type', stagger, size, font, weight, color, glow, spacing, align, out})`.

## Transitions and motion blur (shots.json)
`"in"`: `cut | fade | dip | dipWhite | flash | zoom | whip {dir, vertical, dur, shutter} | push {dir, vertical, dur} | iris {at:[fx,fy], dur, r0} | match {from:[fx,fy], to:[fx,fy], scale, dur} | smash {dur}`. Coordinates are fractions of the frame.
`"mb": n` (or `{"n": 4, "shutter": 0.5}`) renders n sub-frames per frame for that shot (motion blur). Cost scales with n.

## three-kit.js (passed as `T` to `init`/`draw`)
`T.stage({mood, fov, fog:[near, far], sky, keyPos, keyIntensity, ambient, bloom})` → `{scene, camera, composer, sun, add(...objs), render(), dispose()}`. Builders: `box cyl cone sphere plane ground(w, d, color, tex) planks tiles windowPane(w, h, {glowColor, cols, rows, power, interior}) shaft(w, len, color, opacity) building(w, h, d, {color, win, lit}) tree3D pine3D crowd3D({rows, perRow, width, step, rise, colors}) figure3D(outfit, {rim, pose, s}) → .setPose(pose)`, `mat basic canvasTex`, and cameras `orbit(camera, t, {target, radius, height, from, to, dur})` and `dolly(camera, t, [[t, {pos, look, fov}], …])`. Units are metres, a figure is ~1.7 m and faces +x. 3D shots get the same grade, bars and grain automatically. Keep exposure moody: let windows and lamps be the brightest things, and keep the floor dark.

