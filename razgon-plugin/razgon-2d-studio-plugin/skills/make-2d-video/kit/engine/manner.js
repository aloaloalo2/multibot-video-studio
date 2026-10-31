// engine/manner.js — the drawing manner of a style: not a colour grade but how every shape is drawn.
// A style may carry { manner: {...} }; installManner() wraps the 2D canvas so every scene, set and character changes
// at once without touching scene code. A style without a manner draws exactly as before.
//
//   wobble: px          hand-drawn line tremor (in frame pixels); boil: fps at which the tremor re-draws (0 = still)
//   outline: { color, width }   an ink outline around every filled shape that is not a background
//   flat: true          gradients become one flat colour; glow: false drops additive light (glows, bloom blobs)
//   tones: ['#..', ...] every colour snaps to the nearest of these tones by lightness (ink, chalk, two-tone print)
//   fillAlpha: 0..1     fills become this transparent (chalk: outlines carry the drawing)
//   shadow: { x, y, color }    a hard cast shadow under every filled shape (paper cut-out)
//   lineScale: k        every line width times k; imageFilter: CSS filter for pictures (PNG props)
//   paper: { color, amount, mode }   a paper, board or canvas texture laid over the finished frame
import { E } from './core.js';

let M = null, tick = 0;
const P = CanvasRenderingContext2D.prototype, O = {};
const toneCache = new Map(), probe = document.createElement('canvas').getContext('2d');
// the real fillStyle setter, kept before installManner wraps it, so reading a colour never calls the wrapper again
const FILL = Object.getOwnPropertyDescriptor(P, 'fillStyle');

function rgba(color) {
  FILL.set.call(probe, '#000'); FILL.set.call(probe, color); const c = FILL.get.call(probe);
  if (c[0] === '#') return [parseInt(c.slice(1, 3), 16), parseInt(c.slice(3, 5), 16), parseInt(c.slice(5, 7), 16), 1];
  const m = c.match(/[\d.]+/g); return m ? [+m[0], +m[1], +m[2], m[3] === undefined ? 1 : +m[3]] : [0, 0, 0, 1];
}
function tone(color) {
  if (typeof color !== 'string' || !M.tones) return color;
  let out = toneCache.get(color); if (out) return out;
  const [r, g, b, a] = rgba(color), lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  const tones = M._tones; let best = tones[0];
  for (const t of tones) if (Math.abs(t.lum - lum) < Math.abs(best.lum - lum)) best = t;
  out = `rgba(${best.rgb[0]},${best.rgb[1]},${best.rgb[2]},${a})`; toneCache.set(color, out); return out;
}
function flatOf(grad) {
  const stops = grad.__stops || []; if (!stops.length) return '#000';
  return stops.reduce((a, b) => (Math.abs(b[0] - 0.5) < Math.abs(a[0] - 0.5) ? b : a))[1];
}
// deterministic noise: the same point trembles the same way until the boil frame changes
function noise(x, y, k) { const s = Math.sin(x * 12.9898 + y * 78.233 + k * 37.719 + tick * 91.17) * 43758.5453; return s - Math.floor(s) - 0.5; }
function amp(g) { if (!M.wobble) return 0; const m = g.getTransform(); return M.wobble * E.PX / Math.max(0.05, Math.sqrt(Math.abs(m.a * m.d - m.b * m.c))); }
function J(g, x, y) { const a = g.__amp; return a ? [x + noise(x, y, 1) * 2 * a, y + noise(x, y, 2) * 2 * a] : [x, y]; }
function track(g, x, y) { g.__lx = x; g.__ly = y; const b = g.__box; if (b) { b[0] = Math.min(b[0], x); b[1] = Math.min(b[1], y); b[2] = Math.max(b[2], x); b[3] = Math.max(b[3], y); } }
function wobblyLine(g, x, y) {
  const x0 = g.__lx, y0 = g.__ly;
  if (g.__amp && x0 !== undefined) {
    const n = Math.min(24, Math.max(1, Math.floor(Math.hypot(x - x0, y - y0) / (g.__amp * 9 + 6))));
    for (let i = 1; i < n; i++) O.lineTo.call(g, ...J(g, x0 + (x - x0) * i / n, y0 + (y - y0) * i / n));
  }
  O.lineTo.call(g, ...J(g, x, y)); track(g, x, y);
}
function sampled(g, pts) { for (const [x, y] of pts) wobblyLine(g, x, y); }
function isBackground(g) {
  const b = g.__box; if (!b) return true; const m = g.getTransform();
  const w = Math.abs((b[2] - b[0]) * m.a) + Math.abs((b[3] - b[1]) * m.c), h = Math.abs((b[2] - b[0]) * m.b) + Math.abs((b[3] - b[1]) * m.d);
  return w * h > g.canvas.width * g.canvas.height * 0.45;
}
const additive = (g) => g.globalCompositeOperation === 'lighter' || g.globalCompositeOperation === 'screen';

export function installManner(manner) {
  if (!manner || M) return;
  M = manner; M._tones = (M.tones || []).map((c) => { const [r, g, b] = rgba(c); return { rgb: [r, g, b], lum: 0.2126 * r + 0.7152 * g + 0.0722 * b }; });
  for (const k of ['beginPath', 'moveTo', 'lineTo', 'arc', 'ellipse', 'arcTo', 'rect', 'bezierCurveTo', 'quadraticCurveTo', 'fill', 'stroke', 'fillRect', 'drawImage', 'createLinearGradient', 'createRadialGradient']) O[k] = P[k];
  const fillDesc = Object.getOwnPropertyDescriptor(P, 'fillStyle'), strokeDesc = Object.getOwnPropertyDescriptor(P, 'strokeStyle'), widthDesc = Object.getOwnPropertyDescriptor(P, 'lineWidth');

  P.createLinearGradient = function (...a) { const g = O.createLinearGradient.apply(this, a); g.__stops = []; const add = g.addColorStop.bind(g); g.addColorStop = (o, c) => { g.__stops.push([o, c]); add(o, tone(c)); }; return g; };
  P.createRadialGradient = function (...a) { const g = O.createRadialGradient.apply(this, a); g.__stops = []; const add = g.addColorStop.bind(g); g.addColorStop = (o, c) => { g.__stops.push([o, c]); add(o, tone(c)); }; return g; };
  const style = (v) => (typeof v === 'string' ? tone(v) : v && v.__stops && M.flat ? tone(flatOf(v)) : v);
  Object.defineProperty(P, 'fillStyle', { configurable: true, get() { return fillDesc.get.call(this); }, set(v) { fillDesc.set.call(this, style(v)); } });
  Object.defineProperty(P, 'strokeStyle', { configurable: true, get() { return strokeDesc.get.call(this); }, set(v) { strokeDesc.set.call(this, style(v)); } });
  if (M.lineScale && M.lineScale !== 1) Object.defineProperty(P, 'lineWidth', { configurable: true, get() { return widthDesc.get.call(this) / M.lineScale; }, set(v) { widthDesc.set.call(this, v * M.lineScale); } });

  P.beginPath = function () { this.__amp = amp(this); this.__box = null; this.__lx = undefined; return O.beginPath.call(this); };
  P.moveTo = function (x, y) { if (!this.__box) this.__box = [x, y, x, y]; O.moveTo.call(this, ...J(this, x, y)); track(this, x, y); };
  P.lineTo = function (x, y) { if (!this.__box) this.__box = [x, y, x, y]; wobblyLine(this, x, y); };
  P.rect = function (x, y, w, h) { this.moveTo(x, y); this.lineTo(x + w, y); this.lineTo(x + w, y + h); this.lineTo(x, y + h); this.lineTo(x, y); };
  P.arc = function (x, y, r, a0, a1, ccw) {
    if (!this.__box) this.__box = [x - r, y - r, x + r, y + r]; else { track(this, x - r, y - r); track(this, x + r, y + r); }
    if (!this.__amp) return O.arc.call(this, x, y, r, a0, a1, ccw);
    let span = a1 - a0; if (!ccw && span < 0) span += Math.PI * 2; if (ccw && span > 0) span -= Math.PI * 2; span = Math.max(-Math.PI * 2, Math.min(Math.PI * 2, span));
    const n = Math.max(8, Math.min(72, Math.ceil(Math.abs(span) * r / 14))), pts = [];
    for (let i = 0; i <= n; i++) { const a = a0 + span * i / n; pts.push([x + Math.cos(a) * r, y + Math.sin(a) * r]); }
    if (this.__lx === undefined) { O.moveTo.call(this, ...J(this, ...pts[0])); track(this, ...pts[0]); }
    sampled(this, pts);
  };
  P.ellipse = function (x, y, rx, ry, rot, a0, a1, ccw) {
    if (!this.__box) this.__box = [x - rx, y - ry, x + rx, y + ry];
    if (!this.__amp) return O.ellipse.call(this, x, y, rx, ry, rot, a0, a1, ccw);
    let span = a1 - a0; if (!ccw && span < 0) span += Math.PI * 2; span = Math.max(-Math.PI * 2, Math.min(Math.PI * 2, span));
    const n = Math.max(10, Math.min(72, Math.ceil(Math.abs(span) * Math.max(rx, ry) / 14))), c = Math.cos(rot), s = Math.sin(rot), pts = [];
    for (let i = 0; i <= n; i++) { const a = a0 + span * i / n, ex = Math.cos(a) * rx, ey = Math.sin(a) * ry; pts.push([x + ex * c - ey * s, y + ex * s + ey * c]); }
    if (this.__lx === undefined) { O.moveTo.call(this, ...J(this, ...pts[0])); track(this, ...pts[0]); }
    sampled(this, pts);
  };
  P.arcTo = function (x1, y1, x2, y2, r) { if (!this.__amp) { track(this, x1, y1); return O.arcTo.call(this, x1, y1, x2, y2, r); } O.arcTo.call(this, ...J(this, x1, y1), ...J(this, x2, y2), r); track(this, x1, y1); };
  P.bezierCurveTo = function (c1x, c1y, c2x, c2y, x, y) {
    if (!this.__amp || this.__lx === undefined) { track(this, x, y); return O.bezierCurveTo.call(this, c1x, c1y, c2x, c2y, x, y); }
    const x0 = this.__lx, y0 = this.__ly, pts = [];
    for (let i = 1; i <= 12; i++) { const t = i / 12, u = 1 - t; pts.push([u * u * u * x0 + 3 * u * u * t * c1x + 3 * u * t * t * c2x + t * t * t * x, u * u * u * y0 + 3 * u * u * t * c1y + 3 * u * t * t * c2y + t * t * t * y]); }
    sampled(this, pts);
  };
  P.quadraticCurveTo = function (cx, cy, x, y) {
    if (!this.__amp || this.__lx === undefined) { track(this, x, y); return O.quadraticCurveTo.call(this, cx, cy, x, y); }
    const x0 = this.__lx, y0 = this.__ly, pts = [];
    for (let i = 1; i <= 10; i++) { const t = i / 10, u = 1 - t; pts.push([u * u * x0 + 2 * u * t * cx + t * t * x, u * u * y0 + 2 * u * t * cy + t * t * y]); }
    sampled(this, pts);
  };
  P.fill = function (...a) {
    if (M.glow === false && additive(this)) return;
    const shape = !a.length && !isBackground(this);
    if (shape && M.shadow) { this.save(); this.shadowColor = M.shadow.color; this.shadowOffsetX = M.shadow.x * E.PX; this.shadowOffsetY = M.shadow.y * E.PX; this.shadowBlur = (M.shadow.blur || 0) * E.PX; O.fill.apply(this, a); this.restore(); }
    else if (shape && M.fillAlpha != null) { this.save(); this.globalAlpha *= M.fillAlpha; O.fill.apply(this, a); this.restore(); }
    else O.fill.apply(this, a);
    if (shape && M.outline && this.globalAlpha > 0.35) {
      this.save(); const m = this.getTransform(), k = Math.sqrt(Math.abs(m.a * m.d - m.b * m.c)) || 1;
      strokeDesc.set.call(this, M.outline.color); widthDesc.set.call(this, M.outline.width * E.PX / k); this.lineJoin = 'round'; this.lineCap = 'round';
      this.shadowColor = 'transparent'; O.stroke.call(this); this.restore();
    }
  };
  P.stroke = function (...a) { if (M.glow === false && additive(this)) return; return O.stroke.apply(this, a); };
  // a filled rectangle that is not the whole background is a shape too (walls, signs): draw it as one so the manner applies
  P.fillRect = function (x, y, w, h) {
    if (M.glow === false && additive(this)) return;
    const m = this.getTransform(), area = Math.abs(w * h * (m.a * m.d - m.b * m.c));
    if (area > this.canvas.width * this.canvas.height * 0.45 || !(M.outline || M.shadow || M.fillAlpha != null || M.wobble)) return O.fillRect.call(this, x, y, w, h);
    this.save(); this.beginPath(); this.rect(x, y, w, h); this.fill(); this.restore();
  };
  if (M.imageFilter) P.drawImage = function (...a) { if (!(a[0] instanceof HTMLImageElement)) return O.drawImage.apply(this, a); const f = this.filter; this.filter = M.imageFilter; O.drawImage.apply(this, a); this.filter = f; };
}

// the boil: on a still frame the tremor stays, at playback it re-draws `boil` times a second like hand animation
export function mannerFrame(frame, fps) { if (M?.boil) tick = Math.floor((frame / fps) * M.boil); }

let paperTile = null;
export function paperPass(g, W, H) {
  const p = M?.paper; if (!p) return;
  if (!paperTile || paperTile.width !== W) {
    paperTile = document.createElement('canvas'); paperTile.width = W; paperTile.height = H;
    const x = paperTile.getContext('2d'), img = x.createImageData(W, H), d = img.data; let s = 9187;
    const [r, gg, b] = rgba(p.color || '#f3eee2');
    for (let i = 0; i < d.length; i += 4) { s = (s * 1664525 + 1013904223) >>> 0; const n = ((s >>> 24) - 128) / 128; const fib = Math.sin(i * 0.0007) * 0.35; const v = 1 + (n * 0.6 + fib) * 0.12; d[i] = r * v; d[i + 1] = gg * v; d[i + 2] = b * v; d[i + 3] = 255; }
    x.putImageData(img, 0, 0);
  }
  g.save(); g.setTransform(1, 0, 0, 1, 0, 0); g.globalAlpha = p.amount ?? 0.3; g.globalCompositeOperation = p.mode || 'multiply'; O.drawImage ? O.drawImage.call(g, paperTile, 0, 0, W, H) : g.drawImage(paperTile, 0, 0, W, H); g.restore();
}
