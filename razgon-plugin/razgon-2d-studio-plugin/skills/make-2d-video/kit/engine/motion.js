// engine/motion.js — the "director pass" toolkit: camera, weight, optics and kinetic type.
// Everything is deterministic (pure functions of t), so frames render identically in any order.
//
//   camPath  — camera through keyframes WITHOUT stopping at each key (continuous velocity, speed waves)
//   travel   — one move with real acceleration / cruise / braking instead of a symmetric ease
//   spring   — 0→1 with overshoot and settle (weight, inertia)
//   impact   — decaying shake + squash after a hit (contact, reaction)
//   posesSpring — posesAt with overshooting blends (anticipation → action → settle)
//   smear    — directional motion blur for one fast element
//   fg       — soft foreground layer with strong parallax (depth)
//   kText    — kinetic typography: letters drop / rise / slam / spread on the word
import { E, clamp, lerp, ease, prog, noise, blurLayer, measure, text, FONTS, alpha, mixVal } from './core.js';
import { pose as poseOf } from './rig2d.js';

// ---------- camera ----------
// camPath(t, [[0, {z:1, x:0}], [1.2, {z:1.12, x:-40}], [3, {z:1.18, x:-60, r:-0.01}]], {warp})
// Cubic Hermite with Catmull-Rom tangents per field: the camera flows THROUGH the middle keys
// (no dead stop on every accent) and eases in/out only at the ends. Missing fields default to the previous key.
export function camPath(t, keys, o = {}) {
  const n = keys.length; if (n === 1) return { ...keys[0][1] };
  const T0 = keys[0][0], T1 = keys[n - 1][0];
  let tt = clamp(t, T0, T1);
  if (o.warp !== false) { const u = (tt - T0) / (T1 - T0 || 1); tt = T0 + (T1 - T0) * warpEnds(u, o.endEase ?? 0.18); }
  let i = 1; while (i < n - 1 && tt > keys[i][0]) i++;
  const [ta, A] = keys[i - 1], [tb, B] = keys[i], h = tb - ta || 1, u = (tt - ta) / h;
  const P = (j) => keys[clamp(j, 0, n - 1)];
  const out = {}, fields = new Set(keys.flatMap(k => Object.keys(k[1])));
  for (const f of fields) {
    const val = (j) => { for (let k = clamp(j, 0, n - 1); k >= 0; k--) if (keys[k][1][f] != null) return keys[k][1][f]; return f === 'z' ? 1 : 0; };
    const p0 = val(i - 1), p1 = val(i);
    const tan = (j) => { const a = P(j - 1), b = P(j + 1); if (j <= 0 || j >= n - 1) return 0; return (val(j + 1) - val(j - 1)) / ((b[0] - a[0]) || 1); };
    const m0 = tan(i - 1) * h, m1 = tan(i) * h, u2 = u * u, u3 = u2 * u;
    out[f] = (2 * u3 - 3 * u2 + 1) * p0 + (u3 - 2 * u2 + u) * m0 + (-2 * u3 + 3 * u2) * p1 + (u3 - u2) * m1;
  }
  return out;
}
// soften only the very start/end of a path (k = fraction of the path used for ramping)
function warpEnds(u, k) { if (k <= 0) return u; const a = k, v = 1 / (1 - a); // area-preserving trapezoid velocity
  if (u < a) return (v * u * u) / (2 * a); if (u > 1 - a) { const r = 1 - u; return 1 - (v * r * r) / (2 * a); } return v * (u - a / 2); }

// camGlobal(info, t, [[globalT, {z, x, y, r}], …]) — one camera move for a whole episode, keyed in GLOBAL seconds.
// Every shot of the episode calls it with the same keys, so a cut changes the framing, never restarts the move.
// Ends are not eased (the move flows through the cuts); ease the episode's own first/last key instead.
export function camGlobal(info, t, keys, o = {}) { return camPath(info.globalT ?? t, keys, { warp: false, ...o }); }
// episodeP(info, t0, t1) — 0..1 progress through an episode by global time (for tiredness, clock hands, light, piles).
export function episodeP(info, t0, t1) { return clamp(((info.globalT ?? 0) - t0) / Math.max(1e-6, t1 - t0)); }

// travel(t, t0, t1, {accel, brake}) → 0..1 with an asymmetric velocity profile:
// accelerate for `accel` of the time, cruise, brake for `brake` of the time (camera operators brake longer than they accelerate)
export function travel(t, t0, t1, o = {}) {
  const u = prog(t, t0, t1), a = o.accel ?? 0.25, b = o.brake ?? 0.4, vmax = 1 / (1 - a / 2 - b / 2);
  if (u < a) return (vmax * u * u) / (2 * a);
  if (u > 1 - b) { const r = 1 - u; return 1 - (vmax * r * r) / (2 * b); }
  return vmax * (u - a / 2);
}
// a slow organic drift (handheld breathing) for "readable" holds — tiny, never noise-shaky
export function drift(t, amp = 6, seed = 1) { return { x: noise(t * 0.35, seed) * amp, y: noise(t * 0.3, seed + 4) * amp * 0.6, r: noise(t * 0.25, seed + 9) * amp * 0.0006 }; }
// add two camera objects (base + offset)
export const camAdd = (a, b) => ({ x: (a.x || 0) + (b.x || 0), y: (a.y || 0) + (b.y || 0), z: (a.z ?? 1) * (b.z ?? 1), r: (a.r || 0) + (b.r || 0) });

// ---------- weight & inertia ----------
// spring(t, t0) → 0 before t0, then rises past 1 and settles. freq in Hz, damp 0..1 (lower = bouncier)
export function spring(t, t0, o = {}) {
  const x = t - t0; if (x <= 0) return 0;
  const f = o.freq ?? 2.2, z = o.damp ?? 0.42, w = 2 * Math.PI * f, wd = w * Math.sqrt(1 - z * z);
  return 1 - Math.exp(-z * w * x) * (Math.cos(wd * x) + (z * w / wd) * Math.sin(wd * x));
}
// impact(t, tHit) → {x, y, r, sq} decaying shake + squash after a hit. Add x/y/r to a camera or a group transform.
export function impact(t, tHit, o = {}) {
  const x = t - tHit; if (x < 0 || x > (o.len ?? 0.7)) return { x: 0, y: 0, r: 0, sq: 0 };
  const amp = (o.amp ?? 14) * Math.exp(-x * (o.decay ?? 7)), f = o.freq ?? 18;
  return { x: Math.sin(x * f * 6.283) * amp * 0.6, y: Math.cos(x * f * 5.1) * amp, r: Math.sin(x * f * 4.4) * amp * 0.0012, sq: Math.exp(-x * 10) * Math.cos(x * 30) * (o.squash ?? 0.12) };
}
// apply squash & stretch around a contact point (x, y = the base that touches the ground / is hit)
export function squashAt(g, x, y, sq, fn) { g.save(); g.translate(x, y); g.scale(1 + sq, 1 - sq); g.translate(-x, -y); fn(g); g.restore(); }
// posesSpring(t, [[0, POSES.stand], [0.6, POSES.point]]) — like posesAt, but each change overshoots and settles
export function posesSpring(t, keys, o = {}) {
  let cur = keys[0][1];
  for (let i = 1; i < keys.length; i++) { const [ti, pi] = keys[i]; if (t < ti) break; cur = mixVal(typeof cur === 'string' ? poseOf(cur) : cur, typeof pi === 'string' ? poseOf(pi) : pi, spring(t, ti, { freq: o.freq ?? 2.6, damp: o.damp ?? 0.5 })); }
  return cur;
}

// ---------- optics ----------
// smear(g, dx, dy, fn, n) — draw fn n times along the screen motion (dx, dy over one shutter) with fading weights.
// Use for ONE fast element (a slammed fader, a dropping pin, a swung door). For whole-frame blur use shot "mb" in shots.json.
export function smear(g, dx, dy, fn, n = 6) {
  const len = Math.hypot(dx, dy); if (len < 2) { fn(g); return; }
  n = Math.max(2, Math.min(12, Math.round(n * Math.min(1, len / 40) + 1)));
  for (let i = n - 1; i >= 0; i--) { const k = i / (n - 1); g.save(); g.globalAlpha *= i === 0 ? 1 : 0.5 * (1 - k) / 1.2 + 0.12; g.translate(-dx * k, -dy * k); fn(g); g.restore(); }
}
// fg(g, cam, fn, {depth, blur}) — out-of-focus foreground that moves faster than the subject (parallax depth cue)
export function fg(g, cam, fn, o = {}) { blurLayer(g, o.blur ?? 12, fn, cam, o.depth ?? 1.7); }

// ---------- kinetic typography ----------
// kText(g, t, 'ONE RULE', x, y, {start, mode:'drop'|'rise'|'slam'|'spread'|'type', stagger, size, color, glow, ...})
// Letters act individually, then settle into a clean, readable line. Returns {w, h, k} (k = settle 0..1).
export function kText(g, t, str, x, y, o = {}) {
  const { start = 0, mode = 'drop', stagger = 0.035, size: size0 = 72, font = FONTS.title, weight = 700, color = '#fff', spacing = 4, align = 'center', glow = 0, glowColor = alpha(color, 0.6), out = null } = o;
  const lt = t - start; if (lt < 0) return { w: 0, h: size0, k: 0 };
  // maxWidth (default: 90% of the frame): the line shrinks to fit instead of running off screen
  const maxW = o.maxWidth ?? E.W * 0.9, w0 = [...str].reduce((a, c) => a + measure(g, c, size0, o.font ?? FONTS.title, o.weight ?? 700) + (o.spacing ?? 4), 0);
  const size = w0 > maxW ? size0 * maxW / w0 : size0;
  const chars = [...str], widths = chars.map(c => measure(g, c, size, font, weight) + spacing), W = widths.reduce((a, b) => a + b, 0) - spacing;
  let cx = align === 'center' ? x - W / 2 : align === 'right' ? x - W : x;
  const fade = out != null ? 1 - ease.inOut(prog(t, out, out + 0.3)) : 1; let kAll = 0;
  chars.forEach((c, i) => {
    const w = widths[i], lx = cx + (w - spacing) / 2; cx += w; if (c === ' ') return;
    const ti = lt - i * stagger, s = spring(ti, 0, { freq: o.freq ?? 2.4, damp: o.damp ?? 0.45 }), a = clamp(ti / 0.12) * fade; if (a <= 0) return;
    kAll = Math.max(kAll, s);
    let dx = 0, dy = 0, sc = 1, rot = 0;
    if (mode === 'drop') { dy = -(1 - s) * size * 1.4; rot = (1 - s) * (i % 2 ? 0.25 : -0.25); }
    else if (mode === 'rise') { dy = (1 - s) * size * 0.9; }
    else if (mode === 'slam') { sc = lerp(2.6, 1, clamp(s, 0, 1.2)); rot = (1 - s) * 0.12; }
    else if (mode === 'spread') { dx = (lx - x) * (s - 1) * 0.6; }
    else if (mode === 'type') { sc = 0.6 + 0.4 * clamp(s); }
    g.save(); g.translate(lx + dx, y + dy); g.rotate(rot); g.scale(sc, sc);
    if (mode === 'rise') { g.beginPath(); g.rect(-w, -size * 0.75 - dy, w * 2, size * 1.5); g.clip(); }
    text(g, c, 0, 0, { size, font, weight, color, alpha: a, glow, glowColor });
    g.restore();
  });
  return { w: W, h: size, k: kAll };
}
