// engine/player.js — loads a project, maps global time -> shot, renders frames deterministically.
// window.renderFrame(frameIndex) draws one frame onto #main. Used by render.mjs (headless).
import { E, V, setStyle, getShot, clamp, lerp, ease, prog, alpha, text, FONTS } from './core.js';
import { STYLES } from './styles.js';
import { captions } from './ui2d.js';
import { drawOverlays } from './overlays.js';
import { installManner, mannerFrame, paperPass } from './manner.js';

const q = new URLSearchParams(location.search);
const PROJ = '/project';
const RES = { '720p': 720, '1080p': 1080, '1440p': 1440, '2160p': 2160, '4k': 2160 };
let main, mg, bufA, bufB, bufT, bufC, glCanvas, grainTiles = [], three = null;
const errors = (window.ERRORS = []);
const mk = (w, h) => { const c = document.createElement('canvas'); c.width = w; c.height = h; return c; };

async function loadFonts() {
  const F = [['Fredoka', '600', 'fredoka/files/fredoka-latin-600-normal.woff2'], ['Fredoka', '700', 'fredoka/files/fredoka-latin-700-normal.woff2'],
    ['Nunito', '800', 'nunito/files/nunito-latin-800-normal.woff2'], ['Nunito', '900', 'nunito/files/nunito-latin-900-normal.woff2'],
    ['Playfair Display', '900', 'playfair-display/files/playfair-display-latin-900-italic.woff2', 'italic'],
    // Title fonts a channel can pick in the Studio. Each has one weight, declared for every weight so a scene asking
    // for 700 or 900 gets the real letters instead of a smeared synthetic bold.
    ['Bebas Neue', '100 900', 'bebas-neue/files/bebas-neue-latin-400-normal.woff2'], ['Lilita One', '100 900', 'lilita-one/files/lilita-one-latin-400-normal.woff2'],
    ['Bangers', '100 900', 'bangers/files/bangers-latin-400-normal.woff2'], ['Permanent Marker', '100 900', 'permanent-marker/files/permanent-marker-latin-400-normal.woff2'],
    ['Baloo 2', '100 900', 'baloo-2/files/baloo-2-latin-800-normal.woff2'], ['Montserrat', '100 900', 'montserrat/files/montserrat-latin-800-normal.woff2'],
    ['Montserrat', '100 900', 'montserrat/files/montserrat-cyrillic-800-normal.woff2', 'normal', 'U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116']];
  for (const [fam, w, file, style, range] of F) { try { const ff = new FontFace(fam, `url(/node_modules/@fontsource/${file})`, { weight: w, style: style || 'normal', ...(range ? { unicodeRange: range } : {}) }); await ff.load(); document.fonts.add(ff); } catch (e) { console.log('font missing', fam, w); } }
}
async function boot() {
  const cfg = await (await fetch(`${PROJ}/config.json`)).json();
  const story = await (await fetch(`${PROJ}/story/shots.json`)).json();
  let words = []; try { const r = await fetch(`${PROJ}/timeline/words.json`); if (r.ok) words = await r.json(); } catch {}
  const vertical = (cfg.aspect || '16:9') === '9:16';
  const short = RES[cfg.resolution || '1080p'] || 1080, long = Math.round((short * 16) / 9 / 2) * 2;
  const scale = +(q.get('scale') || 1);
  const outW = Math.round(((vertical ? short : long) * scale) / 2) * 2, outH = Math.round(((vertical ? long : short) * scale) / 2) * 2;
  Object.assign(E, { vertical, W: vertical ? 1080 : 1920, H: vertical ? 1920 : 1080, fps: cfg.fps || 24, cfg, words: words.words || words, shots: story.shots, overlays: story.overlays || [], outW, outH });
  E.PX = outW / E.W;
  // A whole style can travel in config.json (a channel's own or a copied style) under the id it names.
  if (cfg.styleDef && typeof cfg.styleDef === 'object') STYLES[cfg.style || 'custom'] = { ...STYLES.dusk, ...cfg.styleDef };
  setStyle(q.get('style') || cfg.style || 'dusk');
  // Optional channel text style from config.json: { fonts: { title, ui, serif }, ui: { accent, ... } } over the style's own.
  if (cfg.fonts && typeof cfg.fonts === 'object') Object.assign(FONTS, cfg.fonts);
  if (cfg.ui && typeof cfg.ui === 'object') E.style = { ...E.style, ui: { ...E.style.ui, ...cfg.ui } };
  installManner(E.style.manner);
  await loadFonts();
  main = document.getElementById('main'); main.width = outW; main.height = outH; mg = main.getContext('2d', { willReadFrequently: !GPU_GRADE });
  buildLUT(); buildGradeFilter();
  bufA = mk(outW, outH); bufB = mk(outW, outH); bufT = mk(outW, outH); bufC = mk(outW, outH);
  const gw = Math.ceil(outW / 2), gh = Math.ceil(outH / 2);
  for (let k = 0; k < 4; k++) { const c = mk(gw, gh), x = c.getContext('2d'), id = x.createImageData(gw, gh); let s = 1234 + k * 999; for (let i = 0; i < id.data.length; i += 4) { s = (s * 1664525 + 1013904223) >>> 0; const v = s >>> 24; id.data[i] = id.data[i + 1] = id.data[i + 2] = v; id.data[i + 3] = 255; } x.putImageData(id, 0, 0); grainTiles.push(c); }
  const list = await (await fetch(`/__manifest`)).json();
  for (const f of list) { try { await import(f); } catch (e) { errors.push(`import ${f}: ${e.message}`); console.log('IMPORT ERROR', f, e.message); } }
  if (E.shots.some(s => getShot(s.id)?.kind === '3d')) { three = await import('./three-kit.js'); glCanvas = mk(outW, outH); three.getRenderer(glCanvas); }
  const dur = story.duration || E.shots[E.shots.length - 1].end;
  window.DURATION = dur; window.TOTAL_FRAMES = Math.ceil(dur * E.fps); window.OUT = [outW, outH];
  window.SHOT_LIST = E.shots.map(s => ({ id: s.id, start: s.start, end: s.end, ok: !!getShot(s.id) }));
  window.READY = true;
}

// colour grade: per-channel lift/gamma/gain + contrast as LUTs, saturation per pixel
let LUT = null, SAT = 1;
function buildLUT() {
  const gr = E.style.grade || {}; const lift = gr.lift || [0, 0, 0], gam = gr.gamma || [1, 1, 1], gain = gr.gain || [1, 1, 1], con = gr.contrast ?? 1; SAT = gr.sat ?? 1;
  const ident = con === 1 && lift.every(v => v === 0) && gam.every(v => v === 1) && gain.every(v => v === 1);
  if (ident && SAT === 1) { LUT = null; return; }
  LUT = [0, 1, 2].map(c => { const a = new Uint8ClampedArray(256); for (let i = 0; i < 256; i++) { let x = i / 255; x = clamp((x - 0.5) * con + 0.5); x = clamp(gain[c] * (x + lift[c] * (1 - x))); x = Math.pow(x, 1 / gam[c]); a[i] = Math.round(x * 255); } return a; });
}
// The grade runs on the GPU as an SVG filter: the same LUT as a 256-step table per channel, then the saturation as a
// colour matrix. Reading every frame back to the CPU waited for the GPU and kept the main canvas in software; it cost
// 15–30 % of a frame (06 Fast Food, 31 October 2026). The CPU loop stays for a canvas without filters.
const GPU_GRADE = typeof CanvasRenderingContext2D !== 'undefined' && 'filter' in CanvasRenderingContext2D.prototype;
let GRADE_FILTER = null, gradeBuf = null;
function buildGradeFilter() {
  if (!LUT || !GPU_GRADE) return;
  const NS = 'http://www.w3.org/2000/svg', el = (tag, attrs = {}) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; };
  const svg = el('svg', { width: 0, height: 0, style: 'position:absolute' }), f = el('filter', { id: 'rz-grade', 'color-interpolation-filters': 'sRGB' });
  const ct = el('feComponentTransfer');
  ['R', 'G', 'B'].forEach((c, i) => ct.append(el(`feFunc${c}`, { type: 'table', tableValues: Array.from(LUT[i], (v) => (v / 255).toFixed(5)).join(' ') })));
  f.append(ct);
  if (SAT !== 1) {   // l = 0.2126 r + 0.7152 g + 0.0722 b, then r' = l + (r - l) * sat, as the CPU loop does
    const L = [0.2126, 0.7152, 0.0722], row = (i) => L.map((l, j) => (l * (1 - SAT) + (i === j ? SAT : 0)).toFixed(6)).join(' ') + ' 0 0';
    f.append(el('feColorMatrix', { type: 'matrix', values: [row(0), row(1), row(2), '0 0 0 1 0'].join(' ') }));
  }
  svg.append(f); document.body.append(svg); GRADE_FILTER = 'url(#rz-grade)';
}
function applyGrade(W, H) {
  if (!LUT) return;
  if (GRADE_FILTER) {
    if (!gradeBuf || gradeBuf.width !== W || gradeBuf.height !== H) gradeBuf = mk(W, H);
    const x = gradeBuf.getContext('2d'); x.setTransform(1, 0, 0, 1, 0, 0); x.globalAlpha = 1; x.globalCompositeOperation = 'copy'; x.filter = GRADE_FILTER; x.drawImage(main, 0, 0); x.filter = 'none';
    mg.save(); mg.setTransform(1, 0, 0, 1, 0, 0); mg.globalAlpha = 1; mg.filter = 'none'; mg.globalCompositeOperation = 'copy'; mg.drawImage(gradeBuf, 0, 0); mg.restore();
    return;
  }
  const img = mg.getImageData(0, 0, W, H), d = img.data, [R, G, B] = LUT, s = SAT;
  for (let i = 0; i < d.length; i += 4) {
    let r = R[d[i]], g = G[d[i + 1]], b = B[d[i + 2]];
    if (s !== 1) { const l = 0.2126 * r + 0.7152 * g + 0.0722 * b; r = l + (r - l) * s; g = l + (g - l) * s; b = l + (b - l) * s; }
    d[i] = r; d[i + 1] = g; d[i + 2] = b;
  }
  mg.putImageData(img, 0, 0);
}
function shotIndexAt(t) { const S = E.shots; for (let i = 0; i < S.length; i++) if (t < S[i].end) return i; return S.length - 1; }
const cache3D = new Map();
function state3D(shot, def, info) {
  if (cache3D.has(shot.id)) return cache3D.get(shot.id);
  for (const [k, v] of cache3D) if (cache3D.size >= 2) { v.dispose?.(); v.stage?.dispose?.(); cache3D.delete(k); }
  const st = def.init(three, info); cache3D.set(shot.id, st); return st;
}
function drawShot(buf, shot, lt) {
  const g = buf.getContext('2d'); g.setTransform(1, 0, 0, 1, 0, 0); g.globalAlpha = 1; g.globalCompositeOperation = 'source-over'; g.filter = 'none';
  g.fillStyle = '#000'; g.fillRect(0, 0, buf.width, buf.height); g.setTransform(E.PX, 0, 0, E.PX, 0, 0);
  const def = getShot(shot.id); const dur = shot.end - shot.start;
  const info = { ...(shot.params || {}), shot, dur, globalT: shot.start + lt, p: clamp(lt / dur), line: shot.line };
  if (!def) { g.fillStyle = '#20141c'; g.fillRect(0, 0, E.W, E.H); text(g, `MISSING SHOT ${shot.id}`, E.W / 2, E.H / 2 - 30, { size: 60, color: '#ff6f61' }); text(g, (shot.line || '').slice(0, 80), E.W / 2, E.H / 2 + 50, { size: 30, color: '#fff', font: FONTS.ui, weight: 800 }); return; }
  try {
    if (def.kind === '3d') {
      const st = state3D(shot, def, info); def.draw(st, lt, info, three); (st.stage || st).render();
      g.save(); g.setTransform(1, 0, 0, 1, 0, 0); g.drawImage(glCanvas, 0, 0, buf.width, buf.height); g.restore();
      if (def.overlay) { g.save(); def.overlay(g, lt, info, st); g.restore(); }
    } else { g.save(); def.draw(g, lt, info); g.restore(); }
  } catch (e) { const msg = `${shot.id}@${lt.toFixed(2)}: ${e.message}`; if (!errors.includes(msg) && errors.length < 200) errors.push(msg); console.log('SHOT ERROR', msg, e.stack?.split('\n')[1]);
    g.setTransform(E.PX, 0, 0, E.PX, 0, 0); text(g, 'ERROR ' + msg.slice(0, 90), E.W / 2, E.H / 2, { size: 34, color: '#ff4040', font: FONTS.ui, weight: 900 }); }
}
// motion blur: shot "mb": 3..6 (or {n, shutter}) averages sub-frames across the shutter (0.5 = 180°).
// Use on fast shots only — cost scales with n.
function drawShotMB(buf, shot, lt) {
  const mb = shot.mb ?? 0, n = typeof mb === 'object' ? mb.n : mb;
  if (!n || n < 2) return drawShot(buf, shot, lt);
  const sh = (typeof mb === 'object' && mb.shutter) || 0.5, g = buf.getContext('2d');
  for (let i = 0; i < n; i++) {
    drawShot(bufT, shot, Math.max(0, lt + (i / (n - 1) - 0.5) * sh / E.fps));
    g.setTransform(1, 0, 0, 1, 0, 0); g.filter = 'none'; g.globalCompositeOperation = 'source-over'; g.globalAlpha = 1 / (i + 1); g.drawImage(bufT, 0, 0);
  }
  g.globalAlpha = 1;
}
// transitions designed with both shots: whip/push (real directional blur), iris (mask from a point),
// match (anchor of shot A morphs onto anchor of shot B), smash (hard cut + impact)
function slide(k0, k1, W, H, dir, vertical, n) {           // composite both shots at sub-frame progress samples, averaged
  for (let s = 0; s < n; s++) {
    const kk = ease.inOut(clamp(lerp(k0, k1, n === 1 ? 0.5 : s / (n - 1)))), off = kk * (vertical ? H : W);
    const c = bufC.getContext('2d'); c.setTransform(1, 0, 0, 1, 0, 0); c.globalAlpha = 1; c.fillStyle = '#000'; c.fillRect(0, 0, W, H);
    if (vertical) { c.drawImage(bufB, 0, -dir * off); c.drawImage(bufA, 0, dir * ((vertical ? H : W) - off)); }
    else { c.drawImage(bufB, -dir * off, 0); c.drawImage(bufA, dir * (W - off), 0); }
    mg.globalAlpha = 1 / (s + 1); mg.drawImage(bufC, 0, 0);
  }
  mg.globalAlpha = 1;
}
function drawAround(img, ax, ay, px, py, sc, a = 1) { mg.save(); mg.globalAlpha = a; mg.translate(px, py); mg.scale(sc, sc); mg.translate(-ax, -ay); mg.drawImage(img, 0, 0); mg.restore(); }

const BARS = () => ({ none: 0, wide: V(60, 0), scope: V(138, 170), thin: V(30, 60) });
const barVal = (s) => (typeof (s?.bars ?? E.cfg.bars) === 'number' ? (s.bars ?? E.cfg.bars) : BARS()[s?.bars ?? E.cfg.bars ?? V('wide', 'none')] ?? 0);

window.renderFrame = function (f) {
  const t = f / E.fps, i = shotIndexAt(t), shot = E.shots[i], lt = t - shot.start;
  mannerFrame(f, E.fps);
  drawShotMB(bufA, shot, lt);
  const tr = shot.in || { type: 'cut' }, tdur = tr.dur ?? ({ whip: 0.35, push: 0.6, iris: 0.7, match: 0.6, smash: 0.45 }[tr.type] || 0.5);
  const W = main.width, H = main.height; mg.setTransform(1, 0, 0, 1, 0, 0); mg.globalAlpha = 1; mg.globalCompositeOperation = 'source-over';
  const grade = E.style.grade; mg.filter = grade.filter && grade.filter !== 'none' ? grade.filter : 'none';
  if (tr.type === 'smash' && i > 0 && lt < tdur) {
    const x = lt, amp = 16 * Math.exp(-x * 9) * E.PX, ox = Math.sin(x * 113) * amp * 0.6, oy = Math.cos(x * 92) * amp, sc = 1 + 0.035 * Math.exp(-x * 6);
    mg.fillStyle = '#000'; mg.fillRect(0, 0, W, H); drawAround(bufA, W / 2, H / 2, W / 2 + ox, H / 2 + oy, sc);
    if (lt < 1.5 / E.fps) { mg.filter = 'none'; mg.globalAlpha = 0.85; mg.fillStyle = '#fff'; mg.fillRect(0, 0, W, H); mg.globalAlpha = 1; }
  } else if (tr.type !== 'cut' && i > 0 && lt < tdur) {
    const prev = E.shots[i - 1], k = ease.inOut(lt / tdur); drawShotMB(bufB, prev, t - prev.start);
    if (tr.type === 'fade') { mg.drawImage(bufB, 0, 0); mg.globalAlpha = k; mg.drawImage(bufA, 0, 0); }
    else if (tr.type === 'dip' || tr.type === 'dipWhite') { const c = tr.type === 'dip' ? '#000' : '#fff'; mg.drawImage(k < 0.5 ? bufB : bufA, 0, 0); mg.filter = 'none'; mg.globalAlpha = k < 0.5 ? k * 2 : (1 - k) * 2; mg.fillStyle = c; mg.fillRect(0, 0, W, H); }
    else if (tr.type === 'flash') { mg.drawImage(bufA, 0, 0); mg.filter = 'none'; mg.globalAlpha = (1 - lt / tdur) ** 2; mg.fillStyle = '#fff'; mg.fillRect(0, 0, W, H); }
    else if (tr.type === 'whip' || tr.type === 'push') {   // the camera pans from A to B; blur = real sub-frame motion
      const u = lt / tdur, du = 1 / (tdur * E.fps), sh = tr.shutter ?? (tr.type === 'whip' ? 1 : 0.5);
      slide(u - du * sh / 2, u + du * sh / 2, W, H, tr.dir || 1, !!tr.vertical, tr.type === 'whip' ? 10 : 10);
    }
    else if (tr.type === 'iris') {                         // B opens inside a growing circle from a point of A (eye, lens, window, carton…)
      const [fx, fy] = tr.at || [0.5, 0.5], px = fx * W, py = fy * H, R = Math.hypot(Math.max(px, W - px), Math.max(py, H - py)) * ease.in(clamp(lt / tdur)) * 1.02 + (tr.r0 || 0) * E.PX;
      drawAround(bufB, px, py, px, py, 1 + 0.18 * k);
      mg.save(); mg.beginPath(); mg.arc(px, py, Math.max(0.1, R), 0, Math.PI * 2); mg.clip(); drawAround(bufA, px, py, px, py, 1.12 - 0.12 * k); mg.restore();
      mg.save(); mg.filter = 'none'; mg.strokeStyle = `rgba(255,255,255,${0.35 * (1 - k)})`; mg.lineWidth = 6 * E.PX; mg.beginPath(); mg.arc(px, py, Math.max(0.1, R), 0, Math.PI * 2); mg.stroke(); mg.restore();
    }
    else if (tr.type === 'match') {                        // anchor `from` of A slides/scales onto anchor `to` of B while they cross
      const A = tr.from || [0.5, 0.5], B = tr.to || A, sc = tr.scale || 1.6, ax = A[0] * W, ay = A[1] * H, bx = B[0] * W, by = B[1] * H;
      const px = lerp(ax, bx, k), py = lerp(ay, by, k), m = Math.pow(sc, k), ki = ease.inOut(prog(lt / tdur, 0.2, 0.85));
      mg.fillStyle = '#000'; mg.fillRect(0, 0, W, H);
      if (sc >= 1) { drawAround(bufB, ax, ay, px, py, m, 1); drawAround(bufA, bx, by, px, py, m / sc, ki); }   // the larger layer goes under, so no black borders show
      else { drawAround(bufA, bx, by, px, py, m / sc, 1); drawAround(bufB, ax, ay, px, py, m, 1 - ki); }
    }
    else if (tr.type === 'zoom') { mg.drawImage(bufB, 0, 0); const s = 1.15 - 0.15 * k; mg.globalAlpha = k; mg.translate(W / 2, H / 2); mg.scale(s, s); mg.drawImage(bufA, -W / 2, -H / 2); mg.setTransform(1, 0, 0, 1, 0, 0); }
    else mg.drawImage(bufA, 0, 0);
  } else mg.drawImage(bufA, 0, 0);
  mg.globalAlpha = 1; mg.filter = 'none'; mg.setTransform(1, 0, 0, 1, 0, 0);
  applyGrade(W, H);
  if (grade.tint) { mg.globalCompositeOperation = grade.tint[1]; mg.fillStyle = alpha(grade.tint[0], grade.tint[2]); mg.fillRect(0, 0, W, H); mg.globalCompositeOperation = 'source-over'; }
  if (shot.vignette !== false && grade.vignette > 0) { const v = mg.createRadialGradient(W / 2, H / 2, Math.min(W, H) * 0.35, W / 2, H / 2, Math.max(W, H) * 0.62); v.addColorStop(0, 'rgba(0,0,0,0)'); v.addColorStop(1, `rgba(0,0,0,${grade.vignette})`); mg.fillStyle = v; mg.fillRect(0, 0, W, H); }
  if (grade.grain > 0) { mg.save(); mg.globalAlpha = grade.grain; mg.globalCompositeOperation = 'overlay'; mg.drawImage(grainTiles[f % 4], 0, 0, W, H); mg.restore(); }
  paperPass(mg, W, H);
  mg.setTransform(E.PX, 0, 0, E.PX, 0, 0);
  drawOverlays(mg, t);
  if (E.cfg.captions && shot.captions !== false) captions(mg, t, E.cfg.captionStyle || {});
  const cur = barVal(shot), prevB = i > 0 ? barVal(E.shots[i - 1]) : cur, bar = prevB + (cur - prevB) * ease.inOut(prog(lt, 0, 0.6));
  if (bar > 0) { mg.fillStyle = '#000'; mg.fillRect(0, 0, E.W, bar); mg.fillRect(0, E.H - bar, E.W, bar); }
  const fi = E.cfg.fadeIn ?? 0.5, fo = E.cfg.fadeOut ?? 0.8, dur = window.DURATION, fade = Math.max(fi > 0 ? 1 - t / fi : 0, fo > 0 ? 1 - (dur - t) / fo : 0);
  if (fade > 0) { mg.fillStyle = `rgba(0,0,0,${clamp(fade)})`; mg.fillRect(0, 0, E.W, E.H); }
  if (q.has('debug')) { mg.fillStyle = 'rgba(0,0,0,.6)'; mg.fillRect(0, E.H - 54, E.W, 54); text(mg, `${shot.id}  ${t.toFixed(2)}s  (${lt.toFixed(2)}/${(shot.end - shot.start).toFixed(2)})  ${(shot.line || '').slice(0, 70)}`, 20, E.H - 27, { size: 26, color: '#fff', font: FONTS.ui, weight: 800, align: 'left' }); }
  mg.setTransform(1, 0, 0, 1, 0, 0);
};
boot().catch(e => { window.BOOT_ERROR = e.message + '\n' + e.stack; console.log('BOOT ERROR', e.message); });
