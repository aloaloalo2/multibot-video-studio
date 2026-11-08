// engine/core.js — shared runtime for every shot. All drawing is in LOGICAL units:
// 16:9 stage = 1920x1080, 9:16 stage = 1080x1920. The player scales to output pixels.
import { STYLES, BASE_MOODS } from './styles.js';

export const E = { W: 1920, H: 1080, PX: 1, fps: 24, vertical: false, style: null, styleId: 'dusk', cfg: {}, words: [], shots: [] };
export const V = (h, v) => (E.vertical ? v : h);           // pick a value by aspect: V(landscape, vertical)

// ---------- math / timing ----------
export const clamp = (x, a = 0, b = 1) => (x < a ? a : x > b ? b : x);
export const lerp = (a, b, k) => a + (b - a) * k;
export const prog = (t, a, b) => clamp((t - a) / (b - a));
export const ease = {
  linear: x => clamp(x),
  in: x => (x = clamp(x)) ** 3,
  out: x => 1 - (1 - clamp(x)) ** 3,
  inOut: x => ((x = clamp(x)) < 0.5 ? 4 * x ** 3 : 1 - (-2 * x + 2) ** 3 / 2),
  sine: x => -(Math.cos(Math.PI * clamp(x)) - 1) / 2,
  outBack: x => { x = clamp(x); const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2; },
  outElastic: x => { x = clamp(x); return x === 0 || x === 1 ? x : 2 ** (-10 * x) * Math.sin((x * 10 - 0.75) * (2 * Math.PI) / 3) + 1; },
};
// keyframes: key(t, [[0, 1], [2, 1.2], [4, 1]], ease.inOut) -> number | array | object of numbers
export function key(t, frames, fn = ease.inOut) {
  if (t <= frames[0][0]) return frames[0][1];
  for (let i = 1; i < frames.length; i++) {
    const [t1, v1] = frames[i];
    if (t <= t1) { const [t0, v0] = frames[i - 1]; return mixVal(v0, v1, (frames[i][2] || fn)((t - t0) / (t1 - t0))); }
  }
  return frames[frames.length - 1][1];
}
export function mixVal(a, b, k) {
  if (typeof a === 'number') return lerp(a, b, k);
  if (Array.isArray(a)) return a.map((v, i) => mixVal(v, b[i], k));
  const o = {}; for (const kk in a) o[kk] = typeof a[kk] === 'number' || Array.isArray(a[kk]) ? mixVal(a[kk], b[kk] ?? a[kk], k) : (k < 0.5 ? a[kk] : b[kk] ?? a[kk]); return o;
}
export function rng(seed = 1) { return () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
const hash = (n) => { const s = Math.sin(n * 127.1 + 311.7) * 43758.5453; return s - Math.floor(s); };
export function noise(x, seed = 0) { const i = Math.floor(x), f = x - i, u = f * f * (3 - 2 * f); return lerp(hash(i + seed * 57), hash(i + 1 + seed * 57), u) * 2 - 1; }
export const shake = (t, amp = 4, freq = 1.3, seed = 3) => [noise(t * freq, seed) * amp, noise(t * freq, seed + 9) * amp];
// talking mouth amount (0..1) driven by the real word timings when available
export function talkAmount(globalT, from = -1, to = 1e9) {
  if (globalT < from || globalT > to) return 0;
  const w = E.words.find(w => globalT >= w.start && globalT <= w.end);
  if (!w && E.words.length) return 0;
  return clamp(0.25 + 0.75 * Math.abs(Math.sin(globalT * 17)) * (0.6 + 0.4 * Math.sin(globalT * 5.3)));
}

// time (global seconds) when a word is spoken: wordTime('brain', 40) -> 43.78 (null if not found)
export function wordTime(match, after = 0) {
  const m = match.toLowerCase().replace(/[^\w']/g, '');
  const w = E.words.find(w => w.start >= after - 0.05 && w.word.toLowerCase().replace(/[^\w']/g, '').startsWith(m));
  return w ? w.start : null;
}

// ---------- colour ----------
export function rgb(c) {
  if (Array.isArray(c)) return c;
  if (c.startsWith('rgb')) { const m = c.match(/[\d.]+/g).map(Number); return [m[0], m[1], m[2], m[3] ?? 1]; }
  let h = c.slice(1); if (h.length === 3) h = [...h].map(x => x + x).join('');
  const n = parseInt(h.slice(0, 6), 16); return [n >> 16, (n >> 8) & 255, n & 255, h.length > 6 ? parseInt(h.slice(6), 16) / 255 : 1];
}
export const css = ([r, g, b, a = 1]) => `rgba(${r | 0},${g | 0},${b | 0},${+a.toFixed(3)})`;
export const mix = (c1, c2, k) => { const a = rgb(c1), b = rgb(c2); return css(a.map((v, i) => lerp(v, b[i] ?? 1, k))); };
export const alpha = (c, a) => { const x = rgb(c); return css([x[0], x[1], x[2], a]); };
export const shade = (c, k) => (k < 0 ? mix(c, '#000000', -k) : mix(c, '#ffffff', k));

// ---------- style / moods ----------
export function setStyle(id) { E.styleId = STYLES[id] ? id : 'dusk'; E.style = STYLES[E.styleId]; }
// mood('night') -> { sky:[...], ambient, key, rim, wall, floor, dark, practical, fog }
export function mood(name = 'dusk') { const base = BASE_MOODS[name] || BASE_MOODS.dusk; return { ...base, ...(E.style.moods?.[name] || {}) }; }
export const S = () => E.style;   // current style tokens (ink, feature, ui colours, grade)

// ---------- drawing primitives (logical units) ----------
export function rr(g, x, y, w, h, r) { r = Math.min(r, w / 2, h / 2); g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r); g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath(); }
export function seg(g, pts, w, col, cap = 'round') { g.strokeStyle = col; g.lineWidth = w; g.lineCap = cap; g.lineJoin = 'round'; g.beginPath(); g.moveTo(pts[0][0], pts[0][1]); for (let i = 1; i < pts.length; i++) g.lineTo(pts[i][0], pts[i][1]); g.stroke(); }
export function poly(g, pts, fill) { g.fillStyle = fill; g.beginPath(); g.moveTo(pts[0][0], pts[0][1]); for (let i = 1; i < pts.length; i++) g.lineTo(pts[i][0], pts[i][1]); g.closePath(); g.fill(); }
export function circle(g, x, y, r, fill) { g.fillStyle = fill; g.beginPath(); g.arc(x, y, Math.max(0, r), 0, Math.PI * 2); g.fill(); }
export function ring(g, x, y, r, w, col) { g.strokeStyle = col; g.lineWidth = w; g.beginPath(); g.arc(x, y, Math.max(0, r), 0, Math.PI * 2); g.stroke(); }
export function linGrad(g, x0, y0, x1, y1, stops) { const gr = g.createLinearGradient(x0, y0, x1, y1); stops.forEach((c, i) => Array.isArray(c) ? gr.addColorStop(c[0], c[1]) : gr.addColorStop(i / Math.max(1, stops.length - 1), c)); return gr; }
export function radGrad(g, x, y, r0, r1, stops) { const gr = g.createRadialGradient(x, y, r0, x, y, r1); stops.forEach((c, i) => Array.isArray(c) ? gr.addColorStop(c[0], c[1]) : gr.addColorStop(i / Math.max(1, stops.length - 1), c)); return gr; }
export function glow(g, x, y, r, col, a = 1) { g.save(); g.globalCompositeOperation = 'lighter'; g.fillStyle = radGrad(g, x, y, 0, r, [alpha(col, a), alpha(col, a * 0.35), alpha(col, 0)]); g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill(); g.restore(); }
// darken / tint the whole stage (e.g. after a blurred background so the subject pops)
export function veil(g, color = '#000', a = 0.3, op = 'source-over') { g.save(); g.globalCompositeOperation = op; g.fillStyle = alpha(color, a); g.fillRect(-E.W, -E.H, E.W * 3, E.H * 3); g.restore(); }
export function fillRect(g, x, y, w, h, fill) { g.fillStyle = fill; g.fillRect(x, y, w, h); }
// sky / backdrop gradient over the whole stage (works under any camera)
export function backdrop(g, colors, area = [-E.W, -E.H, E.W * 3, E.H * 3]) { g.fillStyle = linGrad(g, 0, 0, 0, E.H, colors); g.fillRect(...area); }

// ---------- text ----------
export const FONTS = { title: 'Fredoka', ui: 'Nunito', serif: 'Playfair Display' };
// A font without a letter (Fredoka, Bebas and the other title fonts have no Cyrillic) falls back to Nunito, which player.js
// loads with Cyrillic, never to the browser's serif.
const fontOf = (italic, weight, size, font) => `${italic ? 'italic ' : ''}${weight} ${size}px "${font}", "Nunito", sans-serif`;
// how light a colour looks: sRGB luma, 0 black … 1 white (its alpha is ignored; a colour rgb() cannot read counts as light)
export function luma(c) { try { const [r, g, b] = rgb(c); return Number.isFinite(r + g + b) ? (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 : 0.8; } catch { return 0.8; } }

// Stable palette contrast, chosen from the saved style, never from moving pixels.
export function textContrast(foreground, background) {
  const lum = color => rgb(color).slice(0, 3).map(v => v / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4)
    .reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
  const a = lum(foreground), b = lum(background);
  return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
}
export function readableTextColor(color, background, minimum = 4.5) {
  if (textContrast(color, background) >= minimum) return color;
  const target = textContrast('#000000', background) > textContrast('#ffffff', background) ? '#000000' : '#ffffff';
  for (let step = 1; step <= 20; step++) {
    const candidate = mix(color, target, step / 20);
    if (textContrast(candidate, background) >= minimum) return candidate;
  }
  return target;
}

// Text has clean edges by default. A shadow is explicit artwork, not a side
// effect of contrast=true. The optional GPU tone switch stays off unless a film
// explicitly enables textTone; moving backgrounds must not recolor labels.
const LIGHT_TEXT = 0.45, DARK_TEXT = 0.3;
// a pixel is too close to the letters when its luma comes within .27 of theirs (wholly within .17), or passes it; the opposite
// tone fades in while such pixels cover 42 % to 48 % of the box of the letters
export const TONE_RULE = { near: [0.27, 0.17], share: [0.42, 0.48] };
// the luma band of the pixels too close to letters of luma L (light text: from L - .27 up; dark text: from L + .27 down)
export const nearBand = (L, kind) => { const q = Math.round(L * 20) / 20, [a, b] = TONE_RULE.near, c = (v) => +clamp(v, 0.05, 0.95).toFixed(2); return kind === 'dark' ? [c(q + a), c(q + b)] : [c(q - a), c(q - b)]; };
const textKind = (color) => { const L = luma(color); return L >= LIGHT_TEXT ? 'light' : L < DARK_TEXT ? 'dark' : 'mid'; };
export function legibleShadow(size, dark = true) {
  const c = dark ? '0,0,0' : '255,255,255';
  return [{ color: `rgba(${c},.7)`, blur: size * 0.05, x: 0, y: size * 0.03 }, { color: `rgba(${c},.35)`, blur: size * 0.16, x: 0, y: size * 0.06 }];
}
// the opposite tone of a text colour: a dark one of the same hue for light text, a light one for dark text
export const oppositeTone = (color) => (textKind(color) === 'dark' ? mix(color, '#ffffff', 0.86) : mix(color, '#000000', 0.8));

// ---------- cached text bitmaps (smooth sub-pixel motion for text) ----------
const _textCache = new Map(), TEXT_OVERSAMPLE = 2.5, TEXT_CACHE_MAX = 600;
function textBitmap(g, str, size, o) {
  if (typeof document === 'undefined' || !str) return null;
  const sh = o.shadow || [];
  const key = [str, size.toFixed(2), o.font, o.weight, o.color, o.align, o.base, o.gl, o.glowColor, o.spacing, o.stroke, o.strokeColor, o.italic, JSON.stringify(sh)].join('|');
  let bm = _textCache.get(key);
  if (bm) { _textCache.delete(key); _textCache.set(key, bm); return bm; }
  const shPad = sh.reduce((m, s) => Math.max(m, (s.blur || 0) * 1.5 + Math.max(Math.abs(s.x || 0), Math.abs(s.y || 0))), 0);
  const f = TEXT_OVERSAMPLE * Math.max(1, E.PX || 1), pad = Math.ceil(Math.max((o.gl || 0) * 1.5, shPad) + (o.stroke || 0) + size * 0.25);
  const fontStr = fontOf(o.italic, o.weight, size, o.font);
  const m = (() => { g.save(); g.font = fontStr; if ('letterSpacing' in g) g.letterSpacing = `${o.spacing}px`; const r = g.measureText(str); g.restore(); return r; })();
  const tw = Math.ceil(m.width) + 2, th = Math.ceil(size * 1.5), w = tw + pad * 2, h = th + pad * 2;
  const c = document.createElement('canvas'); c.width = Math.max(1, Math.ceil(w * f)); c.height = Math.max(1, Math.ceil(h * f)); c.__text = true;
  const x = c.getContext('2d'); x.scale(f, f); x.font = fontStr; x.textAlign = o.align; x.textBaseline = o.base; if ('letterSpacing' in x) x.letterSpacing = `${o.spacing}px`;
  const ox = pad + (o.align === 'center' ? tw / 2 : o.align === 'right' || o.align === 'end' ? tw : 0);
  const oy = pad + (o.base === 'top' || o.base === 'hanging' ? size * 0.2 : o.base === 'bottom' || o.base === 'ideographic' ? size * 1.3 : o.base === 'alphabetic' ? size * 1.05 : th / 2);
  // the shadows first: the letters that cast them are thrown off the bitmap, so only the shadow lands and a see-through
  // colour keeps its own opacity (a canvas shadow offset is in pixels, so it carries the oversampling)
  const off = w + 20;
  for (const s of sh) { x.save(); x.shadowColor = s.color; x.shadowBlur = (s.blur || 0) * f; x.shadowOffsetX = ((s.x || 0) + off) * f; x.shadowOffsetY = (s.y || 0) * f; x.fillStyle = '#000'; x.fillText(str, ox - off, oy); x.restore(); }
  if (o.stroke) { x.lineJoin = 'round'; x.lineWidth = o.stroke; x.strokeStyle = o.strokeColor; x.strokeText(str, ox, oy); }
  if (o.gl) { x.shadowColor = o.glowColor; x.shadowBlur = o.gl * f; }
  x.fillStyle = o.color; x.fillText(str, ox, oy);
  // the box of the letters themselves inside the bitmap: the tone samples the picture under the letters, not around them
  const gb = [ox - (m.actualBoundingBoxLeft || 0), ox + (m.actualBoundingBoxRight || tw), oy - (m.actualBoundingBoxAscent || size * 0.4), oy + (m.actualBoundingBoxDescent || size * 0.4)];
  bm = { c, w, h, ox, oy, gb }; _textCache.set(key, bm);
  if (_textCache.size > TEXT_CACHE_MAX) _textCache.delete(_textCache.keys().next().value);
  return bm;
}

// ---------- the tone under the letters, on the GPU ----------
// Scratch canvases large enough to stay on the GPU: a small canvas is drawn on the CPU, and copying a GPU picture into it
// waits for the whole frame. The picture under a line is drawn down to 16x4 through a filter that marks each sample too
// close to the letters (luminanceToAlpha, then a steep ramp; one filter per band, made when first needed), halved to 1x1,
// so that pixel's alpha is the share of such samples; a second filter turns the share into the weight of the opposite tone.
let TONE = null;
function toneKit() {
  if (TONE !== null) return TONE;
  TONE = false;
  if (typeof document === 'undefined' || typeof CanvasRenderingContext2D === 'undefined' || !('filter' in CanvasRenderingContext2D.prototype)) return TONE;
  const NS = 'http://www.w3.org/2000/svg', el = (tag, at = {}) => { const e = document.createElementNS(NS, tag); for (const k in at) e.setAttribute(k, at[k]); return e; };
  const svg = el('svg', { width: 0, height: 0, style: 'position:absolute;width:0;height:0' });
  const ramp = (id, [b0, b1], lum) => {
    const ft = el('filter', { id, 'color-interpolation-filters': 'sRGB' }), ct = el('feComponentTransfer');
    ct.append(el('feFuncA', { type: 'linear', slope: (1 / (b1 - b0)).toFixed(4), intercept: (-b0 / (b1 - b0)).toFixed(4) }));
    if (lum) ft.append(el('feColorMatrix', { type: 'luminanceToAlpha' })); ft.append(ct); svg.append(ft);
  };
  ramp('rz-tone', TONE_RULE.share, false);
  (document.body || document.documentElement).append(svg);
  const mk = (w, h) => { const k = document.createElement('canvas'); k.width = w; k.height = h; return k; }, made = new Set();
  const near = (band) => { const id = `rz-near-${band.join('-')}`; if (!made.has(id)) { ramp(id, band, true); made.add(id); } return `url(#${id})`; };
  TONE = { P: mk(256, 64), Q: mk(256, 64), A: mk(256, 256), B: mk(256, 256), near };
  return TONE;
}
const fit = (c, w, h) => { if (c.width < w || c.height < h) { c.width = Math.max(c.width, w); c.height = Math.max(c.height, h); } };
const reset = (c, smooth = true) => { c.setTransform(1, 0, 0, 1, 0, 0); c.globalAlpha = 1; c.globalCompositeOperation = 'copy'; c.filter = 'none'; c.imageSmoothingEnabled = smooth; c.imageSmoothingQuality = 'low'; return c; };
// draws bitmap A where the picture under it suits its colour and bitmap B (the opposite tone) where it does not; false when
// the line is off the canvas or the browser has no canvas filters (then the caller draws A alone)
function drawToned(g, A, B, dx, dy, kind, L) {
  const K = toneKit(); if (!K) return false;
  const T = g.getTransform(), [x0, x1, y0, y1] = [dx + A.gb[0], dx + A.gb[1], dy + A.gb[2], dy + A.gb[3]];
  const xs = [x0, x1, x0, x1], ys = [y0, y0, y1, y1], X = xs.map((v, i) => T.a * v + T.c * ys[i] + T.e), Y = xs.map((v, i) => T.b * v + T.d * ys[i] + T.f);
  const cw = g.canvas.width, ch = g.canvas.height;
  const bx0 = clamp(Math.min(...X), 0, cw), bx1 = clamp(Math.max(...X), 0, cw), by0 = clamp(Math.min(...Y), 0, ch), by1 = clamp(Math.max(...Y), 0, ch);
  if (bx1 - bx0 < 2 || by1 - by0 < 2) return false;
  const p = reset(K.P.getContext('2d')), q = reset(K.Q.getContext('2d'));
  p.filter = K.near(nearBand(L, kind)); p.drawImage(g.canvas, bx0, by0, bx1 - bx0, by1 - by0, 0, 0, 16, 4); p.filter = 'none';
  q.drawImage(K.P, 0, 0, 16, 4, 0, 0, 8, 2); p.drawImage(K.Q, 0, 0, 8, 2, 0, 0, 4, 1); q.drawImage(K.P, 0, 0, 4, 1, 0, 0, 2, 1); p.drawImage(K.Q, 0, 0, 2, 1, 0, 0, 1, 1);
  const w = A.c.width, h = A.c.height, flt = 'url(#rz-tone)'; fit(K.A, w, h); fit(K.B, w, h);
  const a = reset(K.A.getContext('2d'), false), b = reset(K.B.getContext('2d'), false);
  b.drawImage(B.c, 0, 0); b.globalCompositeOperation = 'destination-in'; b.filter = flt; b.drawImage(K.P, 0, 0, 1, 1, 0, 0, w, h); b.filter = 'none';
  a.drawImage(A.c, 0, 0); a.globalCompositeOperation = 'destination-out'; a.filter = flt; a.drawImage(K.P, 0, 0, 1, 1, 0, 0, w, h); a.filter = 'none';
  a.globalCompositeOperation = 'lighter'; a.drawImage(K.B, 0, 0, w, h, 0, 0, w, h);
  g.drawImage(K.A, 0, 0, w, h, dx, dy, A.w, A.h);
  return true;
}

// Text that belongs to a thing (a page, a sign, a screen, a poster, a label on a box) lies ON that thing: give the four
// corners of its face as they are drawn (top-left, top-right, bottom-right, bottom-left, e.g. measured on the prop's
// picture and placed like pic() places it), and u, v (0..1) on that face. Sizes are in thousandths of the face (a size of
// 60 is about a twelfth of it), so the text slants, shrinks and turns with the face and never hangs flat over a slanted
// surface or runs past its edge (user, 5 November 2026: text «тяп-ляп», lying anywhere, not in its place).
//   textOn(g, [[x0,y0],[x1,y1],[x2,y2],[x3,y3]], 'NAMES', 0.5, 0.1, { size: 66, color: '#6a4224', align: 'center' })
export function textOn(g, quad, str, u, v, o = {}) {
  const at = (uu, vv) => { const [a, b, c, d] = quad, tx = a[0] + (b[0] - a[0]) * uu, ty = a[1] + (b[1] - a[1]) * uu, bx = d[0] + (c[0] - d[0]) * uu, by = d[1] + (c[1] - d[1]) * uu;
    return [tx + (bx - tx) * vv, ty + (by - ty) * vv]; };
  const [ox, oy] = at(u, v), [ux, uy] = at(u + 0.01, v), [vx, vy] = at(u, v + 0.01);
  g.save(); g.transform((ux - ox) / 10, (uy - oy) / 10, (vx - ox) / 10, (vy - oy) / 10, ox, oy);
  text(g, str, 0, 0, { align: 'left', ...o }); g.restore();
}

export function text(g, str, x, y, o = {}) {
  const { font = FONTS.title, weight = 700, color = '#fff', align = 'center', base = 'middle', glow: gl = 0, glowColor = 'rgba(255,140,60,.8)', spacing = 0, alpha: a = 1, stroke = 0, strokeColor = '#000', italic = false, maxWidth = 0, contrast = false } = o;
  let size = o.size ?? 48;
  // maxWidth: shrink the font until the line fits its container (a notebook page, a card, the frame) — text never overflows
  if (maxWidth > 0) { const w = measure(g, str, size, font, weight) + spacing * Math.max(0, String(str).length - 1); if (w > maxWidth) size *= maxWidth / w; }
  const kind = contrast ? textKind(color) : null;
  const shadow = o.shadow ? [].concat(o.shadow) : [];
  // the tone switch is off unless a film asks for it ("textTone": true): on a moving picture it flipped letters between
  // light and dark (user, 5 November 2026: «блимає то чорний, то білий… забудь про такий метод»); the shadow alone keeps
  // the selected palette readable
  const toned = contrast && contrast !== 'shadow' && kind !== 'mid' && E.cfg?.textTone === true;
  g.save(); g.globalAlpha *= a; g.font = fontOf(italic, weight, size, font); g.textAlign = align; g.textBaseline = base;
  if ('letterSpacing' in g) g.letterSpacing = `${spacing}px`;
  // Text is drawn once into a cached bitmap and placed with drawImage: canvas fillText snaps glyphs to whole pixels,
  // so text on a slowly moving or zooming camera would step while everything around it glides.
  const opt = { font, weight, color, align, base, gl, glowColor, spacing, stroke, strokeColor, italic, shadow };
  const bm = textBitmap(g, String(str), size, opt);
  if (bm) {
    const dx = x - bm.ox, dy = y - bm.oy;
    const done = toned && drawToned(g, bm, textBitmap(g, String(str), size, { ...opt, color: oppositeTone(color), shadow: legibleShadow(size, kind === 'dark') }), dx, dy, kind, luma(color));
    if (!done) g.drawImage(bm.c, dx, dy, bm.w, bm.h);
  } else {
    for (const s of shadow) { g.save(); g.shadowColor = s.color; g.shadowBlur = (s.blur || 0) * (E.PX || 1); g.shadowOffsetX = (s.x || 0) * (E.PX || 1); g.shadowOffsetY = (s.y || 0) * (E.PX || 1); g.fillStyle = color; g.fillText(str, x, y); g.restore(); }
    if (stroke) { g.lineJoin = 'round'; g.lineWidth = stroke; g.strokeStyle = strokeColor; g.strokeText(str, x, y); }
    if (gl) { g.shadowColor = glowColor; g.shadowBlur = gl; }
    g.fillStyle = color; g.fillText(str, x, y);
  }
  // render.mjs --text-check: log where every visible line of text lands on the canvas, so text cut by the frame edge is caught
  // render.mjs --logic-check logs it too, in drawing order with the pictures and figures (DRAW_LOG)
  if ((globalThis.TEXT_LOG || globalThis.DRAW_LOG) && g.globalAlpha > 0.2 && !o.offscreen) {
    const m = g.measureText(str), w = m.width, x0 = align === 'center' ? x - w / 2 : align === 'right' || align === 'end' ? x - w : x, T = g.getTransform();
    const px = [x0, x0 + w, x0, x0 + w], py = [y - m.actualBoundingBoxAscent, y - m.actualBoundingBoxAscent, y + m.actualBoundingBoxDescent, y + m.actualBoundingBoxDescent];
    const sx = px.map((v, i) => T.a * v + T.c * py[i] + T.e), sy = px.map((v, i) => T.b * v + T.d * py[i] + T.f);
    const box = { str: String(str), x0: Math.min(...sx), x1: Math.max(...sx), y0: Math.min(...sy), y1: Math.max(...sy), W: g.canvas.width, H: g.canvas.height };
    if (globalThis.TEXT_LOG) globalThis.TEXT_LOG.push(box);
    if (globalThis.DRAW_LOG && String(str).trim()) globalThis.DRAW_LOG.push({ k: 'text', ...box, a: g.globalAlpha, layer: globalThis.__LAYER ?? null });
  }
  g.restore();
}
export function measure(g, str, size, font = FONTS.title, weight = 700) { g.save(); g.font = fontOf(false, weight, size, font); const w = g.measureText(str).width; g.restore(); return w; }

// ---------- camera & parallax ----------
// cam = {x, y, z (zoom), r (roll, radians)}; depth 1 = character plane, <1 farther, >1 foreground
export function layer(g, cam, depth, fn) {
  g.save(); const z = 1 + ((cam.z ?? 1) - 1) * depth;
  g.translate(E.W / 2, E.H / 2); if (cam.r) g.rotate(cam.r * Math.min(1, depth)); g.scale(z, z);
  g.translate(-E.W / 2 - (cam.x || 0) * depth, -E.H / 2 - (cam.y || 0) * depth);
  // the logic check compares depth only inside one layer (a far layer's foot lines are not this layer's)
  const was = globalThis.__LAYER; globalThis.__LAYER = depth; try { fn(g); } finally { globalThis.__LAYER = was; } g.restore();
}
// cheap depth-of-field: draw into a small canvas and upscale (optionally extra blur)
const _blurPool = [];
export function blurLayer(g, amount, fn, cam = null, depth = 1) {
  if (amount <= 0.3) { cam ? layer(g, cam, depth, fn) : fn(g); return; }
  const k = clamp(1 / (1 + amount / 3), 0.06, 1);
  const w = Math.max(8, Math.round(E.W * E.PX * k)), h = Math.max(8, Math.round(E.H * E.PX * k));
  let c = _blurPool.find(b => !b.busy && b.width === w && b.height === h);
  // __blur: a deliberately soft layer; the logic check does not call its upscale a blown-up asset
  if (!c) { c = document.createElement('canvas'); c.width = w; c.height = h; c.__blur = true; _blurPool.push(c); }
  c.busy = true; const x = c.getContext('2d'); x.setTransform(1, 0, 0, 1, 0, 0); x.clearRect(0, 0, w, h);
  x.setTransform(w / E.W, 0, 0, h / E.H, 0, 0); cam ? layer(x, cam, depth, fn) : fn(x);
  // blur at the small size (fast), then upscale smoothly
  if (!c.b) { c.b = document.createElement('canvas'); }
  if (c.b.width !== w || c.b.height !== h) { c.b.width = w; c.b.height = h; }
  const bx = c.b.getContext('2d'); bx.setTransform(1, 0, 0, 1, 0, 0); bx.clearRect(0, 0, w, h);
  bx.filter = `blur(${Math.max(0.4, amount * E.PX * k)}px)`; bx.drawImage(c, 0, 0); bx.filter = 'none';
  g.save(); g.setTransform(1, 0, 0, 1, 0, 0); g.imageSmoothingEnabled = true; g.imageSmoothingQuality = 'high';
  g.drawImage(c.b, 0, 0, E.W * E.PX, E.H * E.PX); g.restore(); c.busy = false;
}

// ---------- shot registry ----------
const SHOTS = {};
// registerShot('s012', { kind: '2d' | '3d', draw(g, t, info), init?(T, info), overlay?(g, t, info) })
export function registerShot(id, def) { SHOTS[id] = { kind: '2d', ...def }; }
export const getShot = id => SHOTS[id];
export const allShots = () => SHOTS;
