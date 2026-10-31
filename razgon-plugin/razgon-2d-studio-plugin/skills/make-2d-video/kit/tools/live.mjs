// tools/live.mjs — watch a project live in the browser, no render: the same player draws every frame in real time
// under the voiceover, with a scrubbable timeline. Any change to scenes, story, config or the engine reloads the page
// at the same moment.
//   node tools/live.mjs --project projects/<slug> [--port 8781]      → http://127.0.0.1:<port>/live.html
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const args = {}; { const a = process.argv.slice(2); for (let i = 0; i < a.length; i++) { if (a[i].startsWith('--')) { const k = a[i].slice(2); const v = a[i + 1] && !a[i + 1].startsWith('--') ? a[++i] : true; args[k] = v; } } }
if (!args.project) { console.error('usage: node tools/live.mjs --project projects/<name> [--port N]'); process.exit(1); }
const PROJECT = path.resolve(ROOT, args.project), PORT = +(args.port || 8781);
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json', '.woff2': 'font/woff2', '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml', '.wav': 'audio/wav', '.mp3': 'audio/mpeg', '.m4a': 'audio/mp4' };
function listScenes(dir, base) { let out = []; if (!fs.existsSync(dir)) return out; for (const f of fs.readdirSync(dir).sort()) { const p = path.join(dir, f); if (fs.statSync(p).isDirectory()) out = out.concat(listScenes(p, `${base}/${f}`)); else if (f.endsWith('.js') && !f.startsWith('_')) out.push(`${base}/${f}`); } return out; }

// change notifications (server-sent events), debounced so a burst of file writes reloads once
const clients = new Set(); let timer = null;
const notify = (why) => { clearTimeout(timer); timer = setTimeout(() => { for (const res of clients) res.write(`data: ${JSON.stringify({ reload: why })}\n\n`); }, 350); };
for (const dir of [path.join(PROJECT, 'scenes'), path.join(PROJECT, 'story'), path.join(ROOT, 'engine')]) { try { fs.watch(dir, { recursive: true }, (_, f) => notify(f || dir)); } catch {} }
try { fs.watch(path.join(PROJECT, 'config.json'), () => notify('config.json')); } catch {}

http.createServer((req, res) => {
  const url = decodeURIComponent(req.url.split('?')[0]);
  if (url === '/__health') { res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }); return res.end(JSON.stringify({ service: 'razgon-live', project: PROJECT })); }
  if (url === '/__events') { res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store', Connection: 'keep-alive' }); res.write(': ok\n\n'); clients.add(res); req.on('close', () => clients.delete(res)); return; }
  if (url === '/__manifest') { res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }); return res.end(JSON.stringify(listScenes(path.join(PROJECT, 'scenes'), '/project/scenes'))); }
  const p = url.startsWith('/project/') ? path.join(PROJECT, url.slice(9)) : path.join(ROOT, url === '/' ? '/live.html' : url);
  if (!(p.startsWith(ROOT) || p.startsWith(PROJECT)) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); return res.end(); }
  const size = fs.statSync(p).size, type = TYPES[path.extname(p).toLowerCase()] || 'application/octet-stream', range = req.headers.range;
  if (range && /^bytes=/.test(range)) {   // audio seeking needs ranges
    const [s, e] = range.slice(6).split('-'), start = +s || 0, end = e ? +e : size - 1;
    res.writeHead(206, { 'Content-Type': type, 'Content-Range': `bytes ${start}-${end}/${size}`, 'Accept-Ranges': 'bytes', 'Content-Length': end - start + 1, 'Cache-Control': 'no-store' });
    return fs.createReadStream(p, { start, end }).pipe(res);
  }
  res.writeHead(200, { 'Content-Type': type, 'Content-Length': size, 'Accept-Ranges': 'bytes', 'Cache-Control': 'no-store' }); fs.createReadStream(p).pipe(res);
}).listen(PORT, '127.0.0.1', () => console.log(`razgon live: http://127.0.0.1:${PORT}/live.html  (${PROJECT})`));
