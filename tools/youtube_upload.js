// The YouTube Studio side of a publication (docs/YOUTUBE_PUBLISH.md). Run this whole file once with the built-in
// browser's javascript_tool on studio.youtube.com; it defines window.__vk. Every step waits for its part of the page and
// answers JSON with `ok`, so a publication is a dozen calls and no hand clicks (user, 19 November 2026: «щоб не було
// права на помилку… щоб все він знав, що робити»).
//
// Nothing here reads a button's caption: Studio may speak Russian, Ukrainian or English (user: «в когось браузер на
// український, когось на англійський»). Elements are found by id, test-id, name and position. Every selector was tried
// on a real draft on 19 November 2026 (Николай Ветров, «Мы нашли сверхбыстро мигающий объект…», scheduled 21.11 15:00).
(() => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const shown = el => !!el && el.offsetParent !== null;
  async function until(find, ms = 20000) {
    const end = Date.now() + ms;
    for (;;) {
      const found = find();
      if (found) return found;
      if (Date.now() > end) return null;
      await sleep(300);
    }
  }
  const text = el => (el?.innerText || '').replace(/\s+/g, ' ').trim();
  const enter = el => el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, composed: true }));

  function write(el, value) {
    el.focus();
    document.execCommand('selectAll', false, null);
    document.execCommand('insertText', false, value);
    return text(el) === value.replace(/\s+/g, ' ').trim();
  }

  // a file from the studio's local server into a file field: no Finder window, no browser cache
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
    // the channel shown in Studio's header: compare it with the episode's channel before anything else
    channel() {
      return { name: text(document.querySelector('ytcp-header #entity-name, #entity-name, ytcp-account-menu #channel-title')) || document.title,
               url: location.href };
    },
    // a draft of this title already in «Контент» (an earlier attempt): its video id, to continue it instead of uploading again
    draft(title) {
      // a row of the content list by its title; the id is in its thumbnail's address (/vi/<id>/), the rows carry no links
      const row = [...document.querySelectorAll('ytcp-video-row')].find(r => text(r.querySelector('#video-title')) === title.trim());
      const id = row && (row.innerHTML.match(/\/vi\/([\w-]{11})\//) || [])[1];
      return { found: !!id, video_id: id || null };
    },
    // the upload dialog of a new video («Создать» → upload), or of a draft by its id
    async open(draftId) {
      if (draftId) {
        const base = location.pathname.match(/\/channel\/[\w-]+/)?.[0];
        if (!base) return { ok: false, error: 'not on a channel page of studio.youtube.com' };
        location.href = `https://studio.youtube.com${base}/videos/upload?d=ud&udvid=${draftId}`;
        return { ok: true, reloading: true, next: 'run this file again, then continue with details()' };
      }
      if (shown(document.querySelector('ytcp-uploads-dialog'))) return { ok: true, already: true };
      const create = await until(() => document.querySelector('ytcp-button.ytcpAppHeaderCreateIcon, ytcp-button#create-icon, #create-icon'));
      if (!create) return { ok: false, error: 'no Create button' };
      create.click();
      const item = await until(() => [...document.querySelectorAll('tp-yt-paper-item[test-id="upload"]')].find(shown), 6000);
      if (!item) return { ok: false, error: 'no upload item in the Create menu' };
      item.click();
      return { ok: !!(await until(() => document.querySelector('input[type=file][name=Filedata]'))) };
    },
    video: (url, name) => attach('input[type=file][name=Filedata]', url, name, 'video/mp4'),
    async details(title, description) {
      const t = await until(() => document.querySelector('#title-textarea #textbox'));
      const d = await until(() => document.querySelector('#description-textarea #textbox'));
      if (!t || !d) return { ok: false, error: 'no title or description field' };
      const a = write(t, title), b = write(d, description);
      return { ok: a && b, title: a, description: b };
    },
    async cover(url) {
      const done = await attach('ytcp-thumbnail-uploader input[type=file]', url, 'cover.png', 'image/png');
      await sleep(2500);
      return done;
    },
    async notForKids() {
      const radio = await until(() => document.querySelector('tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]'));
      if (!radio) return { ok: false, error: 'no audience choice' };
      radio.click();
      const more = document.querySelector('ytcp-button#toggle-button');
      if (more && !document.querySelector('#tags-container')) more.click();
      await sleep(800);
      return { ok: radio.getAttribute('aria-checked') === 'true', tags_field: !!document.querySelector('#tags-container') };
    },
    // the tags as chips, typed by script (the field takes «tag,» + Enter); answers the chips Studio shows
    async tags(list) {
      const box = await until(() => document.querySelector('#tags-container'), 8000);
      if (!box) return { ok: false, error: 'no tags field (call notForKids first, it opens «more»)' };
      const input = box.querySelector('input');
      const have = new Set([...box.querySelectorAll('ytcp-chip')].map(c => text(c).toLowerCase()));
      for (const tag of list) {
        if (have.has(tag.toLowerCase())) continue;
        input.focus();
        document.execCommand('insertText', false, tag + ',');
        enter(input);
        await sleep(250);
      }
      input.blur();
      await sleep(500);
      const chips = [...box.querySelectorAll('ytcp-chip')].map(c => text(c));
      return { ok: list.every(tag => chips.some(c => c.toLowerCase() === tag.toLowerCase())), chips };
    },
    // the playlist with exactly this name; none of that name: { ok: false, playlists } (skip it then)
    async playlist(name) {
      const field = await until(() => document.querySelector('ytcp-video-metadata-playlists'));
      if (!field) return { ok: false, error: 'no playlist field' };
      field.scrollIntoView({ block: 'center' });
      (field.querySelector('ytcp-text-dropdown-trigger') || field).click();
      const dialog = await until(() => { const d = document.querySelector('ytcp-playlist-dialog'); return shown(d?.querySelector('ytcp-checkbox-lit')) && d; }, 8000);
      if (!dialog) return { ok: false, error: 'the playlist list did not open' };
      const boxes = [...dialog.querySelectorAll('ytcp-checkbox-lit')];
      const label = box => text(box.closest('li,label,div'));
      const box = boxes.find(b => label(b) === name.trim());
      if (box && box.getAttribute('aria-checked') !== 'true' && box.querySelector('[aria-checked]')?.getAttribute('aria-checked') !== 'true') box.click();
      await sleep(400);
      dialog.querySelector('ytcp-button.done-button')?.click();
      await sleep(900);
      return { ok: !!box, playlists: boxes.map(label).slice(0, 20), field: text(field) };
    },
    // A/B test of the titles: the first is the title itself, the others go to the next fields; saved with the dialog
    async abTitles(titles) {
      const button = await until(() => [...document.querySelectorAll('ytcp-button#ab-test-button')].find(shown), 6000);
      if (!button) return { ok: false, skipped: true, error: 'no A/B test on this channel or video: skip it' };
      button.scrollIntoView({ block: 'center' });
      button.querySelector('button')?.click() || button.click();
      // the dialog counts as open by its size: its «set test» button stays disabled (and unseen) until the fields are full
      const dialog = await until(() => [...document.querySelectorAll('ytcp-dialog')].find(d => d.querySelector('#set-test-button') && d.querySelector('ytcp-social-suggestions-textbox') && [...d.querySelectorAll('ytcp-social-suggestions-textbox #textbox')].some(shown)), 8000);
      if (!dialog) return { ok: false, error: 'the A/B dialog did not open' };
      const radios = [...dialog.querySelectorAll('tp-yt-paper-radio-button, [role=radio]')].filter(shown);
      if (radios[0] && radios[0].getAttribute('aria-checked') !== 'true') { radios[0].click(); await sleep(600); }   // titles only
      const boxes = [...dialog.querySelectorAll('ytcp-social-suggestions-textbox #textbox')].filter(shown);
      const written = titles.slice(0, boxes.length).map((title, i) => (text(boxes[i]) === title.trim() ? true : write(boxes[i], title)));
      await sleep(500);
      dialog.querySelector('#set-test-button')?.click();
      await sleep(1500);
      return { ok: written.every(Boolean), fields: boxes.length, closed: !shown(dialog.querySelector('#set-test-button')) };
    },
    // the video file is still going up to YouTube while the progress line shows a percentage; leaving the page or closing
    // the tab then leaves it an unfinished draft (19 November 2026). Waits up to 4 minutes a call: call again until ok
    async waitUpload() {
      const end = Date.now() + 240000;
      for (;;) {
        const line = text(document.querySelector('ytcp-video-upload-progress'));
        // only the upload's own percentage: «Проверка: 13 %» after it is YouTube's copyright check, the file is up by then
        const uploading = /(Загрузка|Загружается|Завантаження|Uploading|Upload)[^%]{0,30}\d+\s*%/i.test(line);
        if (!uploading) return { ok: true, progress: line.slice(0, 120) };
        if (Date.now() > end) return { ok: false, still_uploading: true, progress: line.slice(0, 120), next: 'call waitUpload() again; do not leave the page' };
        await sleep(5000);
      }
    },
    progress() {
      return { upload: text(document.querySelector('ytcp-video-upload-progress')).slice(0, 120) };
    },
    // «Далее» up to «Доступ», «Приватное», the schedule opened
    async toVisibility() {
      for (let i = 0; i < 5 && !shown(document.querySelector('#privacy-radios')); i++) {
        document.querySelector('#next-button')?.click();
        await sleep(1500);
      }
      if (!shown(document.querySelector('#privacy-radios'))) return { ok: false, error: 'did not reach the visibility step' };
      if (!shown(document.querySelector('ytcp-datetime-picker #datepicker-trigger'))) {
        document.querySelector('#second-container-expand-button')?.click();
        await sleep(1000);
      }
      const picker = document.querySelector('ytcp-datetime-picker');
      return { ok: shown(picker), date: text(picker?.querySelector('#datepicker-trigger')) };
    },
    // the date ('2026-11-21') in the calendar and the time ('15:00', on the quarter hour) in the time list
    async schedule(date, time) {
      const [y, m, d] = date.split('-').map(Number), [hh, mm] = time.split(':').map(Number);
      const picker = document.querySelector('ytcp-datetime-picker');
      if (!picker) return { ok: false, error: 'call toVisibility first' };
      picker.querySelector('#datepicker-trigger').click();
      const calendar = await until(() => { const c = document.querySelector('ytcp-date-picker #calendar-main'); return shown(c) && c; }, 6000);
      if (!calendar) return { ok: false, error: 'the calendar did not open' };
      const now = new Date(), months = [...calendar.querySelectorAll('.calendar-month')];
      const offset = (y - now.getFullYear()) * 12 + (m - 1) - now.getMonth();   // the calendar starts at this month
      const day = months[offset] && [...months[offset].querySelectorAll('.calendar-day')].find(s => s.textContent.trim() === String(d) && !s.classList.contains('disabled'));
      if (!day) return { ok: false, error: 'that day is not open in the calendar (past, or too far)' };
      day.click();
      await sleep(800);
      const input = picker.querySelector('#time-of-day-container input');
      input.click();
      input.focus();
      const items = await until(() => { const list = [...document.querySelectorAll('tp-yt-paper-item')].filter(e => shown(e) && /\d:\d\d/.test(text(e))); return list.length >= 96 && list; }, 6000);
      if (!items || mm % 15) return { ok: false, error: 'the time list did not open or the time is not on a quarter hour' };
      items[hh * 4 + mm / 15].click();   // 00:00, 00:15, … in any language and clock format
      await sleep(800);
      return { ok: true, date: text(picker.querySelector('#datepicker-trigger')), time: input.value };
    },
    // the AI-content question is never answered (the author's rule); this only reports it
    aiQuestion() {
      return [...document.querySelectorAll('tp-yt-paper-radio-button')].filter(e => /ALTERED|SYNTHETIC|SELF_DECLARED/i.test(e.getAttribute('name') || ''))
        .map(e => e.getAttribute('name') + ':' + e.getAttribute('aria-checked'));
    },
    // the end screen on the video's edit page (studio.youtube.com/video/<id>/edit): Studio's first template, one video and
    // the «Subscribe» button over the last 20 seconds (user, 19 November 2026: «кінечну заставку треба ще ставити»);
    // a video that has one keeps it
    async endScreen() {
      const big = el => !!el && el.getBoundingClientRect().width > 0;   // the editor's buttons have no offsetParent
      // in the upload form, step «Дополнения» (#endscreens-button), before the video is scheduled: the built-in browser's
      // safety check refused editing a video already scheduled (19 November 2026); the edit page's link stays a fallback
      if (shown(document.querySelector('ytcp-uploads-dialog')) && !document.querySelector('#endscreens-button')) {
        for (let i = 0; i < 2 && !document.querySelector('#endscreens-button'); i++) {
          document.querySelector('#next-button')?.click();
          await sleep(1500);
        }
      }
      const link = await until(() => [...document.querySelectorAll('#endscreens-button, #endscreen-editor-link')].find(e => e.getBoundingClientRect().width > 0), 15000);
      if (!link) return { ok: false, error: 'no end-screen button: in the upload form go to its second step («Дополнения»)' };
      link.scrollIntoView({ block: 'center' });
      link.click();
      const modal = await until(() => { const m = document.querySelector('ytve-endscreen-modal'); return big(m?.querySelector('ytve-endscreen-editor-timeline')) && m; }, 60000);   // a long video loads its editor slowly
      if (!modal) return { ok: false, error: 'the end-screen editor did not open' };
      await sleep(2000);
      const timeline = () => text(modal.querySelector('ytve-endscreen-editor-timeline'));   // «Подписаться: … | Видео: …»
      const existing = timeline();
      if (!existing) {
        const card = await until(() => [...modal.querySelectorAll('ytve-endscreen-template-picker .card')].find(big), 8000);
        if (!card) return { ok: false, error: 'no end-screen templates' };
        card.click();
        if (!(await until(() => timeline(), 8000))) return { ok: false, error: 'the template did not apply' };
      }
      const elements = timeline();
      modal.querySelector(existing ? '#discard-button' : '#save-button').click();
      const closed = await until(() => !big(modal.querySelector('ytve-endscreen-editor-timeline')), 15000);
      return { ok: !!closed, kept_existing: !!existing, elements };
    },
    // on the channel's «Контент» page: is this video really scheduled or published, not a draft or a half upload? Its
    // answer `proof` is what `youtube_publish.py done` asks for (19 November 2026: «Эти галактики» was marked done while
    // YouTube kept it a draft)
    async verify(videoId) {
      const row = await until(() => [...document.querySelectorAll('ytcp-video-row')].find(r => r.innerHTML.includes(`/vi/${videoId}/`)), 20000);
      if (!row) return { ok: false, error: 'no row of this video in «Контент»: open the channel content page, run this file again' };
      // a draft's row has its thumbnail as .draft-thumbnail (the draft buttons appear only on hover); a scheduled one
      // shows .schedule-icon. Class names, not captions: the same in any language of Studio
      const draft = !!row.querySelector('.draft-thumbnail, .edit-draft-button, .resume-upload-button');
      return draft ? { ok: false, error: 'still a draft or an unfinished upload on YouTube: open it with open(video_id) and finish' }
                   : { ok: true, proof: 'VK-' + videoId };
    },
    async finish() {
      const done = document.querySelector('#done-button');
      if (!done) return { ok: false, error: 'no schedule button' };
      done.click();
      // only the confirmation window counts: the upload form shows the video's link from the start, so a link alone
      // proved nothing (19 November 2026: «Эти галактики» stayed a draft)
      const shared = await until(() => [...document.querySelectorAll('ytcp-video-share-dialog')].find(shown), 30000);
      if (!shared) return { ok: false, error: 'no «scheduled» confirmation: look at the dialog (a warning, a missing field) and fix it' };
      const link = [...shared.querySelectorAll('a')].map(a => a.href).find(h => /youtu\.be\/[\w-]{11}/.test(h)) || text(shared);
      const id = (String(link).match(/youtu\.be\/([\w-]{11})/) || [])[1];
      await sleep(800);
      [...shared.querySelectorAll('ytcp-button')].find(shown)?.click();
      return { ok: !!id, video_id: id || null, next: 'verify(video_id) on the channel content page before done' };
    },
  };
  return 'window.__vk ready: ' + Object.keys(window.__vk).join(', ');
})();
