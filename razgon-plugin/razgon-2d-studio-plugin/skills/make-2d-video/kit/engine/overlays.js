// engine/overlays.js — graphics that live on the FILM's timeline, not inside a shot.
// story/shots.json → "overlays": [{ "start": 12.4, "end": 15.0, "type": "text", "str": "264 HOURS", ... }]
// They are drawn after the colour grade, survive every cut, always enter and leave with motion, and stay on screen at
// least as long as it takes to read them. Use them for anything that must not pop or be cut off by an edit:
// key numbers, chapter lines, counters, labels that span two shots.
import { E, V, S, clamp, ease, prog, alpha, text, FONTS, measure, rr } from './core.js';
import { kText } from './motion.js';

// seconds a viewer needs to read a string (0.9 s + 0.3 s per word, at least 1.2 s)
export const readTime = (str) => Math.max(1.2, 0.9 + 0.3 * String(str).trim().split(/\s+/).length);
// fade-in/out envelope for anything with a lifetime: 0 → 1 → 0, eased
export function life(t, t0, t1, o = {}) { const i = o.in ?? 0.3, out = o.out ?? 0.4; return Math.min(ease.out(prog(t, t0, t0 + i)), ease.inOut(1 - prog(t, t1 - out, t1))); }
// the window an overlay is really shown for: the minimum reading time is enforced
export function span(ov) { const s = +ov.start, e = Math.max(+ov.end || s, s + (ov.min ?? readTime(ov.str ?? ''))); return [s, e]; }

const colour = (c) => (c && S().ui[c]) || c || S().ui.gold;

export function drawOverlays(g, t) {
  for (const ov of E.overlays || []) {
    const [s, e] = span(ov); if (t < s - 0.05 || t > e) continue;
    const lt = t - s, a = life(t, s, e, { in: ov.fadeIn, out: ov.fadeOut }), x = (ov.x ?? 0.5) * E.W, y = (ov.y ?? 0.2) * E.H, c = colour(ov.color);
    if (a <= 0 && lt > 0.5) continue;
    g.save(); g.globalAlpha = Math.max(0, a);
    if (ov.type === 'badge') {
      const size = ov.size ?? V(36, 42), w = measure(g, ov.str, size, FONTS.ui, 900) + 44;
      rr(g, x - w / 2, y - size * 0.75, w, size * 1.5, size * 0.75); g.fillStyle = alpha('#05040c', 0.55); g.fill();
      text(g, ov.str, x, y, { size, color: c, font: FONTS.ui, weight: 900, glow: 14, glowColor: alpha(c, 0.6), spacing: 2 });
    } else if (ov.type === 'label') {
      text(g, ov.str, x, y + (1 - ease.out(prog(lt, 0, 0.4))) * 18, { size: ov.size ?? V(36, 42), color: c, font: FONTS.ui, weight: 900, glow: 14, glowColor: alpha(c, 0.6), align: ov.align || 'center', spacing: 2 });
    } else {   // kinetic text: the letters animate in with `mode`, the whole line fades out together before `end`
      kText(g, lt, ov.str, x, y, { start: 0, mode: ov.mode || 'rise', size: ov.size ?? V(84, 76), color: c, glow: ov.glow ?? 22, align: ov.align || 'center', font: ov.font === 'ui' ? FONTS.ui : FONTS.title, weight: ov.font === 'ui' ? 900 : 700 });
    }
    g.restore();
  }
}
