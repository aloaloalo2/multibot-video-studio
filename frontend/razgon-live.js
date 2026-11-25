// razgon-live.js — live preview of Razgon 2D episodes inside «Монтаж»: the Razgon player draws the film in real time
// in an iframe over the preview, following the studio playhead, so the timeline can be scrubbed and played without
// waiting for rendered clips. The studio keeps its own timeline and audio. Shown only when the episode folder has
// razgon.json; the backend starts the live server on demand (backend/razgon_live.py).
(() => {
  const live = {};
  // the switch and the quality left the preview with its settings (user, 25 November 2026: «настройки оці прибрав»): the
  // live view is always on, at the quality chosen before (or the middle one)
  const scale = (() => { try { const saved = localStorage.getItem('razgonLiveScale'); return ['0.33', '0.5', '0.75'].includes(saved) ? saved : '0.5'; } catch { return '0.5'; } })();
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
  style.textContent = '.razgon-live-note{position:absolute;inset:0;z-index:30;display:grid;place-content:center;justify-items:center;gap:12px;padding:24px;text-align:center;background:#0a0b0ccc}.razgon-live-note[hidden]{display:none}.razgon-live-note p{margin:0;max-width:520px;color:#e6e7ea;font-size:13.5px;line-height:1.5}' + '#razgon-live-frame,#razgon-live-frame-out{position:absolute;inset:0;width:100%;height:100%;border:0;background:#000;z-index:0;pointer-events:none;transform-origin:50% 50%}#razgon-live-frame-out{visibility:hidden}.razgon-live-on #preview-composition{background:transparent;z-index:1}';
  document.head.append(style);

  const info = () => state.project && live[state.project.id];
  const active = () => !!info()?.url;
  const source = () => `${info().url}?embed=1&scale=${scale}`;
  // the live frame comes into view only with its own moment on the canvas (user, 25 November 2026: «з другого на третій
  // кадр… пригає на якийсь… кадр посередині… а потім… початок»): after a jump of time it waits for the page's «drawn»
  let drawnAt = null, waitingFor = null, waitTimer = null, wasOn = false, lastT = null;
  const reveal = () => { if (waitingFor === null && frame.dataset.wantVisible === '1') frame.style.visibility = ''; };
  let seekTime = null;   // the Razgon time the picture shows: the playhead, or a frame's last moment while a transition fades out of it
  // one drawing a frame of the film, on the export's own moment f/fps: the playback asked for one every screen refresh
  // (about 60 a second) while a film has 25, and Razgon drew most of them twice for nothing (25 November 2026)
  let postedFrame = null, seekWithin = null;
  const post = (force) => {
    if (frame.hidden || !frame.contentWindow) return;
    const fps = state.project?.fps || 25, index = Math.round((seekTime ?? state.playhead) * fps), key = index + (seekWithin ? '|' + seekWithin.join(',') : '');
    if (!force && key === postedFrame) return;
    postedFrame = key; frame.contentWindow.postMessage({ razgon: 'seek', t: index / fps, within: seekWithin }, '*');
  };
  // A live server that went down (the studio restarted, after an update) leaves a black frame: the player says «ready»
  // when it draws, so one that keeps silent is started again (user, 2 November 2026: «код не відтворюється»).
  let ready = false, watch = 0; const retried = new Set();   // one fresh start a project a page
  addEventListener('message', (event) => {
    if (event.source !== frame.contentWindow) return;
    if (event.data?.razgon === 'ready') { ready = true; clearTimeout(watch); showNote(''); post(true); }
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
    if (on && frame.dataset.src !== source()) { frame.src = source(); frame.dataset.src = frame.src; watchStart(state.project.id); }
    if (!on && frame.dataset.src) { frame.removeAttribute('src'); delete frame.dataset.src; }
    // the second player loads with the first, so a seam shows at once while playing
    if (on && frameOut.dataset.src !== source()) { frameOut.src = source(); frameOut.dataset.src = frameOut.src; }
    if (!on && frameOut.dataset.src) { frameOut.removeAttribute('src'); delete frameOut.dataset.src; }
    frame.hidden = frameOut.hidden = !on; if (!on) showNote('');
  }

  // Everything the live view reads about the film's Razgon frames, built once per version of the project and plan: the
  // preview asks for it on every screen refresh, and rebuilt each time (the plan's frames, their groups, the seams around
  // them, and a new layers() function that missed renderUniversalPreview's span cache) it took 8-12 ms of a 16 ms frame on
  // a 514-layer episode (25 November 2026).
  let model = null;
  const razgonModel = () => {
    const project = state.project, plan = state.plan;
    if (model && model.project === project && model.plan === plan) return model;
    const fps = project?.fps || 25, frames = plan?.frames || [], whole = (time) => Math.floor(time * fps + .5 + 1e-8) / fps;
    // Every Razgon frame of the plan with its whole-frame edges, for the seams between two of them.
    const all = frames.filter((f) => f.format === 'razgon_2d').map((f) => ({ ...f, sourceStart: f.start, sourceEnd: f.end, start: whole(f.start), end: whole(f.end) }));
    // A mixed episode (photos, stock, text frames and some Razgon frames, e.g. Alexey Gorbunov's): only its razgon_2d frames
    // are drawn live, and only while the playhead is inside one; the rest of the timeline plays as usual. null: all Razgon.
    const own = all.length && all.length < frames.length ? all : null;
    const groups = sceneGroups(), joins = project?.join_transitions || [], byTitle = new Map();
    for (const group of groups) if (!byTitle.has(group.title)) byTitle.set(group.title, group);
    const info = new Map();
    for (const f of all) {
      const group = byTitle.get(`Кадр ${f.number}`), ref = `group:${group?.id}`;
      const block = group ? groupMembers(group).find((clip) => /^Razgon · кадр/.test(clip.title || '')) || null : null;
      // while a transition fades out of a Razgon frame its last picture stays under the incoming frame, as the export's
      // held tail; the tail ends where the transition and the block end, on whole video frames (joinFrames, clipRenderEnd):
      // the raw seam + duration ended one frame early, and for that frame the block's black base showed over the next
      // picture (user, 25 November 2026: «після переходу просто чорний на один фрейм показується»)
      const tail = joins.find((join) => join.from_ref === ref && Math.abs(join.seam - f.end) < .05);
      const tailEnd = tail ? joinFrames(tail).seam + joinFrames(tail).duration : f.end;
      // a transition into the frame that ends on its seam (out of the host's video, joins.ends_at_seam) shows the frame's
      // first moment from the transition's start
      const lead = joins.find((j) => j.to_ref === ref && joinAhead(j) > 0 && Math.abs(j.seam - f.start) < .05);
      const into = joins.find((join) => join.to_ref === ref);
      const from = into && groups.find((g) => `group:${g.id}` === into.from_ref);
      info.set(f, { block, tailEnd, head: lead ? joinFrames(lead).seam : f.start, into, from });
    }
    // seams between two Razgon frames: the frame before and after each one
    const near = (a, b) => Math.abs(a - b) < 1 / fps / 2;
    for (const f of all) { const own = info.get(f); own.outgoing = all.find((o) => near(o.end, f.start)) || null; own.ahead = all.find((o) => near(o.start, f.end)) || null; }
    // a frame whose row is switched off with its eye is not drawn live either (user, 2 November 2026: «нажав око, але
    // вони не пропали»): the Razgon blocks under the playhead must sit on a row that is seen
    const baseLayers = layers, hiddenClip = new Set(), blocks = [];
    for (const layer of baseLayers()) for (const clip of layer.clips || []) {
      if (layer.hidden) hiddenClip.add(clip.id);
      if (/^Razgon · кадр/.test(clip.title || '')) blocks.push({ clip, start: Number(clip.start), end: Number(clip.start) + Number(clip.duration) });
    }
    const titles = own && new Set(own.map((f) => `Кадр ${f.number}`));
    const keep = new Set(groups.filter((group) => group.role === 'overlay').flatMap((group) => group.clip_ids));
    const drawn = own && new Set(groups.filter((group) => titles.has(group.title)).flatMap((group) => group.clip_ids));
    // the layers the studio still draws over the live player: one function for this version, so the span cache keyed by it holds
    const overLive = baseLayers().map((layer) => ({ ...layer, clips: (layer.clips || []).filter((clip) => clip.kind === 'audio' || keep.has(clip.id) || (drawn && !drawn.has(clip.id))) }));
    model = { project, plan, all, own, info, hiddenClip, blocks, titles, layers: () => overLive };
    return model;
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
  // `within`: the outgoing frame's own edges, so the player draws its last shot on, alive, past the seam (no held picture)
  const outPost = (time, within) => { const fps = state.project?.fps || 25; time = Math.round(time * fps) / fps; const key = time + (within ? '|' + within.join(',') : ''); outWant = [time, within];
    if (!outReady || key === outAt || !frameOut.contentWindow) return; outAt = key; frameOut.contentWindow.postMessage({ razgon: 'seek', t: time, within: within || null }, '*'); };
  frameOut.addEventListener('load', () => { outAt = null; outReady = false; });
  addEventListener('message', (event) => {
    if (event.source !== frameOut.contentWindow || event.data?.razgon !== 'ready') return;
    outReady = true; outAt = null; if (outWant !== null) outPost(...outWant);
  });
  // t inside the transition of a seam between two Razgon frames: the incoming frame in the first player, the outgoing
  // one held at its last moment in the second, each moved by the transition; anything else: the first player as it is
  function seam(t) {
    const { all, info } = razgonModel();
    const incoming = t === null ? null : all.find((f) => t >= f.start && t < f.end), near = incoming && info.get(incoming);
    const outgoing = near?.outgoing;
    // warm up: the frame playing now ends in a seam with a transition into another Razgon frame
    const aheadClip = near?.ahead && near.block;
    if (aheadClip && transitionInfo(aheadClip).outgoing) outPost(incoming.sourceEnd, [incoming.sourceStart, incoming.sourceEnd]);
    const inClip = outgoing && near.block, outClip = outgoing && info.get(outgoing).block;
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
    outPost(outgoing.sourceEnd + (t - outgoing.end), [outgoing.sourceStart, outgoing.sourceEnd]);
  }

  // In live mode the rendered Razgon clips are not decoded at all: the iframe draws the picture under the studio's own
  // overlay layers (the channel plashka group), and the studio keeps time and sound.
  const baseUniversal = renderUniversalPreview;
  renderUniversalPreview = function (...args) {
    const m = razgonModel(), own = m.own, t = state.playhead, content = $('preview-content');
    const head = (f) => m.info.get(f).head, tailEnd = (f) => m.info.get(f).tailEnd;
    const seen = (time) => { let any = false; for (const { clip, start, end } of m.blocks) if (time >= start && time < end) { if (!m.hiddenClip.has(clip.id)) return true; any = true; } return !any; };
    const inside = own && own.find((f) => t >= head(f) && t < f.end), fading = own && !inside && own.find((f) => t >= f.end && t < tailEnd(f));
    const sourceFrame=inside||fading;
    // past the frame's edges (a transition's tail, or an early start) the player draws the frame's edge shot on, alive
    seekTime = sourceFrame ? sourceFrame.sourceStart + (t - sourceFrame.start) : null;
    seekWithin = sourceFrame ? [sourceFrame.sourceStart, sourceFrame.sourceEnd] : null;   // always the frame's own shots and words
    const on = active() && (!own || !!inside || !!fading) && seen(fading ? fading.end - 0.01 : t);
    const jumped = on && (!wasOn || lastT === null || Math.abs(t - lastT) > .25);
    wasOn = on; lastT = t;
    content.classList.toggle('razgon-live-on', on); note.style.visibility = on ? '' : 'hidden';
    frame.dataset.wantVisible = on ? '1' : '';
    if (!on) { frame.style.visibility = 'hidden'; waitingFor = null; clearTimeout(waitTimer);
      // the next Razgon frame within 0.6 s is drawn ahead while hidden, so it comes in on its first moment
      // its first moment is where it comes in: a transition that leads it starts it before its seam (head)
      const next = own && own.find((f) => head(f) > t && head(f) - t < .6);
      if (next && frame.contentWindow && !frame.hidden) { postedFrame = null; frame.contentWindow.postMessage({ razgon: 'seek', t: next.sourceStart + (head(next) - next.start), within: [next.sourceStart, next.sourceEnd] }, '*'); }
    } else if (jumped && !(drawnAt !== null && Math.abs(drawnAt - (seekTime ?? t)) < .2)) {
      frame.style.visibility = 'hidden'; waitingFor = seekTime ?? t; clearTimeout(waitTimer);
      waitTimer = setTimeout(() => { waitingFor = null; reveal(); }, 300);   // a page that never answers still shows
    } else if (waitingFor === null) frame.style.visibility = '';
    seam(on && !fading ? t : null);
    if (!on) return baseUniversal.apply(this, args);
    const all = layers; layers = m.layers;
    try { baseUniversal.apply(this, args); } finally { layers = all; }
    // a seam from another kind of frame (the host's video, a photo, a text) into a Razgon frame: the live player lies
    // under the picture, so the outgoing frame fades out over it, a dissolve (user, 25 November 2026: «29:30… нажимаю
    // play… не показує… перехід»); before, its held last picture covered the player and then vanished, a cut
    if (inside) {
      const { into, from } = m.info.get(inside);
      const span = from && !m.titles.has(from.title) && joinFrames(into);
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
