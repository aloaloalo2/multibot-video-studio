// thumbnail.js — the magic button on a project card: a YouTube thumbnail (backend/thumbnail_gen.py) from the project's
// title and script, stills of the video's made frames and the author's optional wishes, the only field of the window:
// Claude writes the prompt, Codex draws it. The button stays grey until a couple of frames are made. The run goes on
// after the window closes; the card picks up the new picture as its cover when it is ready.
const thumbnailIcon='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m21.6 3.6-1.2-1.2a1.2 1.2 0 0 0-1.7 0L2.4 18.6a1.2 1.2 0 0 0 0 1.7l1.2 1.2a1.2 1.2 0 0 0 1.7 0L21.6 5.4a1.2 1.2 0 0 0 0-1.8M14 7l3 3M5 6v4M19 14v4M10 2v2M7 8H3M21 16h-4M11 3H9"/></svg>';
const thumbnailRuns=new Map(),thumbnailSources=new Map();

const thumbnailFrames=2;
function thumbnailBusy(id){return thumbnailRuns.get(id)?.status==='running';}
// a server from before the count knows nothing about frames: the button stays as it was
function thumbnailReady(project){return project.pictures===undefined || project.pictures>=thumbnailFrames;}
function thumbnailWaits(button){
  const note=`Прев’ю можна створити, коли готові хоча б ${thumbnailFrames} кадри ролику: з них береться стиль.`;
  button.classList.add('is-off');button.setAttribute('aria-disabled','true');button.title=note;
  button.addEventListener('click',event=>{event.stopImmediatePropagation();status(note,true);},{capture:true});
}

async function openThumbnail(project){
  let data;
  try{data=await api(`/api/projects/${encodeURIComponent(project.id)}/thumbnail`);}catch(error){status(error.message,true);return;}
  if(data.job)thumbnailRuns.set(project.id,data.job);
  const current=data.preview?`<img class="thumb-current" src="/api/projects/${encodeURIComponent(project.id)}/cover?v=${Date.now()}" alt="Поточне прев’ю">`:'';
  // the title and script go as they are: the window asks only what the author wants to see, and even that may stay empty
  thumbnailSources.set(project.id,{title:data.title,script:data.script});
  modal('Прев’ю ролика',`${current}
    <label class="thumb-wishes"><span>Побажання <em>необов’язково</em></span><textarea id="thumb-wishes" rows="4" maxlength="2000" placeholder="Наприклад: крупно обличчя героя в шоці, велике слово DAY 340"></textarea></label>
    <p id="thumb-state" class="thumb-state" role="status" aria-live="polite"></p>`,
    [{label:'Згенерувати',primary:true,run:()=>generateThumbnail(project)}]);
  $('modal-backdrop').classList.add('thumb-modal-open');
  document.querySelector('#modal-actions .primary')?.classList.add('glow-action');
  showThumbnailState(project.id);
  if(thumbnailBusy(project.id))pollThumbnail(project.id);
}

function showThumbnailState(id){
  const box=$('thumb-state'),run=thumbnailRuns.get(id);
  if(!box)return;
  // the window's button and the tab's: busy while a run goes on, and the tab's also until a couple of frames are made
  for(const button of document.querySelectorAll('#modal-actions .primary, .thumb-view-generate'))button.disabled=thumbnailBusy(id) || button.dataset.gated==='1';
  box.dataset.status=run?.status || '';
  box.textContent=!run?'':run.status==='running'?({prompt:'Claude вибирає момент і пише промпт, зазвичай до хвилини.',drawing:'Codex малює прев’ю за промптом Claude, зазвичай 1–3 хвилини.'}[run.stage] || 'Codex малює прев’ю, зазвичай 1–3 хвилини.')+' Вікно можна закрити, картка оновиться сама.':run.status==='done'?`Готово: ${run.file}. Воно вже стоїть обкладинкою проєкту й лежить у папці випуску як «Превью.png».`:`Не вдалося: ${run.error}`;
}

async function generateThumbnail(project){
  const source=thumbnailSources.get(project.id) || {},body={title:source.title || project.name,script:source.script || '',wishes:$('thumb-wishes').value};
  try{
    const {job}=await api(`/api/projects/${encodeURIComponent(project.id)}/thumbnail`,'POST',body);
    thumbnailRuns.set(project.id,job);showThumbnailState(project.id);markThumbnailCard(project.id);pollThumbnail(project.id);
  }catch(error){status(error.message,true);}
}

// While a thumbnail is made, its card dims under a slow light sweep with one pill in the middle that says which half
// of the work is going on; the title and buttons stay readable above it.
function markThumbnailCard(id){
  const card=document.querySelector(`.project-card[data-project-id="${CSS.escape(id)}"], .thumb-view-frame[data-project-id="${CSS.escape(id)}"]`);if(!card)return;
  const busy=thumbnailBusy(id);card.classList.toggle('thumb-running',busy);
  let veil=card.querySelector('.thumb-progress');
  if(!busy){veil?.remove();return;}
  if(!veil){veil=document.createElement('div');veil.className='thumb-progress';veil.setAttribute('role','status');
    veil.innerHTML=`<span class="thumb-progress-pill">${typeof exportSpinner==='string'?exportSpinner:''}<span><b>Малюємо прев’ю</b><small></small></span></span>`;card.append(veil);}
  const stage=thumbnailRuns.get(id)?.stage;
  veil.querySelector('small').textContent=stage==='prompt'?'Claude пише промпт':stage==='drawing'?'Codex малює картинку':'Зазвичай 1–3 хвилини';
}

// After a reload the page knows no run: each episode's card asks once whether its thumbnail is being made right now.
const thumbnailAsked=new Set(),thumbnailPolling=new Set();
function watchThumbnails(projects){
  for(const project of projects){
    if(!project.episode_path)continue;
    if(thumbnailRuns.has(project.id)){markThumbnailCard(project.id);continue;}
    if(thumbnailAsked.has(project.id))continue;
    thumbnailAsked.add(project.id);
    api(`/api/projects/${encodeURIComponent(project.id)}/thumbnail`).then(data=>{
      if(!data.job)return;
      thumbnailRuns.set(project.id,data.job);markThumbnailCard(project.id);
      if(thumbnailBusy(project.id))pollThumbnail(project.id);
    }).catch(()=>{});
  }
}

// One watcher per project, however many places start it: the card and the window read the same run.
async function pollThumbnail(id){
  if(thumbnailPolling.has(id))return;
  thumbnailPolling.add(id);
  try{
    do{
      await new Promise(resolve=>setTimeout(resolve,5000));
      try{const data=await api(`/api/projects/${encodeURIComponent(id)}/thumbnail`);if(data.job)thumbnailRuns.set(id,data.job);}catch{}
      showThumbnailState(id);markThumbnailCard(id);
    }while(thumbnailBusy(id));
  }finally{thumbnailPolling.delete(id);}
  if(thumbnailRuns.get(id)?.status==='done'){
    const img=document.querySelector('.thumb-current');if(img)img.src=`/api/projects/${encodeURIComponent(id)}/cover?v=${Date.now()}`;
    const frame=document.querySelector(`.thumb-view-frame[data-project-id="${CSS.escape(id)}"]`);
    if(frame&&!img)frame.innerHTML=`<img class="thumb-current" src="/api/projects/${encodeURIComponent(id)}/cover?v=${Date.now()}" alt="Прев’ю ролику">`;
    const again=document.querySelector('.thumb-view-generate');if(again)again.textContent='Згенерувати нове';
    if(!state.project&&state.channel)refreshProjects().catch(()=>{});
  }
}

// The «Прев’ю» tab of an episode, after «План ролика» and «Монтаж»: the current thumbnail large, the optional wishes and
// «Згенерувати». The address /preview is used once the server knows it; before a restart the tab keeps the project's own.
let thumbRoute='';
function thumbnailFramesMade(project){
  return (project?.tracks || []).flatMap(track=>track.clips || []).filter(clip=>['video','image'].includes(clip.kind)&&!/Логотип|Плашка/.test(clip.title || '')).length;
}
function renderThumbView(){
  const tab=$('view-thumb'),section=$('project-thumb');if(!tab||!section)return;
  const project=state.project,open=!!project&&state.view==='thumb';
  tab.hidden=!project?.episode_path;tab.classList.toggle('active',open);tab.setAttribute('aria-pressed',String(open));
  section.hidden=!open;
  if(!open){if(section.childElementCount)section.replaceChildren();delete section.dataset.project;return;}
  if(section.dataset.project!==project.id)buildThumbView(section,project);
  const ready=thumbnailFramesMade(project)>=thumbnailFrames,button=section.querySelector('.thumb-view-generate');
  button.dataset.gated=ready?'':'1';button.disabled=!ready || thumbnailBusy(project.id);
  section.querySelector('.thumb-view-gate').hidden=ready;
}
async function buildThumbView(section,project){
  const id=project.id;section.dataset.project=id;
  section.innerHTML=`<div class="thumb-view"><h1>Прев’ю</h1>
    <div class="thumb-view-frame" data-project-id="${esc(id)}"><p class="thumb-view-empty">Прев’ю ще немає</p></div>
    <label class="thumb-wishes"><span>Побажання <em>необов’язково</em></span><textarea id="thumb-wishes" rows="3" maxlength="2000" placeholder="Наприклад: крупно обличчя героя в шоці, велике слово DAY 340"></textarea></label>
    <div class="thumb-view-actions"><p id="thumb-state" class="thumb-state" role="status" aria-live="polite"></p><button type="button" class="primary glow-action thumb-view-generate">Згенерувати</button></div>
    <p class="thumb-view-gate" hidden>Прев’ю можна створити, коли готові хоча б ${thumbnailFrames} кадри ролику: з них береться стиль.</p></div>`;
  section.querySelector('.thumb-view-generate').addEventListener('click',()=>generateThumbnail(state.project));
  if(!thumbRoute)fetch(`/channels/${state.channel.id}/projects/${id}/preview`,{method:'GET'}).then(response=>{if(response.ok&&response.headers.get('content-type')?.includes('text/html')){thumbRoute='/preview';if(state.view==='thumb')syncRoute(true);}}).catch(()=>{});
  let data;
  try{data=await api(`/api/projects/${encodeURIComponent(id)}/thumbnail`);}catch(error){status(error.message,true);return;}
  if(section.dataset.project!==id)return;
  thumbnailSources.set(id,{title:data.title,script:data.script});
  if(data.job)thumbnailRuns.set(id,data.job);
  if(data.preview)section.querySelector('.thumb-view-frame').innerHTML=`<img class="thumb-current" src="/api/projects/${encodeURIComponent(id)}/cover?v=${Date.now()}" alt="Прев’ю ролику">`;
  section.querySelector('.thumb-view-generate').textContent=data.preview?'Згенерувати нове':'Згенерувати';
  showThumbnailState(id);markThumbnailCard(id);if(thumbnailBusy(id))pollThumbnail(id);
}
$('view-thumb')?.addEventListener('click',()=>setProjectView('thumb'));
