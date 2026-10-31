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
  const style = document.createElement('style');
  style.textContent = '.razgon-live-tools{display:inline-flex;gap:6px;align-items:center}.razgon-live-tools button,.razgon-live-tools select{background:#24252a;color:inherit;border:1px solid #3f4046;border-radius:9px;padding:4px 9px;font:inherit;font-size:12px;cursor:pointer}.razgon-live-tools button[aria-pressed="true"]{border-color:#f0b429;color:#f0b429}.razgon-live-tools select[hidden]{display:none}#razgon-live-frame{position:absolute;inset:0;width:100%;height:100%;border:0;background:#000;z-index:0;pointer-events:none}.razgon-live-on #preview-composition{background:transparent;z-index:1}';
  document.head.append(style);

  const info = () => state.project && live[state.project.id];
  const active = () => !!(info()?.url && read(KEY, '1') === '1');
  const source = () => `${info().url}?embed=1&scale=${quality.value}`;
  let seekTime = null;   // the Razgon time the picture shows: the playhead, or a frame's last moment while a transition fades out of it
  const post = () => { if (!frame.hidden && frame.contentWindow) frame.contentWindow.postMessage({ razgon: 'seek', t: seekTime ?? state.playhead }, '*'); };
  addEventListener('message', (event) => { if (event.source === frame.contentWindow && event.data?.razgon === 'ready') post(); });

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
      live[id] = { available: false }; if (error.httpStatus !== 423) status(error.message, true);
      setTimeout(() => { delete live[id]; if (state.project?.id === id) { load(id); sync(); } }, 4000);
    }
    sync(); if (state.project?.id === id) renderPreview();
  }
  function sync() {
    const on = active();
    tools.hidden = !info()?.available; quality.hidden = !on;
    toggle.setAttribute('aria-pressed', String(on));
    if (on && frame.dataset.src !== source()) { frame.src = source(); frame.dataset.src = frame.src; }
    if (!on && frame.dataset.src) { frame.removeAttribute('src'); delete frame.dataset.src; }
    frame.hidden = !on;
  }
  toggle.addEventListener('click', () => { write(KEY, active() ? '0' : '1'); sync(); renderPreview(); });
  quality.addEventListener('change', () => { write(QKEY, quality.value); sync(); });

  // A mixed episode (photos, stock, text frames and some Razgon frames, e.g. Alexey Gorbunov's): only its razgon_2d frames
  // are drawn live, and only while the playhead is inside one; the rest of the timeline plays as usual. null: all Razgon.
  const razgonFrames = () => { const frames = state.plan?.frames || [], own = frames.filter((f) => f.format === 'razgon_2d'); return own.length && own.length < frames.length ? own : null; };

  // In live mode the rendered Razgon clips are not decoded at all: the iframe draws the picture under the studio's own
  // overlay layers (the channel plashka group), and the studio keeps time and sound.
  const baseUniversal = renderUniversalPreview;
  renderUniversalPreview = function (...args) {
    const own = razgonFrames(), t = state.playhead, content = $('preview-content');
    // while a transition fades out of a Razgon frame its last picture stays under the incoming frame, as the export's held tail
    const groupId = (f) => sceneGroups().find((group) => group.title === `Кадр ${f.number}`)?.id;
    const tail = (f) => (state.project?.join_transitions || []).find((join) => join.from_ref === `group:${groupId(f)}` && Math.abs(join.seam - f.end) < .05);
    const inside = own && own.find((f) => t >= f.start && t < f.end), fading = own && !inside && own.find((f) => t >= f.end && t < f.end + (tail(f)?.duration || 0));
    seekTime = fading ? fading.end - 1 / (state.project?.fps || 25) : null;
    const on = active() && (!own || !!inside || !!fading);
    content.classList.toggle('razgon-live-on', on); frame.style.visibility = on ? '' : 'hidden';
    if (!on) return baseUniversal.apply(this, args);
    const titles = own && new Set(own.map((f) => `Кадр ${f.number}`));
    const keep = new Set(sceneGroups().filter((group) => group.role === 'overlay').flatMap((group) => group.clip_ids)), all = layers;
    const drawn = own && new Set(sceneGroups().filter((group) => titles.has(group.title)).flatMap((group) => group.clip_ids));
    layers = () => all().map((layer) => ({ ...layer, clips: (layer.clips || []).filter((clip) => clip.kind === 'audio' || keep.has(clip.id) || (drawn && !drawn.has(clip.id))) }));
    try { baseUniversal.apply(this, args); } finally { layers = all; }
    $('preview-placeholder').hidden = true;
    post();
  };
  const baseRender = renderProject;
  renderProject = function (...args) { if (state.view === 'live') state.view = 'editor'; if (state.project) load(state.project.id); sync(); return baseRender.apply(this, args); };
})();
