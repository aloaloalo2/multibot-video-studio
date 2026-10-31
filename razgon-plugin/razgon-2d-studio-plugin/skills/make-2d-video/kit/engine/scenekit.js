// engine/scenekit.js — helpers for long takes (storytelling.md §0): aim the camera at world points, put figures ON
// furniture, x-ray heads, a real side-view brain, viruses and white cells, eyelids, gauges, pages whose text fits.
import { E, V, S, mood, layer, ease, prog, clamp, lerp, mixVal, alpha, shade, seg, circle, ring, rr, poly, glow, text, FONTS, rng, linGrad } from './core.js';
import { drawFigure, POSES, breathe, walkPose, headPos } from './rig2d.js';
import { camPath, camAdd, drift } from './motion.js';
import { life } from './overlays.js';
import * as FX from './fx2d.js';
import * as UI from './ui2d.js';

export { life };
// global time of a spoken word (first match at or after `after`), or the fallback
export const word = (w, after = 0, fb = after) => { const x = E.words.find((o) => o.start >= after - 0.3 && o.word.toLowerCase().replace(/[^\w']/g, '').startsWith(w)); return x ? x.start : fb; };
// camera that centres world point (px, py) of a depth-1 layer at zoom z
export const aim = (px, py, z = 1) => ({ z, x: px - E.W / 2, y: py - E.H / 2 });
export const camera = (t, keys, amp = 4, seed = 3) => { const k = keys.slice().sort((a, b) => a[0] - b[0]).filter((x, i, arr) => !i || x[0] - arr[i - 1][0] > 0.05); return camAdd(camPath(t, k, { warp: false }), drift(t, amp, seed)); };
// 0..1..0 envelope with eased in/out
export const L = (t, s0, s1, i = 0.5, o = 0.6) => life(t, s0, s1, { in: i, out: o });
export const blinkAt = (t, period = 3.3, seed = 0) => ((t + seed) % period) > period - 0.12;

// a seated pose that slumps forward with k (0 upright … 1 wrecked); never stands up
export function slump(k, base = POSES.sit) {
  const s = base, d = { ...s, head: [s.head[0] + 16, s.head[1] + 26], sh: [s.sh[0] + 10, s.sh[1] + 16], eF: [s.eF[0] + 6, s.eF[1] + 18], hF: [s.hF[0] + 4, s.hF[1] + 26], eB: [s.eB[0] + 6, s.eB[1] + 18], hB: [s.hB[0] + 2, s.hB[1] + 26] };
  return mixVal(s, d, clamp(k));
}
// heights that put a figure ON furniture instead of in the air: lying (rot ±π/2 turns the body around the hip, 100·s up)
// rests on a bed mattress (top 96 above the floor) or a sofa seat (top 150); sitting on a bed keeps the feet on the floor
export const lieOnBedY = (GY, s) => GY - 106 + 100 * s, lieOnSofaY = (GY, s) => GY - 160 + 100 * s;
export function chairUnder(g, x, y, s, facing, M) { g.save(); g.translate(x, 0); g.scale(facing, 1); FX.chair(g, -18 * s, y, s, shade(M.dark, -0.2)); g.restore(); }
export function fig(g, outfit, o, M) { drawFigure(g, { rim: { color: M.rim, dir: o.rimDir || [0.35, -1], w: 4 }, shadow: o.shadow ?? true, ...o, outfit }); }

// a translucent "x-ray" head drawn over a character: the inside is clipped to the head circle
export function glassHead(g, cx, cy, r, a, inside) {
  if (a <= 0) return; const ui = S().ui;
  g.save(); g.globalAlpha *= a;
  glow(g, cx, cy, r * 1.6, ui.blueprint, 0.25);
  g.beginPath(); g.arc(cx, cy, r, 0, Math.PI * 2); g.fillStyle = alpha(ui.bpBg || '#08103a', 0.88); g.fill();
  g.save(); g.beginPath(); g.arc(cx, cy, r * 0.96, 0, Math.PI * 2); g.clip(); inside(g); g.restore();
  ring(g, cx, cy, r, 5, alpha(ui.blueprint, 0.9));
  g.restore();
}
// a neon brain in side view (frontal lobe left): cerebrum with gyri, the central and lateral sulci, the cerebellum and
// the brain stem, so it reads as a brain at any size. Activity dots glow inside; spots [[x, y, k, colour]] are in r units.
function brainPath(cx, cy, r) {
  const P = new Path2D(), q = (x, y) => [cx + x * r, cy + y * r];
  P.moveTo(...q(-1.12, 0.12));
  P.bezierCurveTo(...q(-1.25, -0.45), ...q(-0.85, -0.95), ...q(-0.2, -0.98));
  P.bezierCurveTo(...q(0.35, -1.0), ...q(0.95, -0.78), ...q(1.12, -0.25));
  P.bezierCurveTo(...q(1.22, 0.1), ...q(1.08, 0.38), ...q(0.78, 0.42));
  P.bezierCurveTo(...q(0.45, 0.46), ...q(0.25, 0.56), ...q(-0.05, 0.52));
  P.bezierCurveTo(...q(-0.4, 0.62), ...q(-0.78, 0.55), ...q(-0.88, 0.36));
  P.bezierCurveTo(...q(-1.0, 0.36), ...q(-1.1, 0.28), ...q(-1.12, 0.12));
  P.closePath(); return P;
}
export function brainGlyph(g, cx, cy, r, t, o = {}) {
  const ui = S().ui, col = o.color || ui.blueprint, a0 = o.a ?? 1, lw = Math.max(2, r * 0.025), P = brainPath(cx, cy, r);
  g.save(); g.globalAlpha *= a0;
  // brain stem and cerebellum behind the cerebrum
  rr(g, cx + r * 0.22, cy + r * 0.38, r * 0.22, r * 0.62, r * 0.1); g.fillStyle = alpha('#0a1240', 0.95); g.fill(); g.strokeStyle = alpha(col, 0.8); g.lineWidth = lw; g.stroke();
  g.beginPath(); g.ellipse(cx + r * 0.72, cy + r * 0.5, r * 0.36, r * 0.22, -0.15, 0, Math.PI * 2); g.fillStyle = alpha('#0a1240', 0.95); g.fill(); g.stroke();
  for (let k = 1; k < 4; k++) { g.beginPath(); g.ellipse(cx + r * 0.72, cy + r * 0.5, r * 0.36 * (1 - k * 0.2), r * 0.22 * (1 - k * 0.2), -0.15, Math.PI * 0.05, Math.PI * 0.95); g.strokeStyle = alpha(col, 0.45); g.lineWidth = lw * 0.6; g.stroke(); }
  // the cerebrum
  glow(g, cx, cy - r * 0.2, r * 1.6, col, 0.12);
  g.fillStyle = alpha('#0a1240', 0.92); g.fill(P);
  g.save(); g.clip(P);
  g.strokeStyle = alpha(col, 0.45); g.lineWidth = lw * 0.7; g.lineCap = 'round';
  const R = rng(o.seed ?? 9);
  for (let i = 0; i < 22; i++) {   // gyri: short wavy folds following the surface
    const x0 = -1.0 + R() * 1.9, y0 = -0.85 + R() * 1.2, ang = R() * Math.PI, len = 0.25 + R() * 0.3;
    g.beginPath(); for (let k = 0; k <= 12; k++) { const u = k / 12, px = x0 + Math.cos(ang) * len * u, py = y0 + Math.sin(ang) * len * u + Math.sin(u * Math.PI * 3) * 0.05; k ? g.lineTo(cx + px * r, cy + py * r) : g.moveTo(cx + px * r, cy + py * r); } g.stroke();
  }
  g.strokeStyle = alpha(col, 0.85); g.lineWidth = lw;
  g.beginPath(); g.moveTo(cx - r * 0.05, cy - r * 0.97); g.bezierCurveTo(cx + r * 0.05, cy - r * 0.6, cx - r * 0.12, cy - r * 0.3, cx + r * 0.05, cy + r * 0.05); g.stroke();      // central sulcus
  g.beginPath(); g.moveTo(cx - r * 0.75, cy + r * 0.3); g.bezierCurveTo(cx - r * 0.35, cy + r * 0.12, cx + r * 0.1, cy + r * 0.12, cx + r * 0.45, cy - r * 0.05); g.stroke();  // lateral sulcus
  const n = o.dots ?? 70;
  for (let i = 0; i < n; i++) { const x = cx + (-1.05 + R() * 2.1) * r, y = cy + (-0.9 + R() * 1.4) * r, f = 0.5 + 0.5 * Math.sin(t * (1 + R() * 2) + i), off = o.offShare && R() < o.offShare; circle(g, x, y, Math.max(2, r * 0.022), alpha(off ? '#4a4a6a' : i % 4 ? col : ui.accent, (o.dim ?? 1) * (off ? 0.35 : 0.25 + 0.55 * f))); }
  g.restore();
  g.strokeStyle = alpha(col, 0.95); g.lineWidth = lw * 1.3; g.stroke(P);
  (o.spots || []).forEach(([x, y, k, c]) => { if (k > 0) { glow(g, cx + x * r, cy + y * r, r * 0.65 * k, c, 0.6 * k); circle(g, cx + x * r, cy + y * r, r * 0.07 * k, c); } });
  g.restore();
}
// a virus: a ball with knobbed spikes; a white blood cell: a soft round cell with a lobed nucleus
export function virus(g, x, y, r, c, t = 0) { for (let k = 0; k < 10; k++) { const a = k * 0.628 + t * 0.6, ex = x + Math.cos(a) * r * 1.5, ey = y + Math.sin(a) * r * 1.5; seg(g, [[x + Math.cos(a) * r, y + Math.sin(a) * r], [ex, ey]], Math.max(2, r * 0.16), c); circle(g, ex, ey, r * 0.22, c); } circle(g, x, y, r, c); circle(g, x - r * 0.3, y - r * 0.3, r * 0.3, alpha('#ffffff', 0.35)); }
export function whiteCell(g, x, y, r, t = 0) { circle(g, x, y, r * (1 + 0.05 * Math.sin(t * 3)), alpha('#e8f0ff', 0.9)); for (let k = 0; k < 3; k++) circle(g, x + Math.cos(k * 2.1) * r * 0.32, y + Math.sin(k * 2.1) * r * 0.32, r * 0.3, alpha('#8a5ad6', 0.85)); }
// purple adenosine grains filling the lower part of a circle up to `level`
export function grains(g, cx, cy, r, level, t, o = {}) {
  const ui = S().ui, R = rng(o.seed ?? 5), n = Math.floor(260 * clamp(level));
  for (let i = 0; i < n; i++) { const a = R() * 6.28, d = Math.sqrt(R()) * r * 0.9, x = cx + Math.cos(a) * d, yb = cy + Math.sin(a) * d * 0.9, y = cy + r * 0.85 - (cy + r * 0.85 - yb) * clamp(level * 1.2); circle(g, x + Math.sin(t * 2 + i) * 1.5, y, Math.max(2, r * 0.03), alpha(o.color || ui.accent, 0.85)); }
}
// screen-space eyelids closing (0 open … 1 shut) — microsleeps, heavy eyes
export function eyelids(g, k) { if (k <= 0) return; const h = E.H * 0.52 * clamp(k); g.fillStyle = '#000'; g.beginPath(); g.moveTo(0, 0); g.lineTo(E.W, 0); g.lineTo(E.W, h * 0.9); g.quadraticCurveTo(E.W / 2, h * 1.15, 0, h * 0.9); g.fill(); g.beginPath(); g.moveTo(0, E.H); g.lineTo(E.W, E.H); g.lineTo(E.W, E.H - h * 0.9); g.quadraticCurveTo(E.W / 2, E.H - h * 1.15, 0, E.H - h * 0.9); g.fill(); }
export function fadeBlack(g, k) { if (k > 0) { g.fillStyle = alpha('#000', clamp(k)); g.fillRect(0, 0, E.W, E.H); } }
// round gauge with a needle 0..1
export function gauge(g, x, y, r, v, label, color, a = 1) {
  const ui = S().ui; g.save(); g.globalAlpha *= a; circle(g, x, y, r, alpha('#05061a', 0.85)); ring(g, x, y, r, 4, alpha(color, 0.9));
  for (let i = 0; i <= 10; i++) { const an = Math.PI * (0.75 + 1.5 * i / 10); seg(g, [[x + Math.cos(an) * r * 0.78, y + Math.sin(an) * r * 0.78], [x + Math.cos(an) * r * 0.9, y + Math.sin(an) * r * 0.9]], 3, alpha(color, 0.7)); }
  const an = Math.PI * (0.75 + 1.5 * clamp(v)); seg(g, [[x, y], [x + Math.cos(an) * r * 0.75, y + Math.sin(an) * r * 0.75]], 5, color); circle(g, x, y, 7, color);
  text(g, label, x, y + r * 0.5, { size: r * 0.2, color: ui.cream, font: FONTS.ui, weight: 900, maxWidth: r * 1.6 }); g.restore();
}
// a paper page with handwritten lines that fit the page
export function page(g, x, y, w, h, lines, t, o = {}) {
  rr(g, x, y, w, h, 10); g.fillStyle = o.paper || '#efe6d0'; g.fill();
  for (let i = 1; i < 10; i++) { g.fillStyle = alpha('#6a8ad0', 0.3); g.fillRect(x + 20, y + 30 + i * (h - 40) / 10, w - 40, 2); }
  g.fillStyle = alpha('#d04a4a', 0.45); g.fillRect(x + w * 0.1, y, 3, h);
  lines.forEach(([t0, str], i) => { const n = Math.floor(clamp((t - t0) / 0.05, 0, str.length)); if (n > 0) text(g, str.slice(0, n), x + w * 0.14, y + 60 + i * (h - 80) / Math.max(4, lines.length + 1), { size: o.size || h * 0.09, color: '#26304a', font: FONTS.ui, weight: 800, align: 'left', maxWidth: w * 0.8 }); });
}
export { FX, UI, drawFigure, POSES, breathe, walkPose, headPos, brainPath };
