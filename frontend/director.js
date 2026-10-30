// director.js — the steps of an animated episode on its plan, as tabs: 1 the voice, 2 the director, 3 making the video.
// Once the voice is recognised the Studio hands the episode to Claude Opus 5.5 (high effort), which directs it and writes
// the frame plan back (backend/director.py). The tabs say where the episode stands; each opens its own pane with its
// buttons and data: the voice summary, recognition report and script; the director's report with the timeline and frame
// table; how many frames to make with the request and cost. The current stage opens first.
const directorRuns={};
const stepChoice=new Map();
let directorTimer=null;

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

function directorTime(seconds){return new Date(seconds*1000).toLocaleTimeString('uk-UA',{hour:'2-digit',minute:'2-digit'});}

function stepButton(label,run,primary=false){const b=document.createElement('button');b.type='button';b.className=primary?'primary':'secondary';b.textContent=label;b.addEventListener('click',run);return b;}

function episodeStep(number,icon,title){
  const step=document.createElement('section');step.className='episode-step';step.tabIndex=0;step.setAttribute('role','tab');
  step.innerHTML=`<div class="episode-step-head"><span class="episode-step-icon">${stepIcons[icon]}</span><span class="episode-step-number">${number}</span><strong>${title}</strong></div><p></p><small class="episode-step-cost"></small>`;
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
  take(video,'.plan-start');
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
  step.querySelector('.episode-step-cost').textContent='Безкоштовно · Whisper на цьому Mac';
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
  // Claude Code runs on the subscription; the dollar figure is what the same run would cost through the API.
  step.querySelector('.episode-step-cost').textContent=run.cost_usd?`Підписка Claude · еквівалент $${Number(run.cost_usd).toFixed(2)}`:'Підписка Claude, окремо не оплачується';
  const say=message=>{if(info){const line=document.createElement('p');line.className='plan-note';line.textContent=message;info.append(line);}};
  clearTimeout(directorTimer);
  if(run.status==='loading'){step.dataset.state=directed?'done':'waiting';text.textContent='Перевіряємо...';}
  else if(run.status==='queued' || run.status==='running'){
    step.dataset.state='active';text.textContent=`Іде${run.started_at?` з ${directorTime(run.started_at)}`:''}`;
    say('Режисер ділить озвучку на шоти й пише план кадрів. Сцени він не малює. Сторінку можна закрити: план оновиться сам.');
    directorTimer=setTimeout(()=>pollDirector(id),10000);
  }else if(run.status==='failed'){
    step.dataset.state='failed';text.textContent='Не вдалася';say(run.error || 'Невідома помилка');restart('Спробувати ще раз');
  }else if(run.status==='done' || directed){
    step.dataset.state='done';
    const frames=run.frames || (directed?state.plan.frames.length:0);
    text.textContent=frames?`${frames} кадрів`:'Готово';
    if(run.status==='done'){
      say(`Готово о ${directorTime(run.finished_at)}${run.cost_usd?` · за підпискою, еквівалент $${Number(run.cost_usd).toFixed(2)}`:''}.`);
      if(run.summary&&info){const details=document.createElement('details');details.className='plan-script';const summary=document.createElement('summary');summary.textContent='Звіт режисера';const body=document.createElement('div');body.className='plan-script-text';body.textContent=run.summary;details.append(summary,body);info.append(details);}
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
  step.querySelector('.episode-step-cost').textContent='Підписки Claude і Codex, окремо не оплачується';
  if(!directorDone()){step.dataset.state='waiting';text.textContent='Після режисури';if(info)info.textContent='Після режисури тут можна вибрати, скільки перших кадрів зробити, і агент намалює їхні сцени.';return;}
  if(request){step.dataset.state=['done','complete'].includes(request.status)?'done':'active';text.textContent=`Кадри 1–${request.frames}, ${request.status==='requested'?'чекає агента':request.status}`;}
  else{step.dataset.state='active';text.textContent='Виберіть кадри';}
  // The frame picker stands open in this pane: its own «Створити N кадрів» confirms, so the heading's start button
  // and the picker's «Скасувати» are not needed.
  document.querySelector('.plan-heading .plan-start-button')?.remove();
  actions?.replaceChildren();
  const picker=pane?.querySelector('.plan-start');
  if(picker?.hidden&&picker.open){
    const scroll=picker.scrollIntoView;picker.scrollIntoView=()=>{};   // opening it here must not scroll the page
    picker.open();picker.scrollIntoView=scroll;
    framePicker(picker);
  }
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

async function startDirector(id){
  if(!confirm('Запустити режисуру Claude Opus 5.5? Агент розіб’є озвучку на шоти й перезапише план кадрів цього випуску.'))return;
  try{
    directorRuns[id]=(await api(`/api/projects/${encodeURIComponent(id)}/director`,'POST',{})).director;
    stepChoice.set(id,1);refreshSteps(document.querySelector('.episode-steps'));
  }catch(error){status(error.message,true);}
}
