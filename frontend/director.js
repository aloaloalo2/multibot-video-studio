// director.js — the steps of an animated episode on its plan, as tabs: 1 the voice, 2 the director, 3 making the video.
// Once the voice is recognised the Studio hands the episode to Claude Opus 5.5 (high effort), which directs it and writes
// the frame plan back (backend/director.py). The tabs say where the episode stands; each opens its own pane with its
// buttons and data: the voice summary, recognition report and script; the director's report with the timeline and frame
// table; how many frames to make with the request and cost. The current stage opens first.
const directorRuns={};
const stepChoice=new Map();
let directorTimer=null,productionTimer=null;

const stepIcons={voice:'<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6"/></svg>',
  director:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 10h16v9a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1zM4 10l-.6-3.3a1 1 0 0 1 .8-1.2L17 3.2a1 1 0 0 1 1.2.8L18.7 7M8 4.8l2.4 3.6M13.2 3.9l2.4 3.6"/></svg>',
  video:'<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 5v14M17 5v14M3 9.5h4M3 14.5h4M17 9.5h4M17 14.5h4"/></svg>'};

function directorAnimated(){return state.channel?.settings?.channel_kind==='animated';}

// An animated episode has no frames until the director writes them: the Studio's own split by sentences is only
// the timing behind them, so the plan shows the steps instead of those frames.
function directorAwaited(){return directorAnimated() && state.plan?.frame_source!=='razgon-direction';}
function directorDone(){return state.plan?.frame_source==='razgon-direction' && !state.plan?.director_stale;}

function renderDirectorWait(panel){
  const heading=document.createElement('div');heading.className='plan-heading';heading.innerHTML='<div class="plan-heading-label"><h1>План ролика</h1></div>';
  panel.append(heading);
  renderDirectorStatus(panel);
}

async function loadDirector(id){
  try{directorRuns[id]=(await api(`/api/projects/${encodeURIComponent(id)}/director`)).director || {status:'none'};}
  catch{directorRuns[id]={status:'none'};}
  return directorRuns[id];
}

function tokenCount(value){return value>=1e6?`${(value/1e6).toFixed(1).replace('.',',')} млн токенів`:`${Math.round(value/1000)} тис. токенів`;}

function directorTime(seconds){return new Date(seconds*1000).toLocaleTimeString('uk-UA',{hour:'2-digit',minute:'2-digit'});}

function stepButton(label,run,primary=false){const b=document.createElement('button');b.type='button';b.className=primary?'primary':'secondary';b.textContent=label;b.addEventListener('click',run);return b;}

function episodeStep(number,icon,title){
  const step=document.createElement('section');step.className='episode-step';step.tabIndex=0;step.setAttribute('role','tab');
  step.innerHTML=`<span class="episode-step-run" aria-hidden="true"></span><div class="episode-step-head"><span class="episode-step-icon">${stepIcons[icon]}</span><span class="episode-step-number">${number}</span><strong>${title}</strong></div><p></p><small class="episode-step-cost"></small>`;
  return step;
}

function renderDirectorStatus(panel){
  if(!state.project || !directorAnimated())return;
  const id=state.project.id,steps=document.createElement('div');steps.className='episode-steps';steps.dataset.project=id;steps.setAttribute('role','tablist');
  const items=[episodeStep(1,'voice','Озвучка'),episodeStep(2,'director','Режисура'),episodeStep(3,'video','Створення відео')];
  items[1].setAttribute('aria-live','polite');
  items.forEach((step,index)=>{
    const pick=()=>{stepChoice.set(id,index);showStepPane(steps);};
    step.addEventListener('click',pick);
    step.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();pick();}});
  });
  const stage=document.createElement('p');stage.className='episode-stage';
  steps.append(...items);panel.append(stage,steps);
  // The rest of the plan is drawn right after this call: once it is there, its blocks move under the step they belong to.
  queueMicrotask(()=>arrangeStepPanes(panel,steps));
  if(!directorRuns[id])loadDirector(id).then(()=>{if(state.project?.id===id&&steps.isConnected)refreshSteps(steps);});
  refreshSteps(steps);
}

function arrangeStepPanes(panel,steps){
  if(!steps.isConnected)return;
  const panes=['voice','director','video'].map(name=>{
    const pane=document.createElement('div');pane.className='episode-pane';pane.dataset.pane=name;pane.setAttribute('role','tabpanel');
    const actions=document.createElement('div');actions.className='episode-pane-actions';const info=document.createElement('div');info.className='episode-pane-info';
    pane.append(actions,info);return pane;});
  const take=(pane,selector)=>{for(const node of panel.querySelectorAll(`:scope > ${selector}`))pane.append(node);};
  const [voice,director,video]=panes;
  // Voice: the summary of frames and voice length, the recognition report in full and the script. Its own buttons go to
  // the pane's button row; the report button is not needed next to the report itself.
  panel.querySelector(':scope > .plan-heading .plan-stage-tag')?.remove();   // the tabs show the stage now
  const summary=panel.querySelector(':scope > .plan-summary');
  if(summary){summary.querySelector('.speech-report-button')?.remove();summary.querySelector('.plan-bind-audio')?.remove();voice.append(summary);}
  const report=state.analysis?.job?.project_id===state.project?.id?state.analysis.report:null;
  const reportSlot=document.createElement('div');voice.append(reportSlot);
  if(report)appendSpeechReport(reportSlot,report);
  else if(state.project){
    // A plan opened by its link has not loaded the recognition yet: fetch it and fill the pane when it comes.
    const id=state.project.id;
    api(`/api/projects/${encodeURIComponent(id)}/analysis`).then(result=>{
      if(state.project?.id!==id||!reportSlot.isConnected)return;
      state.analysis=result;if(result.report)appendSpeechReport(reportSlot,result.report);refreshSteps(steps);
    }).catch(()=>{});
  }
  take(voice,'.plan-script');
  // Director: the frames it wrote.
  for(const selector of ['.plan-settings-warning','.plan-timeline','.plan-table-fold','.plan-table'])take(director,selector);
  // An animated film is all one format and its plan is not agreed in a chat: those service lines only add doubt here.
  for(const node of panel.querySelectorAll(':scope > .plan-formats, :scope > .plan-note'))node.remove();
  // Video: how many frames to make. The plan's cost estimate counts stock, generated photos and DeepSeek requests,
  // none of which an animated film uses, so it is left out here.
  // the frame picker comes first in its tab, above the team and the feed
  const picker=panel.querySelector(':scope > .plan-start');if(picker)video.querySelector('.episode-pane-info').before(picker);
  panel.querySelector(':scope > .plan-cost-estimate')?.remove();
  steps.after(...panes);
  refreshSteps(steps);
}

function paneOf(steps,name){let pane=steps.nextElementSibling;while(pane?.classList.contains('episode-pane')){if(pane.dataset.pane===name)return pane;pane=pane.nextElementSibling;}return null;}

// Fills every tab's status line and every pane's buttons from the current state; runs again whenever the director run changes.
function refreshSteps(steps){
  if(!steps?.isConnected)return;
  const id=steps.dataset.project,[voice,director,video]=steps.querySelectorAll('.episode-step');
  fillVoice(voice,paneOf(steps,'voice'));
  fillDirector(director,paneOf(steps,'director'),id);
  fillVideo(video,paneOf(steps,'video'));
  markStage(steps);
}

function fillVoice(step,pane){
  const analysis=state.analysis?.job?.project_id===state.project?.id?state.analysis:null,report=analysis?.report,job=analysis?.job,text=step.querySelector('p');
  const percent=report?`${Number(report.word_match_percent).toFixed(1)}%`:'';
  if(state.project?.production?.plan_ready){step.dataset.state='done';text.textContent=percent?`Розпізнано, ${percent} слів збіглося`:'Розпізнано';}
  else if(job && ['queued','running'].includes(job.status)){step.dataset.state='active';text.textContent=`${(typeof speechStageNames!=='undefined'&&speechStageNames[job.stage]) || 'Обробка'}: ${job.progress}%`;}
  else if(report){step.dataset.state='failed';text.textContent=`Потрібна перевірка, ${percent}`;}
  else if(job?.status==='failed'){step.dataset.state='failed';text.textContent='Не вдалося розпізнати';}
  else{step.dataset.state='waiting';text.textContent='Додайте аудіо озвучки';}
  step.querySelector('.episode-step-cost').textContent=step.dataset.state==='waiting'?'Ще нічого не витрачено':'Витрачено $0 · Whisper на цьому Mac';
  if(!pane)return;
  // Once the voice is in, the button replaces it: a new recognition follows, and the director redoes the plan if the text changed.
  const replace=step.dataset.state==='done';
  const button=stepButton(replace?'Замінити озвучку':'Додати озвучку / таймінги',openNarrationBinding,step.dataset.state==='waiting');
  if(replace)button.title='Нова озвучка або таймінги: студія розпізнає її заново, а режисер переробить план, якщо змінився текст';
  pane.querySelector('.episode-pane-actions').replaceChildren(button);
  pane.querySelector('.episode-pane-info').textContent=job?.status==='failed'?job.error:!report&&step.dataset.state!=='active'?'Звіт розпізнавання з’явиться тут, коли студія розпізнає озвучку.':'';
}

function fillDirector(step,pane,id){
  const run=directorRuns[id] || {status:'loading'},synced=!!state.project?.production?.plan_ready,directed=directorDone(),text=step.querySelector('p');
  const actions=pane?.querySelector('.episode-pane-actions'),info=pane?.querySelector('.episode-pane-info');
  actions?.replaceChildren();info?.replaceChildren();
  if(!step.querySelector('.director-model')){const who=document.createElement('span');who.className='director-model';who.textContent='Opus 5.5 · високий';step.querySelector('.episode-step-head').append(who);}
  const restart=label=>actions?.append(stepButton(label,()=>startDirector(id)));
  // What the run actually used. Claude Code runs on the subscription; the dollar figure is what it would cost through the API.
  const cost=step.querySelector('.episode-step-cost');
  if(run.cost_usd){cost.textContent=`Витрачено $${Number(run.cost_usd).toFixed(2)} за цінами API${run.tokens_in?` · ${tokenCount(run.tokens_in)} на вхід, ${tokenCount(run.tokens_out)} на вихід`:''}${run.minutes?` · ${run.minutes} хв`:''}`;cost.title='Режисура йде за підпискою Claude, тож окремо не оплачується; сума показує, скільки це коштувало б через API';}
  else cost.textContent=run.status==='running'||run.status==='queued'?'Рахуємо, поки йде режисура':'Ще нічого не витрачено';
  const say=message=>{if(info){const line=document.createElement('p');line.className='plan-note';line.textContent=message;info.append(line);}};
  clearTimeout(directorTimer);
  step.classList.toggle('running',run.status==='queued' || run.status==='running');
  if(run.status==='loading'){step.dataset.state=directed?'done':'waiting';text.textContent='Перевіряємо...';}
  else if(run.status==='queued' || run.status==='running'){
    step.dataset.state='active';text.textContent=`Іде${run.started_at?` з ${directorTime(run.started_at)}`:''}`;
    say('Режисер ділить озвучку на шоти й пише план кадрів. Сцени він не малює. Сторінку можна закрити: план оновиться сам.');
    renderTeam(info,'director',id,true);
    directorTimer=setTimeout(()=>pollDirector(id),8000);
  }else if(run.status==='failed'){
    step.dataset.state='failed';text.textContent='Не вдалася';say(run.error || 'Невідома помилка');restart('Спробувати ще раз');
  }else if(run.status==='done' || directed){
    step.dataset.state='done';
    const frames=run.frames || (directed?state.plan.frames.length:0);
    text.textContent=frames?`${frames} кадрів`:'Готово';
    if(run.status==='done'){
      say(`Готово о ${directorTime(run.finished_at)}.`);
      if(run.summary&&info){const details=document.createElement('details');details.className='plan-script';const summary=document.createElement('summary');summary.textContent='Звіт режисера';const body=document.createElement('div');body.className='plan-script-text';body.textContent=run.summary;details.append(summary,body);info.append(details);}
      renderTeam(info,'director',id,false);
    }
    restart('Переробити режисуру');
  }else{
    step.dataset.state=synced?'active':'waiting';text.textContent=synced?'Можна запускати':'Після озвучки';
    say(synced?'Озвучку розпізнано. Режисер розіб’є її на шоти й запише план кадрів.':'Режисура почнеться сама, щойно студія розпізнає озвучку.');
    if(actions){const b=stepButton('Запустити режисуру',()=>startDirector(id),synced);b.disabled=!synced;actions.append(b);}
  }
}

// Step 3 follows the production request: the author picks the first frames, the agent draws their scenes.
function fillVideo(step,pane){
  const text=step.querySelector('p'),request=state.project?.production_request;
  const actions=pane?.querySelector('.episode-pane-actions'),info=pane?.querySelector('.episode-pane-info');
  if(info)info.textContent='';
  const cost=step.querySelector('.episode-step-cost'),working=['requested','in_progress'].includes(request?.status);
  step.classList.toggle('running',working&&directorDone());
  cost.textContent=request?.cost_usd?`Витрачено $${Number(request.cost_usd).toFixed(2)} за цінами API${request.tokens_in?` · ${tokenCount(request.tokens_in)} на вхід, ${tokenCount(request.tokens_out)} на вихід`:''}${request.minutes?` · ${request.minutes} хв`:''}`
    :working?'Рахуємо, поки агент малює':'Ще нічого не витрачено';
  if(!directorDone()){step.dataset.state='waiting';text.textContent='Після режисури';if(info)info.textContent='Після режисури тут можна вибрати, скільки перших кадрів зробити, і агент намалює їхні сцени.';return;}
  clearTimeout(productionTimer);
  if(working){
    step.dataset.state='active';text.textContent=`Малює кадри 1–${request.frames}`;
    if(info){const line=document.createElement('p');line.className='plan-note';line.textContent=`Claude Opus 5.5 малює сцени кадрів 1–${request.frames}${request.started_at?` з ${directorTime(request.started_at)}`:''}. Готові кадри ляжуть на таймлайн у «Монтажі». Сторінку можна закрити.`;info.append(line);}
    renderTeam(info,'production',state.project.id,true);
    productionTimer=setTimeout(()=>pollProduction(state.project.id),8000);
  }else if(request?.status==='failed'){
    step.dataset.state='failed';text.textContent=`Кадри 1–${request.frames} не вдалися`;if(info)info.textContent=`${request.error || 'Невідома помилка'} Виберіть кадри й натисніть ще раз.`;
  }else if(request?.status==='done'){
    const all=request.frames>=request.total_frames;step.dataset.state=all?'done':'active';
    text.textContent=all?'Усі кадри готові':`Кадри 1–${request.frames} готові`;
    if(info){info.textContent=all?'':'Готові кадри вже на таймлайні в «Монтажі». Перегляньте їх і, якщо подобаються, виберіть наступні.';
      if(request.summary){const details=document.createElement('details');details.className='plan-script';const summary=document.createElement('summary');summary.textContent='Звіт агента';const body=document.createElement('div');body.className='plan-script-text';body.textContent=request.summary;details.append(summary,body);info.append(details);}
      renderTeam(info,'production',state.project.id,false);}
  }else{step.dataset.state='active';text.textContent='Виберіть кадри';}
  // The frame picker stands open in this pane: its own «Створити N кадрів» confirms, so the heading's start button
  // and the picker's «Скасувати» are not needed.
  document.querySelector('.plan-heading .plan-start-button')?.remove();
  actions?.replaceChildren();
  const picker=pane?.querySelector('.plan-start');
  if(picker){
    // One request at a time: while the agent draws, the confirm button turns into the progress of the run.
    picker.classList.toggle('busy',working);
    const confirm=picker.querySelector('.plan-start-actions .primary');
    if(confirm&&working){confirm.disabled=true;confirm.classList.add('loading');
      const last=humanFeed(teamFeeds['production'+state.project.id] || []).slice(-1)[0];
      confirm.innerHTML=`${typeof exportSpinner==='string'?exportSpinner:''}<span>Створюємо ${request.frames} ${planFrameWord(request.frames)}…</span>${last?`<small>${esc(last.text)}</small>`:''}`;}
    else if(confirm?.classList.contains('loading')){confirm.classList.remove('loading');confirm.disabled=false;confirm.textContent=`Створити ${request?.frames || ''} ${planFrameWord(request?.frames || 1)}`.replace('  ',' ');}
  }
  if(picker?.hidden&&picker.open){
    const scroll=picker.scrollIntoView;picker.scrollIntoView=()=>{};   // opening it here must not scroll the page
    picker.open();picker.scrollIntoView=scroll;
  }
  // The plan remembers an open picker, so on a return to the plan it is already open: the strip is built either way.
  if(picker&&!picker.hidden)framePicker(picker);
}

// In the video tab the frames are picked on a strip of the film itself: every frame is as wide as it is long, a drag
// across it takes the first frames up to the pointer, and «Макс» takes them all. The plan's slider stays the one source
// of the count, the strip only drives it.
function framePicker(picker){
  const slider=picker.querySelector('.plan-start-range'),frames=state.plan?.frames || [];
  if(!slider||!frames.length||picker.querySelector('.frame-strip'))return;
  const total=Number(frames[frames.length-1].end) || 1,row=document.createElement('div');row.className='frame-strip-row';
  const strip=document.createElement('div');strip.className='frame-strip';strip.setAttribute('role','slider');strip.tabIndex=0;
  strip.setAttribute('aria-label','Скільки перших кадрів створити');strip.setAttribute('aria-valuemin','1');strip.setAttribute('aria-valuemax',String(frames.length));
  const segments=frames.map((frame,index)=>{const cell=document.createElement('span');cell.className='frame-strip-cell';
    cell.style.flexGrow=String(Math.max(.2,Number(frame.end)-Number(frame.start)));cell.title=`Кадр ${index+1} · ${clock(frame.start)}–${clock(frame.end)}`;strip.append(cell);return cell;});
  const handle=document.createElement('span');handle.className='frame-strip-handle';strip.append(handle);
  const max=document.createElement('button');max.type='button';max.className='secondary frame-strip-max';max.textContent='Макс';max.title=`Усі ${frames.length} кадрів`;
  row.append(strip,max);slider.after(row);
  const paint=()=>{const count=Number(slider.value);segments.forEach((cell,index)=>cell.classList.toggle('chosen',index<count));
    handle.style.left=`${Number(frames[count-1].end)/total*100}%`;strip.setAttribute('aria-valuenow',String(count));max.classList.toggle('active',count===frames.length);};
  const set=count=>{slider.value=String(Math.max(1,Math.min(frames.length,count)));slider.dispatchEvent(new Event('input'));paint();};
  const at=event=>{const box=strip.getBoundingClientRect(),time=Math.max(0,Math.min(1,(event.clientX-box.left)/box.width))*total;
    const index=frames.findIndex(frame=>Number(frame.end)>=time);return index<0?frames.length:index+1;};
  strip.addEventListener('pointerdown',event=>{strip.setPointerCapture(event.pointerId);set(at(event));});
  strip.addEventListener('pointermove',event=>{if(strip.hasPointerCapture(event.pointerId))set(at(event));});
  strip.addEventListener('keydown',event=>{const step={ArrowRight:1,ArrowUp:1,ArrowLeft:-1,ArrowDown:-1}[event.key];if(step){event.preventDefault();set(Number(slider.value)+step);}});
  max.addEventListener('click',()=>set(frames.length));
  paint();
}

// The first step that is not done is where the episode stands: it is marked «Зараз», the done ones get a tick, the
// later ones stay dim, and a line above says it in words.
function markStage(steps){
  const items=[...steps.querySelectorAll('.episode-step')],current=items.findIndex(item=>item.dataset.state!=='done');
  items.forEach((item,index)=>{item.classList.toggle('current',index===current);item.classList.toggle('upcoming',current>=0&&index>current);
    item.querySelector('.episode-step-number').textContent=item.dataset.state==='done'?'✓':String(index+1);});
  const line=steps.previousElementSibling;
  if(line?.classList.contains('episode-stage'))line.innerHTML=current<0?'<strong>Усі етапи пройдено</strong>':`Етап <strong>${current+1} з ${items.length}</strong> · ${esc(items[current].querySelector('strong').textContent)}`;
  showStepPane(steps);
}

function showStepPane(steps){
  if(!steps?.isConnected)return;
  const items=[...steps.querySelectorAll('.episode-step')],current=items.findIndex(item=>item.classList.contains('current'));
  const chosen=stepChoice.get(steps.dataset.project) ?? (current<0?items.length-1:current);
  items.forEach((item,index)=>{item.classList.toggle('selected',index===chosen);item.setAttribute('aria-selected',String(index===chosen));});
  ['voice','director','video'].forEach((name,index)=>{const pane=paneOf(steps,name);if(pane)pane.hidden=index!==chosen;});
}

async function pollDirector(id){
  if(state.project?.id!==id)return;
  const before=directorRuns[id]?.status,run=await loadDirector(id);
  if(state.project?.id!==id)return;
  // The frames arrive with the finished run: reload the plan so the new frames show at once.
  if(before!==run.status && run.status==='done' && state.view==='plan'){await setProjectView('plan');return;}
  refreshSteps(document.querySelector('.episode-steps'));
}

// While the agent draws, the project is read again now and then: the request carries its state and spend.
// The team behind a run: who works on it and what each did last, then the latest actions in order. Opus directs; the
// others are the tools it drives, and helpers are agents it sends off in parallel.
const teamRoles={opus:['Режисер','Claude Opus 5.5, керує всім'],codex:['Художник','Codex, малює предмети'],razgon:['Рендер','Razgon, збирає кадри'],helper:['Помічник','паралельне завдання']};
// The author never sees file names or the agent's English notes: reading and preparing read as one plain line, files
// written read as what they are for (scenes, the director's shot table, a brief for the artist), and real steps keep
// their own words.
function humanStep(text){
  const own=/^Команда: (.*)/.exec(text);
  if(own)return /[а-яіїєґ]/i.test(own[1])?own[1]:'Вивчає матеріали й готує роботу';   // the agent's own note, when it is in Ukrainian
  if(/^Читає /.test(text))return 'Вивчає матеріали й готує роботу';
  if(/^Пише сцену /.test(text))return 'Пише сцени';
  if(/^Пише prompt/.test(text))return 'Описує предмети для художника';
  if(/^Пише (gen_shots|shots)/.test(text))return 'Пише режисуру шотів';
  if(/^Пише bible/.test(text))return 'Записує задум ролика';
  if(/^Пише /.test(text))return 'Готує допоміжні файли';
  return text;
}
// The Studio only receives what the director writes into it, so every step once credited to it is the director's.
function humanFeed(steps){const out=[];for(const raw of steps){const step=raw.who==='studio'?{...raw,who:'opus'}:raw;const text=humanStep(step.text);if(out[out.length-1]?.text===text&&out[out.length-1].who===step.who)continue;out.push({...step,text});}return out;}
const teamFeeds={};
function renderTeam(info,kind,id,live){
  if(!info)return;
  const box=document.createElement('div');box.className='team';box.dataset.kind=kind;info.append(box);
  const draw=()=>{
    const steps=humanFeed(teamFeeds[kind+id] || []),last=steps[steps.length-1];
    const who=['opus','codex','razgon',...(steps.some(step=>step.who==='helper')?['helper']:[])];
    box.innerHTML=`<div class="team-members">${who.map(role=>{const mine=steps.filter(step=>step.who===role),active=live&&last?.who===role;
      return `<div class="team-member${active?' active':''}${mine.length?'':' idle'}"><strong>${teamRoles[role][0]}</strong><span>${teamRoles[role][1]}</span><small>${active?'Зараз: ':''}${mine.length?esc(mine[mine.length-1].text):'Зараз не працює'}</small></div>`;}).join('')}</div>`
      +(steps.length?`<ol class="team-feed">${steps.slice(-6).reverse().map(step=>`<li><time>${directorTime(step.t)}</time><b>${teamRoles[step.who]?.[0] || ''}</b>${esc(step.text)}</li>`).join('')}</ol>`:`<p class="plan-note">${live?'Режисер тільки починає, перші дії з’являться за кілька секунд.':''}</p>`);
  };
  draw();
  api(`/api/projects/${encodeURIComponent(id)}/activity/${kind}`).then(({activity})=>{teamFeeds[kind+id]=activity;if(box.isConnected)draw();}).catch(()=>{});
}

async function pollProduction(id){
  if(state.project?.id!==id)return;
  try{const {project}=await api(`/api/projects/${encodeURIComponent(id)}`);if(state.project?.id!==id)return;
    const before=state.project.production_request?.status;state.project=project;
    if(before!==project.production_request?.status&&state.view==='plan'){renderPlan();return;}}catch{}
  refreshSteps(document.querySelector('.episode-steps'));
}

async function startDirector(id){
  if(!confirm('Запустити режисуру Claude Opus 5.5? Агент розіб’є озвучку на шоти й перезапише план кадрів цього випуску.'))return;
  try{
    directorRuns[id]=(await api(`/api/projects/${encodeURIComponent(id)}/director`,'POST',{})).director;
    stepChoice.set(id,1);refreshSteps(document.querySelector('.episode-steps'));
  }catch(error){status(error.message,true);}
}
