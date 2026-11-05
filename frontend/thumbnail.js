// thumbnail.js — the magic button on a project card: a YouTube thumbnail (backend/thumbnail_gen.py) from the project's
// title and script, stills of the video's made frames and the author's optional wishes, the only field of the window:
// Claude writes the prompt, Codex draws it. The card button appears once a couple of frames are made. The run goes on
// after the window closes; the card picks up the new picture as its cover when it is ready.
const thumbnailIcon='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m21.6 3.6-1.2-1.2a1.2 1.2 0 0 0-1.7 0L2.4 18.6a1.2 1.2 0 0 0 0 1.7l1.2 1.2a1.2 1.2 0 0 0 1.7 0L21.6 5.4a1.2 1.2 0 0 0 0-1.8M14 7l3 3M5 6v4M19 14v4M10 2v2M7 8H3M21 16h-4M11 3H9"/></svg>';
const thumbnailRuns=new Map(),thumbnailSources=new Map();

const thumbnailFrames=2;
function thumbnailBusy(id){return thumbnailRuns.get(id)?.status==='running';}
// a server from before the count knows nothing about frames: the button stays as it was
function thumbnailReady(project){return project.pictures===undefined || project.pictures>=thumbnailFrames;}

// Every thumbnail made for the episode, newest first, the cover marked; a click makes another one the cover. A new run
// adds one more and keeps the others (user, 1 November 2026: «немає бібліотеки моїх прев'юшок… не видно, що
// додається ще одна»).
function thumbLibrary(id,versions){
  const box=document.createElement('div');box.className='thumb-library';
  if(!versions?.length)return box;
  const url=name=>`/api/projects/${encodeURIComponent(id)}/thumbnails/${encodeURIComponent(name)}`;
  const tag=item=>item.writer==='deepseek'?'<i>DeepSeek</i>':item.writer==='trending'?'<i>Трендове</i>':item.writer==='edit'?`<i title="${esc(item.notes || '')}">Правка v${item.from}</i>`:'';
  box.innerHTML=`<p class="thumb-library-head"><b>Ваші прев’ю</b><span>${versions.length} · натисніть на картинку, щоб зробити її обкладинкою</span></p>
    <div class="thumb-library-grid">${versions.map(item=>`<div class="thumb-tile${item.current?' current':''}" data-name="${esc(item.name)}">
      <button type="button" class="thumb-pick" aria-pressed="${item.current}" title="${item.current?'Зараз обкладинка':'Зробити обкладинкою'}"><img src="${url(item.name)}?v=${Math.round(item.time)}" alt="" loading="lazy"></button>
      <span class="thumb-tile-tags">${item.current?'<em>Обкладинка</em>':''}${tag(item)}</span>
      <small>${item.earlier?`до v${item.number}`:`v${item.number}`}</small>
      <button type="button" class="thumb-edit" title="Внести правку в це прев’ю">Правка</button></div>`).join('')}</div>
    <div class="thumb-edit-box" hidden><label><span class="thumb-edit-title"></span><textarea rows="3" maxlength="1500" placeholder="Наприклад: зроби фон темнішим, а слово DAY 340 більшим і жовтим"></textarea></label>
      <div class="thumb-edit-actions"><button type="button" class="secondary thumb-edit-cancel">Скасувати</button><button type="button" class="primary thumb-edit-send">Внести правку</button></div></div>`;
  const editBox=box.querySelector('.thumb-edit-box');let base=null;
  box.addEventListener('click',async event=>{
    const tile=event.target.closest('.thumb-tile');
    if(event.target.closest('.thumb-edit')&&tile){
      base=tile.dataset.name;editBox.hidden=false;
      box.querySelectorAll('.thumb-tile').forEach(item=>item.classList.toggle('editing',item===tile));
      editBox.querySelector('.thumb-edit-title').textContent=`Що змінити в ${tile.querySelector('small').textContent}? Codex перемалює цю картинку з вашою правкою, а результат додасться новою версією.`;
      editBox.querySelector('textarea').focus();return;
    }
    if(event.target.closest('.thumb-edit-cancel')){editBox.hidden=true;base=null;box.querySelectorAll('.thumb-tile.editing').forEach(item=>item.classList.remove('editing'));return;}
    if(event.target.closest('.thumb-edit-send')){
      const notes=editBox.querySelector('textarea').value.trim();
      if(!notes){status('Напишіть, що змінити в прев’ю.',true);return;}
      const source=thumbnailSources.get(id) || {};
      try{
        const {job}=await api(`/api/projects/${encodeURIComponent(id)}/thumbnail`,'POST',{title:source.title || state.project?.name || '',script:source.script || '',wishes:notes,base});
        thumbnailRuns.set(id,job);
        if(!$('modal-backdrop').hidden&&$('modal-backdrop').classList.contains('thumb-modal-open'))closeModal();
        editBox.hidden=true;showThumbnailState(id);markThumbnailCard(id);pollThumbnail(id);
      }catch(error){status(error.message,true);}
      return;
    }
    if(!event.target.closest('.thumb-pick')||!tile||tile.classList.contains('current'))return;
    try{
      const {versions:next}=await api(`/api/projects/${encodeURIComponent(id)}/thumbnail/choose`,'POST',{name:tile.dataset.name});
      box.replaceWith(thumbLibrary(id,next));
      for(const img of document.querySelectorAll(`.thumb-current[data-project-id="${CSS.escape(id)}"]`))img.src=`/api/projects/${encodeURIComponent(id)}/cover?v=${Date.now()}`;
      if(!state.project&&state.channel)refreshProjects().catch(()=>{});
      status('Обкладинку змінено.');
    }catch(error){status(error.message,true);}
  });
  return box;
}
async function openThumbnail(project){
  let data;
  try{data=await api(`/api/projects/${encodeURIComponent(project.id)}/thumbnail`);}catch(error){status(error.message,true);return;}
  if(data.job)thumbnailRuns.set(project.id,data.job);
  // the title and script go as they are: the window asks only what the author wants to see, and even that may stay empty
  thumbnailSources.set(project.id,{title:data.title,script:data.script});
  modal('Створити нове прев’ю',`
    <label class="thumb-wishes"><span>Побажання <em>необов’язково</em></span><textarea id="thumb-create-wishes" rows="4" maxlength="2000" placeholder="Опишіть ідею для нового прев’ю..."></textarea></label>
    <p id="thumb-state" class="thumb-state" role="status" aria-live="polite"></p>`,
    // «з DeepSeek» is a trial (user, 1 November 2026): DeepSeek writes the prompt instead of Claude, Codex draws the same way
    [{label:'Створити з DeepSeek',run:()=>generateThumbnail(project,'deepseek',$('thumb-create-wishes').value)},
     {label:'Створити з Codex',run:()=>generateThumbnail(project,'trending',$('thumb-create-wishes').value)},
     {label:'Створити з Claude',primary:true,run:()=>generateThumbnail(project,'claude',$('thumb-create-wishes').value)}]);
  const writerIcons=[
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12c3-6 8-6 11-2l6-3-2 6c-2 7-11 7-15-1Z"/><path d="M7 11h.01M13 16l2 3"/></svg>',
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8 6-6 6 6 6m8-12 6 6-6 6m-3-14-2 16"/></svg>',
    projectCostIcons.claude_code];
  [...$('modal-actions').children].forEach((button,index)=>{button.innerHTML=writerIcons[index]+`<span>${esc(button.textContent)}</span>`;button.classList.add('thumb-writer-button');});
  $('modal-actions').children[1].title='Трендове прев’ю: Codex сам продумує ідею за правилами обкладинок';
  $('modal-backdrop').classList.add('thumb-modal-open');
  document.querySelector('#modal-actions .primary')?.classList.add('glow-action');
  showThumbnailState(project.id);
  if(thumbnailBusy(project.id))pollThumbnail(project.id);
}

function showThumbnailState(id){
  const box=$('thumb-state'),run=thumbnailRuns.get(id);
  if(!box)return;
  // the window's button and the tab's: busy while a run goes on, and the tab's also until a couple of frames are made
  for(const button of document.querySelectorAll('#modal-actions button, .thumb-view-generate, .thumb-view-trending'))button.disabled=thumbnailBusy(id) || button.dataset.gated==='1';
  box.dataset.status=run?.status || '';
  const writer=run?.writer==='trending'?'Codex':run?.writer==='deepseek'?'DeepSeek':'Claude';
  box.textContent=!run?'':run.status==='running'?({prompt:`${writer} вибирає момент і пише промпт, зазвичай до хвилини.`,drawing:run.base?'Codex вносить вашу правку, зазвичай 1–3 хвилини.':run.writer==='trending'?'Codex продумує ідею й створює трендове прев’ю.':`Codex малює прев’ю за промптом ${writer}, зазвичай 1–3 хвилини.`}[run.stage] || 'Codex малює прев’ю, зазвичай 1–3 хвилини.')+' Вікно можна закрити, картка оновиться сама.':run.status==='done'?'':`Не вдалося: ${run.error}`;
}

async function generateThumbnail(project,writer='claude',wishes=$('thumb-wishes')?.value || ''){
  const source=thumbnailSources.get(project.id) || {},body={title:source.title || project.name,script:source.script || '',wishes,writer};
  try{
    if(writer==='trending'){
      const available=await api(`/api/projects/${encodeURIComponent(project.id)}/thumbnail`);
      if(!available.writers?.includes('trending'))throw new Error('Трендове прев’ю стане доступним після безпечного перезапуску студії. Зараз триває робота.');
    }
    const {job}=await api(`/api/projects/${encodeURIComponent(project.id)}/thumbnail`,'POST',body);
    thumbnailRuns.set(project.id,job);
    // the window closes once the wishes are sent: the card behind it shows «Малюємо прев’ю» while the picture is made
    if(!$('modal-backdrop').hidden&&$('modal-backdrop').classList.contains('thumb-modal-open'))closeModal();
    showThumbnailState(project.id);markThumbnailCard(project.id);pollThumbnail(project.id);
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
  veil.querySelector('small').textContent=stage==='prompt'?`${thumbnailRuns.get(id)?.writer==='deepseek'?'DeepSeek':'Claude'} пише промпт`:stage==='drawing'?'Codex малює картинку':'Зазвичай 1–3 хвилини';
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
    // only this project's picture: another episode's window may be open by now
    const frame=document.querySelector(`.thumb-view-frame[data-project-id="${CSS.escape(id)}"]`);
    const img=document.querySelector(`.thumb-current[data-project-id="${CSS.escape(id)}"]`);if(img)img.src=`/api/projects/${encodeURIComponent(id)}/cover?v=${Date.now()}`;
    if(frame&&!img)frame.innerHTML=`<img class="thumb-current" data-project-id="${esc(id)}" src="/api/projects/${encodeURIComponent(id)}/cover?v=${Date.now()}" alt="Прев’ю ролика">`;
    const again=document.querySelector('.thumb-view-generate');if(again)again.textContent='Згенерувати ще одне';
    // the tab's library takes in the new picture
    const view=document.getElementById('project-thumb');if(view&&!view.hidden&&view.dataset.project===id){delete view.dataset.project;renderThumbView();}
    if(!state.project&&state.channel)refreshProjects().catch(()=>{});
  }
}

// The «Прев’ю» tab of an episode, after «План ролика» and «Монтаж»: the current thumbnail large, the optional wishes and
// «Згенерувати». The address /preview is used once the server knows it; before a restart the tab keeps the project's own.
let thumbRoute='';
const thumbnailPictures=new Map();
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
  // the server counts made frames as it gates the run: pictures on the timeline and frames drawn as code alike
  const ready=(thumbnailPictures.get(project.id) ?? thumbnailFramesMade(project))>=thumbnailFrames;
  for(const button of section.querySelectorAll('.thumb-view-generate, .thumb-view-trending')){
    button.dataset.gated=ready?'':'1';button.disabled=!ready || thumbnailBusy(project.id);
  }
  section.querySelector('.thumb-view-gate').hidden=ready;
}
async function buildThumbView(section,project){
  const id=project.id;section.dataset.project=id;
  section.innerHTML=`<div class="thumb-view thumb-studio">
    <header class="thumb-studio-head"><h1>Прев’ю</h1></header>
    <div class="thumb-workspace"><div class="thumb-hero"><div class="thumb-view-frame" data-project-id="${esc(id)}"><p class="thumb-view-empty">Прев’ю ще немає</p><a class="thumb-preview-download" title="Завантажити прев’ю" aria-label="Завантажити прев’ю" hidden><svg viewBox="0 0 24 24"><path d="M12 3v12m-4-4 4 4 4-4M4 16v5h16v-5"/></svg></a></div>
      <div class="thumb-preview-meta"><span class="thumb-preview-language">Оригінал</span><div><button type="button" class="secondary thumb-set-cover" hidden>Зробити обкладинкою</button></div></div></div>
    <aside class="thumb-compose"><span class="thumb-compose-icon">${thumbnailIcon}</span><h2>Нова ідея</h2>
      <label class="thumb-wishes"><span>Побажання <em>необов’язково</em></span><textarea id="thumb-wishes" rows="4" maxlength="2000" placeholder="Опишіть ідею для нового прев’ю..."></textarea></label>
      <div class="thumb-view-actions"><button type="button" class="primary thumb-view-generate">Згенерувати</button><button type="button" class="secondary thumb-view-trending">Трендове прев’ю</button><p id="thumb-state" class="thumb-state" role="status" aria-live="polite"></p></div>
      <p class="thumb-view-gate" hidden>Для прев’ю потрібні хоча б ${thumbnailFrames} готові кадри ролика.</p></aside></div>
    <section class="thumb-collection"><header><h2>Галерея</h2><div class="thumb-filters" role="group" aria-label="Мова прев’ю"></div></header><div class="thumb-gallery-grid"></div></section></div>`;
  section.querySelector('.thumb-view-generate').addEventListener('click',()=>generateThumbnail(state.project));
  section.querySelector('.thumb-view-trending').addEventListener('click',()=>generateThumbnail(state.project,'trending'));
  if(!thumbRoute)fetch(`/channels/${state.channel.id}/projects/${id}/preview`,{method:'GET'}).then(response=>{if(response.ok&&response.headers.get('content-type')?.includes('text/html')){thumbRoute='/preview';if(state.view==='thumb')syncRoute(true);}}).catch(()=>{});
  let data;
  try{data=await api(`/api/projects/${encodeURIComponent(id)}/thumbnail`);}catch(error){status(error.message,true);return;}
  if(section.dataset.project!==id)return;
  thumbnailSources.set(id,{title:data.title,script:data.script});
  if(Number.isFinite(data.pictures))thumbnailPictures.set(id,data.pictures);
  if(data.job)thumbnailRuns.set(id,data.job);
  section.querySelector('.thumb-view-generate').textContent=data.versions?.length?'Згенерувати ще одне':'Згенерувати';
  buildThumbnailGallery(section,project,data);
  renderThumbView();                      // the gate again, now with the server's count of made frames
  showThumbnailState(id);markThumbnailCard(id);if(thumbnailBusy(id))pollThumbnail(id);
}
$('view-thumb')?.addEventListener('click',()=>setProjectView('thumb'));


function buildThumbnailGallery(section,project,data){
  const id=project.id,base=`/api/projects/${encodeURIComponent(id)}`;
  const flags={en:'🇬🇧',uk:'🇺🇦',ru:'🇷🇺',de:'🇩🇪',es:'🇪🇸',fr:'🇫🇷',pt:'🇵🇹',it:'🇮🇹',pl:'🇵🇱',tr:'🇹🇷',nl:'🇳🇱',hi:'🇮🇳',ar:'🇸🇦',ja:'🇯🇵',ko:'🇰🇷',zh:'🇨🇳',id:'🇮🇩',cs:'🇨🇿',ro:'🇷🇴',kk:'🇰🇿'};
  let versions=data.versions || [];
  let items=[...versions.map(v=>({key:v.name,code:'original',label:'Оригінал',detail:`v${v.number}`,current:v.current,url:`${base}/thumbnails/${encodeURIComponent(v.name)}?v=${Math.round(v.time)}`,name:v.name,flag:flags[data.original_language] || '◈'})),
    ...(data.translated_thumbnails || []).map(v=>({key:`${v.code}:${v.version_name || 'current'}`,code:v.code,label:v.name,detail:v.number?`v${v.number}`:'Переклад',url:v.version_name?`${base}/languages/${v.code}/thumbnails/${encodeURIComponent(v.version_name)}?v=${v.stamp}`:`${base}/languages/${v.code}/file/thumbnail?v=${v.stamp}`,flag:flags[v.code] || '🌐'}))];
  if(!versions.length&&data.preview)items.unshift({key:'cover',code:'original',label:'Оригінал',detail:'Обкладинка',current:true,url:`${base}/cover?v=${Date.now()}`,flag:flags[data.original_language] || '◈'});
  let selected=items.find(x=>x.current)?.key || items[0]?.key,filter='all';
  const grid=section.querySelector('.thumb-gallery-grid'),filters=section.querySelector('.thumb-filters'),frame=section.querySelector('.thumb-view-frame'),download=section.querySelector('.thumb-preview-download'),choose=section.querySelector('.thumb-set-cover');
  const draw=()=>{
    const codes=['all',...new Set(items.map(x=>x.code))];
    filters.innerHTML=codes.map(code=>`<button type="button" data-code="${code}" aria-pressed="${code===filter}">${code==='all'?'Усі':code==='original'?'Оригінал':`${flags[code] || '🌐'} ${esc(items.find(x=>x.code===code).label)}`}</button>`).join('');
    const visible=items.filter(x=>filter==='all'||x.code===filter);
    grid.innerHTML=visible.length?visible.map(item=>`<button type="button" class="thumb-gallery-card${item.key===selected?' selected':''}" data-key="${esc(item.key)}" aria-pressed="${item.key===selected}" aria-label="Показати ${esc(item.label)} ${esc(item.detail)}"><span class="thumb-gallery-image"><img src="${item.url}" alt="${esc(item.label)} ${esc(item.detail)}" loading="lazy">${item.current?'<em>Обкладинка</em>':''}</span><span class="thumb-gallery-caption"><b>${item.flag} ${esc(item.label)}</b><small>${esc(item.detail)}</small></span></button>`).join(''):'<p class="thumb-gallery-empty">Тут з’являться згенеровані прев’ю та їхні переклади.</p>';
  };
  const show=key=>{
    const item=items.find(x=>x.key===key);if(!item)return;selected=key;
    frame.replaceChildren();const img=document.createElement('img');img.src=item.url;img.alt=`${item.label} ${item.detail}`;frame.append(img,download);
    section.querySelector('.thumb-preview-language').textContent=`${item.flag} ${item.label} · ${item.detail}`;
    download.hidden=false;download.href=item.url+`&download=${encodeURIComponent(`Прев’ю ${item.label}.png`)}`;download.download=`Прев’ю ${item.label}.png`;
    choose.hidden=!item.name||item.current;draw();
  };
  filters.addEventListener('click',event=>{const button=event.target.closest('button[data-code]');if(!button)return;filter=button.dataset.code;const first=items.find(x=>x.code===filter);if(filter!=='all'&&first)show(first.key);else draw();});
  grid.addEventListener('click',event=>{const button=event.target.closest('[data-key]');if(button)show(button.dataset.key);});
  choose.addEventListener('click',async()=>{
    const item=items.find(x=>x.key===selected);if(!item?.name)return;choose.disabled=true;
    try{const result=await api(`${base}/thumbnail/choose`,'POST',{name:item.name});for(const current of items)current.current=result.versions.some(v=>v.name===current.name&&v.current);show(selected);status('Обкладинку збережено.');}
    catch(error){status(error.message,true);}finally{choose.disabled=false;}
  });
  if(selected)show(selected);else draw();
}
