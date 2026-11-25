import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../../../../frontend/fonts/', import.meta.url));
const prefix = '/studio-fonts/';

export function serveStudioFont(url, response) {
  if (!url.startsWith(prefix)) return false;
  const name = url.slice(prefix.length);
  const type = name === 'catalog.json' ? 'application/json'
    : /^[a-z0-9-]+\.ttf$/.test(name) ? 'font/ttf' : null;
  const file = type && path.join(root, name);
  if (!file || !fs.statSync(file, {throwIfNoEntry:false})?.isFile()) {
    response.writeHead(404);
    response.end();
  } else {
    response.writeHead(200, {'Content-Type':type, 'Cache-Control':'no-store'});
    fs.createReadStream(file).pipe(response);
  }
  return true;
}
