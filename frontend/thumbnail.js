// thumbnail.js — the magic button on a project card: a YouTube thumbnail (backend/thumbnail_gen.py) from the project's
// title (editable here), its script (shown folded, read only), the author's wishes and stills of the video's made frames:
// Claude writes the prompt, Codex draws it. The button stays grey until a couple of frames are made. The run goes on
// after the window closes; the card picks up the new picture as its cover when it is ready.
const thumbnailIcon='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m21.6 3.6-1.2-1.2a1.2 1.2 0 0 0-1.7 0L2.4 18.6a1.2 1.2 0 0 0 0 1.7l1.2 1.2a1.2 1.2 0 0 0 1.7 0L21.6 5.4a1.2 1.2 0 0 0 0-1.8M14 7l3 3M5 6v4M19 14v4M10 2v2M7 8H3M21 16h-4M11 3H9"/></svg>';
const thumbnailRuns=new Map(),thumbnailScripts=new Map();

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
  thumbnailScripts.set(project.id,data.script);
  modal('Прев’ю ролика',`<p class="thumb-note">Прев’ю створюється за сценарієм, заголовком і готовими кадрами ролику, з яких береться стиль. Заголовок можна відредагувати тут, а в побажаннях описати, що хочете побачити. Промпт пише Claude, малює ChatGPT через Codex, один варіант за раз.</p>${current}
    <label>Заголовок<input id="thumb-title" type="text" maxlength="200" value="${esc(data.title)}"></label>
    <details class="thumb-script"><summary>Сценарій${data.script?'':' (ще немає)'}</summary><div class="thumb-script-text">${esc(data.script) || 'Сценарію в проєкті ще немає: прев’ю намалюється за заголовком і побажаннями.'}</div></details>
    <label>Побажання<textarea id="thumb-wishes" rows="3" maxlength="2000" placeholder="Наприклад: крупно обличчя героя в шоці, за ним Земля, велике слово DAY 340"></textarea></label>
    <p id="thumb-state" class="thumb-state" role="status" aria-live="polite"></p>`,
    [{label:'Згенерувати',primary:true,run:()=>generateThumbnail(project)}]);
  $('modal-backdrop').classList.add('thumb-modal-open');
  showThumbnailState(project.id);
  if(thumbnailBusy(project.id))pollThumbnail(project.id);
}

function showThumbnailState(id){
  const box=$('thumb-state'),run=thumbnailRuns.get(id),button=document.querySelector('#modal-actions .primary');
  if(!box)return;
  if(button)button.disabled=thumbnailBusy(id);
  box.dataset.status=run?.status || '';
  box.textContent=!run?'':run.status==='running'?(run.stage==='prompt'?'Claude вибирає момент і пише промпт, зазвичай до хвилини.':'Codex малює прев’ю за промптом Claude, зазвичай 1–3 хвилини.')+' Вікно можна закрити, картка оновиться сама.':run.status==='done'?`Готово: ${run.file}. Воно вже стоїть обкладинкою проєкту й лежить у папці випуску як «Превью.png».`:`Не вдалося: ${run.error}`;
}

async function generateThumbnail(project){
  const body={title:$('thumb-title').value,script:thumbnailScripts.get(project.id) || '',wishes:$('thumb-wishes').value};
  if(!body.title.trim()){status('Вкажіть заголовок.',true);return;}
  try{
    const {job}=await api(`/api/projects/${encodeURIComponent(project.id)}/thumbnail`,'POST',body);
    thumbnailRuns.set(project.id,job);showThumbnailState(project.id);markThumbnailCard(project.id);pollThumbnail(project.id);
  }catch(error){status(error.message,true);}
}

function markThumbnailCard(id){
  const card=document.querySelector(`.project-card[data-project-id="${CSS.escape(id)}"]`);
  card?.classList.toggle('thumb-running',thumbnailBusy(id));
}

async function pollThumbnail(id){
  await new Promise(resolve=>setTimeout(resolve,5000));
  try{const data=await api(`/api/projects/${encodeURIComponent(id)}/thumbnail`);if(data.job)thumbnailRuns.set(id,data.job);}catch{}
  showThumbnailState(id);markThumbnailCard(id);
  if(thumbnailBusy(id)){pollThumbnail(id);return;}
  if(thumbnailRuns.get(id)?.status==='done'){
    const img=document.querySelector('.thumb-current');if(img)img.src=`/api/projects/${encodeURIComponent(id)}/cover?v=${Date.now()}`;
    if(!state.project&&state.channel)refreshProjects().catch(()=>{});
  }
}
