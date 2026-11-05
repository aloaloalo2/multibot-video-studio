// render.mjs — deterministic frame renderer (headless Chromium -> ffmpeg), parallel workers.
//   node render.mjs --project projects/my-video                      full video  -> build/video_silent.mp4
//   node render.mjs --project P --from 30 --to 45 --scale 0.5         preview a range
//   node render.mjs --project P --sheet                               one still per shot -> build/sheets/*.png
//   node render.mjs --project P --stills 3.5,12,40                    stills at times -> build/stills
//   node render.mjs --project P --styles dusk,midnight,golden,neon --at 3.5,12,40   style comparison grid
//   node render.mjs --project P --text-check [0.25] [--from A --to B]                 every text cut by the frame edge (sampled every 0.25 s) -> build/text_check.json, exit 1 if any
//   node render.mjs --project P --logic-check [0.5] [--from A --to B]                a closer thing drawn under a farther one, text covered by a later picture,
//                                                                                      a picture blown up past its pixels -> build/logic_check.json, exit 1 if any
//   node render.mjs --project P --speed-check [2.5]                                    every take timed in one browser; takes slower than 2.5 x the median -> build/speed_check.json, exit 1 if any
// Options: --workers N  --scale K  --style ID  --debug  --format png|jpeg  --crf 18  --gl auto|gpu|swiftshader  --encoder x264|videotoolbox  --q 75  --out FILE
import http from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const args = {}; { const a = process.argv.slice(2); for (let i = 0; i < a.length; i++) { if (a[i].startsWith('--')) { const k = a[i].slice(2); const v = a[i + 1] && !a[i + 1].startsWith('--') ? a[++i] : true; args[k] = v; } } }
if (!args.project) { console.error('usage: node render.mjs --project projects/<name> [options]'); process.exit(1); }
const PROJECT = path.resolve(args.project);
const BUILD = path.join(PROJECT, 'build'); fs.mkdirSync(BUILD, { recursive: true });
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json', '.woff2': 'font/woff2', '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml' };

function listScenes(dir, base) { let out = []; if (!fs.existsSync(dir)) return out; for (const f of fs.readdirSync(dir).sort()) { const p = path.join(dir, f); if (fs.statSync(p).isDirectory()) out = out.concat(listScenes(p, `${base}/${f}`)); else if (f.endsWith('.js') && !f.startsWith('_')) out.push(`${base}/${f}`); } return out; }
const server = http.createServer((req, res) => {
  const url = decodeURIComponent(req.url.split('?')[0]);
  if (url === '/__manifest') { res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }); return res.end(JSON.stringify(listScenes(path.join(PROJECT, 'scenes'), '/project/scenes'))); }
  const p = url.startsWith('/project/') ? path.join(PROJECT, url.slice(9)) : path.join(ROOT, url);
  if (!(p.startsWith(ROOT) || p.startsWith(PROJECT)) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'Content-Type': TYPES[path.extname(p)] || 'application/octet-stream', 'Cache-Control': 'no-store' }); fs.createReadStream(p).pipe(res);
}).listen(0);
const PORT = server.address().port;
// a Mac draws on its GPU by default: headless Chromium's software drawing (--gl auto) is 4–7 times slower, the same picture (30 October 2026)
const gl = args.gl || (process.platform === 'linux' ? 'swiftshader' : process.platform === 'darwin' ? 'gpu' : 'auto');
const LAUNCH = { args: ['--ignore-gpu-blocklist', '--enable-unsafe-swiftshader', '--disable-dev-shm-usage', ...(gl === 'swiftshader' ? ['--use-angle=swiftshader'] : []), ...(gl === 'gpu' ? ['--enable-gpu', '--use-angle=default'] : [])] };
const FORMAT = args.format === 'jpeg' ? 'jpeg' : 'png';
// a Mac encodes on its hardware H.264 encoder (VideoToolbox): x264 took about 60% of a render's CPU, the hardware one next
// to none, at the same look (PSNR 47.3 dB against lossless, x264 medium 46.7 dB; 30 October 2026). x264 elsewhere.
const ENCODER = args.encoder || (process.platform === 'darwin' && /\bh264_videotoolbox\b/.test(spawnSync('ffmpeg', ['-hide_banner', '-encoders'], { encoding: 'utf8' }).stdout || '') ? 'videotoolbox' : 'x264');
const ENCODE = ENCODER === 'videotoolbox'
  ? ['-c:v', 'h264_videotoolbox', ...(process.arch === 'arm64' ? ['-q:v', String(args.q || 75)] : ['-b:v', '30M']), '-profile:v', 'high']
  : ['-c:v', 'libx264', '-preset', args.preset || 'medium', '-crf', String(args.crf || 18)];
const CFG = JSON.parse(fs.readFileSync(path.join(PROJECT, 'config.json'), 'utf8'));
const FPS = CFG.fps || 24;

async function openPlayer(browser, style) {
  const qs = new URLSearchParams(); if (args.scale) qs.set('scale', args.scale); if (style || args.style) qs.set('style', style || args.style); if (args.debug) qs.set('debug', '1');
  const page = await browser.newPage({ viewport: { width: 640, height: 360 } });
  page.on('pageerror', e => console.log('[pageerror]', e.message));
  page.on('requestfailed', r => console.log('[requestfailed]', r.url(), r.failure()?.errorText || 'unknown'));
  page.on('console', m => { const t = m.text(); if (/ERROR|missing/i.test(t)) console.log('[page]', t); });
  await page.goto(`http://localhost:${PORT}/player.html?${qs}`);
  await page.waitForFunction('window.READY === true || !!window.BOOT_ERROR', null, { timeout: 120000 });
  const boot = await page.evaluate('window.BOOT_ERROR'); if (boot) throw new Error('Player failed to boot: ' + boot);
  const [w, h] = await page.evaluate('window.OUT'); await page.setViewportSize({ width: w, height: h });
  return page;
}
const shot = (page, f) => page.evaluate(i => window.renderFrame(i), f).then(() => page.screenshot({ type: FORMAT, ...(FORMAT === 'jpeg' ? { quality: 94 } : {}) }));
const fmtT = s => `${Math.floor(s / 60)}m${String(Math.round(s % 60)).padStart(2, '0')}s`;

async function renderVideo() {
  const b0 = await chromium.launch(LAUNCH); const p0 = await openPlayer(b0);
  const total = await p0.evaluate('window.TOTAL_FRAMES'), fps = FPS;
  const missing = (await p0.evaluate('window.SHOT_LIST')).filter(s => !s.ok); if (missing.length) console.log(`WARNING: ${missing.length} shots have no scene file yet: ${missing.slice(0, 12).map(s => s.id).join(', ')}${missing.length > 12 ? ' …' : ''}`);
  await b0.close();
  const f0 = Math.max(0, Math.round((+args.from || 0) * fps)), f1 = Math.min(total, args.to ? Math.round(+args.to * fps) : total);
  const W = Math.max(1, Math.min(+(args.workers || Math.max(1, Math.min(8, Math.floor(os.cpus().length / 2)))), Math.ceil((f1 - f0) / 24)));
  const partsDir = path.join(BUILD, `parts-${process.pid}`); fs.rmSync(partsDir, { recursive: true, force: true }); fs.mkdirSync(partsDir, { recursive: true });   // per run: two renders of one project never clobber each other's parts
  process.on('exit', () => fs.rmSync(partsDir, { recursive: true, force: true }));   // the parts only feed the concat below; on success or failure they are left behind otherwise
  const chunk = Math.ceil((f1 - f0) / W); let done = 0; const t0 = Date.now(); const errs = new Set();
  console.log(`Rendering frames ${f0}-${f1} (${((f1 - f0) / fps).toFixed(1)} s) with ${W} worker(s)…`);
  const work = async (k) => {
    const a = f0 + k * chunk, b = Math.min(f1, a + chunk); if (a >= b) return null;
    const browser = await chromium.launch(LAUNCH); const page = await openPlayer(browser);
    const out = path.join(partsDir, `part_${String(k).padStart(3, '0')}.mp4`);
    const ff = spawn('ffmpeg', ['-y', '-v', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-i', '-', ...ENCODE, '-pix_fmt', 'yuv420p', '-r', String(fps), out], { stdio: ['pipe', 'inherit', 'inherit'] });
    for (let f = a; f < b; f++) {
      const img = await shot(page, f); if (!ff.stdin.write(img)) await new Promise(r => ff.stdin.once('drain', r)); done++;
      if (done % 48 === 0) { const el = (Date.now() - t0) / 1000, eta = (el / done) * (f1 - f0 - done); process.stdout.write(`  ${done}/${f1 - f0} frames  ${(done / el).toFixed(2)} fps  elapsed ${fmtT(el)}  eta ${fmtT(eta)}\n`); }
    }
    (await page.evaluate('window.ERRORS')).forEach(e => errs.add(e));
    ff.stdin.end(); await new Promise(r => ff.on('close', r)); await browser.close(); return out;
  };
  const parts = (await Promise.all([...Array(W)].map((_, k) => work(k)))).filter(Boolean);
  const list = path.join(partsDir, 'list.txt'); fs.writeFileSync(list, parts.map(p => `file '${p.replace(/\\/g, '/').replace(/'/g, "'\\''")}'`).join('\n'));
  const out = path.resolve(args.out || path.join(BUILD, args.from || args.to ? 'preview.mp4' : 'video_silent.mp4'));
  await new Promise((res, rej) => spawn('ffmpeg', ['-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', list, '-c', 'copy', '-movflags', '+faststart', out], { stdio: 'inherit' }).on('close', c => (c ? rej(new Error('concat failed')) : res())));
  if (errs.size) { console.log(`\n${errs.size} shot error(s):`); [...errs].slice(0, 40).forEach(e => console.log('  ' + e)); }
  console.log(`\nDone: ${out}  (${fmtT((Date.now() - t0) / 1000)})`);
}
// grid of labelled images, laid out by the browser (works on every OS)
async function contactSheet(browser, items, outFile, cols = 4, cellW = 480) {
  const page = await browser.newPage({ viewport: { width: cols * (cellW + 12) + 12, height: 400 } });
  const html = `<html><body style="margin:0;background:#111;font:600 15px sans-serif;color:#eee"><div style="display:grid;grid-template-columns:repeat(${cols},${cellW}px);gap:12px;padding:12px">${items.map(it => `<div><img src="data:image/${FORMAT};base64,${it.img.toString('base64')}" style="width:${cellW}px;display:block;border-radius:4px"><div style="padding:5px 2px">${it.label.replace(/</g, '&lt;')}</div></div>`).join('')}</div></body></html>`;
  await page.setContent(html); await page.screenshot({ path: outFile, fullPage: true }); await page.close();
}
async function renderStills() {
  const browser = await chromium.launch(LAUNCH); const styles = args.styles ? String(args.styles).split(',') : [args.style || null];
  // --dir build/<name>: a folder of its own, so several reviewers rendering stills at once never empty each other's
  const dir = args.dir ? path.resolve(PROJECT, String(args.dir)) : path.join(BUILD, args.styles ? 'styles' : args.sheet ? 'sheets' : 'stills'); fs.rmSync(dir, { recursive: true, force: true }); fs.mkdirSync(dir, { recursive: true });
  const all = [];
  for (const st of styles) {
    const page = await openPlayer(browser, st); const fps = FPS;
    let targets;
    if (args.sheet) targets = (await page.evaluate('window.SHOT_LIST')).map(s => ({ t: s.start + (s.end - s.start) * 0.45, label: `${s.id}  ${s.start.toFixed(1)}s${s.ok ? '' : '  (MISSING)'}` }));
    else targets = String(args.stills || args.at || '1').split(',').map(Number).map(t => ({ t, label: `${t}s` }));
    for (const tg of targets) { const img = await shot(page, Math.round(tg.t * fps)); const name = `${st ? st + '_' : ''}${tg.label.split(' ')[0].replace(/[^\w.]/g, '')}_${tg.t.toFixed(2)}.${FORMAT}`; fs.writeFileSync(path.join(dir, name), img); all.push({ img, label: `${st ? `[${st}] ` : ''}${tg.label}`, st }); }
    (await page.evaluate('window.ERRORS')).forEach(e => console.log('  shot error:', e)); await page.close();
  }
  if (args.styles) { const n = all.length / styles.length; await contactSheet(browser, all, path.join(dir, 'style_grid.png'), n, 420); }
  else { const per = 24; for (let i = 0; i < all.length; i += per) await contactSheet(browser, all.slice(i, i + per), path.join(dir, `sheet_${String(i / per + 1).padStart(2, '0')}.png`), 4, 440); }
  await browser.close(); console.log(`Wrote ${all.length} stills + contact sheet(s) to ${dir}`);
}
// Text must never be cut by the frame edge (a direct rule of the user, 29 Oct 2026): every visible line drawn with text()
// is logged with its on-canvas box; a line partly outside the frame is a FAIL. Fully off-screen text (still entering) and
// lines drawn with { offscreen: true } are ignored.
// a scene that does not load or throws draws nothing to check: a check that passed over it would be a false OK
// (08: a broken e132 passed the text and logic checks). Both checks fail on any shot error.
async function shotErrors(page) {
  const errs = (await page.evaluate('window.ERRORS || []').catch(() => [])) || [];
  if (errs.length) { console.log(`Shot errors (${errs.length}): the check cannot see these shots, fix them first:`); [...new Set(errs)].slice(0, 20).forEach((e) => console.log('  ' + e)); process.exitCode = 1; }
  return errs.length;
}
async function textCheck() {
  const browser = await chromium.launch(LAUNCH); const page = await openPlayer(browser); const fps = FPS;
  const total = await page.evaluate('window.TOTAL_FRAMES'), step = Math.max(1, Math.round((+args['text-check'] > 0 ? +args['text-check'] : 0.25) * fps));
  const hits = [];
  const fa = Math.max(0, Math.round((+args.from || 0) * fps)), fb = Math.min(total, args.to ? Math.round(+args.to * fps) : total);
  for (let f = fa; f < fb; f += step) {
    const log = await page.evaluate((i) => { window.TEXT_LOG = []; window.renderFrame(i); const l = window.TEXT_LOG; window.TEXT_LOG = null; return l; }, f);
    const dims = new Map(); log.forEach((b) => dims.set(`${b.W}x${b.H}`, (dims.get(`${b.W}x${b.H}`) || 0) + 1));
    for (const b of log) {
      const pad = 1, visible = b.x1 > 0 && b.x0 < b.W && b.y1 > 0 && b.y0 < b.H, cut = b.x0 < -pad || b.y0 < -pad || b.x1 > b.W + pad || b.y1 > b.H + pad;
      if (visible && cut && b.str.trim()) hits.push({ t: +(f / fps).toFixed(2), str: b.str, box: [b.x0, b.y0, b.x1, b.y1].map(Math.round), canvas: [b.W, b.H] });
    }
  }
  const broken = await shotErrors(page);
  await browser.close();
  const runs = []; for (const h of hits) { const r = runs.find((x) => x.str === h.str && h.t - x.to <= step / fps + 1e-6); if (r) { r.to = h.t; r.last = h.box; } else runs.push({ str: h.str, from: h.t, to: h.t, box: h.box, last: h.box, canvas: h.canvas }); }
  // text that crosses the edge while the camera travels past it is a normal pan; text that stays cut is the bug:
  // FAIL when it stays cut for a second or longer
  runs.forEach((r) => { r.fail = r.to - r.from + step / fps >= 1.0; });
  fs.writeFileSync(path.join(BUILD, 'text_check.json'), JSON.stringify(runs, null, 1));
  const fails = runs.filter((r) => r.fail);
  console.log(`Text check: ${runs.length - fails.length} text(s) only pass the edge during camera moves (${Math.ceil((fb - fa) / step)} frames sampled)`);
  if (!fails.length) { console.log(broken ? 'Text check: FAIL, shots with errors were not checked' : 'Text check: OK, no text is held cut by the frame'); return; }
  console.log(`Text check: FAIL, ${fails.length} text(s) held cut by the frame edge:`);
  fails.forEach((r) => console.log(`  ${r.from.toFixed(2)}–${r.to.toFixed(2)} s  "${r.str}"  box ${r.box.join(',')} on ${r.canvas.join('x')}`));
  process.exitCode = 1;
}
// The scene logic check (user, 5 November 2026: «людина сквозь машину не може проходити», «текст… не там, де потрібно»,
// «асети… якість портять, якщо їх розтягнути»): every picture, figure and line of text of a sampled frame is logged in
// drawing order with its box on the canvas, and three things are flagged, without a single image for anyone to look at:
//  - depth: a thing standing closer to the camera (its foot line lower on the screen) drawn UNDER a farther thing that
//    overlaps it, as a person behind a car's body with his legs in front of it; a thing resting on another (a teletype on
//    a desk, a sleeper on a bed) is not flagged, nor are small held props;
//  - text covered: a line of text under a later opaque picture or figure (a date under a lamp);
//  - blown up: a picture drawn more than 1.6 times its own pixels at the output size (a 400 px viaduct over the whole
//    frame goes soft): such props are drawn one or two to a sheet at full size.
// Depth or covered text held 1 s or more is a FAIL (a thing passing another for an instant is not), a blown-up picture 0.5 s.
async function logicCheck() {
  const browser = await chromium.launch(LAUNCH); const page = await openPlayer(browser); const fps = FPS;
  await page.evaluate(() => {
    const proto = CanvasRenderingContext2D.prototype, orig = proto.drawImage, main = document.getElementById('main') || document.querySelector('canvas');
    window.__LOGIC_MAIN = main;
    // a filled rectangle on the frame (a paper slip, a screen, a sign board drawn in code) can carry text: logged as a host
    const fillRect0 = proto.fillRect;
    proto.fillRect = function (x, y, w, h) {
      try {
        if (window.DRAW_LOG && (this.canvas === main || (this.canvas.width === main.width && this.canvas.height === main.height)) && this.globalAlpha > 0.6 && Math.abs(w * h) > 400) {
          const T = this.getTransform(), xs = [x, x + w, x, x + w], ys = [y, y, y + h, y + h];
          const px = xs.map((v, i) => T.a * v + T.c * ys[i] + T.e), py = xs.map((v, i) => T.b * v + T.d * ys[i] + T.f);
          window.DRAW_LOG.push({ k: 'host', name: 'shape', x0: Math.min(...px), x1: Math.max(...px), y0: Math.min(...py), y1: Math.max(...py), a: this.globalAlpha, layer: window.__LAYER ?? null, W: main.width, H: main.height });
        }
      } catch (e) { /* the check never breaks a frame */ }
      return fillRect0.call(this, x, y, w, h);
    };
    proto.drawImage = function (img, ...a) {
      try {
        const name = img && img.src ? decodeURIComponent(img.src.split('/').pop().replace(/\.(png|jpe?g|webp)(\?.*)?$/i, '')) : null;
        const sw = a.length === 8 ? a[2] : (img.naturalWidth || img.width), sh = a.length === 8 ? a[3] : (img.naturalHeight || img.height);
        const [dx, dy, dw, dh] = a.length === 8 ? a.slice(4) : a.length === 4 ? a : [a[0], a[1], img.naturalWidth || img.width, img.naturalHeight || img.height];
        if (this.canvas !== main && !(this.canvas.width === main.width && this.canvas.height === main.height)) {
          // a cached copy of a prop (shade, flip): remember which picture it holds and how much it already enlarged it
          if (name && sh) this.canvas.__src = { name, k: (Math.abs(dh) * Math.hypot(this.getTransform().b, this.getTransform().d)) / sh };
          else if (img.__src) { this.canvas.__src = img.__src; this.canvas.__soft = !!(img.__blur || img.__soft); }
        } else if (window.DRAW_LOG && !img.__text && !img.__blur && !img.__soft && this.globalAlpha > 0.3) {
          const T = this.getTransform(), xs = [dx, dx + dw, dx, dx + dw], ys = [dy, dy, dy + dh, dy + dh];
          const px = xs.map((v, i) => T.a * v + T.c * ys[i] + T.e), py = xs.map((v, i) => T.b * v + T.d * ys[i] + T.f);
          const screenH = Math.abs(dh) * Math.hypot(T.b, T.d), src = name ? { name, k: 1 } : img.__src;
          const blow = src && sh ? (screenH / sh) * src.k * (window.OUT[1] / main.height) : 0;
          window.DRAW_LOG.push({ k: 'img', name: src ? src.name : 'canvas', x0: Math.min(...px), x1: Math.max(...px), y0: Math.min(...py), y1: Math.max(...py), base: Math.max(...py), blow, a: this.globalAlpha, layer: window.__LAYER ?? null, W: main.width, H: main.height });
        }
      } catch (e) { /* the check never breaks a draw */ }
      return orig.call(this, img, ...a);
    };
  });
  const total = await page.evaluate('window.TOTAL_FRAMES'), step = Math.max(1, Math.round((+args['logic-check'] > 0 ? +args['logic-check'] : 0.5) * fps));
  const fa = Math.max(0, Math.round((+args.from || 0) * fps)), fb = Math.min(total, args.to ? Math.round(+args.to * fps) : total);
  const hits = [];
  // a transition draws two shots in one frame (their things are not one room): leave 0.6 s on either side of a cut out
  let cuts = []; try { const sj = JSON.parse(fs.readFileSync(path.join(PROJECT, 'story', 'shots.json'), 'utf8')); cuts = (sj.shots || sj).map((x) => +x.start).filter((x) => x > 0); } catch (e) { /* no story: every frame */ }
  const nearCut = (t) => cuts.some((c) => Math.abs(c - t) < 0.6);
  const area = (b) => Math.max(0, b.x1 - b.x0) * Math.max(0, b.y1 - b.y0);
  const inter = (a, b) => Math.max(0, Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0)) * Math.max(0, Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0));
  for (let f = fa; f < fb; f += step) {
    const log = await page.evaluate((i) => { window.DRAW_LOG = []; window.renderFrame(i); const l = window.DRAW_LOG; window.DRAW_LOG = null; return l; }, f);
    const t = +(f / fps).toFixed(2);
    if (!log.length || nearCut(t)) continue;
    const sized = log.find((b) => b.W && b.H); if (!sized) continue;
    const H = sized.H, W = sized.W, frame = W * H;
    // things that stand on the ground of a layer: not screen overlays (a phone held up to the viewer), not what hangs on a wall
    const WALL = /curtain|poster|frame|clock|calendar|window|painting|picture|map|board|sign|shelf|bookcase|sky|cloud|moon|sun|mountain|banner/i;
    const things = log.map((b, i) => ({ ...b, i })).filter((b) => b.k !== 'text' && b.k !== 'host' && b.layer != null && !WALL.test(b.name) && area(b) < frame * 0.6 && (b.y1 - b.y0) > H * 0.07 && b.x1 > 0 && b.x0 < W && b.y1 > 0 && b.y0 < H);
    for (const b of log) if (b.k === 'img' && b.blow > 1.6 && (b.y1 - b.y0) > H * 0.1 && b.x1 > 0 && b.x0 < W && b.y1 > 0 && b.y0 < H)
      hits.push({ kind: 'blown up', key: `blown up: ${b.name}`, t, text: `${b.name} drawn ${b.blow.toFixed(1)}× its pixels` });
    for (let a = 0; a < things.length; a++) for (let c = a + 1; c < things.length; c++) {
      const A = things[a], B = things[c];             // A drawn first, B over it
      const ov = inter(A, B); if (ov < Math.min(area(A), area(B)) * 0.15) continue;
      const hA = A.y1 - A.y0, tol = H * 0.025;
      if (A.layer !== B.layer) continue;                // only inside one layer
      if (!(A.base > B.base + tol)) continue;          // B is not farther than A
      if (B.base <= A.y0 + hA * 0.45) continue;        // B rests on A (on its top) or hangs above it
      const wB = B.x1 - B.x0, inside = Math.max(0, Math.min(A.x1, B.x1) - Math.max(A.x0, B.x0)) / (wB || 1);
      if (inside >= 0.8 && B.base < A.base) continue;   // B lies on A (a duvet on a bed, a book on a table)
      if (A.lying || B.lying) continue;
      // a small thing over most of a person is held by that person (an umbrella, a radio, a box, a spade): no depth error
      const held = (P, Q) => { if (P.k !== 'fig' || Q.k === 'fig' || (Q.y1 - Q.y0) > (P.y1 - P.y0) * 0.6) return false; const w = P.x1 - P.x0, cx = (Q.x0 + Q.x1) / 2, cy = (Q.y0 + Q.y1) / 2;
        return cx > P.x0 - w * 0.35 && cx < P.x1 + w * 0.35 && cy > P.y0 && cy < P.base; };
      if (held(A, B) || held(B, A)) continue;
      hits.push({ kind: 'depth', key: `depth: ${B.name} over ${A.name}`, t, text: `${B.name} (foot ${Math.round(B.base)}) drawn over the closer ${A.name} (foot ${Math.round(A.base)})` });
    }
    const texts = log.map((b, i) => ({ ...b, i })).filter((b) => b.k === 'text' && b.x1 > 0 && b.x0 < W && b.y1 > 0 && b.y0 < H);
    for (const tx of texts) for (const o of log.slice(tx.i + 1)) {
      if (o.k === 'text' || o.k === 'host' || o.a < 0.6 || area(o) >= frame * 0.6) continue;
      if (inter(tx, o) > area(tx) * 0.3) { hits.push({ kind: 'text covered', key: `text covered: "${tx.str}" by ${o.name}`, t, text: `"${tx.str}" under ${o.name}` }); break; }
    }
    // text half on a thing and half off it: a heading sticking out of its page, a caption lying across the edge of a
    // painting or a window. Text that belongs to a thing goes on it whole (textOn), a caption goes on bare wall or sky
    // a text lying whole on something drawn before it (a phone's screen, a paper slip, a page) has its host and is fine
    for (const tx of texts) {
      if ((tx.a ?? 1) < 0.5) continue;
      const under = log.slice(0, tx.i).filter((o) => (o.k === 'img' || o.k === 'host') && o.a >= 0.6 && area(o) < frame * 0.6);
      if (under.some((o) => inter(tx, o) / (area(tx) || 1) >= 0.8)) continue;
      let worst = null, wf = 0;
      for (const o of under) {
        if (o.k !== 'img' || (o.y1 - o.y0) < H * 0.06 || (tx.layer != null && o.layer !== tx.layer)) continue;   // a caption over the frame (no layer) against anything
        const f = inter(tx, o) / (area(tx) || 1);
        if (f > 0.2 && f < 0.8 && f > wf) { worst = o; wf = f; }
      }
      if (worst) hits.push({ kind: 'text half on', key: `text half on: "${tx.str}" across ${worst.name}`, t, text: `"${tx.str}" lies ${Math.round(wf * 100)}% on ${worst.name}, the rest off it` });
    }
  }
  const broken = await shotErrors(page);
  await browser.close();
  const runs = []; for (const h of hits) { const r = runs.find((x) => x.key === h.key && h.t - x.to <= step / fps + 1e-6); if (r) r.to = h.t; else runs.push({ ...h, from: h.t, to: h.t }); }
  // depth and covered text held for a second or more (an instant at a cut inside a shot is not a scene); a blown-up picture
  // is soft for as long as it shows
  runs.forEach((r) => { r.fail = r.to - r.from + step / fps >= (r.kind === 'blown up' ? 0.5 : 1.0); });
  fs.writeFileSync(path.join(BUILD, 'logic_check.json'), JSON.stringify(runs, null, 1));
  const fails = runs.filter((r) => r.fail);
  console.log(`Logic check: ${Math.ceil((fb - fa) / step)} frames sampled, ${fails.length} finding(s)`);
  if (!fails.length) { console.log(broken ? 'Logic check: FAIL, shots with errors were not checked' : 'Logic check: OK, no closer thing under a farther one, no covered text, no blown-up picture'); return; }
  for (const kind of ['depth', 'text covered', 'text half on', 'blown up']) {
    const list = fails.filter((r) => r.kind === kind); if (!list.length) continue;
    console.log(`Logic check: FAIL, ${kind} (${list.length}):`);
    list.slice(0, 40).forEach((r) => console.log(`  ${r.from.toFixed(1)}–${r.to.toFixed(1)} s  ${r.text}`));
  }
  process.exitCode = 1;
}
// every take timed on its own: two frames at 20, 50 and 80 % of it, drawn and captured in one browser. A take far slower than
// the others puts a filter on each of many draws (g.filter = 'blur(...)' over a whole layer of shapes, a shade filter on 365
// props): in 06 Fast Food such takes cost 4-6 times a normal frame (31 October 2026). Blur a group once with blurLayer();
// pic(..., { shade }) keeps a darkened copy of the prop.
async function speedCheck() {
  const browser = await chromium.launch(LAUNCH); const page = await openPlayer(browser); const fps = FPS;
  const factor = typeof args['speed-check'] === 'string' && +args['speed-check'] > 0 ? +args['speed-check'] : 2.5, rows = [];
  // timed with the export's own capture (JPEG): a PNG screenshot alone takes ~380 ms at 1080p and hides the drawing
  const timed = (f) => page.evaluate((i) => window.renderFrame(i), f).then(() => page.screenshot({ type: 'jpeg', quality: 94 }));
  for (const s of await page.evaluate('window.SHOT_LIST')) {
    let ms = 0, n = 0;
    for (const u of [0.2, 0.5, 0.8]) {
      const f = Math.round((s.start + (s.end - s.start) * u) * fps); await timed(f - 1);   // the first draw of a place loads its pictures
      const t0 = Date.now(); await timed(f); await timed(f + 1); ms += Date.now() - t0; n += 2;
    }
    rows.push({ id: s.id, start: +s.start.toFixed(2), end: +s.end.toFixed(2), ms: Math.round(ms / n) });
  }
  await browser.close();
  const sorted = rows.map((r) => r.ms).sort((a, b) => a - b), median = sorted[Math.floor(sorted.length / 2)] || 0, limit = Math.max(100, Math.round(median * factor));
  const slow = rows.filter((r) => r.ms > limit).sort((a, b) => b.ms - a.ms);
  fs.writeFileSync(path.join(BUILD, 'speed_check.json'), JSON.stringify({ median, limit, slow, takes: rows }, null, 1));
  console.log(`Speed check: ${rows.length} takes, median ${median} ms a frame, limit ${limit} ms`);
  if (!slow.length) { console.log('OK, no take is far slower than the rest'); return; }
  console.log(`FAIL, ${slow.length} take(s) far slower than the rest:`);
  for (const r of slow) console.log(`  ${r.id}  ${r.start}-${r.end} s  ${r.ms} ms a frame`);
  process.exitCode = 1;
}
try { if (args['logic-check']) await logicCheck(); else if (args['text-check']) await textCheck(); else if (args['speed-check']) await speedCheck(); else if (args.sheet || args.stills || args.styles) await renderStills(); else await renderVideo(); }
catch (e) { console.error('RENDER FAILED:', e.message); process.exitCode = 1; }
finally { server.close(); }
