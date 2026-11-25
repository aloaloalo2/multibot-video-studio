// razgon-live.js — live preview of Razgon 2D episodes inside «Монтаж»: the Razgon player draws the film in real time
// in an iframe over the preview, following the studio playhead, so the timeline can be scrubbed and played without
// waiting for rendered clips. The studio keeps its own timeline and audio. Shown only when the episode folder has
// razgon.json; the backend starts the live server on demand (backend/razgon_live.py).
(() => {
  const live = {}, KEY = 'razgonLiveMonitor', QKEY = 'razgonLiveScale';
  const read = (key, fallback) => { try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; } };
  const write = (key, value) => { try { localStorage.setItem(key, value); } catch {} };

  const tools = document.createElement('div');
  tools.className = 'razgon-live-tools'; tools.hidden = true;
  tools.innerHTML = '<button id="razgon-live-toggle" type="button" aria-pressed="false" title="Малювати кадри Razgon наживо, без рендеру">Наживо</button>'
    + '<select id="razgon-live-quality" aria-label="Якість живого перегляду" title="Якість живого перегляду"><option value="0.33">низька</option><option value="0.5">середня</option><option value="0.75">висока</option></select>';
  document.querySelector('.preview-tools').prepend(tools);
  const toggle = tools.querySelector('button'), quality = tools.querySelector('select');
  quality.value = read(QKEY, '0.5');
  const frame = document.createElement('iframe');
  frame.id = 'razgon-live-frame'; frame.title = 'Razgon наживо'; frame.hidden = true;
  $('preview-content').append(frame);
  // A seam between two Razgon frames: the outgoing frame's last moment in a second player over the incoming one, both
  // moved by the seam's transition the way the preview moves any clip (user, 21 November 2026: «переходи… хотів би бачити
  // все-таки онлайн, щоб було видно, що це за перехід»); one player alone shows only one moment, so the seam read as a cut
  const frameOut = document.createElement('iframe');
  frameOut.id = 'razgon-live-frame-out'; frameOut.title = 'Razgon наживо, попередній кадр'; frameOut.hidden = true;
  frameOut.setAttribute('aria-hidden', 'true'); frameOut.tabIndex = -1;
  $('preview-content').append(frameOut);
  // what went wrong, over the preview, instead of an empty frame (user, 2 November 2026: «всеодно сіре, хоча код є»)
  const note = document.createElement('div');
  note.className = 'razgon-live-note'; note.hidden = true;
  note.innerHTML = '<p></p><button type="button" class="secondary">Перезапустити перегляд</button>';
  $('preview-content').append(note);
  const showNote = (text) => { note.querySelector('p').textContent = text; note.hidden = !text; };
  note.querySelector('button').addEventListener('click', async () => {
    const id = state.project?.id; if (!id) return;
    const button = note.querySelector('button'); button.disabled = true; showNote('Перезапускаємо живий перегляд…');
    try { live[id] = await api(`/api/projects/${encodeURIComponent(id)}/razgon-live`, 'POST', { restart: true }); retried.delete(id);
      frame.removeAttribute('src'); delete frame.dataset.src; sync(); renderPreview(); }
    catch (error) { showNote(error.message); }
    finally { button.disabled = false; }
  });
  const style = document.createElement('style');
  style.textContent = '.razgon-live-note{position:absolute;inset:0;z-index:30;display:grid;place-content:center;justify-items:center;gap:12px;padding:24px;text-align:center;background:#0a0b0ccc}.razgon-live-note[hidden]{display:none}.razgon-live-note p{margin:0;max-width:520px;color:#e6e7ea;font-size:13.5px;line-height:1.5}' + '.razgon-live-tools{display:inline-flex;gap:6px;align-items:center}.razgon-live-tools button,.razgon-live-tools select{background:#24252a;color:inherit;border:1px solid #3f4046;border-radius:9px;padding:4px 9px;font:inherit;font-size:12px;cursor:pointer}.razgon-live-tools button[aria-pressed="true"]{border-color:#f0b429;color:#f0b429}.razgon-live-tools select[hidden]{display:none}#razgon-live-frame,#razgon-live-frame-out{position:absolute;inset:0;width:100%;height:100%;border:0;background:#000;z-index:0;pointer-events:none;transform-origin:50% 50%}#razgon-live-frame-out{visibility:hidden}.razgon-live-on #preview-composition{background:transparent;z-index:1}';
  document.head.append(style);

  const info = () => state.project && live[state.project.id];
  const active = () => !!(info()?.url && read(KEY, '1') === '1');
  const source = () => `${info().url}?embed=1&scale=${quality.value}`;
  // the live frame comes into view only with its own moment on the canvas (user, 25 November 2026: «з другого на третій
  // кадр… пригає на якийсь… кадр посередині… а потім… початок»): after a jump of time it waits for the page's «drawn»
  let drawnAt = null, waitingFor = null, waitTimer = null, wasOn = false, lastT = null;
  const reveal = () => { if (waitingFor === null && frame.dataset.wantVisible === '1') frame.style.visibility = ''; };
  let seekTime = null;   // the Razgon time the picture shows: the playhead, or a frame's last moment while a transition fades out of it
  const post = () => { if (!frame.hidden && frame.contentWindow) frame.contentWindow.postMessage({ razgon: 'seek', t: seekTime ?? state.playhead }, '*'); };
  // A live server that went down (the studio restarted, after an update) leaves a black frame: the player says «ready»
  // when it draws, so one that keeps silent is started again (user, 2 November 2026: «код не відтворюється»).
  let ready = false, watch = 0; const retried = new Set();   // one fresh start a project a page
  addEventListener('message', (event) => {
    if (event.source !== frame.contentWindow) return;
    if (event.data?.razgon === 'ready') { ready = true; clearTimeout(watch); showNote(''); post(); }
    if (event.data?.razgon === 'drawn') { drawnAt = event.data.t; if (waitingFor !== null && Math.abs(drawnAt - waitingFor) < .2) { waitingFor = null; clearTimeout(waitTimer); reveal(); } }
    if (event.data?.razgon === 'error') showNote(`Живий перегляд не може намалювати сцени: ${event.data.message || 'невідома помилка'}. Виправте сцену або натисніть «Перезапустити перегляд».`);
  });
  function watchStart(id) {
    ready = false; clearTimeout(watch);
    watch = setTimeout(() => {
      if (ready || state.project?.id !== id || !active()) return;
      if (retried.has(id)) { showNote('Живий перегляд не відповідає. Натисніть «Перезапустити перегляд». Якщо не допоможе, причина в журналі build/live.log проєкту Razgon.'); return; }
      retried.add(id);
      delete live[id]; frame.removeAttribute('src'); delete frame.dataset.src;
      // the server says whether its live view runs; a stale one is started again
      api(`/api/projects/${encodeURIComponent(id)}/razgon-live`, 'POST', {}).then(fresh => { live[id] = fresh; sync(); renderPreview(); })
        .catch(() => { load(id); });
    }, 12000);
  }

  async function load(id) {
    if (id in live) return;
    live[id] = null;
    try {
      const known = await api(`/api/projects/${encodeURIComponent(id)}/razgon-live`);
      // a live server that already runs needs no start, so an export's project lock does not stand in its way
      live[id] = known.available && !known.running ? await api(`/api/projects/${encodeURIComponent(id)}/razgon-live`, 'POST', {}) : known;
    } catch (error) {
      // the studio was restarting or the live server was busy: try again instead of hiding the live view until a reload.
      // The export's lock (423) is shown on the project itself, so it goes without a banner
      live[id] = { available: false }; if (error.httpStatus !== 423) { status(error.message, true); showNote(error.message); }
      setTimeout(() => { delete live[id]; if (state.project?.id === id) { load(id); sync(); } }, 4000);
    }
    sync(); if (state.project?.id === id) renderPreview();
  }
  function sync() {
    const on = active();
    tools.hidden = !info()?.available; quality.hidden = !on;
    toggle.setAttribute('aria-pressed', String(on));
    if (on && frame.dataset.src !== source()) { frame.src = source(); frame.dataset.src = frame.src; watchStart(state.project.id); }
    if (!on && frame.dataset.src) { frame.removeAttribute('src'); delete frame.dataset.src; }
    // the second player loads with the first, so a seam shows at once while playing
    if (on && frameOut.dataset.src !== source()) { frameOut.src = source(); frameOut.dataset.src = frameOut.src; }
    if (!on && frameOut.dataset.src) { frameOut.removeAttribute('src'); delete frameOut.dataset.src; }
    frame.hidden = frameOut.hidden = !on; if (!on) showNote('');
  }
  toggle.addEventListener('click', () => { write(KEY, active() ? '0' : '1'); sync(); renderPreview(); });
  quality.addEventListener('change', () => { write(QKEY, quality.value); sync(); });

  // A mixed episode (photos, stock, text frames and some Razgon frames, e.g. Alexey Gorbunov's): only its razgon_2d frames
  // are drawn live, and only while the playhead is inside one; the rest of the timeline plays as usual. null: all Razgon.
  const razgonFrames = () => {
    const frames = state.plan?.frames || [], fps=state.project?.fps||25;
    const own = frames.filter(f=>f.format==='razgon_2d').map(f=>({...f,sourceStart:f.start,sourceEnd:f.end,
      start:Math.floor(f.start*fps+.5+1e-8)/fps,end:Math.floor(f.end*fps+.5+1e-8)/fps}));
    return own.length && own.length < frames.length ? own : null;
  };

  // Every Razgon frame of the plan with its whole-frame edges, for the seams between two of them.
  const allRazgon = () => {
    const fps = state.project?.fps || 25;
    return (state.plan?.frames || []).filter((f) => f.format === 'razgon_2d').map((f) => ({ ...f, sourceStart: f.start, sourceEnd: f.end,
      start: Math.floor(f.start * fps + .5 + 1e-8) / fps, end: Math.floor(f.end * fps + .5 + 1e-8) / fps }));
  };
  const blockOf = (f) => {
    const group = sceneGroups().find((g) => g.title === `Кадр ${f.number}`);
    return group ? groupMembers(group).find((clip) => /^Razgon · кадр/.test(clip.title || '')) : null;
  };
  const place = (element, clip, local) => {
    const base = { x: .5, y: .5, scale: 1, opacity: 1 };
    const v = clip ? transitionValues(clip, local, { ...base }) : base;
    element.style.transform = v.x === .5 && v.y === .5 && v.scale === 1 ? '' : `translate(${(v.x - .5) * 100}%, ${(v.y - .5) * 100}%) scale(${v.scale})`;
    element.style.opacity = v.opacity >= 1 ? '' : String(Math.max(0, v.opacity));
  };
  // the second player draws the outgoing frame's last moment while that frame still plays, so its scene is loaded and
  // drawn when the seam comes (posted only at the seam, the first 0.35 s showed its empty black field)
  // a seek posted while the second player still loads is lost (the seam stayed black, 21 November 2026): the wanted
  // moment is kept and posted again when that player says «ready»
  let outAt = null, outWant = null, outReady = false;
  const outPost = (time) => { outWant = time; if (!outReady || time === outAt || !frameOut.contentWindow) return; outAt = time; frameOut.contentWindow.postMessage({ razgon: 'seek', t: time }, '*'); };
  frameOut.addEventListener('load', () => { outAt = null; outReady = false; });
  addEventListener('message', (event) => {
    if (event.source !== frameOut.contentWindow || event.data?.razgon !== 'ready') return;
    outReady = true; outAt = null; if (outWant !== null) outPost(outWant);
  });
  // t inside the transition of a seam between two Razgon frames: the incoming frame in the first player, the outgoing
  // one held at its last moment in the second, each moved by the transition; anything else: the first player as it is
  function seam(t) {
    const frames = t === null ? [] : allRazgon(), fps = state.project?.fps || 25;
    const incoming = frames.find((f) => t >= f.start && t < f.end);
    const outgoing = incoming && frames.find((f) => Math.abs(f.end - incoming.start) < 1 / fps / 2);
    // warm up: the frame playing now ends in a seam with a transition into another Razgon frame
    const ahead = incoming && frames.find((f) => Math.abs(f.start - incoming.end) < 1 / fps / 2);
    const aheadClip = ahead && blockOf(incoming);
    if (aheadClip && transitionInfo(aheadClip).outgoing) outPost(incoming.sourceEnd - 1 / fps);
    const inClip = outgoing && blockOf(incoming), outClip = outgoing && blockOf(outgoing);
    const join = outClip && transitionInfo(outClip).outgoing;
    const span = join && joinFrames(join);
    if (!span || t < span.seam || t >= span.seam + span.duration) {
      frameOut.style.visibility = 'hidden'; place(frame, null, 0); return;
    }
    place(frame, inClip, t - Number(inClip.start));
    place(frameOut, outClip, t - Number(outClip.start));
    // the outgoing player lies on top and fades by itself: the incoming one under it stays opaque, or the middle of a
    // dissolve showed both half through over black, darker than either frame (whichever side the montage keeps on top)
    frame.style.opacity = '';
    const type = join.type, fades = type === 'crossfade' || type.startsWith('zoom_') || type.startsWith('capcut_t') || graphicTransitionPresets[type]?.kind === 'cinematic';
    if (fades) frameOut.style.opacity = String(Math.max(0, 1 - easedProgress((t - span.seam) / span.duration, 'ease_in_out')));
    frameOut.style.visibility = 'visible';   // '' would fall back to the stylesheet's hidden
    outPost(outgoing.sourceEnd - 1 / fps);
  }

  // In live mode the rendered Razgon clips are not decoded at all: the iframe draws the picture under the studio's own
  // overlay layers (the channel plashka group), and the studio keeps time and sound.
  const baseUniversal = renderUniversalPreview;
  renderUniversalPreview = function (...args) {
    const own = razgonFrames(), t = state.playhead, content = $('preview-content');
    // while a transition fades out of a Razgon frame its last picture stays under the incoming frame, as the export's held tail
    const groupId = (f) => sceneGroups().find((group) => group.title === `Кадр ${f.number}`)?.id;
    const tail = (f) => (state.project?.join_transitions || []).find((join) => join.from_ref === `group:${groupId(f)}` && Math.abs(join.seam - f.end) < .05);
    // a frame whose row is switched off with its eye is not drawn live either (user, 2 November 2026: «нажав око, але
    // вони не пропали»): the Razgon blocks under the playhead must sit on a row that is seen
    const hiddenClip = new Set(layers().filter((layer) => layer.hidden).flatMap((layer) => (layer.clips || []).map((clip) => clip.id)));
    const blocksAt = (time) => layers().flatMap((layer) => layer.clips || []).filter((clip) => /^Razgon · кадр/.test(clip.title || '') && time >= Number(clip.start) && time < Number(clip.start) + Number(clip.duration));
    const seen = (time) => { const blocks = blocksAt(time); return !blocks.length || blocks.some((clip) => !hiddenClip.has(clip.id)); };
    // the tail ends where the transition and the block end, on whole video frames (joinFrames, clipRenderEnd): the raw
    // seam + duration ended one frame early, and for that frame the block's black base showed over the next picture
    // (user, 25 November 2026: «після переходу просто чорний на один фрейм показується»)
    const tailEnd = (f) => { const join = tail(f); if (!join) return f.end; const span = joinFrames(join); return span.seam + span.duration; };
    const inside = own && own.find((f) => t >= f.start && t < f.end), fading = own && !inside && own.find((f) => t >= f.end && t < tailEnd(f));
    const sourceFrame=inside||fading;
    seekTime = sourceFrame ? Math.max(sourceFrame.sourceStart,Math.min(t,sourceFrame.sourceEnd-1/(state.project?.fps||25))) : null;
    const on = active() && (!own || !!inside || !!fading) && seen(fading ? fading.end - 0.01 : t);
    const jumped = on && (!wasOn || lastT === null || Math.abs(t - lastT) > .25);
    wasOn = on; lastT = t;
    content.classList.toggle('razgon-live-on', on); note.style.visibility = on ? '' : 'hidden';
    frame.dataset.wantVisible = on ? '1' : '';
    if (!on) { frame.style.visibility = 'hidden'; waitingFor = null; clearTimeout(waitTimer);
      // the next Razgon frame within 0.6 s is drawn ahead while hidden, so it comes in on its first moment
      const next = own && own.find((f) => f.start > t && f.start - t < .6);
      if (next && frame.contentWindow && !frame.hidden) frame.contentWindow.postMessage({ razgon: 'seek', t: next.sourceStart ?? next.start }, '*');
    } else if (jumped && !(drawnAt !== null && Math.abs(drawnAt - (seekTime ?? t)) < .2)) {
      frame.style.visibility = 'hidden'; waitingFor = seekTime ?? t; clearTimeout(waitTimer);
      waitTimer = setTimeout(() => { waitingFor = null; reveal(); }, 300);   // a page that never answers still shows
    } else if (waitingFor === null) frame.style.visibility = '';
    seam(on && !fading ? t : null);
    if (!on) return baseUniversal.apply(this, args);
    const titles = own && new Set(own.map((f) => `Кадр ${f.number}`));
    const keep = new Set(sceneGroups().filter((group) => group.role === 'overlay').flatMap((group) => group.clip_ids)), all = layers;
    const drawn = own && new Set(sceneGroups().filter((group) => titles.has(group.title)).flatMap((group) => group.clip_ids));
    layers = () => all().map((layer) => ({ ...layer, clips: (layer.clips || []).filter((clip) => clip.kind === 'audio' || keep.has(clip.id) || (drawn && !drawn.has(clip.id))) }));
    try { baseUniversal.apply(this, args); } finally { layers = all; }
    // a seam from another kind of frame (the host's video, a photo, a text) into a Razgon frame: the live player lies
    // under the picture, so the outgoing frame fades out over it, a dissolve (user, 25 November 2026: «29:30… нажимаю
    // play… не показує… перехід»); before, its held last picture covered the player and then vanished, a cut
    if (inside) {
      const into = (state.project?.join_transitions || []).find((join) => join.to_ref === `group:${groupId(inside)}`);
      const from = into && sceneGroups().find((group) => `group:${group.id}` === into.from_ref);
      const span = from && !titles.has(from.title) && joinFrames(into);
      if (span && t >= span.seam && t < span.seam + span.duration) {
        const left = 1 - easedProgress((t - span.seam) / span.duration, 'ease_in_out');
        for (const id of from.clip_ids) { const node = state.previewNodes.get(id); if (node) node.style.opacity = String(Math.max(0, Math.min(Number(node.style.opacity || 1), left))); }
      }
    }
    $('preview-placeholder').hidden = true;
    post();
  };
  const baseRender = renderProject;
  renderProject = function (...args) { if (state.view === 'live') state.view = 'editor'; if (state.project) load(state.project.id); sync(); return baseRender.apply(this, args); };
})();
