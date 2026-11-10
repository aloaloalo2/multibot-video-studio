// thumbnail.js — the magic button on a project card: a YouTube thumbnail (backend/thumbnail_gen.py) from the project's
// title and script, stills of the video's made frames and the author's optional wishes, the only field of the window:
// Claude writes the prompt, Codex draws it. The card button appears once a couple of frames are made. The run goes on
// after the window closes; the card picks up the new picture as its cover when it is ready.
const thumbnailIcon='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m21.6 3.6-1.2-1.2a1.2 1.2 0 0 0-1.7 0L2.4 18.6a1.2 1.2 0 0 0 0 1.7l1.2 1.2a1.2 1.2 0 0 0 1.7 0L21.6 5.4a1.2 1.2 0 0 0 0-1.8M14 7l3 3M5 6v4M19 14v4M10 2v2M7 8H3M21 16h-4M11 3H9"/></svg>';
const thumbnailRuns=new Map(),thumbnailSources=new Map();

const thumbnailFrames=2;
function thumbnailBusy(id){return thumbnailRuns.get(id)?.status==='running';}

// Every thumbnail made for the episode, newest first, the cover marked; a click makes another one the cover. A new run
// adds one more and keeps the others (user, 1 November 2026: «немає бібліотеки моїх прев'юшок… не видно, що
// додається ще одна»).
async function openThumbnail(project){
  let data;
  try{data=await api(`/api/projects/${encodeURIComponent(project.id)}/thumbnail`);}catch(error){status(error.message,true);return;}
  if(data.job)thumbnailRuns.set(project.id,data.job);
  // the title and script go as they are: the window asks only what the author wants to see, and even that may stay empty
  thumbnailSources.set(project.id,{title:data.title,script:data.script,reference_selection:data.reference_selection});
  modal('New Preview',`
    ${data.reference_selection?`<div class="thumb-mode-switch episode-entry-options" id="thumb-mode-switch" role="group" aria-label="Спосіб створення прев’ю"><button type="button" data-thumb-mode="new">${thumbnailIcon}<span>Нове прев’ю</span></button><button type="button" data-thumb-mode="clone"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 13a5 5 0 0 0 7.07 0l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.07 0l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg><span>Клонувати прев’ю</span></button></div><div class="thumb-reference-field" id="thumb-reference-field" hidden><label for="thumb-reference-url">Посилання на YouTube</label><div class="episode-reference-input">${episodeIcon('link')}<input id="thumb-reference-url" type="url" placeholder="Вставте посилання на YouTube" value="${esc(data.clone_reference?.url || '')}"></div><small id="thumb-reference-state" role="status" hidden></small></div>`:''}
    <div class="thumb-brief-layout" id="thumb-brief-layout"><figure class="thumb-reference-preview" id="thumb-reference-preview" hidden><figcaption id="thumb-reference-caption">Прев’ю конкурента</figcaption><img id="thumb-reference-image" alt="Прев’ю конкурента" hidden></figure><label class="thumb-wishes"><span>Побажання <em>необов’язково</em></span><textarea id="thumb-create-wishes" rows="4" maxlength="2000" placeholder="Вкажіть побажання для нового прев’ю…"></textarea></label></div>
    ${data.hero_reference?'<label class="thumb-hero-choice"><input id="thumb-use-hero" type="checkbox" checked>Головний герой</label>':''}
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
  if(data.hero_reference)$('modal-actions').prepend($('thumb-use-hero').closest('label'));
  $('modal-title').innerHTML=`${thumbnailIcon}<span>New Preview</span>`;
  $('modal-backdrop').dataset.thumbnailProject=project.id;
  $('modal-backdrop').classList.add('thumb-modal-open');
  document.querySelector('#modal-actions .primary')?.classList.add('glow-action');
  if(data.reference_selection){
    setupThumbnailModes(project,data);
    $('modal-title').after($('thumb-mode-switch'));
  }
  else delete $('modal-backdrop').dataset.thumbnailMode;
  showThumbnailState(project.id);
  if(thumbnailBusy(project.id))pollThumbnail(project.id);
}

function setupThumbnailModes(project,data){
  const backdrop=$('modal-backdrop'),buttons=[...backdrop.querySelectorAll('[data-thumb-mode]')];
  const field=$('thumb-reference-url'),preview=$('thumb-reference-preview'),image=$('thumb-reference-image'),caption=$('thumb-reference-caption');
  const source=thumbnailSources.get(project.id);
  let timer,version=0,loadingUrl='';
  $('modal-body').channelSettingsCleanup=()=>{clearTimeout(timer);version++;$('thumb-mode-switch')?.remove();$('modal-actions').hidden=false;};
  const referenceState=$('thumb-reference-state');
  const note=text=>{referenceState.textContent=text;referenceState.hidden=!text;};
  const updateReferenceView=()=>{
    const cloning=backdrop.dataset.thumbnailMode==='clone';
    const ready=!!(source.reference?.id&&source.reference?.thumbnail_url&&source.referenceUrl===field.value.trim());
    const awaiting=cloning&&!ready;
    preview.hidden=!cloning||!ready;
    $('thumb-brief-layout').hidden=awaiting;
    $('modal-actions').hidden=awaiting;
    $('thumb-state').hidden=awaiting;
    $('thumb-brief-layout').classList.toggle('has-reference',cloning&&ready);
    for(const [index,button] of [...backdrop.querySelectorAll('#modal-actions button')].entries()){
      button.dataset.referenceMissing=cloning&&!ready?'1':'';
      button.querySelector('span').textContent=`${cloning?'Клонувати':'Створити'} з ${['DeepSeek','Codex','Claude'][index]}`;
      if(index===1)button.title=cloning?'Codex адаптує прев’ю конкурента за вашими побажаннями':'Трендове прев’ю: Codex сам продумує ідею за правилами обкладинок';
    }
    showThumbnailState(project.id);
  };
  const paint=reference=>{
    image.hidden=!reference?.thumbnail_url;
    if(reference?.thumbnail_url)image.src=reference.thumbnail_url;else image.removeAttribute('src');
    caption.textContent='Прев’ю конкурента';
    image.title=reference?.title||'';
    updateReferenceView();
  };
  if(data.clone_reference){source.reference=data.clone_reference;source.referenceUrl=field.value.trim();paint(data.clone_reference);}
  const load=async()=>{
    const url=field.value.trim();
    if(url&&loadingUrl===url)return;
    const current=++version;
    if(!url){paint(null);return;}
    if(source.referenceUrl===url&&source.reference){paint(source.reference);return;}
    loadingUrl=url;paint(null);note('Завантажуємо прев’ю…');
    try{
      const reference=await api(`/api/channels/${encodeURIComponent(project.channel_id || state.channel?.id)}/idea-reference`,'POST',{url});
      if(!preview.isConnected||current!==version||field.value.trim()!==url)return;
      source.reference=reference;source.referenceUrl=url;note('');paint(reference);
    }catch(error){if(preview.isConnected&&current===version){source.reference=null;paint(null);note(error.message);}}
    finally{if(preview.isConnected&&current===version){loadingUrl='';updateReferenceView();}}
  };
  field.addEventListener('input',()=>{clearTimeout(timer);version++;loadingUrl='';source.reference=null;note('');paint(null);if(field.value.trim())timer=setTimeout(()=>{if(preview.isConnected)load();},450);});
  field.addEventListener('change',()=>{clearTimeout(timer);return load();});
  field.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();return load();}});
  const select=mode=>{
    backdrop.dataset.thumbnailMode=mode;
    for(const button of buttons)button.setAttribute('aria-pressed',String(button.dataset.thumbMode===mode));
    $('thumb-reference-field').hidden=mode!=='clone';
    $('thumb-create-wishes').placeholder=mode==='clone'?'Вкажіть побажання або правки до клонованого прев’ю…':'Вкажіть побажання для нового прев’ю…';
    note('');
    updateReferenceView();
    if(mode!=='clone'){clearTimeout(timer);version++;loadingUrl='';}
    const gated=mode==='new'&&Number(data.pictures||0)<Number(data.creation_min_frames??thumbnailFrames);
    for(const button of backdrop.querySelectorAll('#modal-actions button'))button.dataset.gated=gated?'1':'';
    $('thumb-state').textContent=gated?`Для нового прев’ю потрібні хоча б ${data.creation_min_frames??thumbnailFrames} готові кадри. Клонування доступне за посиланням.`:'';
    showThumbnailState(project.id);
  };
  for(const button of buttons)button.addEventListener('click',()=>select(button.dataset.thumbMode));
  select(data.clone_reference?.url?'clone':'new');
}

const thumbnailLanguageRuns=new Map(),thumbnailSelection=new Map(),thumbnailDrafts=new Map(),thumbnailEditPending=new Set(),thumbnailPictures=new Map();
function readThumbnailData(id,data){
  if(Number.isFinite(data.pictures))thumbnailPictures.set(id,data.pictures);
  if(data.job)thumbnailRuns.set(id,data.job);
  thumbnailLanguageRuns.set(id,data.thumbnail_jobs || []);
}
function thumbnailWorking(id){return thumbnailBusy(id)||(thumbnailLanguageRuns.get(id)||[]).some(job=>job.status==='running');}
function showThumbnailState(id){
  const run=thumbnailRuns.get(id),backdrop=$('modal-backdrop');
  if(backdrop?.classList.contains('thumb-modal-open')&&backdrop.dataset.thumbnailProject===id){
    const box=backdrop.querySelector('.thumb-state');
    for(const button of backdrop.querySelectorAll('#modal-actions button'))button.disabled=thumbnailBusy(id)||button.dataset.gated==='1'||button.dataset.referenceMissing==='1';
    if(box&&(run?.status==='running'||run?.status==='failed'))box.textContent=run.status==='running'?'Створюємо прев’ю…':`Не вдалося: ${run.error}`;
  }
  const section=$('project-thumb');
  if(section?.dataset.project!==id)return;
  const editor=section.querySelector('.thumb-compose'),code=editor?.dataset.code;
  const own=code==='original'?run:(thumbnailLanguageRuns.get(id)||[]).find(job=>job.code===code);
  const pending=thumbnailEditPending.has(`${id}:${code}`),busy=own?.status==='running'||pending;
  const button=section.querySelector('.thumb-edit-send'),box=section.querySelector('.thumb-edit-state');
  if(button){button.disabled=busy;button.innerHTML=busy?`${typeof exportSpinner==='string'?exportSpinner:''}<span>Вносимо правки…</span>`:'Внести правки';}
  if(box)box.textContent=own?.status==='failed'?`Не вдалося: ${own.error}`:'';
  const create=section.querySelector('.thumb-view-create');
  if(create)create.disabled=thumbnailBusy(id)||create.dataset.gated==='1';
}
async function editThumbnail(project,item,wishes){
  const id=project.id,key=`${id}:${item.code}`;
  if(state.project?.id!==id||thumbnailEditPending.has(key))return;
  wishes=wishes.trim();
  if(!wishes){status('Напишіть, що змінити в прев’ю.',true);return;}
  thumbnailEditPending.add(key);showThumbnailState(id);
  try{
    const available=await api(`/api/projects/${encodeURIComponent(id)}/thumbnail`);
    if(state.project?.id!==id)return;
    const running=item.code==='original'?available.job:(available.thumbnail_jobs||[]).find(job=>job.code===item.code);
    if(running?.status==='running')throw new Error('Прев’ю ще створюється. Дочекайтеся завершення.');
    if((item.code!=='original'||item.base==='current')&&!available.image_editing)throw new Error('Правки цього прев’ю стануть доступними після безпечного перезапуску студії.');
    const source=thumbnailSources.get(id)||{},body={base:item.base,wishes};
    const url=item.code==='original'?`/api/projects/${encodeURIComponent(id)}/thumbnail`:`/api/projects/${encodeURIComponent(id)}/languages/${item.code}/thumbnail`;
    if(item.code==='original')Object.assign(body,{title:source.title||project.name,script:source.script||''});
    const {job}=await api(url,'POST',body);
    if(item.code==='original')thumbnailRuns.set(id,job);
    else thumbnailLanguageRuns.set(id,[...(thumbnailLanguageRuns.get(id)||[]).filter(old=>old.code!==item.code),job]);
    thumbnailDrafts.delete(`${id}:${item.key}`);
    if($('project-thumb')?.dataset.project===id&&thumbnailSelection.get(id)===item.key)$('project-thumb').querySelector('.thumb-edit-input').value='';
    markThumbnailCard(id);pollThumbnail(id);
  }catch(error){status(error.message,true);}
  finally{thumbnailEditPending.delete(key);showThumbnailState(id);}
}

async function generateThumbnail(project,writer='claude',wishes=$('thumb-wishes')?.value || ''){
  const source=thumbnailSources.get(project.id) || {},body={title:source.title || project.name,script:source.script || '',wishes,writer};
  if($('thumb-use-hero'))body.use_hero=$('thumb-use-hero').checked;
  try{
    const backdrop=$('modal-backdrop');
    if(source.reference_selection&&backdrop?.dataset.thumbnailProject===project.id){
      if(backdrop.dataset.thumbnailMode==='clone'){
        const url=$('thumb-reference-url').value.trim();if(!url)throw new Error('Вставте посилання на YouTube.');
        const reference=source.referenceUrl===url&&source.reference?.id?source.reference:await api(`/api/channels/${encodeURIComponent(project.channel_id || state.channel?.id)}/idea-reference`,'POST',{url});
        if(!reference?.id)throw new Error('Не вдалося прочитати прев’ю за посиланням.');
        body.reference_id=reference.id;
      }else body.reference_id='';
    }
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
// of the work is going on; CSS hides the card actions until the run finishes.
function markThumbnailCard(id){
  const card=document.querySelector(`.project-card[data-project-id="${CSS.escape(id)}"], .thumb-view-frame[data-project-id="${CSS.escape(id)}"]`);if(!card)return;
  const busy=thumbnailBusy(id);card.classList.toggle('thumb-running',busy);
  const create=card.querySelector('.project-action.thumbnail');if(create)create.disabled=busy;
  card.setAttribute('aria-busy',String(busy||['producing','exporting','stage-working'].some(name=>card.classList.contains(name))));
  if(typeof updateProjectDeleteButton==='function')updateProjectDeleteButton(card);
  let veil=card.querySelector('.thumb-progress');
  if(!busy){veil?.remove();return;}
  if(!veil){veil=document.createElement('div');veil.className='thumb-progress';veil.setAttribute('role','status');
    veil.innerHTML=`<span class="thumb-progress-pill">${typeof exportSpinner==='string'?exportSpinner:''}<span><b>Малюємо прев’ю</b><small></small></span></span>`;card.append(veil);}
  const stage=thumbnailRuns.get(id)?.stage;
  veil.querySelector('small').textContent=stage==='prompt'?`${thumbnailRuns.get(id)?.writer==='deepseek'?'DeepSeek':'Claude'} пише промпт`:stage==='drawing'?'Codex малює картинку':'Зазвичай 1–3 хвилини';
}

// Automatic clone covers can start after the card's initial thumbnail read.
const thumbnailDiscovering=new Set();
async function discoverThumbnailActivity(id){
  if(thumbnailBusy(id)||thumbnailDiscovering.has(id))return;
  thumbnailDiscovering.add(id);
  try{
    const data=await api(`/api/projects/${encodeURIComponent(id)}/thumbnail`);
    readThumbnailData(id,data);markThumbnailCard(id);
    if(thumbnailWorking(id))pollThumbnail(id);
  }catch{}
  finally{thumbnailDiscovering.delete(id);}
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
      readThumbnailData(project.id,data);markThumbnailCard(project.id);
      if(thumbnailWorking(project.id))pollThumbnail(project.id);
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
      try{
        const before=[thumbnailRuns.get(id),...(thumbnailLanguageRuns.get(id)||[])].filter(job=>job?.status==='running');
        const data=await api(`/api/projects/${encodeURIComponent(id)}/thumbnail`);readThumbnailData(id,data);
        if(thumbnailSelection.has(id)){
          if(before.some(job=>!job.code)&&data.job?.status==='done'&&data.job.file)thumbnailSelection.set(id,data.job.file);
          for(const job of data.thumbnail_jobs||[])if(job.status==='done'&&job.version&&before.some(old=>old.code===job.code))thumbnailSelection.set(id,`${job.code}:v${job.version}.png`);
        }
      }catch{}
      showThumbnailState(id);markThumbnailCard(id);
    }while(thumbnailWorking(id));
  }finally{thumbnailPolling.delete(id);}
  if(thumbnailRuns.get(id)?.status==='done'||(thumbnailLanguageRuns.get(id)||[]).some(job=>job.status==='done')){
    // only this project's picture: another episode's window may be open by now
    const frame=document.querySelector(`.thumb-view-frame[data-project-id="${CSS.escape(id)}"]`);
    const img=document.querySelector(`.thumb-current[data-project-id="${CSS.escape(id)}"]`);if(img)img.src=`/api/projects/${encodeURIComponent(id)}/cover?v=${Date.now()}`;
    if(frame&&!img)frame.innerHTML=`<img class="thumb-current" data-project-id="${esc(id)}" src="/api/projects/${encodeURIComponent(id)}/cover?v=${Date.now()}" alt="Прев’ю ролика">`;
    // the tab's library takes in the new picture
    const view=document.getElementById('project-thumb');if(view&&!view.hidden&&view.dataset.project===id){delete view.dataset.project;renderThumbView();}
    if(!state.project&&state.channel)refreshProjects().catch(()=>{});
  }
}

// Opening the tab shows the gallery; selecting a saved image opens its edit workspace.
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
  const create=section.querySelector('.thumb-view-create');
  create.dataset.gated='';create.disabled=thumbnailBusy(project.id);
  create.title='Створити нове прев’ю або клонувати прев’ю';
}
async function buildThumbView(section,project){
  const id=project.id;section.dataset.project=id;
  section.innerHTML=`<div class="thumb-view thumb-studio">
    <header class="thumb-studio-head"><h1>Галерея прев’ю</h1><button type="button" class="icon-button thumb-view-create" title="Створити нове прев’ю" aria-label="Створити нове прев’ю"><span class="thumb-create-mark">${thumbnailIcon}<b>+</b></span><span>New Preview</span></button></header>
    <div class="thumb-workspace" hidden><div class="thumb-hero"><div class="thumb-view-frame" data-project-id="${esc(id)}"></div>
      <div class="thumb-preview-meta"><span class="thumb-preview-language"></span><button type="button" class="secondary thumb-set-cover" hidden>Зробити обкладинкою</button></div></div>
    <form class="thumb-compose"><header><h2>Внести правки</h2><button type="button" class="icon-button thumb-edit-close" aria-label="Закрити перегляд">×</button></header>
      <textarea class="thumb-edit-input" aria-label="Правки до вибраного прев’ю" rows="5" maxlength="1500"></textarea>
      <div class="thumb-view-actions"><button type="submit" class="secondary thumb-edit-send">Внести правки</button><p class="thumb-edit-state thumb-state" role="status" aria-live="polite"></p></div></form></div>
    <section class="thumb-collection"><div class="thumb-filters" role="group" aria-label="Мова прев’ю"></div><div class="thumb-gallery-grid"><p class="thumb-gallery-empty">Завантаження…</p></div></section></div>`;
  section.querySelector('.thumb-view-create').addEventListener('click',()=>openThumbnail(project));
  if(!thumbRoute)fetch(`/channels/${state.channel.id}/projects/${id}/preview`,{method:'GET'}).then(response=>{if(response.ok&&response.headers.get('content-type')?.includes('text/html')){thumbRoute='/preview';if(state.view==='thumb')syncRoute(true);}}).catch(()=>{});
  let data;
  try{data=await api(`/api/projects/${encodeURIComponent(id)}/thumbnail`);}catch(error){status(error.message,true);return;}
  if(section.dataset.project!==id)return;
  thumbnailSources.set(id,{title:data.title,script:data.script});
  readThumbnailData(id,data);
  buildThumbnailGallery(section,project,data);
  renderThumbView();showThumbnailState(id);markThumbnailCard(id);
  if(thumbnailWorking(id))pollThumbnail(id);
}
$('view-thumb')?.addEventListener('click',()=>setProjectView('thumb'));

function buildThumbnailGallery(section,project,data){
  const id=project.id,base=`/api/projects/${encodeURIComponent(id)}`;
  const flags={en:'🇬🇧',uk:'🇺🇦',ru:'🇷🇺',de:'🇩🇪',es:'🇪🇸',fr:'🇫🇷',pt:'🇵🇹',it:'🇮🇹',pl:'🇵🇱',tr:'🇹🇷',nl:'🇳🇱',hi:'🇮🇳',ar:'🇸🇦',ja:'🇯🇵',ko:'🇰🇷',zh:'🇨🇳',id:'🇮🇩',cs:'🇨🇿',ro:'🇷🇴',kk:'🇰🇿'};
  const versions=data.versions || [];
  const items=[...versions.map(v=>({key:v.name,code:'original',base:v.name,label:'Оригінал',detail:`v${v.number}`,current:v.current,url:`${base}/thumbnails/${encodeURIComponent(v.name)}?v=${Math.round(v.time)}`,name:v.name,flag:flags[data.original_language] || '◈'})),
    ...(data.translated_thumbnails || []).map(v=>({key:`${v.code}:${v.version_name}`,code:v.code,base:v.version_name,label:v.name,detail:v.number?`v${v.number}`:'Переклад',url:`${base}/languages/${v.code}/thumbnails/${encodeURIComponent(v.version_name)}?v=${v.stamp}`,flag:flags[v.code] || '🌐'}))];
  if(data.preview&&!versions.some(v=>v.current))items.unshift({key:'cover',code:'original',base:'current',label:'Оригінал',detail:'Обкладинка',current:true,url:`${base}/cover?v=${Date.now()}`,flag:flags[data.original_language] || '◈'});
  let selected=thumbnailSelection.get(id),filter='all';
  const grid=section.querySelector('.thumb-gallery-grid'),filters=section.querySelector('.thumb-filters'),frame=section.querySelector('.thumb-view-frame'),choose=section.querySelector('.thumb-set-cover'),workspace=section.querySelector('.thumb-workspace'),editor=section.querySelector('.thumb-compose'),input=section.querySelector('.thumb-edit-input');
  const draw=()=>{
    const codes=['all',...new Set(items.map(x=>x.code))];
    filters.innerHTML=codes.map(code=>`<button type="button" data-code="${code}" aria-pressed="${code===filter}">${code==='all'?'Усі':code==='original'?'Оригінал':`${flags[code] || '🌐'} ${esc(items.find(x=>x.code===code).label)}`}</button>`).join('');
    const visible=items.filter(x=>filter==='all'||x.code===filter);
    grid.innerHTML=visible.length?visible.map(item=>`<button type="button" class="thumb-gallery-card${item.key===selected?' selected':''}" data-key="${esc(item.key)}" aria-pressed="${item.key===selected}" aria-label="Показати ${esc(item.label)} ${esc(item.detail)}"><span class="thumb-gallery-image"><img src="${item.url}" alt="${esc(item.label)} ${esc(item.detail)}" loading="lazy">${item.current?'<em>Обкладинка</em>':''}</span><span class="thumb-gallery-caption"><b>${item.flag} ${esc(item.label)}</b><small>${esc(item.detail)}</small></span></button>`).join(''):'<p class="thumb-gallery-empty">Тут з’являться створені прев’ю та їхні переклади.</p>';
  };
  const show=(key,focus=false)=>{
    const item=items.find(x=>x.key===key);if(!item)return;
    selected=key;thumbnailSelection.set(id,key);workspace.hidden=false;editor.dataset.code=item.code;
    frame.innerHTML=`<img src="${item.url}" alt="${esc(item.label)} ${esc(item.detail)}"><div class="thumb-preview-tools"><a class="thumb-preview-download" title="Завантажити прев’ю" aria-label="Завантажити прев’ю" href="${item.url}&delivery=clean-png-v1&download=${encodeURIComponent(`Прев’ю ${item.label}.png`)}" download="Прев’ю ${esc(item.label)}.png"><svg viewBox="0 0 24 24"><path d="M12 3v12m-4-4 4 4 4-4M4 16v5h16v-5"/></svg></a></div>`;
    section.querySelector('.thumb-preview-language').textContent=`${item.flag} ${item.label} · ${item.detail}`;
    input.value=thumbnailDrafts.get(`${id}:${key}`)||'';
    choose.hidden=!item.name||item.current;draw();showThumbnailState(id);markThumbnailCard(id);
    if(focus){workspace.scrollIntoView({behavior:'smooth',block:'nearest'});input.focus({preventScroll:true});}
  };
  input.addEventListener('input',()=>thumbnailDrafts.set(`${id}:${selected}`,input.value));
  editor.addEventListener('submit',event=>{event.preventDefault();const item=items.find(x=>x.key===selected);if(item)editThumbnail(project,item,input.value);});
  section.querySelector('.thumb-edit-close').addEventListener('click',()=>{workspace.hidden=true;selected=null;thumbnailSelection.delete(id);draw();});
  filters.addEventListener('click',event=>{const button=event.target.closest('button[data-code]');if(button){filter=button.dataset.code;draw();}});
  grid.addEventListener('click',event=>{const button=event.target.closest('[data-key]');if(button)show(button.dataset.key,true);});
  choose.addEventListener('click',async()=>{
    const item=items.find(x=>x.key===selected);if(!item?.name)return;choose.disabled=true;
    try{const result=await api(`${base}/thumbnail/choose`,'POST',{name:item.name});for(const current of items)current.current=result.versions.some(v=>v.name===current.name&&v.current);show(selected);status('Обкладинку збережено.');}
    catch(error){status(error.message,true);}finally{choose.disabled=false;}
  });
  if(selected)show(selected);else draw();
}
