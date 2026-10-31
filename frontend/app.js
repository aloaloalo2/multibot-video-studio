const monitorStorageKey='multibot-studio-monitor';
function loadMonitorSettings(){
  const defaults={monitorMuted:true,monitorVolume:0,monitorPreviousVolume:1};
  if(new URLSearchParams(location.search).get('muted')==='1')return defaults;
  try{
    const saved=JSON.parse(localStorage.getItem(monitorStorageKey));
    if(!saved || typeof saved.volume!=='number' || !Number.isFinite(saved.volume))return defaults;
    const volume=Math.max(0,Math.min(1,saved.volume));
    const previous=typeof saved.previousVolume==='number' && Number.isFinite(saved.previousVolume) && saved.previousVolume>0?Math.min(1,saved.previousVolume):(volume || 1);
    const muted=saved.muted===true || volume===0;
    return {monitorMuted:muted,monitorVolume:muted?0:volume,monitorPreviousVolume:previous};
  }catch{return defaults;}
}

const state = {
  channels: [], channel: null, projects: [], project: null, assets: [], assetsLoading:false, pixabay: [], projectExports:new Map(),
  selected: null, selectedTrack: null, libraryTab: 'all', pixabayKind: 'video', search: '',
  playhead: 0, playing: false, ...loadMonitorSettings(), scrubbing:false, audioNodes: [], zoom: 1, busy: false, job: null, poll: null, exportWatch: null,
  activeLayer: null, replaceMode: false, previewNodes: new Map(), previewSignature: '', navigation: 0, restoringProject:false,
  previewZoom:1,previewPanX:0,previewPanY:0,
  view:'editor',plan:null,planError:'',planSettingsMatch:null,
  selectedGroup:null,selectedTransition:null,expandedGroup:null,compactTimeline:true,multiSelection:[]
};

const $ = id => document.getElementById(id);
let studioFontCatalog=[];
const studioFontsReady=fetch('/fonts/catalog.json').then(async response=>{
  if(!response.ok)throw new Error('Каталог шрифтів недоступний');
  const entries=await response.json();
  const style=document.createElement('style');style.id='studio-font-faces';
  style.textContent=entries.flatMap(entry=>[
    `@font-face{font-family:${JSON.stringify(entry.family)};src:url('/fonts/${entry.regular}') format('truetype');font-weight:400;font-display:swap;}`,
    `@font-face{font-family:${JSON.stringify(entry.family)};src:url('/fonts/${entry.bold}') format('truetype');font-weight:700;font-display:swap;}`
  ]).join('\n');document.head.append(style);studioFontCatalog=entries;
  return Promise.all([document.fonts.load('500 32px Golos'),document.fonts.load('500 32px Literata')]);
}).catch(error=>{console.error('Шрифти студії:',error);return [];});
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const trashIcon='<svg class="trash-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16M10 4h4m-8 3 1 13h10l1-13M10 11v5m4-5v5"/></svg>';
const exportSpinner='<span class="export-spinner" aria-hidden="true"></span>';
function setTrashButton(button,label,iconOnly=false){button.innerHTML=trashIcon+(iconOnly?'':`<span>${esc(label)}</span>`);button.classList.add('trash-button');button.setAttribute('aria-label',label);}
setTrashButton($('delete-selected'),'Прибрати фрагмент');
const channelIcon = '<svg class="channel-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="14" rx="3"/><path d="M8 21h8M10 8l5 3-5 3z"/></svg>';
const seconds = value => Number.isFinite(Number(value)) ? Math.max(0, Number(value)) : 0;
const clock = value => { const n = Math.floor(seconds(value)); return `${String(Math.floor(n / 60)).padStart(2,'0')}:${String(n % 60).padStart(2,'0')}`; };
const projectIcon='<svg class="project-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="3"/><path d="M7 3v18M17 3v18M3 8h4m-4 8h4m10-8h4m-4 8h4m-11-5 4 3-4 3z"/></svg>';

function locationRoute(){const match=location.pathname.match(/^\/channels\/([0-9a-f]{16})(?:\/projects\/([0-9a-f]{24})(\/(?:plan|agent|preview))?)?\/?$/);return match?{channelId:match[1],projectId:match[2],view:match[3]==='/plan'?'plan':match[3]==='/agent'?'agent':match[3]==='/preview'?'thumb':'editor'}:null;}
let restoreGeneration=0,restoreTimer=null;
function cancelLocationRestore(){restoreGeneration++;if(restoreTimer!==null){clearTimeout(restoreTimer);restoreTimer=null;}state.restoringProject=false;$('project-loading').hidden=true;}
async function restoreCurrentLocation(){
  cancelLocationRestore();
  state.restoringProject=!!locationRoute()?.projectId;
  $('project-loading').hidden=!state.restoringProject || !!state.project;
  if(state.restoringProject && !state.project)$('channel-overview').hidden=true;
  const generation=restoreGeneration,path=location.pathname;
  try{await loadChannels(undefined,{restoreLocation:true});}
  catch(error){
    if(generation!==restoreGeneration || location.pathname!==path)return;
    status(`Не вдалося відкрити сторінку: ${error.message}. Спробуємо ще раз.`,true);
    restoreTimer=setTimeout(()=>{if(generation===restoreGeneration && location.pathname===path)restoreCurrentLocation();},4000);
  }
}
function syncRoute(replace=false){
  const path=state.channel?`/channels/${state.channel.id}${state.project?'/projects/'+state.project.id+(state.view==='plan'?'/plan':state.view==='agent'?'/agent':state.view==='thumb'?thumbRoute:''):''}`:'/';
  if(location.pathname!==path || location.search || location.hash)history[replace?'replaceState':'pushState'](null,'',path);
}

async function api(path, method='GET', body) {
  const options = {method, headers: {'Accept':'application/json'}};
  if (body !== undefined) {options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(body);}
  const startupRead=method==='GET' && (path==='/api/health' || path==='/api/channels' || path.startsWith('/api/projects?') || /^\/api\/projects\/[0-9a-f]{24}(?:\/(?:assets|plan|analysis|export\/active))?$/.test(path));
  for(let attempt=0;;attempt++){
    const controller=startupRead?new AbortController():null;
    const timeout=controller?setTimeout(()=>controller.abort(),15000):null;
    if(controller)options.signal=controller.signal;
    try {
      const response=await fetch(path,options);
      let data;
      try{data=await response.json();}catch(error){if(error.name==='AbortError')throw error;const invalid=new Error(`Сервер повернув помилку ${response.status}.`);invalid.httpStatus=response.status;throw invalid;}
      if(!response.ok){const error=new Error(data.error || data.message || `Помилка ${response.status}`);error.httpStatus=response.status;throw error;}
      return data;
    } catch(error) {
      const transient=!error.httpStatus || error.httpStatus>=500;
      if(startupRead && transient && attempt<2){await new Promise(resolve=>setTimeout(resolve,250*(attempt+1)));continue;}
      if(error.name==='AbortError')throw new Error('Студія занадто довго не відповідає');
      throw error;
    } finally {if(timeout!==null)clearTimeout(timeout);}
  }
}

function status(message, error=false) {
  $('status-line').textContent = message;
  const banner = $('banner');
  if (error) {banner.textContent=message; banner.hidden=false;}
  else {banner.hidden=true;}
}

function modal(title, body, actions=[]) {
  stopModalMedia();
  $('modal-title').textContent = title;
  $('modal-body').innerHTML = body;
  const box = $('modal-actions'); box.replaceChildren();
  for (const action of actions) {
    const button = document.createElement('button');
    button.type='button';
    if(action.icon==='trash' || /^(Прибрати|Видалити)(?:\s|$)/u.test(action.label))setTrashButton(button,action.label);
    else button.textContent=action.label;
    if (action.primary) button.classList.add('primary');
    if (action.danger) button.classList.add('danger');
    button.addEventListener('click', action.run);
    box.append(button);
  }
  $('modal-backdrop').hidden=false;
  if(document.activeElement instanceof HTMLElement)document.activeElement.blur();
}
function stopModalMedia() {$('modal-body').querySelectorAll('audio,video').forEach(media=>media.pause());}
function closeModal() {stopModalMedia();$('modal-backdrop').hidden=true;$('modal-backdrop').classList.remove('settings-modal-open');}
$('modal-close').addEventListener('click',closeModal);
$('modal-backdrop').addEventListener('click', event => {if (event.target === $('modal-backdrop')) closeModal();});
document.addEventListener('keydown', event => {if (event.key==='Escape' && !$('modal-backdrop').hidden) closeModal();});

async function loadChannels(preferred,{restoreLocation=false}={}) {
  const route=restoreLocation?locationRoute():null;
  const [health,data] = await Promise.all([api('/api/health'),api('/api/channels')]);
  if(health.api_version!==2 || health.layer_mode!=='item' || health.plan_workflow!=='audio_required')throw new Error('Запущена стара копія студії. Потрібен перезапуск студії та оновлення сторінки.');
  state.channels = data.channels || [];
  renderChannels();
  if (!state.channels.length) {
    if(route)throw new Error('Канал тимчасово недоступний');
    state.channel=null; state.projects=[]; state.project=null;
    renderProjects(); renderProject();syncRoute(true); status('Додайте папку каналу, щоб почати.'); return;
  }
  if(route && !state.channels.some(item=>item.id===route.channelId))throw new Error('Канал тимчасово недоступний');
  const channel = state.channels.find(item=>item.id===(preferred || route?.channelId)) || state.channels.find(item=>item.id===state.channel?.id) || state.channels[0];
  const restoreProject=!!route?.projectId && channel.id===route.channelId;
  if(!await selectChannel(channel.id,{updateUrl:!restoreLocation,loadProjects:!restoreProject}))return;
  if(restoreLocation){
    if(restoreProject){
      if(!await selectProject(route.projectId,{updateUrl:false,view:route.view}))return;
      refreshProjects().catch(error=>console.warn('Не вдалося оновити список випусків',error));
    }
    syncRoute(true);
  }
}

function renderChannels() {
  const list=$('channel-list'); list.replaceChildren();
  for (const channel of state.channels) {
    const row=document.createElement('div'); row.className='channel-item'+(state.channel?.id===channel.id?' active':''); row.setAttribute('role','listitem');
    const choose=document.createElement('button'); choose.className='channel-select'; choose.type='button';choose.innerHTML=`${channelIcon}<span class="channel-name">${esc(channel.name)}</span>`; choose.title=channel.name;
    choose.addEventListener('click',()=>selectChannel(channel.id).catch(error=>status(error.message,true)));
    row.append(choose); list.append(row);
  }
}

async function selectChannel(id,{updateUrl=true,loadProjects=true}={}) {
  if(updateUrl)cancelLocationRestore();
  const navigation=++state.navigation;
  stopPlayback();
  const channel=state.channels.find(item=>item.id===id) || null;
  if (!channel) return false;
  const data=loadProjects?await api(`/api/projects?channel=${encodeURIComponent(id)}`):{projects:[]};
  if(navigation!==state.navigation)return false;
  state.channel=channel;
  state.project=null; state.selected=null;state.selectedTransition=null; state.assets=[]; state.pixabay=[];state.projects=[];
  renderChannels(); renderProject();
  state.projects=data.projects || [];
  if(updateUrl)syncRoute();
  renderProjects(); renderProject();
  status('');
  return true;
}

function renderProjects() {
  const list=$('project-list'); list.replaceChildren();
  for (const project of state.projects) {
    const row=document.createElement('div');row.className='project-row';
    const button=document.createElement('button'); button.className='project-item'+(state.project?.id===project.id?' active':''); button.type='button'; button.innerHTML=`${projectIcon}<span class="project-item-name">${esc(project.name || project.id)}</span>`;button.title=project.name || project.id;
    button.addEventListener('click',()=>selectProject(project.id,{view:project.has_plan&&!project.scene_count?'plan':'editor'}).catch(error=>status(error.message,true)));
    row.append(button,projectActions(project));list.append(row);
  }
}

function projectActions(project){
  const actions=document.createElement('div');actions.className='project-actions';
  const icons={rename:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 5 4 4M4 20l4-1L20 7a2.8 2.8 0 0 0-4-4L4 15z"/></svg>',delete:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M10 4h4m-8 3 1 13h10l1-13M10 11v5m4-5v5"/></svg>'};
  if(project.episode_path)icons.thumbnail=thumbnailIcon;
  icons.space=spaceIcon;
  for(const [type,title,run] of [...(project.episode_path?[['thumbnail','Створити прев’ю',()=>openThumbnail(project)]]:[]),['space','Звільнити місце',()=>openSpace(project)],['rename','Перейменувати проєкт',()=>renameProject(project)],['delete','Видалити проєкт',()=>deleteProject(project)]]){
    const button=document.createElement('button');button.type='button';button.className=`project-action ${type}`;button.innerHTML=icons[type];button.title=title;button.setAttribute('aria-label',`${title} «${project.name}»`);button.addEventListener('click',run);actions.append(button);
    // the thumbnail takes its look from the video's own frames: grey until a couple are made (thumbnail.js)
    if(type==='thumbnail'&&!thumbnailReady(project))thumbnailWaits(button);
  }
  return actions;
}

async function refreshProjects(){
  const channelId=state.channel?.id;if(!channelId)return;
  const result=await api(`/api/projects?channel=${encodeURIComponent(channelId)}`);
  if(state.channel?.id!==channelId)return;
  state.projects=result.projects || [];renderProjects();renderOverview();
}

function renameProject(project){
  modal('Перейменувати проєкт',`<label>Назва проєкту<input id="rename-project-name" type="text" maxlength="100" value="${esc(project.name)}"></label>`,[{label:'Скасувати',run:closeModal},{label:'Зберегти',primary:true,run:async()=>{
    const button=$('modal-actions').querySelector('.primary');button.disabled=true;
    try{
      const name=$('rename-project-name').value.trim();if(!name)throw new Error('Введіть назву проєкту.');
      const result=await api(`/api/projects/${encodeURIComponent(project.id)}`,'PATCH',{name,expected_revision:project.revision});
      if(state.project?.id===project.id){state.project=result.project;renderProject();}
      await refreshProjects();closeModal();status(`Проєкт перейменовано на «${result.project.name}».`);
    }catch(error){button.disabled=false;status(error.message,true);}
  }}]);
}

function deleteProject(project){
  modal('Видалити проєкт?',`<p>Проєкт «${esc(project.name)}» зникне зі списку студії. Його матеріали та папка випуску збережуться.</p>`,[{label:'Скасувати',run:closeModal},{label:'Видалити проєкт',icon:'trash',danger:true,run:async()=>{
    const button=$('modal-actions').querySelector('.danger');button.disabled=true;
    try{
      await api(`/api/projects/${encodeURIComponent(project.id)}`,'DELETE');
      if(state.project?.id===project.id)showProjectList();
      closeModal();await refreshProjects();status(`Проєкт «${project.name}» видалено зі списку.`);
    }catch(error){button.disabled=false;status(error.message,true);}
  }}]);
}

async function selectProject(id,{updateUrl=true,view='editor'}={}) {
  if(updateUrl)cancelLocationRestore();
  const navigation=++state.navigation;
  if (state.poll) {clearInterval(state.poll);state.poll=null;}
  if (state.exportWatch) {clearInterval(state.exportWatch);state.exportWatch=null;}
  stopPlayback();
  const projectPath=`/api/projects/${encodeURIComponent(id)}`;
  const [data,plan,exportState]=await Promise.all([api(projectPath),api(`${projectPath}/plan`),api(`${projectPath}/export/active`)]);
  if(navigation!==state.navigation)return false;
  if(data.project?.channel_id!==state.channel?.id)throw new Error('Проєкт належить іншому каналу.');
  state.project=data.project;
  setPreviewZoom(1);
  state.restoringProject=false;
  state.selected=null;state.selectedTransition=null;state.selectedStack=null;state.selectedTrack=null;state.activeLayer=isUniversal()?state.project.tracks?.[0]?.id:null;state.replaceMode=false;state.playhead=0;state.zoom=1;
  // a link with ?t=83.4 opens the montage at that moment (tools/studio.py still prints one beside the export's still)
  const requested=Number(new URLSearchParams(location.search).get('t'));if(!updateUrl&&requested>0&&Number.isFinite(requested))state.playhead=requested;state.pixabay=[];state.previewNodes.clear();state.previewSignature='';
  state.assets=state.project.assets || [];state.assetsLoading=true;state.analysis=null;state.job=exportState.job;
  state.plan=plan.plan;state.planError=plan.error || '';state.planSettingsMatch=plan.settings_match ?? null;state.view=view==='editor' && !editorUnlocked()?'plan':view;
  if(updateUrl)syncRoute();
  buildAudioNodes();
  renderProjects(); renderProject(); status('');if(state.job)pollJob();
  const current=()=>navigation===state.navigation && state.project?.id===id;
  (async()=>{
    for(let attempt=0;attempt<3 && current();attempt++){
      const revision=state.project.revision;
      const library=await api(`${projectPath}/assets`);
      if(!current())return;
      if(state.project.revision!==revision)continue;
      state.assets=library.assets || [];state.assetsLoading=false;
      buildAudioNodes();renderAssets();renderPreview();return;
    }
    if(current()){state.assetsLoading=false;renderAssets();}
  })().catch(error=>{if(current()){state.assetsLoading=false;renderAssets();status(`Не вдалося завантажити медіатеку: ${error.message}`,true);}});
  api(`${projectPath}/analysis`).then(analysis=>{
    if(!current() || state.analysis!==null)return;
    state.analysis=analysis;
    if(state.view==='plan' && typeof renderSpeechReport==='function')renderSpeechReport($('project-plan'));
  }).catch(error=>console.warn('Не вдалося завантажити аналіз озвучки',error));
  state.exportWatch=setInterval(async()=>{if(!state.project || state.project.id!==id || exportIsActive())return;try{const result=await api(`/api/projects/${encodeURIComponent(id)}/export/active`);if(state.project?.id===id && result.job){state.job=result.job;updateExportLock();pollJob();}}catch(error){console.warn('Не вдалося перевірити експорт',error);}},4000);
  return true;
}

function showProjectList() {
  cancelLocationRestore();
  ++state.navigation;
  if(state.exportWatch){clearInterval(state.exportWatch);state.exportWatch=null;}
  if(state.poll){clearInterval(state.poll);state.poll=null;}
  stopPlayback();state.project=null;state.selected=null;state.selectedTransition=null;state.selectedTrack=null;
  state.audioNodes=[];state.previewNodes.clear();state.previewSignature='';$('preview-audio-container').replaceChildren();$('preview-composition').replaceChildren();renderProjects();renderProject();
  syncRoute();
  if(state.channel){
    status('');
    refreshProjects().catch(error=>status(error.message,true));
  }
}

function projectCreationDate(timestamp){
  const raw=Number(timestamp);
  if(!Number.isFinite(raw) || raw<=0)return null;
  const date=new Date(raw<1e11?raw*1000:raw);
  if(!Number.isFinite(date.getTime()))return null;
  const formatter=new Intl.DateTimeFormat('uk-UA',{timeZone:'Europe/Kyiv',day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
  const values=Object.fromEntries(formatter.formatToParts(date).map(part=>[part.type,part.value]));
  const now=Object.fromEntries(formatter.formatToParts(new Date()).map(part=>[part.type,part.value]));
  const today=values.day===now.day && values.month===now.month && values.year===now.year;
  return {label:today?'Створено сьогодні':'Створено',text:today?`о ${values.hour}:${values.minute}`:`${values.day} ${values.month} ${values.year}, ${values.hour}:${values.minute}`,datetime:date.toISOString()};
}

function renderOverview() {
  $('overview-title').innerHTML=state.channel?`${channelIcon}<span>${esc(state.channel.name)}</span>`:'Оберіть канал';
  $('overview-create').disabled=!state.channel;
  $('overview-channel-settings').disabled=!state.channel;
  const container=$('overview-projects');container.replaceChildren();
  if(!state.channel){container.innerHTML='<div class="overview-empty"><strong>Каналів ще немає</strong>Додай папку каналу з лівої панелі.</div>';return;}
  if(!state.projects.length){container.innerHTML='<div class="overview-empty"><strong>Поки немає випусків</strong>Створи перший проєкт цього каналу.</div>';return;}
  for(const project of state.projects){
    const card=document.createElement('article');card.className='project-card';card.dataset.projectId=project.id;card.setAttribute('aria-label',`Випуск «${project.name}»`);
    const open=document.createElement('button');open.type='button';open.className='project-open';open.setAttribute('aria-label',`Відкрити випуск «${project.name}»`);
    const created=projectCreationDate(project.created_at);
    const count=project.scene_count ?? project.scenes?.length ?? 0;
    open.innerHTML=`<h2>${projectIcon}<span>${esc(project.name || 'Без назви')}</span></h2><div class="project-meta"><span class="project-created">${created?`${esc(created.label)} <time datetime="${created.datetime}" title="Час за Києвом">${esc(created.text)}</time>`:'Дата створення невідома'}</span></div>`;
    // While the agent makes the frames the card shows how far it got and does not open; after it is done, paused or
    // stopped, it opens as usual.
    const making=project.production_request,producing=['requested','in_progress'].includes(making?.status);
    open.addEventListener('click',()=>{
      if(producing){status('Агент ще створює кадри цього ролика. Випуск відкриється, коли він закінчить.');return;}
      selectProject(project.id,{view:count?'editor':'plan'}).catch(error=>status(error.message,true));
    });
    if(count>0 && Number.isFinite(Number(project.duration)) && Number(project.duration)>0){
      const duration=document.createElement('span');duration.className='project-duration';
      const value=Number(project.duration),hours=Math.floor(value/3600);
      const formatted=hours?`${hours}:${String(Math.floor(value/60)%60).padStart(2,'0')}:${String(Math.floor(value)%60).padStart(2,'0')}`:clock(value);
      duration.textContent=formatted;duration.title='Тривалість ролика';
      open.querySelector('.project-meta').append(duration);
    }
    if(project.cover_asset_id || project.preview_mtime){
      // The Studio picks a telling frame of the montage for the cover and fades it in once loaded.
      const cover=document.createElement('img');cover.className='project-cover';cover.alt='';cover.loading='lazy';cover.decoding='async';
      cover.src=`/api/projects/${encodeURIComponent(project.id)}/cover?v=${encodeURIComponent(project.preview_mtime || project.updated_at || project.revision || 0)}`;
      cover.addEventListener('load',()=>card.classList.add('cover-ready'),{once:true});
      cover.addEventListener('error',()=>{card.classList.remove('has-cover');card.classList.add('no-cover');cover.remove();},{once:true});
      card.classList.add('has-cover');card.append(cover);
    }else card.classList.add('no-cover');
    const exporting=document.createElement('div');exporting.className='project-export-state';exporting.hidden=true;open.insertBefore(exporting,open.querySelector('.project-meta'));
    if(producing){
      const total=Number(making.frames) || 0,done=Math.min(total,Number(making.made) || 0),progress=total?Math.round(done/total*100):0;
      const box=document.createElement('div');box.className='project-making';
      box.innerHTML=`<span class="project-export-label">${exportSpinner}<span>Створюємо кадри · ${done} з ${total}</span></span><span class="project-export-progress" role="progressbar" aria-label="Створення кадрів" aria-valuemin="0" aria-valuemax="${total}" aria-valuenow="${done}"><span style="width:${progress}%"></span></span>`;
      open.insertBefore(box,open.querySelector('.project-meta'));
      card.classList.add('producing');card.setAttribute('aria-busy','true');open.setAttribute('aria-disabled','true');
    }
    card.append(open,projectActions(project));
    container.append(card);
  }
  updateOverviewExports();pollOverviewExports(true);
  if(typeof watchThumbnails==='function')watchThumbnails(state.projects);
}

function updateOverviewExports(){
  for(const card of $('overview-projects').querySelectorAll('[data-project-id]')){
    const job=state.projectExports.get(card.dataset.projectId),active=!!job&&['queued','running','cancelling'].includes(job.status);
    card.classList.toggle('exporting',active);card.setAttribute('aria-busy',String(active));
    for(const button of card.querySelectorAll('.project-action'))button.disabled=active;
    const box=card.querySelector('.project-export-state');box.hidden=!active;
    if(!active){box.replaceChildren();continue;}
    const progress=Math.max(0,Math.min(100,Math.round(job.progress||0)));
    const label=job.status==='cancelling'?'Зупиняємо експорт':job.status==='queued'?'Експорт у черзі':job.stage==='razgon_frames'?`Малюємо кадри Razgon · ${Number(job.razgon_completed)||0} з ${Number(job.razgon_total)||0}`:job.stage==='razgon_sound'?'Зводимо звук':job.stage==='verifying'?'Перевіряємо файл':'Експорт триває';
    box.innerHTML=`<span class="project-export-label">${exportSpinner}<span>${label}</span><strong>${progress}%</strong></span><span class="project-export-progress" role="progressbar" aria-label="Експорт" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${progress}"><span style="width:${progress}%"></span></span>`;
  }
}
let overviewExportRequest=false,overviewBatchExports=true;
async function pollOverviewExports(force=false){
  if(overviewExportRequest || state.project || !state.channel || (!force && document.hidden))return;
  overviewExportRequest=true;const channelId=state.channel.id,ids=state.projects.map(project=>project.id);
  try{
    let jobs;
    if(overviewBatchExports){
      try{jobs=(await api('/api/exports/active')).jobs || [];}catch(error){if(error.httpStatus!==404)throw error;overviewBatchExports=false;}
    }
    if(!jobs){
      jobs=[];
      for(let offset=0;offset<ids.length;offset+=4){
        const found=await Promise.all(ids.slice(offset,offset+4).map(id=>api(`/api/projects/${encodeURIComponent(id)}/export/active`)));
        jobs.push(...found.map(result=>result.job).filter(Boolean));
      }
    }
    if(state.channel?.id!==channelId)return;
    for(const id of ids)state.projectExports.delete(id);
    for(const job of jobs)state.projectExports.set(job.project_id,job);
    updateOverviewExports();
  }catch(error){console.warn('Не вдалося оновити стан експорту',error);}
  finally{overviewExportRequest=false;}
}
setInterval(pollOverviewExports,3000);
// While the agent makes frames of an episode of this channel, its card is read again now and then.
setInterval(()=>{
  if(state.project || !state.channel || document.hidden)return;
  if(state.projects.some(project=>['requested','in_progress'].includes(project.production_request?.status)))refreshProjects().catch(()=>{});
},8000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)pollOverviewExports();});

function scenes() {return Array.isArray(state.project?.scenes) ? [...state.project.scenes].sort((a,b)=>seconds(a.start)-seconds(b.start)) : [];}
function allTracks() {return Array.isArray(state.project?.tracks) ? state.project.tracks : [];}
function assetById(id) {return state.assets.find(asset=>asset.id===id);}
function buildAudioNodes() {
  const container=$('preview-audio-container'),previous=new Map(state.audioNodes.map(item=>[item.clip.id,item]));state.audioNodes=[];
  if(isUniversal()){
    for(const layer of layers())for(const clip of layer.clips || [])if(clip.kind==='audio'){
      const asset=assetById(clip.asset_id),url=asset?.preview_url || asset?.media_url || asset?.url;
      if(!url)continue;
      const old=previous.get(clip.id),element=old?.element.getAttribute('src')===url?old.element:document.createElement('audio');if(element!==old?.element){element.src=url;element.preload='auto';}element.muted=state.monitorMuted || layer.muted===true;if(element.parentElement!==container)container.append(element);state.audioNodes.push({clip,element});
    }
    for(const old of previous.values())if(!state.audioNodes.some(item=>item.element===old.element)){old.element.pause();old.element.remove();}
    return;
  }
  for(const old of previous.values())old.element.pause();container.replaceChildren();
  for(const track of allTracks()){
    const type=(track.type || '').toLowerCase();
    if(!['voice','audio','music','sfx','sound'].some(item=>type.includes(item)))continue;
    for(const clip of track.clips || []){
      const asset=assetById(clip.asset_id),url=asset?.preview_url || asset?.media_url || asset?.url;
      if(!url)continue;
      const element=document.createElement('audio');element.src=url;element.preload='metadata';element.muted=state.monitorMuted;container.append(element);
      state.audioNodes.push({clip,element});
    }
  }
}

function requestMediaPlayback(element){
  if(!element.paused || element._studioPlayPending)return;
  const promise=element.play();element._studioPlayPending=true;
  Promise.resolve(promise).catch(error=>{if(error.name==='NotAllowedError')status('Браузер очікує натискання Play для запуску звуку.',true);}).finally(()=>{element._studioPlayPending=false;if(!state.playing)element.pause();});
}
// The voice at 100% plays at the Studio's standard level (backend/audio_level.py): its clip carries the gain the export
// uses. A gain above 1 (a quiet voice brought up) needs Web Audio, which an <audio> element's volume cannot give.
const studioAudio={context:null};
function setClipLevel(element,clip){
  const level=Math.max(0,Number(clip.volume ?? 1)*Number(state.project?.audio_gain?.[clip.asset_id] ?? 1)*state.monitorVolume);
  if(level<=1&&!element._studioGain){element.volume=level;return;}
  try{
    if(!element._studioGain){studioAudio.context=studioAudio.context || new AudioContext();const source=studioAudio.context.createMediaElementSource(element),gain=studioAudio.context.createGain();
      source.connect(gain).connect(studioAudio.context.destination);element._studioGain=gain;element.volume=1;}
    if(studioAudio.context.state==='suspended')studioAudio.context.resume().catch(()=>{});
    element._studioGain.gain.value=level;
  }catch{element.volume=Math.min(1,level);}
}
function syncStudioAudio(){
  for(const {clip,element} of state.audioNodes){
    const start=seconds(clip.start),end=start+seconds(clip.duration),active=state.playhead>=start&&state.playhead<end;
    setClipLevel(element,clip);element.muted=state.monitorMuted || (isUniversal()&&clipIsMuted(clip));
    if(!active){if(!element.paused)element.pause();continue;}
    const target=seconds(clip.trim_start)+state.playhead-start,threshold=state.playing ? .45 : .025;
    if(element.readyState===0){element._studioSeekTarget=target;if(!element._studioMetadataBound){element._studioMetadataBound=true;element.addEventListener('loadedmetadata',()=>{if(element._studioSeekTarget!=null)element.currentTime=Math.min(element._studioSeekTarget,element.duration);});}}
    if(element.readyState>=1 && !element.seeking && Math.abs(element.currentTime-target)>threshold){element._studioSeekTarget=target;element.currentTime=Math.min(Math.max(0,target),element.duration);}
    if(state.playing)requestMediaPlayback(element);else if(!element.paused)element.pause();
  }
}
// Each edit replaces state.project, so values derived from the whole project are kept per project object.
const projectMemo=new WeakMap();
function memoForProject(key,compute){if(!state.project)return compute();let memo=projectMemo.get(state.project);if(!memo)projectMemo.set(state.project,memo=new Map());if(!memo.has(key))memo.set(key,compute());return memo.get(key);}
function duration() {return memoForProject('duration',measureDuration);}
function measureDuration() {return isUniversal()?Math.max(seconds(state.project?.duration),...universalClips().map(c=>seconds(c.start)+seconds(c.duration)),0):Math.max(seconds(state.project?.duration), ...scenes().map(s=>seconds(s.start)+seconds(s.duration)), 0);}
function selectedScene() {return scenes().find(s=>s.id===state.selected);}
function stopPlayback(){state.playing=false;$('preview-video').pause();state.previewNodes.forEach(node=>node.querySelectorAll('video').forEach(video=>video.pause()));state.audioNodes.forEach(item=>item.element.pause());$('play-pause').textContent='▶';$('play-pause').setAttribute('aria-label','Відтворити');}

function updateMonitorControls(){
  const muted=state.monitorMuted || state.monitorVolume===0,button=$('monitor-audio');
  button.innerHTML=`<svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 4 6 8H3v8h3l5 4z"/>${muted?'<path d="m16 9 5 6m0-6-5 6"/>':'<path d="M15 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/>'}</svg>`;
  button.classList.toggle('sound-on',!muted);button.setAttribute('aria-pressed',String(!muted));button.setAttribute('aria-label',muted?'Увімкнути звук':'Вимкнути звук');button.title=muted?'Увімкнути звук':'Вимкнути звук';
  $('monitor-volume').value=Math.round(state.monitorVolume*100);$('monitor-volume-value').textContent=Math.round(state.monitorVolume*100)+'%';
}

function saveMonitorSettings(){
  try{localStorage.setItem(monitorStorageKey,JSON.stringify({muted:state.monitorMuted,volume:state.monitorVolume,previousVolume:state.monitorPreviousVolume}));}catch{}
}

function renderProject() {
  if(state.plan && state.project && !state.project.production?.plan_ready && state.view==='editor')state.view='plan';
  updateMonitorControls();
  $('preview-surface').style.setProperty('--preview-ratio',`${state.project?.width || 1920}/${state.project?.height || 1080}`);
  if(isUniversal() && !layers().some(layer=>layer.id===state.activeLayer))state.activeLayer=layers()[0]?.id || null;
  document.querySelector('.app-shell').classList.toggle('editor-open',!!state.project);
  // An animated film has its own agents on the plan (director, frames), so the Studio agent tab is not offered there.
  const animatedChannel=state.channel?.settings?.channel_kind==='animated';
  if(animatedChannel && state.view==='agent')state.view='plan';
  document.querySelector('.app-shell').classList.toggle('agent-open',!!state.project && state.view==='agent');
  $('channel-sidebar').hidden=!!state.project;
  $('editor-brand').hidden=!state.project;
  $('overview-channel-settings').hidden=!!state.project || !state.channel;
  const title=$('project-title');title.replaceChildren();
  const channelName=document.createElement('strong');channelName.title=state.channel?.name || '';channelName.innerHTML=state.channel?`${channelIcon}<span>${esc(state.channel.name)}</span>`:'Оберіть канал';title.append(channelName);
  if(state.project){
    const slash=document.createElement('span');slash.className='project-title-slash';slash.textContent='/';
    const name=document.createElement('button');name.type='button';name.className='project-name';name.title=`Перейменувати проєкт «${state.project.name}»`;name.setAttribute('aria-label',`Перейменувати проєкт «${state.project.name}»`);name.innerHTML=`${projectIcon}<span>${esc(state.project.name)}</span>`;name.addEventListener('click',()=>renameProject(state.project));title.append(slash,name);
  }
  document.title=state.project?.name || state.channel?.name?`${state.project?.name || state.channel.name} | VideoKey Studio`:'VideoKey Studio';
  $('save-state').textContent=state.project?'● Локально збережено':'';
  $('channel-overview').hidden=!!state.project || state.restoringProject;
  $('project-loading').hidden=!state.restoringProject || !!state.project;
  $('editor-workspace').hidden=!state.project || state.view!=='editor';
  $('editor-timeline').hidden=!state.project || state.view!=='editor';
  $('project-plan').hidden=!state.project || state.view!=='plan';
  $('project-agent').hidden=!state.project || state.view!=='agent';
  $('project-views').hidden=!state.project;
  $('view-agent').hidden=animatedChannel;
  document.querySelectorAll('.editor-only').forEach(element=>element.hidden=!state.project || state.view!=='editor');
  // Export appears once the video exists: a picture on the timeline. An animated film's frames are code blocks until
  // they are drawn, and a voice alone is not a video either.
  const clips=(state.project?.tracks || []).flatMap(track=>track.clips || []),animated=state.channel?.settings?.channel_kind==='animated';
  $('export-open').hidden=!clips.some(clip=>['video','image'].includes(clip.kind) || (!animated && clip.kind!=='audio'));
  renderPlan();
  if(typeof renderThumbView==='function')renderThumbView();
  if(state.project && state.view==='agent' && typeof renderAgent==='function')renderAgent();
  renderOverview();
  $('view-editor').disabled=!!state.project && !editorUnlocked();
  $('view-editor').title=$('view-editor').disabled?editorLockedHint:'';
  $('export-open').disabled=!state.project;$('export-open').title=state.project?.production?.reason || ''; $('undo').disabled=!state.project?.can_undo; $('redo').disabled=!state.project?.can_redo;
  $('add-transition').disabled=!state.project || (isUniversal()?!universalClips().length:!scenes().length);$('add-text').disabled=!state.project || (!isUniversal()&&!scenes().length);
  $('play-pause').disabled=!state.project; $('seek').disabled=!state.project;
  $('time-total').textContent=clock(duration());
  $('add-scene').hidden=isUniversal();$('add-scene').disabled=!state.project;
  $('add-layer').hidden=!isUniversal();$('add-layer').disabled=!state.project;
  $('add-animation').hidden=!isUniversal();$('add-animation').disabled=!state.project;
  renderAssets(); renderTimeline(); renderInspector(); renderPreview();
  updateExportLock();
  requestAnimationFrame(layoutPreview);
  updatePreviewViewport();
}

const previewZoomLevels=[1,1.25,1.5,1.75,2,2.5,3,4];
let previewPanGesture=null;
function updatePreviewViewport(){
  const surface=$('preview-surface'),zoom=state.previewZoom;
  const limitX=surface.clientWidth*(zoom-1)/2,limitY=surface.clientHeight*(zoom-1)/2;
  state.previewPanX=Math.max(-limitX,Math.min(limitX,state.previewPanX));
  state.previewPanY=Math.max(-limitY,Math.min(limitY,state.previewPanY));
  $('preview-content').style.transform=`translate(${state.previewPanX}px,${state.previewPanY}px) scale(${zoom})`;
  surface.classList.toggle('is-zoomed',zoom>1);
  surface.title=zoom>1?'Перетягніть кадр, щоб роздивитися деталі. Подвійне натискання повертає масштаб 100%.':'';
  $('preview-zoom-out').disabled=!state.project || zoom<=previewZoomLevels[0];
  $('preview-zoom-in').disabled=!state.project || zoom>=previewZoomLevels.at(-1);
  $('preview-zoom-reset').disabled=!state.project || zoom===1;
  $('preview-zoom-reset').textContent=Math.round(zoom*100)+'%';
}
function setPreviewZoom(value){
  state.previewZoom=Math.max(1,Math.min(4,value));
  if(state.previewZoom===1){state.previewPanX=0;state.previewPanY=0;}
  updatePreviewViewport();
}
$('preview-zoom-in').addEventListener('click',()=>setPreviewZoom(previewZoomLevels.find(value=>value>state.previewZoom) || previewZoomLevels.at(-1)));
$('preview-zoom-out').addEventListener('click',()=>setPreviewZoom([...previewZoomLevels].reverse().find(value=>value<state.previewZoom) || 1));
$('preview-zoom-reset').addEventListener('click',()=>setPreviewZoom(1));
$('preview-surface').addEventListener('dblclick',()=>setPreviewZoom(1));
$('preview-surface').addEventListener('dragstart',event=>{if(state.previewZoom>1)event.preventDefault();});
$('preview-surface').addEventListener('pointerdown',event=>{
  if(state.previewZoom<=1 || event.button!==0)return;
  event.preventDefault();
  previewPanGesture={id:event.pointerId,x:event.clientX,y:event.clientY,panX:state.previewPanX,panY:state.previewPanY};
  event.currentTarget.setPointerCapture(event.pointerId);event.currentTarget.classList.add('is-panning');
});
$('preview-surface').addEventListener('pointermove',event=>{
  if(previewPanGesture?.id!==event.pointerId)return;
  state.previewPanX=previewPanGesture.panX+event.clientX-previewPanGesture.x;
  state.previewPanY=previewPanGesture.panY+event.clientY-previewPanGesture.y;updatePreviewViewport();
});
function stopPreviewPan(event){
  if(previewPanGesture?.id!==event.pointerId)return;
  previewPanGesture=null;event.currentTarget.classList.remove('is-panning');
  if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);
}
for(const event of ['pointerup','pointercancel','lostpointercapture'])$('preview-surface').addEventListener(event,stopPreviewPan);
new ResizeObserver(updatePreviewViewport).observe($('preview-surface'));

function layoutPreview(){
  const workspace=$('editor-workspace');
  if(!state.project || workspace.hidden)return;
  const width=workspace.clientWidth,height=workspace.clientHeight;
  if(width<800){workspace.classList.remove('fitted-preview');return;}
  const panel=document.querySelector('.preview-panel');
  const ratio=Number(state.project.width || 1920)/Number(state.project.height || 1080);
  const frameHeight=Math.max(80,height-20-panel.querySelector('.panel-title').offsetHeight-panel.querySelector('.transport').offsetHeight-26);
  const panelWidth=Math.max(260,Math.min(width-410,frameHeight*ratio+26));
  workspace.classList.add('fitted-preview');workspace.style.setProperty('--preview-panel-width',Math.round(panelWidth)+'px');
}
new ResizeObserver(layoutPreview).observe($('editor-workspace'));
let previewLastWidth=0,previewLastHeight=0;
new ResizeObserver(()=>{const box=$('preview-composition');if(!state.project || !isUniversal() || box.clientWidth===previewLastWidth && box.clientHeight===previewLastHeight)return;previewLastWidth=box.clientWidth;previewLastHeight=box.clientHeight;if(!state.playing)renderUniversalPreview();}).observe($('preview-composition'));
studioFontsReady.then(()=>{if(state.project && isUniversal() && !state.playing)renderUniversalPreview();});

function visibleAssets() {
  const query=state.libraryTab==='pixabay'?state.search.toLocaleLowerCase():'';
  const list=state.libraryTab==='pixabay' ? state.pixabay : state.assets;
  const used=new Set((state.project?.tracks || []).flatMap(track=>(track.clips || []).map(clip=>clip.asset_id)));
  return list.filter(asset=>{
    if(asset.source==='episode'&&!used.has(asset.id)&&/\/Studio\/(QA|sheets|Review|Stock|GeneratedPhotos)\//.test(asset.path || ''))return false;
    const kind=(asset.kind || asset.type || '').toLowerCase();
    if (state.libraryTab==='video' && !kind.includes('video')) return false;
    if (state.libraryTab==='photo' && !['image','photo'].some(x=>kind.includes(x))) return false;
    return !query || `${asset.name || ''} ${asset.source || ''}`.toLocaleLowerCase().includes(query);
  });
}

function assetSourceLabel(asset){
  const labels={episode:'Файл випуску',project:'Медіатека',local:'Локальний файл','speech-analysis':'Озвучка з відео',pixabay:'Pixabay',audio:'Аудіо',video:'Відео',image:'Фото'};
  return labels[asset.source] || asset.source || labels[asset.kind] || 'Локальний файл';
}

function openAssetPreview(asset){
  stopPlayback();
  const kind=(asset.kind || '').toLowerCase();
  const url=asset.preview_video_url || asset.preview_url || asset.media_url || asset.url;
  const name=asset.name || 'Матеріал';
  modal('Перегляд медіа',`<div class="asset-preview"><strong>${esc(name)}</strong><div id="asset-preview-media"></div><p>${esc(assetSourceLabel(asset))}${asset.duration?' · '+clock(asset.duration):''}</p></div>`,[{label:'Закрити',run:closeModal}]);
  const container=$('asset-preview-media');
  if(!url){container.textContent='Перегляд цього матеріалу недоступний.';return;}
  if(kind==='image' || kind==='photo'){
    const image=document.createElement('img');image.src=url;image.alt=name;container.append(image);
  }else if(kind==='audio' || kind==='video'){
    const media=document.createElement(kind);media.src=url;media.controls=true;media.muted=true;media.preload='metadata';
    if(kind==='video')media.playsInline=true;
    media.setAttribute('aria-label',name);container.append(media);
  }else container.textContent='Перегляд цього формату недоступний.';
}

function renderAssets() {
  const transitions=state.libraryTab==='transitions';
  const effects=state.libraryTab==='effects';$('effect-library').hidden=!effects;
  $('transition-library').hidden=!transitions;$('asset-list').hidden=transitions;$('asset-search').hidden=state.libraryTab!=='pixabay';$('asset-search').placeholder='Пошук у Pixabay';
  if(transitions)return;
  if(effects){$('asset-list').hidden=true;return;}
  const list=$('asset-list');
  // Most edits only move clips; rebuilding hundreds of cards then costs time and reloads thumbnails.
  const used=[...new Set((state.project?.tracks || []).flatMap(track=>(track.clips || []).map(clip=>clip.asset_id)))].sort().join();
  const key=[state.project?.id,state.libraryTab,state.libraryTab==='pixabay'?state.search:'',state.assetsLoading,used];
  if(list._assets===state.assets&&list._pixabay===state.pixabay&&list._key?.every((value,index)=>value===key[index]))return;
  list._assets=state.assets;list._pixabay=state.pixabay;list._key=key;
  list.replaceChildren();
  const assets=visibleAssets();
  if (!assets.length) {const empty=document.createElement('div');empty.className='empty-state';empty.textContent=state.libraryTab==='pixabay' ? 'Введіть запит, щоб знайти матеріали Pixabay.' : (state.project?(state.assetsLoading?'Завантаження медіатеки...':state.libraryTab==='all'?'Додайте медіафайл через кнопку «+».':'Матеріалів цього типу ще немає.'):'Оберіть випуск.');list.append(empty);return;}
  for (const asset of assets) {
    if(state.libraryTab==='pixabay' && asset.kind==='video' && asset.preview_video_url){
      const row=document.createElement('div');row.className='asset-video-result';row.draggable=true;
      const preview=document.createElement('video');preview.src=asset.preview_video_url;preview.muted=true;preview.playsInline=true;preview.preload='none';preview.setAttribute('aria-label',`Попередній перегляд: ${asset.name || 'відео'}`);
      const info=document.createElement('div');info.className='asset-info';info.innerHTML=`<strong>${esc(asset.name || 'Стокове відео')}</strong><small>${esc(asset.source || 'Pixabay')}${asset.duration?' · '+clock(asset.duration):''}</small>`;
      const buttons=document.createElement('div');buttons.className='asset-result-actions';
      const play=document.createElement('button');play.type='button';play.className='asset-preview-toggle';play.textContent='▶ Переглянути';play.addEventListener('click',async()=>{if(preview.paused){document.querySelectorAll('.asset-video-result video').forEach(item=>{if(item!==preview)item.pause();});try{preview.currentTime=0;await preview.play();play.textContent='❚❚ Пауза';}catch{status('Не вдалося відтворити прев’ю цього стоку.',true);}}else{preview.pause();play.textContent='▶ Переглянути';}});preview.addEventListener('ended',()=>play.textContent='▶ Переглянути');
      const add=document.createElement('button');add.type='button';add.className='asset-use';add.textContent='＋ На таймлайн';add.addEventListener('click',()=>useAsset(asset).catch(error=>status(error.message,true)));
      buttons.append(play,add);row.append(preview,info,buttons);row.addEventListener('dragstart',event=>event.dataTransfer.setData('application/x-videostudio-asset',JSON.stringify({id:asset.id,kind:asset.kind,source:'pixabay'})));list.append(row);continue;
    }
    const button=document.createElement('button');button.className='asset';button.type='button';button.draggable=true;button.title=asset.name || 'Матеріал';
    const kind=(asset.kind || '').toLowerCase();
    const thumb=asset.thumbnail_url || ((kind==='image'||kind==='photo') ? (asset.preview_url || asset.url) : null);
    const visual=thumb ? `<img src="${esc(thumb)}" alt="" loading="lazy" decoding="async" fetchpriority="low">` : `<span class="asset-thumb">${kind==='video'?'▶':kind==='audio'?'♫':'▣'}</span>`;
    button.innerHTML=`${visual}<span class="asset-info"><strong>${esc(asset.name || 'Матеріал')}</strong><small>${esc(assetSourceLabel(asset))}${asset.duration ? ' · '+clock(asset.duration) : ''}</small></span>`;
    button.addEventListener('click',()=>openAssetPreview(asset));
    button.addEventListener('dragstart', event=>event.dataTransfer.setData('application/x-videostudio-asset',JSON.stringify({id:asset.id,kind:asset.kind,source:state.libraryTab})));
    list.append(button);
  }
}

async function refreshCurrentProject() {
  if (!state.project) return;
  const result=await api(`/api/projects/${encodeURIComponent(state.project.id)}`);
  state.project=result.project;
  const library=await api(`/api/projects/${encodeURIComponent(state.project.id)}/assets`);
  state.assets=library.assets || [];
  buildAudioNodes();renderProject();
}

async function useAsset(asset, sceneId=selectedScene()?.id, options={}) {
  if (!state.project) throw new Error('Спершу оберіть випуск.');
  let chosen=asset;
  if (state.libraryTab==='pixabay' || asset.pixabay_id) {
    const result=await api(`/api/projects/${encodeURIComponent(state.project.id)}/assets/from-pixabay`,'POST',{kind:asset.kind,id:asset.pixabay_id || asset.id});
    chosen=result.asset;
    await refreshCurrentProject();
  }
  if(isUniversal()){await useUniversalAsset(chosen,sceneId,options);return;}
  if(chosen.kind==='audio'){openAddAudio(chosen);return;}
  if(!sceneId){await action('add_scene',{asset_id:chosen.id,duration:5,title:chosen.name},`Додано кадр «${chosen.name}».`);return;}
  await action('replace_scene_asset',{scene_id:sceneId,asset_id:chosen.id},`Матеріал кадру замінено на «${chosen.name}».`);
}

function openAddAudio(asset, preferredTrack) {
  const tracks=allTracks().filter(track=>['voice','audio','music','sfx','sound'].some(type=>(track.type || '').includes(type)));
  if(!tracks.length){status('У проєкті немає звукової доріжки.',true);return;}
  const options=tracks.map(track=>`<option value="${esc(track.id)}" ${track.id===preferredTrack?'selected':''}>${esc(track.name || track.type)}</option>`).join('');
  modal(`Додати звук: ${asset.name}`,`<label>Доріжка<select id="audio-track">${options}</select></label><label>Початок, с<input id="audio-start" type="number" min="0" step="0.1" value="${state.playhead.toFixed(1)}"></label><label>Тривалість, с<input id="audio-duration" type="number" min="0.1" step="0.1" value="${Math.max(1,Number(asset.duration)||10)}"></label>`,[{label:'Скасувати',run:closeModal},{label:'Додати',primary:true,run:async()=>{try{const track_id=$('audio-track').value,start=Number($('audio-start').value),duration=Number($('audio-duration').value);if(!Number.isFinite(start)||!Number.isFinite(duration)||start<0||duration<=0)throw new Error('Перевірте час фрагмента.');await action('add_track_clip',{track_id,asset_id:asset.id,start,duration,volume:1},'Звуковий фрагмент додано.');closeModal();}catch(error){status(error.message,true);}}}]);
}

function renderPreview() {
  if(isUniversal()){renderUniversalPreview();return;}
  const scene=scenes().find(s=>state.playhead>=seconds(s.start) && state.playhead<seconds(s.start)+seconds(s.duration)) || selectedScene();
  const asset=scene && assetById(scene.asset_id);
  const video=$('preview-video'),image=$('preview-image'),placeholder=$('preview-placeholder');
  const url=asset?.preview_url || asset?.media_url || asset?.url;
  const kind=(asset?.kind || scene?.type || '').toLowerCase();
  if (url && kind.includes('video')) {
    image.hidden=true;video.hidden=false;placeholder.hidden=true;
    if (video.dataset.url!==url) {video.src=url;video.dataset.url=url;video.muted=true;}
    const target=seconds(scene.trim_start)+(state.playhead-seconds(scene.start));
    if(Number.isFinite(video.duration) && Math.abs(video.currentTime-target)>.35)video.currentTime=Math.min(Math.max(0,target),video.duration);
    if(state.playing && video.paused)video.play().catch(()=>{});
  } else if (url && (kind.includes('image')||kind.includes('photo'))) {
    video.pause();video.hidden=true;image.hidden=false;placeholder.hidden=true;
    if (image.src!==url) image.src=url;
  } else {video.pause();video.hidden=true;image.hidden=true;placeholder.hidden=false;placeholder.textContent=scene ? (scene.type==='color'?'Фоновий кадр без матеріалу':`Матеріал для кадру «${scene.title || 'Кадр'}» ще не вибрано`) : 'Оберіть кадр на таймлайні';}
  const textTrack=allTracks().find(track=>track.type==='text');
  const activeText=textTrack?.clips?.filter(clip=>state.playhead>=seconds(clip.start)&&state.playhead<seconds(clip.start)+seconds(clip.duration)).map(clip=>clip.text).filter(Boolean).join(' · ');
  $('preview-overlay').textContent=activeText || '';
  $('preview-overlay').style.display=activeText?'block':'none';
  $('time-current').textContent=clock(state.playhead);
  $('seek').value=duration()?Math.round(state.playhead/duration()*1000):0;
  updateTimelinePlayhead();
  for(const item of state.audioNodes){
    const clip=item.clip,element=item.element,start=seconds(clip.start),end=start+seconds(clip.duration);
    if(state.playhead>=start && state.playhead<end){
      const target=seconds(clip.trim_start)+(state.playhead-start);
      if(Number.isFinite(element.duration) && Math.abs(element.currentTime-target)>.35)element.currentTime=Math.min(Math.max(0,target),element.duration);
      setClipLevel(element,clip);
      element.muted=state.monitorMuted;
      if(state.playing && element.paused)element.play().catch(()=>{});
      if(!state.playing && !element.paused)element.pause();
    }else if(!element.paused)element.pause();
  }
}

const timelineZoomLevels=[.25,.4,.5,.67,.8,1,1.25,1.5,2,2.5,3,4,5,6,8,10,12.5,16,20,25,32,40,50,64];
let timelineRenderCache=null;
function timelineOrigin(){if(timelineRenderCache)return timelineRenderCache.origin;const group=sceneGroups().find(g=>g.id===state.expandedGroup);return group?groupBounds(group).start:0;}
function timelineSpan(){if(timelineRenderCache)return timelineRenderCache.span;const group=sceneGroups().find(g=>g.id===state.expandedGroup);return group?Math.max(.1,groupBounds(group).end-groupBounds(group).start):(duration() || 60);}
function timelineLayout(){
  if(timelineRenderCache)return timelineRenderCache.layout;
  const scroller=document.querySelector('.timeline-scroll'),style=getComputedStyle(scroller);
  const label=Number.parseFloat(style.getPropertyValue('--timeline-label-width')) || 142;
  const rawGap=Number.parseFloat(style.getPropertyValue('--timeline-label-gap')),gap=Number.isFinite(rawGap)?rawGap:6;
  const padding=Number.parseFloat(style.paddingLeft)+Number.parseFloat(style.paddingRight);
  const gutter=0,fit=Math.max(1,scroller.clientWidth-padding-label-gap);
  return {label,gap,gutter,fit};
}
function timelineWidth(){return timelineLayout().fit*state.zoom*.98;}
function timelineTicks(total,width){
  if(width<70)return [total];
  const intervals=[1,2,5,10,15,30,60,120,300,600,900,1800,3600,7200,14400,36000];
  const step=intervals.find(value=>value/total*width>=70) || intervals.at(-1);
  const ticks=[0];
  for(let time=step;time<total;time+=step)if(time/total*width>=55 && (total-time)/total*width>=55)ticks.push(time);
  ticks.push(total);return ticks;
}
function renderTimelineRulerMarks(marks,total,width){
  const labels=timelineTicks(total,width),intervals=[1,2,5,10,15,30,60,120,300,600,900,1800,3600,7200,14400,36000];
  const step=intervals.find(value=>value/total*width>=16) || intervals.at(-1);
  $('timeline-content').style.setProperty('--timeline-tick-step-px',(step/total*width)+'px');
  $('timeline-content').style.setProperty('--timeline-minute-step-px',(Math.max(60,step)/total*width)+'px');
  for(let time=0;time<total;time+=step){
    const tick=document.createElement('i');tick.className='ruler-tick'+(time>0 && time%60===0?' minute':'')+(labels.includes(time)?' labelled':'');
    tick.style.left=time/total*100+'%';tick.setAttribute('aria-hidden','true');marks.append(tick);
  }
  for(const time of labels){
    const label=document.createElement('span');label.style.left=time/total*100+'%';label.textContent=clock(time);
    if(time===total)label.className='ruler-end';marks.append(label);
  }
}

document.addEventListener('keydown',event=>{
  if(event.code!=='Space' && event.key!==' ')return;
  const target=event.target;
  if(!state.project || !$('modal-backdrop').hidden || target.closest('input,textarea,select,[contenteditable="true"],[role="textbox"]'))return;
  event.preventDefault();if(event.repeat)return;
  $('play-pause').click();
});
document.addEventListener('click',event=>{const button=event.target.closest('button');if(button)button.blur();});
document.addEventListener('dragend',event=>{event.target.closest('button')?.blur();});
function clipHtml(clip,kind,isScene=false,trackId='') {
  const span=Math.max(.1,seconds(clip.duration));
  const left=Math.max(0,seconds(clip.start)/timelineSpan()*100);
  const width=span/timelineSpan()*100;
  const label=clip.title || clip.text || clip.name || assetById(clip.asset_id)?.name || (isScene?'Кадр':'Фрагмент');
  const cls=`track-clip kind-${esc((kind||'').toLowerCase())}${state.selected===clip.id?' selected':''}`;
  return `<button type="button" draggable="${isScene}" class="${cls}" data-clip-id="${esc(clip.id)}" data-track-id="${esc(trackId)}" data-scene="${isScene}" style="left:${left}%;width:${width}%" title="${esc(label)} · ${clock(clip.start)} - ${clock(seconds(clip.start)+span)}">${esc(label)}</button>`;
}

// The ruler width is set from the zoom, so the previous value is remembered instead of measured:
// measuring here would force a layout of everything the edit has just changed.
let timelineMarksWidth=null;
function renderTimeline() {
  const scroller=document.querySelector('.timeline-scroll'),oldWidth=document.querySelector('.time-ruler-marks')?timelineMarksWidth:null;
  const oldScroll=scroller.scrollLeft,oldTop=scroller.scrollTop,layout=timelineLayout(),canvasWidth=layout.fit*state.zoom,width=canvasWidth*.98;
  const previousCache=timelineRenderCache;
  timelineRenderCache={layout,span:timelineSpan(),origin:timelineOrigin()};
  try{
  $('timeline-content').style.setProperty('--timeline-media-width',canvasWidth+'px');
  $('timeline-content').style.width=(layout.label+layout.gap+canvasWidth+layout.gutter)+'px';
  const handle=$('playhead-handle');if(handle)$('timeline-playhead').append(handle);
  $('time-ruler').replaceChildren();$('timeline-tracks').replaceChildren();
  if(state.project)renderUniversalTimeline();
  const marks=document.querySelector('.time-ruler-marks');if(handle&&marks)marks.append(handle);
  timelineMarksWidth=marks?Number.parseFloat(marks.style.width)||null:null;
  if(state.project)renderTimelineGaps();
  scroller.scrollLeft=state.zoom<=1?0:oldWidth?oldScroll/oldWidth*width:0;
  $('zoom-value').textContent=Math.round(state.zoom*100)+'%';
  $('zoom-in').disabled=state.zoom>=timelineZoomLevels.at(-1);
  $('zoom-out').disabled=state.zoom<=timelineZoomLevels[0];
  invalidatePlayheadGeometry();updateTimelinePlayhead();
  scroller.scrollTop=oldTop;
  }finally{timelineRenderCache=previousCache;}
}

function setTimelineZoom(zoom,pointerX){
  const scroller=document.querySelector('.timeline-scroll'),marks=document.querySelector('.time-ruler-marks');
  const rect=marks?.getBoundingClientRect(),layout=timelineLayout(),panel=scroller.getBoundingClientRect();
  const left=panel.left+Number.parseFloat(getComputedStyle(scroller).paddingLeft)+layout.label+layout.gap;
  const local=Math.max(0,Math.min(timelineSpan(),state.playhead-timelineOrigin())),playhead=rect?rect.left+local/timelineSpan()*rect.width:left;
  const pointer=Number.isFinite(pointerX),anchor=pointer?Math.max(left,Math.min(panel.right-10,pointerX)):(playhead>=left&&playhead<=panel.right-10?playhead:left+layout.fit/2),oldTop=scroller.scrollTop;
  const time=pointer&&rect?Math.max(0,Math.min(timelineSpan(),(anchor-rect.left)/rect.width*timelineSpan())):local;
  state.zoom=Math.max(timelineZoomLevels[0],Math.min(timelineZoomLevels.at(-1),zoom));renderTimeline();
  if(state.zoom>1){const updated=document.querySelector('.time-ruler-marks')?.getBoundingClientRect();if(updated)scroller.scrollLeft+=updated.left+time/timelineSpan()*updated.width-anchor;}
  scroller.scrollTop=oldTop;
}
document.querySelector('.timeline-scroll').addEventListener('wheel',event=>{
  if(!(event.ctrlKey||event.metaKey||event.altKey)||!state.project)return;
  event.preventDefault();setTimelineZoom(Math.round(state.zoom*Math.exp(-event.deltaY*.004)*100)/100,event.clientX);
},{passive:false});

new ResizeObserver(()=>{
  if(!state.project || $('editor-timeline').hidden)return;
  const width=document.querySelector('.time-ruler-marks')?.getBoundingClientRect().width;
  if(!width || Math.abs(width-timelineWidth())>.5)renderTimeline();
}).observe(document.querySelector('.timeline-scroll'));

// Reading element boxes after the preview has changed styles forces a full layout, so playback
// reuses the timeline geometry until the timeline is redrawn, scrolled or resized.
let playheadGeometry=null;
function invalidatePlayheadGeometry(){playheadGeometry=null;}
function updateTimelinePlayhead(){
  const marks=document.querySelector('.time-ruler-marks'),line=$('timeline-playhead');
  line.hidden=!state.project || !marks;
  if(!marks){playheadGeometry=null;return;}
  if(!playheadGeometry || playheadGeometry.marks!==marks){
    const container=$('timeline-content').getBoundingClientRect(),rect=marks.getBoundingClientRect(),scroller=document.querySelector('.timeline-scroll'),viewport=scroller.getBoundingClientRect();
    playheadGeometry={marks,left:rect.left-container.left,width:rect.width,visibleFrom:viewport.left+timelineLayout().label-.5-container.left,visibleTo:viewport.left+scroller.clientWidth+.5-container.left};
  }
  const geometry=playheadGeometry,span=timelineSpan(),local=Math.max(0,Math.min(span,state.playhead-timelineOrigin()));
  const x=geometry.left+local/span*geometry.width,visible=x>=geometry.visibleFrom&&x<=geometry.visibleTo,handle=$('playhead-handle');
  line.hidden=!visible;line.style.left=x+'px';
  handle.hidden=!visible;handle.style.left=(local/span*100)+'%';
  handle.setAttribute('aria-valuemax',span);handle.setAttribute('aria-valuenow',local.toFixed(2));handle.setAttribute('aria-valuetext',clock(local));
}
document.querySelector('.timeline-scroll').addEventListener('scroll',()=>{invalidatePlayheadGeometry();updateTimelinePlayhead();},{passive:true});
new ResizeObserver(invalidatePlayheadGeometry).observe(document.querySelector('.timeline-scroll'));

function scrubTimeline(event){
  const marks=document.querySelector('.time-ruler-marks');if(!marks)return;
  const rect=marks.getBoundingClientRect();state.playhead=timelineOrigin()+Math.max(0,Math.min(timelineSpan(),(event.clientX-rect.left)/rect.width*timelineSpan()));renderPreview();updateTimelinePlayhead();
}
$('timeline-content').addEventListener('pointerdown',event=>{if(event.button!==0 || !event.target.closest('#playhead-handle,.time-ruler-marks'))return;event.preventDefault();stopPlayback();state.scrubbing=true;scrubTimeline(event);});
document.addEventListener('pointermove',event=>{if(state.scrubbing)scrubTimeline(event);});
document.addEventListener('pointerup',()=>{state.scrubbing=false;});
$('playhead-handle').addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();stopPlayback();const first=timelineOrigin(),last=first+timelineSpan();state.playhead=event.key==='Home'?first:event.key==='End'?last:Math.max(first,Math.min(last,state.playhead+(event.key==='ArrowRight'?1:-1)*(event.shiftKey?1:.1)));renderPreview();updateTimelinePlayhead();});

function selectScene(id) {
  state.selected=id;state.selectedTrack=null;
  const scene=selectedScene();if(scene)state.playhead=seconds(scene.start);
  renderTimeline();renderInspector();renderPreview();
  if(scene)status(`Вибрано кадр «${scene.title || id}».`);
}
function selectTrackClip(id,trackId){state.selected=id;state.selectedTrack=trackId;const clip=allTracks().find(item=>item.id===trackId)?.clips?.find(item=>item.id===id);if(clip)state.playhead=seconds(clip.start);renderTimeline();renderInspector();renderPreview();status('Вибрано фрагмент на доріжці.');}

function renderInspector() {
  if(isUniversal()){renderUniversalInspector();return;}
  const scene=selectedScene();const track=allTracks().find(item=>item.id===state.selectedTrack);const clip=scene || track?.clips?.find(item=>item.id===state.selected);
  $('inspector-empty').hidden=!!clip;$('inspector-fields').hidden=!clip;
  if(!clip)return;
  $('selected-name').textContent=clip.title || clip.text || clip.name || assetById(clip.asset_id)?.name || 'Фрагмент';
  $('selected-kind').textContent=scene?'Основний кадр':(track?.name || 'Доріжка');
  $('scene-start').value=seconds(clip.trim_start).toFixed(1);$('scene-duration').value=seconds(clip.duration).toFixed(1);
  $('scene-start').disabled=!scene;$('scene-duration').disabled=!scene;$('apply-trim').disabled=!scene;
  $('transition-type').disabled=!scene;$('transition-duration').disabled=!scene;$('apply-transition').disabled=!scene;
  $('transition-type').value=['cut','crossfade'].includes(scene?.transition?.type) ? scene.transition.type : 'cut';$('transition-duration').value=seconds(scene?.transition?.duration ?? .3).toFixed(1);$('transition-duration').disabled=!scene || $('transition-type').value==='cut';
  $('clip-volume').value=Math.round((clip.volume ?? 1)*100);$('clip-volume-value').textContent=$('clip-volume').value+'%';
  $('clip-volume').disabled=track?.type==='text';$('apply-volume').disabled=track?.type==='text';
  $('move-left').disabled=!scene;$('move-right').disabled=!scene;$('split-scene').disabled=!scene;
}

async function action(type,payload,message,options={}) {
  if(!state.project)throw new Error('Оберіть випуск.');
  if(state.busy)throw new Error('Попередня дія ще виконується.');
  if(type==='add_clip' && state.expandedGroup)payload={...payload,group_id:state.expandedGroup};
  const projectId=state.project.id;state.busy=true;$('save-state').textContent='● Зберігається...';
  try {
    const result=await api(`/api/projects/${encodeURIComponent(state.project.id)}/actions`,'POST',{type,payload,expected_revision:state.project.revision});
    if(!result.project)throw new Error('Сервер не підтвердив збереження проєкту.');
    if(options.preserveInspector && state.project?.id!==projectId)return result.project;
    state.project=result.project;
    if(options.preserveInspector){
      $('save-state').textContent='● Локально збережено';$('undo').disabled=!state.project.can_undo;$('redo').disabled=!state.project.can_redo;
      renderTimeline();renderPreview();
    }else{buildAudioNodes();renderProject();}
    status(message || 'Зміну збережено.');
  } catch(error){$('save-state').textContent='● Локально збережено';status(error.message,true);throw error;}
  finally{state.busy=false;}
}

function motionPicker(value){
  const options=[['linear','Linear'],['ease_in','Ease In'],['ease_out','Ease Out'],['ease_in_out','Ease In Out']];
  const selected=options.some(([key])=>key===value)?value:'ease_in_out';
  return `<input id="settings-easing" type="hidden" value="${selected}"><div class="easing-options" role="radiogroup" aria-label="Animation motion">${options.map(([mode,label])=>{
    const path=Array.from({length:25},(_,i)=>`${i?'L':'M'}${(8+i/24*84).toFixed(2)},${(60-easedProgress(i/24,mode)*52).toFixed(2)}`).join(' ');
    return `<button type="button" class="easing-card" role="radio" data-easing="${mode}" aria-checked="${selected===mode}" tabindex="${selected===mode?0:-1}"><svg viewBox="0 0 100 70" aria-hidden="true"><path class="easing-axes" d="M8 8V60H92"/><path class="easing-curve" d="${path}"/></svg><span>${label}</span></button>`;
  }).join('')}</div>`;
}

function openChannelSettings(channel) {
  const original=channel.settings || {};const weights=original.weights || {};
  const allKeys=['stock_video','generated_video','stock_photo','generated_photo','animation','razgon_2d','host','text'];
  const names={'stock_video':'Стокове відео','generated_video':'Створене відео','stock_photo':'Стокове фото','generated_photo':'Створене фото','animation':'Анімація','razgon_2d':'2D-анімація Razgon','host':'Ведучий','text':'Текстові тези'};
  const allColors=['#ffbe0b','#00c8f8','#ad85ff','#ff77b7','#9bdf24','#ff4fd8','#ff8845','#56e3c2'];
  // «Анімація» (the old generated scheme) is retired: its row stays only for a channel that still has a share in it
  const shown=allKeys.map((key,index)=>index).filter(index=>allKeys[index]!=='animation'||Number(weights.animation)>0);
  const keys=shown.map(index=>allKeys[index]),colors=shown.map(index=>allColors[index]);
  const sources=state.channels.filter(item=>item.id!==channel.id);
  let values=Object.fromEntries(keys.map(key=>[key,Number(weights[key] ?? 0)]));
  const body=`${brandingSections(channel)}<p class="settings-purpose regular-only">Скрипт використовує ці налаштування для автоматичної розстановки кадрів у нових планах цього каналу.</p>
    <section class="settings-section regular-only"><h3>Імпорт з іншого каналу</h3><p>Виберіть канал, щоб скопіювати його пропорції форматів у ці поля. Потім натисніть «Зберегти».</p><div class="settings-import-row"><label>Канал для імпорту<select id="settings-source-channel" aria-label="Канал для імпорту" ${sources.length?'':'disabled'}><option value="">Оберіть канал</option>${sources.map(item=>`<option value="${esc(item.id)}">${esc(item.name)}</option>`).join('')}</select></label><button id="settings-import" class="secondary" type="button" disabled>Імпортувати пропорції</button></div><p id="settings-import-feedback" role="status" aria-live="polite">${sources.length?'':'Додайте ще один канал, щоб імпортувати його пропорції.'}</p></section>
    <section class="settings-section regular-only"><h3>Візуальні формати</h3><p>Пропорції форматів під час автоматичного планування. Зміни одного поля не змінюють інші.</p><div id="settings-weights" class="weights-grid"></div><div class="weights-summary"><strong id="settings-total">Разом 100%</strong><div id="settings-bar" class="weights-bar" aria-hidden="true"></div><div id="settings-legend" class="weights-legend" aria-label="Пропорції форматів"></div><p id="settings-feedback" role="status"></p></div><button id="normalize-weights" class="secondary" type="button">Привести до 100%</button></section>
    <section class="settings-section regular-only"><h3>Рух анімації</h3>${motionPicker(original.motion_easing)}<p>Використовується для нових анімацій і ключових кадрів у випусках цього каналу.</p></section>
    <section class="settings-section regular-only"><h3>Початок ролика</h3><label>Формат початкових кадрів<select id="settings-first-format"><option value="auto" ${!original.first_clip_format || original.first_clip_format==='auto'?'selected':''}>Автоматично, з пріоритетом відео</option><option value="video" ${original.first_clip_format==='video'?'selected':''}>Відео за пропорціями</option>${keys.map(key=>`<option value="${key}" ${original.first_clip_format===key?'selected':''}>${names[key]}</option>`).join('')}</select></label><label>Кількість початкових кадрів вибраного формату<input id="settings-first-count" type="number" min="1" max="30" step="1" value="${Number(original.first_clip_count ?? 1)}"></label><label>Тривалість першого кадру, с<input id="settings-first" type="number" min="0" max="60" step="0.1" value="${Number(original.first_clip_seconds ?? 0)}"></label><p>Автоматично на початку обирається відео з додатною часткою. Якщо відео вимкнене, обирається інший доступний формат. Кількість застосовується до вибраного формату. 0 секунд означає тривалість за загальним планом.</p></section>
    <section class="settings-section regular-only"><h3>Розбиття сценарію</h3><div class="settings-two-column"><label>Коротке речення, до слів<input id="settings-short" type="number" min="1" max="15" step="1" value="${Number(original.short_sentence_words ?? 5)}"></label><label>Речень на кадр, максимум<input id="settings-max-sentences" type="number" min="1" max="10" step="1" value="${Number(original.max_sentences_per_scene ?? 4)}"></label></div></section>
    <section class="settings-section"><h3>Пам’ять агента для каналу</h3><p>Правила монтажу, які агент використовує в проєктах цього каналу.</p><textarea id="channel-agent-memory" rows="5" maxlength="30000" disabled></textarea><p id="channel-agent-memory-feedback" role="status">Завантажуємо...</p></section>`;
  // The agent memory is saved by the main Save button too, only when it was loaded and then changed.
  let brandingValues=()=>({}),savedMemory=null;
  modal(`Налаштування: ${channel.name}`,body,[{label:'Видалити канал зі списку',icon:'trash',danger:true,run:()=>confirmDisableChannel(channel)},{label:'Зберегти',primary:true,run:async()=>{
    try {if(!validWeights())throw new Error('Сума часток має дорівнювати 100%.');const settings={...original,weights:Object.fromEntries(keys.filter(key=>values[key]>0).map(key=>[key,values[key]])),motion_easing:$('settings-easing').value,first_clip_seconds:Number($('settings-first').value),first_clip_format:$('settings-first-format').value,first_clip_count:Number($('settings-first-count').value),short_sentence_words:Number($('settings-short').value),max_sentences_per_scene:Number($('settings-max-sentences').value),...brandingValues()};
      const result=await api(`/api/channels/${encodeURIComponent(channel.id)}`,'PATCH',{settings});
      const memory=$('channel-agent-memory').value;
      if(savedMemory!==null&&memory!==savedMemory)await api(`/api/channels/${encodeURIComponent(channel.id)}/agent-memory`,'POST',{memory});
      const next=result.channel || {...channel,settings};state.channels=state.channels.map(item=>item.id===channel.id?next:item);if(state.channel?.id===channel.id)state.channel=next;closeModal();renderChannels();status(`Налаштування каналу «${channel.name}» збережено.`);
    }catch(error){status(error.message,true);}
  }}]);
  $('modal-backdrop').classList.add('settings-modal-open');
  brandingValues=bindBranding(channel);
  const memoryField=$('channel-agent-memory'),memoryFeedback=$('channel-agent-memory-feedback');
  api(`/api/channels/${encodeURIComponent(channel.id)}/agent-memory`).then(data=>{if($('channel-agent-memory')!==memoryField)return;savedMemory=data.memory || '';memoryField.value=savedMemory;memoryField.disabled=false;memoryFeedback.textContent='';}).catch(error=>{if($('channel-agent-memory')===memoryField)memoryFeedback.textContent=error.message;});
  $('settings-easing').value=original.motion_easing || 'ease_in_out';
  const motionButtons=[...document.querySelectorAll('.easing-card')];
  motionButtons.forEach((button,index)=>{
    button.addEventListener('click',()=>{$('settings-easing').value=button.dataset.easing;motionButtons.forEach(item=>{const selected=item===button;item.setAttribute('aria-checked',String(selected));item.tabIndex=selected?0:-1;});});
    button.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;event.preventDefault();const next=motionButtons[(index+(['ArrowRight','ArrowDown'].includes(event.key)?1:3))%4];next.click();});
  });
  const box=$('settings-weights');
  keys.forEach((key,index)=>{const row=document.createElement('label');row.className='weight-row';row.innerHTML=`<span class="weight-dot" style="background:${colors[index]}" aria-hidden="true">${index+1}</span><span>${names[key]}</span><span class="weight-input"><input type="number" min="0" max="100" step="1" value="${Number.isFinite(values[key])?values[key]:0}" data-weight="${key}" aria-label="${names[key]}, відсотків"><span>%</span></span>`;row.querySelector('input').addEventListener('input',event=>{values[key]=event.target.value===''?NaN:Number(event.target.value);drawSummary();});box.append(row);});
  $('settings-source-channel').addEventListener('change',event=>{$('settings-import').disabled=!event.target.value;});
  $('settings-import').addEventListener('click',async()=>{
    const sourceId=$('settings-source-channel').value,button=$('settings-import'),feedback=$('settings-import-feedback');
    if(!sourceId)return;
    button.disabled=true;
    try{
      const data=await api('/api/channels');
      if($('settings-weights')!==box)return;
      const source=(data.channels || []).find(item=>item.id===sourceId);
      if(!source)throw new Error('Канал для імпорту недоступний.');
      const sourceWeights=source.settings?.weights || {};
      const imported=Object.fromEntries(keys.map(key=>[key,Number(sourceWeights[key] ?? 0)]));
      if(Object.keys(sourceWeights).some(key=>!keys.includes(key)) || !validWeights(imported))throw new Error('Перевірте пропорції вихідного каналу: потрібні цілі відсотки із сумою 100%.');
      values=imported;
      box.querySelectorAll('input').forEach(input=>{input.value=values[input.dataset.weight];});
      drawSummary();
      feedback.textContent=`Пропорції каналу «${source.name}» імпортовано. Натисніть «Зберегти», щоб застосувати їх до каналу «${channel.name}».`;
      feedback.classList.remove('invalid');
    }catch(error){if($('settings-weights')===box){feedback.textContent=error.message;feedback.classList.add('invalid');}}
    finally{if($('settings-weights')===box)button.disabled=!$('settings-source-channel').value;}
  });
  $('normalize-weights').addEventListener('click',()=>{try{values=normalizeWeights(values,keys);box.querySelectorAll('input').forEach(input=>{input.value=values[input.dataset.weight];});drawSummary();}catch(error){$('settings-feedback').textContent=error.message;$('settings-feedback').classList.add('invalid');}});
  function validWeights(current=values){return keys.every(key=>Number.isInteger(current[key])&&current[key]>=0&&current[key]<=100)&&keys.reduce((total,key)=>total+current[key],0)===100;}
  function drawSummary(){
    const finite=keys.every(key=>Number.isInteger(values[key])&&values[key]>=0&&values[key]<=100);
    const sum=finite?keys.reduce((total,key)=>total+values[key],0):NaN,valid=validWeights();
    $('settings-total').textContent=Number.isFinite(sum)?`Разом ${sum}% із 100%`:'Перевірте відсотки';
    $('settings-total').classList.toggle('invalid',!valid);$('settings-feedback').classList.toggle('invalid',!valid);
    $('settings-feedback').textContent=!finite?'Укажіть ціле число від 0 до 100 для кожного формату.':sum===100?'Готово до збереження.':sum===0?'Сума 0%. Укажіть частки перед нормалізацією.':sum<100?`Не вистачає ${100-sum}%.`:`Забагато на ${sum-100}%.`;
    const bar=$('settings-bar'),legend=$('settings-legend');bar.replaceChildren();legend.replaceChildren();
    const scale=Math.max(100,keys.reduce((total,key)=>total+(Number.isFinite(values[key])&&values[key]>0?values[key]:0),0));
    keys.forEach((key,index)=>{
      const amount=Number.isFinite(values[key])&&values[key]>0?values[key]:0;if(!amount)return;
      const piece=document.createElement('span');piece.className='weight-segment';piece.style.width=(amount/scale*100)+'%';piece.style.background=colors[index];piece.title=`${index+1}. ${names[key]}: ${amount}%`;
      if(amount/scale>=.055)piece.textContent=`${index+1}`;
      bar.append(piece);
      const item=document.createElement('div');item.className='weight-legend-item';item.innerHTML=`<span class="weight-dot" style="background:${colors[index]}" aria-hidden="true">${index+1}</span><span>${names[key]}</span><strong>${amount}%</strong>`;legend.append(item);
    });
    bar.classList.toggle('invalid',!valid);$('modal-actions').querySelector('.primary').disabled=!valid;
  }
  drawSummary();
}
function normalizeWeights(values,keys){if(keys.some(key=>!Number.isInteger(values[key])||values[key]<0||values[key]>100))throw new Error('Укажіть цілі числа від 0 до 100.');const total=keys.reduce((sum,key)=>sum+values[key],0);if(total===0)throw new Error('Сума 0%. Спочатку задайте хоча б одну частку.');const exact=keys.map(key=>values[key]/total*100),floors=exact.map(Math.floor),remain=100-floors.reduce((sum,value)=>sum+value,0);exact.map((value,index)=>[value-floors[index],index]).sort((a,b)=>b[0]-a[0]||a[1]-b[1]).slice(0,remain).forEach(([,index])=>floors[index]++);return Object.fromEntries(keys.map((key,index)=>[key,floors[index]]));}

async function openStudioSettings(){
  try{
    const result=await api('/api/settings');const settings=result.settings || {};
    modal('Загальні налаштування студії',`<section class="settings-section"><h3>Формат нових випусків</h3><p>Значення застосовуються до проєктів, які будуть створені після збереження.</p><div class="settings-three-column"><label>Ширина, пікселі<input id="studio-width" type="number" min="128" max="7680" step="2" value="${Number(settings.default_width || 1920)}"></label><label>Висота, пікселі<input id="studio-height" type="number" min="128" max="4320" step="2" value="${Number(settings.default_height || 1080)}"></label><label>Кадрів за секунду<input id="studio-fps" type="number" min="1" max="120" step="1" value="${Number(settings.default_fps || 30)}"></label></div></section><section class="settings-section"><h3>Збереження відео</h3><label>Папка для готових MP4 всередині випуску<input id="studio-export-folder" type="text" placeholder="Прямо у папку випуску" value="${esc(settings.export_subfolder || '')}"></label><p>Якщо поле порожнє, готовий файл потрапить прямо у папку випуску.</p></section>${serviceKeyMarkup()}`, [{label:'Скасувати',run:closeModal},{label:'Зберегти',primary:true,run:async()=>{
      try{const next={default_width:Number($('studio-width').value),default_height:Number($('studio-height').value),default_fps:Number($('studio-fps').value),export_subfolder:$('studio-export-folder').value.trim()};await api('/api/settings','PATCH',{settings:next});closeModal();status('Загальні налаштування студії збережено.');}catch(error){status(error.message,true);}
    }}]);
    $('modal-backdrop').classList.add('settings-modal-open');
    await initServiceKeys();
  }catch(error){status(error.message,true);}
}

function confirmDisableChannel(channel){modal(`Видалити канал «${channel.name}» зі списку?`,'<p>Канал зникне зі списку студії. Його папка та файли залишаться на комп’ютері.</p>',[{label:'Скасувати',run:closeModal},{label:'Видалити канал зі списку',icon:'trash',danger:true,run:async()=>{try{await api(`/api/channels/${encodeURIComponent(channel.id)}`,'DELETE');closeModal();await loadChannels();status('Канал видалено зі списку.');}catch(error){status(error.message,true);}}}]);}

function exportIsActive(){return !!state.job && state.job.project_id===state.project?.id && ['queued','running','cancelling'].includes((state.job.status||'').toLowerCase());}
function exportTimeRemaining(seconds){
  if(!Number.isFinite(seconds) || seconds<0)return 'Розраховуємо час до завершення';
  if(seconds<60)return 'Орієнтовно залишилося менше хвилини';
  const minutes=Math.ceil(seconds/60),hours=Math.floor(minutes/60),rest=minutes%60;
  return `Орієнтовно залишилося: ${hours?`${hours} год${rest?` ${rest} хв`:''}`:`${minutes} хв`}`;
}
function updateExportLock(){
  const locked=exportIsActive();
  for(const id of ['editor-workspace','editor-timeline','project-plan','project-title'])$(id).inert=locked;
  $('undo').disabled=locked || !state.project?.can_undo;$('redo').disabled=locked || !state.project?.can_redo;
  const exportPercent=Math.max(0,Math.min(100,Math.round(state.job?.progress || 0)));
  $('export-open').innerHTML=locked?`${exportSpinner}<span>Експорт триває · ${exportPercent}%</span>`:'Експорт MP4';
  $('export-open').classList.toggle('export-busy',locked);$('export-open').setAttribute('aria-busy',String(locked));
  if(state.job){if(['queued','running','cancelling'].includes(state.job.status))state.projectExports.set(state.job.project_id,state.job);else state.projectExports.delete(state.job.project_id);updateOverviewExports();}
  if(locked)$('save-state').textContent='● Проєкт заблоковано під час експорту';
  else if(state.project)$('save-state').textContent='● Локально збережено';
}
function exportActions(){
  const actions=[{label:'Закрити вікно',run:closeModal}];
  if(state.job?.status!=='cancelling')actions.push({label:'Скасувати експорт',danger:true,run:async()=>{
    const button=[...$('modal-actions').querySelectorAll('button')].find(b=>b.textContent==='Скасувати експорт');
    if(button){button.disabled=true;button.textContent='Зупиняємо...';}
    try{const result=await api(`/api/jobs/${encodeURIComponent(state.job.id)}/cancel`,'POST',{});state.job=result.job;updateExportLock();await pollJob();}
    catch(error){if(button){button.disabled=false;button.textContent='Скасувати експорт';}status(error.message,true);}
  }});
  return actions;
}
async function openExport() {
  if(!state.project)return;
  try{const result=await api(`/api/projects/${encodeURIComponent(state.project.id)}/export/active`);if(result.job)state.job=result.job;updateExportLock();}catch(error){status(error.message,true);return;}
  if(!state.project.production?.export_ready){
    modal('Експорт ролика',`<p>${esc(state.project.production?.reason || 'Спочатку додайте таймінги готової озвучки.')}</p>`,[{label:'Зрозуміло',primary:true,run:closeModal}]);
    return;
  }
  if(exportIsActive()){
    modal('Експорт ролика','<div id="render-state" aria-live="polite"></div>',exportActions());
    pollJob();return;
  }
  const gaps=visualGaps(),shownGaps=gaps.slice(0,6);
  const gapWarning=gaps.length?`<div class="export-gaps" role="note"><p><strong>Без кадру: ${gaps.length} ${gaps.length===1?'місце':gaps.length<5?'місця':'місць'}.</strong> У готовому відео там буде порожній екран.</p><div class="export-gap-list">${shownGaps.map((gap,index)=>`<button type="button" data-gap="${index}">${clock(gap.start)}–${clock(gap.end)}</button>`).join('')}${gaps.length>shownGaps.length?`<span>і ще ${gaps.length-shownGaps.length}</span>`:''}</div></div>`:'';
  modal('Експорт ролика',`${gapWarning}<div id="render-state" aria-live="polite"><p>Готовий MP4 збережеться у папці випуску або вибраній підпапці.</p></div>`,[{label:'Закрити',run:closeModal},{label:'Почати експорт',primary:true,run:async()=>{
    const button=$('modal-actions').querySelector('.primary');
    if(button.disabled)return;
    button.disabled=true;button.textContent='Підготовка...';
    $('render-state').textContent='Готуємо проєкт до експорту...';
    const projectId=state.project.id, renderState=$('render-state');
    try{const result=await api(`/api/projects/${encodeURIComponent(projectId)}/export`,'POST',{confirm_export:true});state.job=result.job;if(!state.job?.id)throw new Error('Сервер не повернув завдання експорту.');updateExportLock();if(renderState.isConnected){modal('Експорт ролика','<div id="render-state" aria-live="polite"></div>',exportActions());}pollJob();}catch(error){status(error.message,true);if(renderState.isConnected)renderState.textContent=error.message;button.disabled=false;button.textContent='Почати експорт';}
  }}]);
  for(const button of document.querySelectorAll('.export-gap-list button'))button.addEventListener('click',()=>{const gap=shownGaps[Number(button.dataset.gap)];closeModal();stopPlayback();state.playhead=gap.start;renderPreview();revealTimelineTime(gap.start);});
}
function revealTimelineTime(time){
  const marks=document.querySelector('.time-ruler-marks'),scroller=document.querySelector('.timeline-scroll');if(!marks)return;
  const x=(time-timelineOrigin())/timelineSpan()*marks.offsetWidth;scroller.scrollLeft=Math.max(0,x-scroller.clientWidth/3);
}
async function pollJob(){
  if(!state.job)return;
  const jobId=state.job.id;
  try{
    const result=await api(`/api/jobs/${encodeURIComponent(jobId)}`);
    if(state.job?.id!==jobId)return;
    state.job=result.job;
    const jobStatus=(state.job.status||'').toLowerCase();
    const complete=['done','complete','completed'].includes(jobStatus),failed=['failed','error'].includes(jobStatus),cancelled=jobStatus==='cancelled';
    updateExportLock();
    const progress=Math.max(0,Math.min(100,Math.round(state.job.progress||0)));
    const target=$('render-state');
    if(target && state.project?.id===state.job.project_id){
      const label=cancelled?'Експорт скасовано':jobStatus==='cancelling'?'Зупиняємо експорт':failed?'Експорт не завершився':complete?'Експорт завершено':jobStatus==='queued'?'Експорт у черзі':state.job.stage==='preparing_cloud'?'Завантажуємо матеріали з хмари':state.job.stage==='razgon_frames'?'Малюємо кадри Razgon':state.job.stage==='razgon_sound'?'Зводимо звук':state.job.stage==='verifying'?'Перевіряємо готовий файл':'Експорт триває';
      const detail=cancelled?'Проєкт знову доступний для редагування.':jobStatus==='cancelling'?'Зачекайте, доки студія завершить зупинку.':failed?'Перевірте повідомлення нижче.':complete?'Готовий файл збережено у папці випуску.':state.job.stage==='razgon_frames'?`Готово ${Number(state.job.razgon_completed)||0} із ${Number(state.job.razgon_total)||0} кадрів. Проєкт заблоковано до завершення експорту.`:state.job.stage==='preparing_cloud'?`Завантажено ${Number(state.job.cloud_completed)||0} із ${Number(state.job.cloud_total)||0} матеріалів. Проєкт заблоковано до завершення експорту.`:state.job.gpu_fallback?'Швидкий режим недоступний, студія продовжує звичайний експорт. Проєкт заблоковано до завершення експорту.':progress===0?'Студія готує матеріали. На початку це може зайняти деякий час. Проєкт заблоковано до завершення експорту.':'Проєкт заблоковано до завершення експорту.';
      const estimate=!complete&&!failed&&!cancelled&&jobStatus!=='cancelling'?`<p>${exportTimeRemaining(state.job.remaining_seconds)}</p>`:'';
      target.innerHTML=`<p>${label}</p><div class="render-progress"><span style="width:${progress}%"></span></div><p>${progress}%</p>${estimate}<p>${detail}</p>${state.job.output_path?`<p>Файл: ${esc(state.job.output_path)}</p>`:''}${state.job.error?`<p class="render-error">${esc(state.job.error)}</p>`:''}`;
    }
    if(complete||failed||cancelled){if(state.poll)clearInterval(state.poll);state.poll=null;if(target){const box=$('modal-actions');box.replaceChildren();const close=document.createElement('button');close.type='button';close.textContent='Закрити';close.addEventListener('click',closeModal);box.append(close);}status(cancelled?'Експорт скасовано.':failed?'Експорт не завершився.':'Експорт завершено.',failed);return;}
    if(!state.poll)state.poll=setInterval(pollJob,1500);
  }catch(error){if(state.poll)clearInterval(state.poll);state.poll=null;const target=$('render-state');if(target)target.textContent=error.message;status(error.message,true);}
}

$('add-channel').addEventListener('click',()=>{modal('Додати канал','<p>Створіть новий канал у папці YOUTUBE або додайте наявну папку каналу.</p><label>Назва нового каналу<input id="new-channel-name" type="text" maxlength="100" placeholder="Назва каналу"></label>',[{label:'Скасувати',run:closeModal},{label:'Обрати папку',run:async()=>{try{const result=await api('/api/channels/pick','POST',{});if(!result.channel)throw new Error('Папку не додано.');closeModal();await loadChannels(result.channel.id);status(`Канал «${result.channel.name}» додано.`);}catch(error){status(error.message,true);}}},{label:'Створити',primary:true,run:async()=>{try{const name=$('new-channel-name').value.trim();if(!name)throw new Error('Введіть назву каналу.');const result=await api('/api/channels/create','POST',{name});closeModal();await loadChannels(result.channel.id);status(`Канал «${result.channel.name}» створено.`);}catch(error){status(error.message,true);}}}]);});
for(const logo of document.querySelectorAll('.brand-logo')){logo.addEventListener('click',showProjectList);logo.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();showProjectList();}});}
$('overview-create').addEventListener('click',()=>$('add-project').click());
$('overview-channel-settings').addEventListener('click',()=>{if(state.channel)openChannelSettings(state.channel);});
$('add-project').addEventListener('click',()=>{if(!state.channel){status('Спершу додайте канал.',true);return;}modal('Новий випуск','<label>Назва випуску<input id="new-project-name" type="text" placeholder="Назва ролика"></label>',[{label:'Скасувати',run:closeModal},{label:'Створити',primary:true,run:async()=>{try{const name=$('new-project-name').value.trim();if(!name)throw new Error('Введіть назву випуску.');const result=await api('/api/projects','POST',{channel_id:state.channel.id,name});closeModal();await selectChannel(state.channel.id);if(result.project?.id)await selectProject(result.project.id,{view:'plan'});}catch(error){status(error.message,true);}}}]);});
$('global-settings').addEventListener('click',openStudioSettings);
$('asset-search').addEventListener('input',event=>{state.search=event.target.value;renderAssets();if(state.libraryTab==='pixabay')debouncedPixabay();});
let searchTimer;
function debouncedPixabay(){clearTimeout(searchTimer);searchTimer=setTimeout(searchPixabay,350);}
async function searchPixabay(){const query=state.search.trim();if(!query){state.pixabay=[];renderAssets();return;}try{const data=await api(`/api/pixabay/search?kind=${state.pixabayKind}&q=${encodeURIComponent(query)}`);state.pixabay=data.results||[];renderAssets();status(`Знайдено ${state.pixabay.length} матеріалів Pixabay.`);}catch(error){state.pixabay=[];renderAssets();status(error.message,true);}}
document.querySelectorAll('.library-tabs button').forEach(button=>button.addEventListener('click',()=>{state.libraryTab=button.dataset.tab;$('pixabay-kind-control').hidden=state.libraryTab!=='pixabay';document.querySelectorAll('.library-tabs button').forEach(item=>{item.classList.toggle('active',item===button);item.setAttribute('aria-selected',String(item===button));});renderAssets();if(state.libraryTab==='pixabay')searchPixabay();}));
$('pixabay-kind').addEventListener('change',event=>{state.pixabayKind=event.target.value;searchPixabay();});
$('add-file').addEventListener('click',()=>{if(!state.project){status('Оберіть випуск.',true);return;}$('local-media-file').click();});
$('local-media-file').addEventListener('change',async event=>{const file=event.target.files?.[0];event.target.value='';if(!file||!state.project)return;try{status(`Додаю «${file.name}»...`);const response=await fetch(`/api/projects/${encodeURIComponent(state.project.id)}/assets/upload`,{method:'POST',headers:{'Content-Type':'application/octet-stream','X-File-Name':encodeURIComponent(file.name)},body:file});const result=await response.json();if(!response.ok)throw new Error(result.error || `Помилка ${response.status}`);await refreshCurrentProject();status(`Матеріал «${result.asset?.name || file.name}» додано.`);}catch(error){status(error.message,true);}});
$('apply-trim').addEventListener('click',()=>{if(!state.selected)return;const start=Number($('scene-start').value),duration=Number($('scene-duration').value);if(!Number.isFinite(start)||!Number.isFinite(duration)||start<0||duration<=0){status('Укажіть правильні початок і тривалість.',true);return;}action('trim_scene',{scene_id:state.selected,start,duration},'Час кадру оновлено.').catch(()=>{});});
$('add-scene').addEventListener('click',()=>{if(!state.project)return;modal('Новий кадр','<label>Назва<input id="new-scene-title" type="text" placeholder="Що буде у кадрі"></label><label>Тривалість, с<input id="new-scene-duration" type="number" min="0.1" step="0.1" value="5"></label><p>Матеріал можна додати пізніше з медіатеки.</p>',[{label:'Скасувати',run:closeModal},{label:'Додати кадр',primary:true,run:async()=>{try{const title=$('new-scene-title').value.trim() || 'Новий кадр',duration=Number($('new-scene-duration').value);if(!Number.isFinite(duration)||duration<=0)throw new Error('Укажіть правильну тривалість.');await action('add_scene',{type:'color',title,duration},'Кадр додано.');closeModal();}catch(error){status(error.message,true);}}}]);});
$('apply-transition').addEventListener('click',()=>{if(!selectedScene())return;const type=$('transition-type').value;action('set_transition',{scene_id:state.selected,transition_type:type,duration:type==='cut'?0:Number($('transition-duration').value)},'Перехід оновлено.').catch(()=>{});});
$('transition-type').addEventListener('change',event=>{const cut=event.target.value==='cut';$('transition-duration').disabled=cut;if(!cut && Number($('transition-duration').value)<=0)$('transition-duration').value='0.4';});
$('clip-volume').addEventListener('input',event=>{$('clip-volume-value').textContent=event.target.value+'%';});
$('apply-volume').addEventListener('click',()=>{if(!state.selected)return;action('set_clip_volume',{clip_id:state.selected,volume:Number($('clip-volume').value)/100},'Гучність оновлено.').catch(()=>{});});
$('move-left').addEventListener('click',()=>moveSelected(-1));$('move-right').addEventListener('click',()=>moveSelected(1));
$('delete-selected').addEventListener('click',()=>{if(!state.selected)return;const scene=selectedScene();const type=scene?'delete_scene':'remove_track_clip';const payload=scene?{scene_id:scene.id}:{clip_id:state.selected};action(type,payload,'Фрагмент прибрано. Дію можна скасувати.').then(()=>{state.selected=null;state.selectedTrack=null;renderInspector();renderTimeline();}).catch(()=>{});});
function moveSelected(delta){const list=scenes(),index=list.findIndex(s=>s.id===state.selected);if(index<0)return;const to=Math.max(0,Math.min(list.length-1,index+delta));if(to!==index)action('move_scene',{scene_id:state.selected,to_index:to},'Кадр переміщено.').catch(()=>{});}
$('split-scene').addEventListener('click',()=>{const scene=selectedScene();if(!scene)return;const at=state.playhead>seconds(scene.start)&&state.playhead<seconds(scene.start)+seconds(scene.duration)?state.playhead:seconds(scene.start)+seconds(scene.duration)/2;action('split_scene',{scene_id:scene.id,at},'Кадр розділено.').catch(()=>{});});
$('add-transition').addEventListener('click',()=>{if(isUniversal()){openUniversalTransition();return;}if(!selectedScene()){status('Виберіть кадр перед переходом.',true);return;}modal('Перехід після кадру','<p>Виберіть тип переходу для поточного кадру.</p>',[{label:'Склейка',run:()=>{action('set_transition',{scene_id:state.selected,transition_type:'cut',duration:0},'Перехід оновлено.').then(closeModal).catch(()=>{});}},{label:'Плавний · 0,4 с',primary:true,run:()=>{action('set_transition',{scene_id:state.selected,transition_type:'crossfade',duration:.4},'Перехід додано.').then(closeModal).catch(()=>{});}}]);});
document.querySelectorAll('.transition-chip').forEach(button=>{button.addEventListener('dragstart',event=>event.dataTransfer.setData('application/x-videostudio-transition',button.dataset.transition));button.addEventListener('click',()=>{if(isUniversal()){const selected=universalSelection();if(!selected){status('Виберіть кліп для переходу.',true);return;}const type=button.dataset.transition;action('set_transition',{clip_id:selected.clip.id,type,duration:type==='cut'?0:.4},'Перехід оновлено.').catch(()=>{});return;}if(!selectedScene()){status('Виберіть кадр для переходу.',true);return;}const type=button.dataset.transition;action('set_transition',{scene_id:state.selected,transition_type:type,duration:type==='cut'?0:.4},'Перехід оновлено.').catch(()=>{});});});
$('add-text').addEventListener('click',()=>{if(!state.project)return;if(isUniversal()){openUniversalText();return;}modal('Додати текст',`<label>Текст<input id="new-text" type="text" placeholder="Важлива теза"></label><label>Початок, с<input id="new-text-start" type="number" min="0" step="0.1" value="${state.playhead.toFixed(1)}"></label><label>Тривалість, с<input id="new-text-duration" type="number" min="0.1" step="0.1" value="4"></label>`,[{label:'Скасувати',run:closeModal},{label:'Додати',primary:true,run:async()=>{try{const text=$('new-text').value.trim();if(!text)throw new Error('Введіть текст.');await action('add_text',{start:Number($('new-text-start').value),duration:Number($('new-text-duration').value),text},'Текстову сцену додано.');closeModal();}catch(error){status(error.message,true);}}}]);});
$('undo').addEventListener('click',()=>action('undo',{},'Дію скасовано.').catch(()=>{}));$('redo').addEventListener('click',()=>action('redo',{},'Дію повторено.').catch(()=>{}));
$('export-open').addEventListener('click',openExport);
$('seek').addEventListener('input',event=>{state.playhead=timelineOrigin()+timelineSpan()*Number(event.target.value)/1000;renderPreview();updateTimelinePlayhead();});
$('play-pause').addEventListener('click',()=>{if(!state.project)return;state.playing=!state.playing;if(state.playing && state.playhead>=timelineOrigin()+timelineSpan()-.04)state.playhead=timelineOrigin();$('play-pause').textContent=state.playing?'❚❚':'▶';$('play-pause').setAttribute('aria-label',state.playing?'Пауза':'Відтворити');if(state.playing){syncStudioAudio();requestAnimationFrame(tick);}else {$('preview-video').pause();state.previewNodes.forEach(node=>node.querySelectorAll('video').forEach(video=>video.pause()));state.audioNodes.forEach(item=>item.element.pause());}});
$('monitor-audio').addEventListener('click',()=>{
  if(state.monitorMuted || state.monitorVolume===0){state.monitorVolume=state.monitorPreviousVolume || 1;state.monitorMuted=false;}
  else{state.monitorPreviousVolume=state.monitorVolume;state.monitorVolume=0;state.monitorMuted=true;}
  saveMonitorSettings();updateMonitorControls();renderPreview();status(state.monitorMuted?'Звук перегляду вимкнено.':'Звук перегляду увімкнено.');
});
$('monitor-volume').addEventListener('input',event=>{state.monitorVolume=Number(event.target.value)/100;state.monitorMuted=state.monitorVolume===0;if(state.monitorVolume>0)state.monitorPreviousVolume=state.monitorVolume;saveMonitorSettings();updateMonitorControls();renderPreview();});
let lastFrame=0;
function tick(now){
  if(!state.playing){lastFrame=0;return;}if(!lastFrame)lastFrame=now;
  const delta=Math.min(.1,(now-lastFrame)/1000);lastFrame=now;
  const master=state.audioNodes.find(({clip})=>state.playhead>=seconds(clip.start)&&state.playhead<seconds(clip.start)+seconds(clip.duration)&&Number(clip.volume ?? 1)>0&&!(isUniversal()&&clipIsMuted(clip)));
  if(master){const audio=master.element;if(audio._studioSeekTarget!=null&&!audio.seeking&&audio.readyState>=2&&Math.abs(audio.currentTime-audio._studioSeekTarget)<.15)audio._studioSeekTarget=null;if(audio._studioSeekTarget==null&&audio.readyState>=2&&!audio.seeking&&!audio.paused)state.playhead=seconds(master.clip.start)+audio.currentTime-seconds(master.clip.trim_start);}
  else state.playhead+=delta;
  const end=timelineOrigin()+timelineSpan();if(state.playhead>=end){state.playhead=Math.max(timelineOrigin(),end-.001);stopPlayback();lastFrame=0;}
  renderPreview();if(state.playing)requestAnimationFrame(tick);
}
$('zoom-in').addEventListener('click',()=>setTimelineZoom(timelineZoomLevels.find(value=>value>state.zoom) || timelineZoomLevels.at(-1)));
$('zoom-out').addEventListener('click',()=>setTimelineZoom([...timelineZoomLevels].reverse().find(value=>value<state.zoom) || timelineZoomLevels[0]));
$('zoom-value').addEventListener('click',()=>setTimelineZoom(1));

$('loading-go-home').addEventListener('click',()=>{
  cancelLocationRestore();++state.navigation;
  state.channel=null;state.projects=[];state.project=null;
  renderChannels();renderProjects();renderProject();
  history.pushState(null,'','/');restoreCurrentLocation();
});
window.addEventListener('popstate',()=>{closeModal();restoreCurrentLocation();});
window.addEventListener('DOMContentLoaded',restoreCurrentLocation);
