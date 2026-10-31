#!/usr/bin/env python3
"""Private local Pixabay search page for the YouTube workspace."""

import html
import secrets
import unicodedata
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from pixabay import ROOT, api_get, download


PORT = 8765
TOKEN = secrets.token_urlsafe(24)
CHANNELS = {
    "common": "Загальна папка",
    "alexey": "Олексій Горбунов",
    "valentin": "Валентин Чичваркін",
    "karl": "Karl Brenners Werkstatt",
    "wade": "Wade Corbin",
}


def folder_for(channel):
    if channel == "common":
        # inside the studio: the YOUTUBE folder keeps only the channels (user, 31 October 2026)
        return Path(__file__).resolve().parents[1] / "Pixabay"
    names = {
        "alexey": "Алексей Горбунов",
        "valentin": "Валентин Чичваркин",
        "karl": "Karl Brenners Werkstatt",
        "wade": "Wade Corbin",
    }
    wanted = names.get(channel)
    if not wanted:
        raise ValueError("Оберіть папку каналу")
    folder = next(
        (path for path in ROOT.iterdir()
         if path.is_dir() and unicodedata.normalize("NFC", path.name) == wanted),
        None,
    )
    if folder is None:
        raise ValueError("Папку каналу не знайдено")
    return folder / "Pixabay"


def e(value):
    return html.escape(str(value or ""), quote=True)


def search_form(query, kind):
    image_selected = "selected" if kind == "image" else ""
    video_selected = "selected" if kind == "video" else ""
    return f"""
    <form class="search" method="get">
      <input name="q" value="{e(query)}" maxlength="100" placeholder="Наприклад: car engine, walking, coffee" autofocus required>
      <select name="kind" aria-label="Тип матеріалу">
        <option value="video" {video_selected}>Відео</option>
        <option value="image" {image_selected}>Фото</option>
      </select>
      <button type="submit">Знайти</button>
    </form>"""


def card(hit, kind, query):
    media_id = hit.get("id")
    if not isinstance(media_id, int):
        return ""
    if kind == "video":
        versions = hit.get("videos", {})
        best = versions.get("large") or {}
        quality = "large" if best.get("url") and best.get("width", 0) else "medium"
        selected = versions.get(quality) or {}
        preview = selected.get("thumbnail", "")
        size = f"{selected.get('width', '?')} × {selected.get('height', '?')} · {hit.get('duration', '?')} с"
    else:
        quality = "large"
        preview = hit.get("webformatURL") or hit.get("previewURL") or ""
        size = "Фото · до 1280 px через звичайний API"
    source = hit.get("pageURL", "")
    if urlsplit(source).hostname != "pixabay.com":
        source = "https://pixabay.com/"
    options = "".join(f'<option value="{e(key)}">{e(label)}</option>' for key, label in CHANNELS.items())
    return f"""
    <article class="card">
      <a href="{e(source)}" target="_blank" rel="noopener noreferrer"><img src="{e(preview)}" loading="lazy" alt="{e(hit.get('tags'))}"></a>
      <div class="body">
        <div class="tags">{e(hit.get('tags', ''))}</div>
        <div class="meta">{e(size)} · автор: {e(hit.get('user', 'Pixabay'))}</div>
        <a class="source" href="{e(source)}" target="_blank" rel="noopener noreferrer">Переглянути на Pixabay ↗</a>
        <form method="post" action="/download">
          <input type="hidden" name="token" value="{e(TOKEN)}">
          <input type="hidden" name="kind" value="{e(kind)}">
          <input type="hidden" name="id" value="{media_id}">
          <input type="hidden" name="quality" value="{quality}">
          <input type="hidden" name="q" value="{e(query)}">
          <select name="channel" aria-label="Куди зберегти">{options}</select>
          <button type="submit" class="save">Зберегти файл</button>
        </form>
      </div>
    </article>"""


def page(query="", kind="video", notice="", error=""):
    cards = ""
    if query:
        try:
            if len(query) > 100:
                raise ValueError("Запит завеликий")
            result = api_get(kind, q=query, per_page=18, safesearch="true")
            cards = "".join(card(hit, kind, query) for hit in result.get("hits", []))
            if not cards:
                cards = '<p class="empty">Нічого не знайшлося. Спробуй коротший запит англійською.</p>'
        except (RuntimeError, ValueError) as exc:
            error = str(exc)
    message = f'<div class="notice">{e(notice)}</div>' if notice else ""
    problem = f'<div class="error">{e(error)}</div>' if error else ""
    return f"""<!doctype html>
<html lang="uk"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Пошук Pixabay</title><style>
  *{{box-sizing:border-box}} body{{margin:0;background:#f6f7fa;color:#20242d;font:16px -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif}}
  header{{background:#1f2532;color:white;padding:34px max(24px,calc((100vw - 1160px)/2)) 44px}}
  h1{{font-size:30px;margin:0 0 8px}} header p{{margin:0 0 24px;color:#cfd5df}}
  .search{{display:flex;gap:10px;max-width:1000px}} input,select,button{{font:inherit;border-radius:10px;border:1px solid #d9dde5;padding:12px}}
  .search input{{flex:1;min-width:150px}} button{{background:#f3a739;color:#1e2632;font-weight:700;border:0;cursor:pointer}}
  button:hover{{filter:brightness(.95)}} main{{max-width:1208px;padding:25px 24px;margin:auto}}
  .hint{{color:#566273;font-size:14px;margin:0 0 22px}} .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:18px}}
  .card{{background:white;border-radius:15px;overflow:hidden;box-shadow:0 3px 15px #1f253211}}
  .card img{{width:100%;height:190px;object-fit:cover;background:#e3e6eb;display:block}} .body{{padding:14px}}
  .tags{{font-weight:600;min-height:48px;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
  .meta{{color:#677385;font-size:13px;margin:9px 0}} .source{{display:inline-block;color:#245a9b;font-size:13px;margin-bottom:12px}}
  .body form{{display:grid;gap:8px}} .body select{{width:100%}} .save{{width:100%}}
  .notice,.error{{padding:13px 16px;border-radius:10px;margin-bottom:18px}} .notice{{background:#e1f3e5}} .error{{background:#ffe7e3}}
  footer{{max-width:1208px;margin:28px auto;padding:0 24px 30px;color:#697687;font-size:13px}} footer a{{color:inherit}}
  @media(max-width:620px){{.search{{flex-wrap:wrap}} .search input{{width:100%;flex:auto}}}}
</style></head><body>
<header><h1>Пошук Pixabay</h1><p>Фото й відео для твоїх роликів. Ключ працює локально і не показується в браузері.</p>{search_form(query, kind)}</header>
<main>{message}{problem}<p class="hint">Вибери кадр, переглянь його на Pixabay і збережи в потрібний канал. Завантажений файл залишиться кандидатом до перевірки в монтажі.</p><div class="grid">{cards}</div></main>
<footer>Результати надає <a href="https://pixabay.com/" target="_blank" rel="noopener noreferrer">Pixabay</a>. Умови використання: <a href="https://pixabay.com/service/terms/" target="_blank" rel="noopener noreferrer">Pixabay Content License</a>.</footer>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format_string, *args):
        pass

    def respond(self, body, status=200):
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path != "/":
            self.respond("Сторінку не знайдено", 404)
            return
        params = parse_qs(parsed.query)
        query = params.get("q", [""])[0].strip()
        kind = params.get("kind", ["video"])[0]
        if kind not in {"video", "image"}:
            kind = "video"
        self.respond(page(query, kind))

    def do_POST(self):
        if self.path != "/download":
            self.respond("Сторінку не знайдено", 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length < 4096:
                raise ValueError("Некоректний запит")
            fields = parse_qs(self.rfile.read(length).decode("utf-8"))
            get = lambda name, default="": fields.get(name, [default])[0]
            if get("token") != TOKEN:
                raise ValueError("Онови сторінку й спробуй ще раз")
            kind = get("kind")
            if kind not in {"video", "image"}:
                raise ValueError("Невідомий тип файлу")
            record = download(kind, int(get("id")), get("quality"), str(folder_for(get("channel"))))
            self.respond(page(get("q"), kind, f"Збережено: {record['local_file']}"))
        except (RuntimeError, ValueError) as exc:
            self.respond(page(error=str(exc)))


if __name__ == "__main__":
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        webbrowser.open(f"http://127.0.0.1:{PORT}/")
        raise SystemExit(0)
    webbrowser.open(f"http://127.0.0.1:{PORT}/")
    print("Pixabay search is open. Keep this window running while using the page.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
