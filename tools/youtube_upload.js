// The YouTube Studio side of a publication (docs/YOUTUBE_PUBLISH.md). Run this whole file once with the built-in
// browser's javascript_tool on studio.youtube.com; it defines window.__vk. Each step waits for its part of the upload
// dialog and returns a short JSON answer, so a publication is a few calls instead of dozens of clicks (user, 19 November
// 2026: «щоб завантаження було чітко… і не було шансів на збій»). The selectors are the ones the first publications
// used (Космос PRO, 19 November 2026).
(() => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const visible = el => !!el && el.offsetParent !== null;
  async function until(find, ms = 20000) {
    const end = Date.now() + ms;
    for (;;) {
      const found = find();
      if (found) return found;
      if (Date.now() > end) return null;
      await sleep(300);
    }
  }
  const dialog = () => document.querySelector('ytcp-uploads-dialog');
  const text = el => (el?.innerText || '').replace(/\s+/g, ' ').trim();

  async function setText(selector, value) {
    const el = await until(() => document.querySelector(selector));
    if (!el) return false;
    el.focus();
    document.execCommand('selectAll', false, null);
    document.execCommand('insertText', false, value);
    return text(el) === value.replace(/\s+/g, ' ').trim();
  }

  // a file from the studio's local server into a file field; no Finder window, no browser cache
  async function attach(selector, url, name, type) {
    const input = await until(() => document.querySelector(selector));
    if (!input) return { ok: false, error: 'no file field ' + selector };
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) return { ok: false, error: 'file server answered ' + response.status };
    const blob = await response.blob();
    const transfer = new DataTransfer();
    transfer.items.add(new File([blob], name, { type }));
    input.files = transfer.files;
    input.dispatchEvent(new Event('change', { bubbles: true }));
    return { ok: true, bytes: blob.size };
  }

  window.__vk = {
    // the dialog through Studio's own buttons («Создать» → «Добавить видео»), not by address
    async open() {
      if (visible(dialog())) return { ok: true, already: true };
      const create = await until(() => document.querySelector('ytcp-button#create-icon, #create-icon'));
      if (!create) return { ok: false, error: 'no Create button: is this studio.youtube.com of the right channel?' };
      create.click();
      const item = await until(() => [...document.querySelectorAll('tp-yt-paper-item')]
        .find(e => visible(e) && /Добавить видео|Загрузить видео|Upload videos|Завантажити відео/i.test(text(e))), 5000);
      if (!item) return { ok: false, error: 'no «Добавить видео» item' };
      item.click();
      const field = await until(() => document.querySelector('input[type=file][name=Filedata]'));
      return { ok: !!field };
    },
    // the video file; returns at once, the upload itself goes on in Studio
    video: (url, name) => attach('input[type=file][name=Filedata]', url, name, 'video/mp4'),
    async details(title, description) {
      const t = await setText('#title-textarea #textbox', title);
      const d = await setText('#description-textarea #textbox', description);
      return { ok: t && d, title: t, description: d };
    },
    async cover(url) {
      const shown = await attach('ytcp-thumbnail-uploader input[type=file]', url, 'cover.png', 'image/png');
      await sleep(2500);
      return shown;
    },
    async notForKids() {
      const radio = await until(() => document.querySelector('tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]'));
      if (!radio) return { ok: false, error: 'no audience choice' };
      radio.click();
      const more = [...document.querySelectorAll('ytcp-button')].find(e => /^(Развернуть|Показать все|Show more|Показати більше)$/i.test(text(e)));
      if (more) more.click();
      await sleep(600);
      return { ok: radio.getAttribute('aria-checked') === 'true' };
    },
    // the tag field: the session types the tags itself (computer type, comma at the end); this focuses and reads it
    async tagsField() {
      const input = await until(() => document.querySelector('#tags-container input'), 8000);
      if (!input) return { ok: false, error: 'no tags field' };
      input.scrollIntoView({ block: 'center' });
      input.focus();
      return { ok: true };
    },
    tags() {
      const box = document.querySelector('#tags-container');
      return { chips: box ? box.querySelectorAll('ytcp-chip').length : 0, text: text(box).slice(0, 300) };
    },
    progress() {
      return { upload: text(document.querySelector('ytcp-video-upload-progress')).slice(0, 120),
               step: text(document.querySelector('ytcp-stepper [aria-selected=true]')) };
    },
    // «Далее» up to the «Доступ» step
    async toVisibility() {
      for (let i = 0; i < 4; i++) {
        if (await until(() => document.querySelector('#privacy-radios'), 1500)) break;
        document.querySelector('#next-button')?.click();
        await sleep(1200);
      }
      const radios = document.querySelector('#privacy-radios');
      if (!radios) return { ok: false, error: 'did not reach the visibility step' };
      radios.querySelector('tp-yt-paper-radio-button[name=PRIVATE]')?.click();
      const expand = document.querySelector('#second-container-expand-button');
      if (expand) expand.click();
      const picker = await until(() => document.querySelector('ytcp-datetime-picker'), 6000);
      picker?.scrollIntoView({ block: 'center' });
      return { ok: !!picker, picker: text(picker) };
    },
    schedule() {
      const picker = document.querySelector('ytcp-datetime-picker');
      return { picker: text(picker), time: picker?.querySelector('input')?.value, button: text(document.querySelector('#done-button')),
               upload: text(document.querySelector('ytcp-video-upload-progress')).slice(0, 120) };
    },
    async finish() {
      const done = document.querySelector('#done-button');
      if (!done) return { ok: false, error: 'no schedule button' };
      done.click();
      const said = await until(() => (document.body.innerText.match(/Видео запланировано[^\n]*|Video scheduled[^\n]*|Відео заплановано[^\n]*/) || [])[0], 15000);
      const link = [...document.querySelectorAll('a')].map(a => a.href).find(h => /youtu\.be\/|watch\?v=/.test(h)) || '';
      const id = (link.match(/(?:youtu\.be\/|v=)([\w-]{11})/) || [])[1] || null;
      return { ok: !!said, said, video_id: id };
    },
  };
  return 'window.__vk ready: ' + Object.keys(window.__vk).join(', ');
})();
