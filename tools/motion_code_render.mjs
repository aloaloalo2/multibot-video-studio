// motion_code_render.mjs: one motion-code clip (content_type "code") drawn by the studio's own /motion-code.html in
// headless Chromium, on a transparent canvas.
//   node tools/motion_code_render.mjs --spec clip.json --out clip.mov            HEVC with alpha (ProRes 4444 off the Mac), every frame
//   node tools/motion_code_render.mjs --spec clip.json --stills 0.5,2,4 --out-dir D   PNG stills with alpha
// clip.json: {code, width, height, fps, duration, words?}. Options: --studio URL, --modules DIR (a node_modules with
// playwright, the Razgon kit's by default). Prints one JSON line {ok, frames|stills, error}; exit 1 on a code error.
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const args = {};
{ const a = process.argv.slice(2); for (let i = 0; i < a.length; i++) if (a[i].startsWith('--')) { const k = a[i].slice(2); args[k] = a[i + 1] && !a[i + 1].startsWith('--') ? a[++i] : true; } }
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const modules = path.resolve(args.modules || path.join(ROOT, 'razgon-2d-studio', 'node_modules'));
const { chromium } = createRequire(path.join(modules, 'noop.js'))('playwright');
const studio = (args.studio || 'http://127.0.0.1:8770').replace(/\/$/, '');
const spec = JSON.parse(fs.readFileSync(args.spec, 'utf8'));
const width = Math.round(spec.width), height = Math.round(spec.height), fps = Number(spec.fps) || 25;
// a margin drawn before and after the clip (spec.pad_head/pad_tail seconds) so a transition that starts it early or carries
// it on past its end reads real frames from this file, never a held copy of it (25 November 2026: copies took 1.4 GB each)
const padHead = Math.max(0, Number(spec.pad_head) || 0), padTail = Math.max(0, Number(spec.pad_tail) || 0);
const frames = Math.max(1, Math.round((Number(spec.duration) + padHead + padTail) * fps));
const say = value => process.stdout.write(JSON.stringify(value) + '\n');

const browser = await chromium.launch({ args: ['--disable-gpu-vsync', '--force-color-profile=srgb'] });
let exitCode = 0;
try {
  const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
  await page.goto(studio + '/motion-code.html');
  const compileError = await page.evaluate(s => window.motionInit(s), spec);
  if (compileError) throw new Error(compileError);
  const shot = () => page.screenshot({ type: 'png', omitBackground: true, clip: { x: 0, y: 0, width, height } });
  if (args.stills) {
    const dir = path.resolve(args['out-dir']); fs.mkdirSync(dir, { recursive: true });
    const stills = [];
    for (const raw of String(args.stills).split(',')) {
      const t = Math.min(Math.max(0, Number(raw)), Math.max(0, Number(spec.duration) - 1 / fps));
      const error = await page.evaluate(x => window.motionAt(x), t);
      if (error) throw new Error(`${t.toFixed(2)} с: ${error}`);
      const file = path.join(dir, `still-${t.toFixed(2)}.png`);
      fs.writeFileSync(file, await shot());
      stills.push(file);
    }
    say({ ok: true, stills });
  } else {
    // each render writes its own part: two renders of one clip at once (a still and the frame agent) renamed one
    // shared part under each other («ENOENT… rename», 25 November 2026)
    const out = path.resolve(args.out), part = `${out}.${process.pid}.part.mov`;
    // HEVC with alpha on the Mac's hardware encoder: about a hundred times lighter than ProRes 4444 (1.3 GB for 11 s
    // before), its alpha read by FFmpeg and AVFoundation alike; ProRes 4444 elsewhere
    const codec = process.platform === 'darwin'
      ? ['-c:v', 'hevc_videotoolbox', '-alpha_quality', '0.9', '-q:v', '70', '-tag:v', 'hvc1', '-pix_fmt', 'bgra']
      : ['-c:v', 'prores_ks', '-profile:v', '4444', '-pix_fmt', 'yuva444p10le', '-vendor', 'apl0'];
    const ff = spawn('ffmpeg', ['-y', '-v', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-i', '-',
      ...codec, '-r', String(fps), part],
      { stdio: ['pipe', 'inherit', 'inherit'] });
    const closed = new Promise((resolve, reject) => ff.on('close', code => (code ? reject(new Error('ffmpeg ' + code)) : resolve())));
    // a failed render removes its own part: each one is up to a gigabyte, and failed renders on a full disk left 11 GB
    // of them behind (25 November 2026)
    ff.stdin.on('error', () => {});
    try {
      for (let f = 0; f < frames; f++) {
        const error = await page.evaluate(x => window.motionAt(x), Math.max(0, f / fps - padHead));
        if (error) { ff.stdin.destroy(); throw new Error(`${(f / fps).toFixed(2)} с: ${error}`); }
        const png = await shot();
        if (!ff.stdin.write(png)) await new Promise(resolve => ff.stdin.once('drain', resolve));
      }
      ff.stdin.end();
      await closed;
      fs.renameSync(part, out);
    } catch (error) {
      try { fs.unlinkSync(part); } catch {}
      throw error;
    }
    say({ ok: true, frames });
  }
} catch (error) {
  say({ ok: false, error: String(error && error.message || error) });
  exitCode = 1;
} finally {
  await browser.close();
}
process.exit(exitCode);
