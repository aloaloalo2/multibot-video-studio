// director.js — the steps of an animated episode on its plan, as tabs: 1 the voice and its direction, 2 making the video. Once the voice is recognised the Studio hands the episode to Claude Opus 5.5 (high effort), which
// directs it and writes the frame plan back (backend/director.py); the author does nothing in between, so both read as
// one step whose result is the frame plan. Each tab opens its own pane with its buttons and data: the frame plan with
// the recognition report, script and director's report; how many frames to make with the run and its spend. The film is
// exported by the header's «Експорт MP4», which shows once the frames are pictures. The current stage opens first.
const directorRuns={};
const stepChoice=new Map();
let directorTimer=null,productionTimer=null;

const stepIcons={voice:'<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6"/></svg>',
  video:'<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 5v14M17 5v14M3 9.5h4M3 14.5h4M17 9.5h4M17 14.5h4"/></svg>'};
const stepNames=['voice','video'];
const stepTitles={voice:'Озвучка й режисура',video:'Створення відео'};

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

// The step shows money and time only; the token counts stay in the tooltip for whoever watches the limits.
function spentLine(run){return `Витрачено $${Number(run.cost_usd).toFixed(2)}${run.minutes?` · ${run.minutes} хв`:''}`;}
function spentTokens(run){return run.tokens_in?` ${tokenCount(run.tokens_in)} на вхід, ${tokenCount(run.tokens_out)} на вихід.`:'';}
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
  const id=state.project.id,steps=document.createElement('div');steps.className='episode-steps';steps.dataset.project=id;steps.setAttribute('role','tablist');steps.setAttribute('aria-orientation','vertical');
  const items=stepNames.map((name,index)=>episodeStep(index+1,name,stepTitles[name]));
  items[0].setAttribute('aria-live','polite');
  items.forEach((step,index)=>{
    const pick=()=>{stepChoice.set(id,index);showStepPane(steps);};
    step.addEventListener('click',pick);
    step.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();pick();}});
  });
  // The making of the film reads top to bottom on the left; the chosen step's data fills the right.
  const stage=document.createElement('p');stage.className='episode-stage';
  const flow=document.createElement('div');flow.className='episode-flow';
  const rail=document.createElement('div');rail.className='episode-rail';
  const panes=document.createElement('div');panes.className='episode-panes';
  steps.append(...items);rail.append(stage,steps);flow.append(rail,panes);panel.append(flow);
  // The rest of the plan is drawn right after this call: once it is there, its blocks move under the step they belong to.
  queueMicrotask(()=>arrangeStepPanes(panel,steps));
  if(!directorRuns[id])loadDirector(id).then(()=>{if(state.project?.id===id&&steps.isConnected)refreshSteps(steps);});
  refreshSteps(steps);
}

function arrangeStepPanes(panel,steps){
  if(!steps.isConnected)return;
  const panes=stepNames.map((name,index)=>{
    const pane=document.createElement('div');pane.className='episode-pane';pane.dataset.pane=name;pane.setAttribute('role','tabpanel');
    // each pane opens with its step's title and its buttons on one row, so a button always says what it belongs to
    const head=document.createElement('div');head.className='episode-pane-head';head.innerHTML=`<h2><span>${index+1}</span>${stepTitles[name]}</h2>`;
    const actions=document.createElement('div');actions.className='episode-pane-actions';head.append(actions);
    const info=document.createElement('div');info.className='episode-pane-info';
    pane.append(head,info);return pane;});
  const take=(pane,selector)=>{for(const node of panel.querySelectorAll(`:scope > ${selector}`))pane.append(node);};
  const [voice,video]=panes;
  // Voice and direction: the frame plan on the film strip, the run's state, the frame table, then the recognition
  // report and the script. Its own buttons go to the pane's button row; the report button is not needed
  // next to the report itself.
  panel.querySelector(':scope > .plan-heading .plan-stage-tag')?.remove();   // the tabs show the stage now
  // The frame plan on the film strip replaces the summary row and the voice timeline: the strip carries the same facts.
  for(const node of panel.querySelectorAll(':scope > .plan-summary, :scope > .plan-timeline'))node.remove();
  const plan=framePlan();if(plan)voice.querySelector('.episode-pane-info').before(plan);
  const report=state.analysis?.job?.project_id===state.project?.id?state.analysis.report:null;
  for(const selector of ['.plan-settings-warning','.plan-table-fold','.plan-table'])take(voice,selector);
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
  // An animated film is all one format and its plan is not agreed in a chat: those service lines only add doubt here.
  for(const node of panel.querySelectorAll(':scope > .plan-formats, :scope > .plan-note'))node.remove();
  // Video: how many frames to make. The plan's cost estimate counts stock, generated photos and DeepSeek requests,
  // none of which an animated film uses, so it is left out here.
  // the frame picker comes first in its tab, above the team and the feed
  const picker=panel.querySelector(':scope > .plan-start');if(picker)video.querySelector('.episode-pane-info').before(picker);
  panel.querySelector(':scope > .plan-cost-estimate')?.remove();
  steps.closest('.episode-flow').querySelector('.episode-panes').append(...panes);
  refreshSteps(steps);
}

function paneOf(steps,name){return steps?.closest('.episode-flow')?.querySelector(`.episode-pane[data-pane="${name}"]`) || null;}

// Fills every tab's status line and every pane's buttons from the current state; runs again whenever the director run changes.
function refreshSteps(steps){
  if(!steps?.isConnected)return;
  const id=steps.dataset.project,[voice,video]=steps.querySelectorAll('.episode-step');
  fillVoice(voice,paneOf(steps,'voice'),id);
  fillVideo(video,paneOf(steps,'video'));
  markStage(steps);
}

// Step 1 is the voice and its direction together: until the voice is recognised it says how the recognition goes,
// after that the director's run speaks for the step.
function fillVoice(step,pane,id){
  const analysis=state.analysis?.job?.project_id===state.project?.id?state.analysis:null,report=analysis?.report,job=analysis?.job,text=step.querySelector('p');
  const percent=report?`${Number(report.word_match_percent).toFixed(1)}%`:'';
  const actions=pane?.querySelector('.episode-pane-actions'),info=pane?.querySelector('.episode-pane-info');
  actions?.replaceChildren();info?.replaceChildren();
  const cost=step.querySelector('.episode-step-cost');cost.title='';
  if(state.project?.production?.plan_ready){
    // Once the voice is in, the button replaces it: a new recognition follows, and the director redoes the plan if the text changed.
    const replace=stepButton('Замінити озвучку',openNarrationBinding);
    replace.title='Нова озвучка або новий текст: студія розпізнає озвучку заново, а режисер сам переробить план кадрів, якщо змінився текст';
    actions?.append(replace);fillDirector(step,info,actions,id,percent);actions?.append(restartButton(id));return;
  }
  clearTimeout(directorTimer);
  const working=!!job&&['queued','running'].includes(job.status);step.classList.toggle('running',working);
  if(working){step.dataset.state='active';text.textContent=`${(typeof speechStageNames!=='undefined'&&speechStageNames[job.stage]) || 'Обробка'}: ${job.progress}%`;}
  else if(report){step.dataset.state='failed';text.textContent=`Потрібна перевірка, ${percent}`;}
  else if(job?.status==='failed'){step.dataset.state='failed';text.textContent='Не вдалося розпізнати';}
  else{step.dataset.state='waiting';text.textContent='Додайте аудіо озвучки';}
  cost.textContent=step.dataset.state==='waiting'?'Ще нічого не витрачено':'Розпізнавання на цьому Mac · $0';
  actions?.append(stepButton('Додати озвучку / таймінги',openNarrationBinding,step.dataset.state==='waiting'));
  if(report||job)actions?.append(restartButton(id));
  if(info)info.textContent=job?.status==='failed'?job.error:!report&&!working?'Додайте аудіо озвучки: студія розпізнає його на цьому Mac, а режисер сам розкладе озвучку на кадри.':'';
}

// «Почати заново»: the episode goes back to an empty one that waits for its script and voice. The agents stop, and what
// the Studio held moves into a backup next to the project (backend/episode_restart.py); drawn files stay in the episode.
function restartButton(id){
  const button=document.createElement('button');button.type='button';button.className='history-button episode-restart';
  setTrashButton(button,'Почати випуск заново',true);button.title='Почати випуск заново';
  button.addEventListener('click',()=>confirmRestart(id));return button;
}

function confirmRestart(id){
  modal('Почати випуск заново?','<p>Студія зупинить режисера й агента, прибере план кадрів, озвучку й кадри з таймлайну. Випуск відкриється порожнім, і ви додасте сценарій та озвучку наново.</p><p>Нічого не зникне назавжди: попередній стан збережеться в резервній копії проєкту, а намальовані файли лишаться в папці випуску.</p>',
    [{label:'Скасувати',run:closeModal},{label:'Почати заново',icon:'trash',danger:true,run:async()=>{
      const button=$('modal-actions').querySelector('.danger');button.disabled=true;
      try{
        await api(`/api/projects/${encodeURIComponent(id)}/restart`,'POST',{});
        clearTimeout(directorTimer);clearTimeout(productionTimer);
        delete directorRuns[id];stepChoice.delete(id);delete voiceScriptDraft[id];
        for(const kind of ['director','production'])delete teamFeeds[kind+id];
        state.analysis=null;closeModal();await selectProject(id,{view:'plan'});status('Випуск почато заново. Додайте сценарій та озвучку.');
      }catch(error){button.disabled=false;status(error.message,true);}
    }}]);
}

function fillDirector(step,info,actions,id,percent){
  const run=directorRuns[id] || {status:'loading'},directed=directorDone(),text=step.querySelector('p');
  const restart=(label,primary=false)=>actions?.append(stepButton(label,()=>startDirector(id),primary));
  // What the step actually used: recognition is free on this Mac; Claude Code runs on the subscription, and the dollar
  // figure is what the direction would cost through the API.
  const cost=step.querySelector('.episode-step-cost');
  if(run.cost_usd){cost.textContent=spentLine(run);cost.title=`Розпізнавання йде на цьому Mac безкоштовно. Режисура йде за підпискою Claude, тож окремо не оплачується; сума показує, скільки це коштувало б через API.${spentTokens(run)}`;}
  else cost.textContent=run.status==='running'||run.status==='queued'?'Рахуємо, поки йде режисура':'Розпізнавання на цьому Mac · $0';
  const say=message=>{if(info){const line=document.createElement('p');line.className='plan-note';line.textContent=message;info.append(line);}};
  clearTimeout(directorTimer);
  step.classList.toggle('running',run.status==='queued' || run.status==='running');
  if(run.status==='loading'){step.dataset.state=directed?'done':'active';text.textContent='Перевіряємо...';}
  else if(run.status==='queued' || run.status==='running'){
    step.dataset.state='active';text.textContent='Режисер розкладає озвучку на кадри';
    renderTeam(info,'director',id,true);
    directorTimer=setTimeout(()=>pollDirector(id),8000);
  }else if(run.status==='failed'){
    // the subscription limit only pauses the director: once it resets, the same button goes on
    step.dataset.state=run.limit?'active':'failed';text.textContent=run.limit?'Пауза: закінчився ліміт':'Режисура не вдалася';
    say(run.limit?`${run.error} Коли ліміт оновиться, натисніть «Продовжити режисуру».`:(run.error || 'Невідома помилка'));restart(run.limit?'Продовжити режисуру':'Спробувати ще раз',true);
  }else if(run.status==='done' || directed){
    step.dataset.state='done';
    const frames=run.frames || (directed?state.plan.frames.length:0);
    text.textContent=frames?`${frames} ${planFrameWord(frames)}${percent?`, збіг слів ${percent}`:''}`:'Готово';
    if(run.status==='done'&&run.summary&&info){const details=document.createElement('details');details.className='plan-script';const summary=document.createElement('summary');summary.textContent=`Звіт режисера · ${directorTime(run.finished_at)}`;const body=document.createElement('div');body.className='plan-script-text';body.textContent=run.summary;details.append(summary,body);info.append(details);}
    // nothing to redo by hand: a new voice or a new text sends the episode back to the director by itself
  }else{
    step.dataset.state='active';text.textContent='Озвучку розпізнано';
    say('Режисер ще не розклав озвучку на кадри. Запустіть режисуру, і план кадрів з’явиться тут.');
    restart('Запустити режисуру',true);
  }
}

const allMade='Усі кадри вже на таймлайні. Готовий ролик збирає кнопка «Експорт MP4» угорі: кадри, плашку й логотип каналу, музику й озвучку.';
// Step 2 follows the production request: the author picks the first frames, the agent draws their scenes.
function fillVideo(step,pane){
  const text=step.querySelector('p'),request=state.project?.production_request;
  const actions=pane?.querySelector('.episode-pane-actions'),info=pane?.querySelector('.episode-pane-info');
  if(info)info.textContent='';
  const cost=step.querySelector('.episode-step-cost'),working=['requested','in_progress'].includes(request?.status);
  step.classList.toggle('running',working&&directorDone());
  cost.title=request?.cost_usd?`Кадри малюються за підпискою Claude; сума показує, скільки це коштувало б через API.${spentTokens(request)}`:'';
  cost.textContent=request?.cost_usd?spentLine(request)
    :working?'Рахуємо, поки агент малює':'Ще нічого не витрачено';
  if(!directorDone()){step.dataset.state='waiting';text.textContent='Після режисури';if(info)info.textContent='Після режисури тут можна вибрати, скільки перших кадрів зробити, і агент намалює їхні сцени.';return;}
  clearTimeout(productionTimer);
  // A run the subscription limit stopped is a pause: what it made stays, and «Продовжити кадри» picks its session up.
  const paused=request?.status==='failed'&&(request.limit||/hit your \w+ limit/i.test(request.error || ''));
  let resume=null;
  if(working){
    step.dataset.state='active';text.textContent=`Малює кадри 1–${request.frames}`;
    renderTeam(info,'production',state.project.id,true);
    productionTimer=setTimeout(()=>pollProduction(state.project.id),8000);
  }else if(paused){
    step.dataset.state='active';text.textContent='Пауза: закінчився ліміт';
    if(info)info.textContent=`${request.limit?request.error:'Закінчився ліміт підписки Claude.'} Усе зроблене збережено. Коли ліміт оновиться, натисніть «Продовжити кадри», і агент продовжить з того місця, де зупинився.`;
    resume=stepButton(`Продовжити кадри ${Math.min(madeFrames()+1,request.frames)}–${request.frames}`,()=>resumeFrames(state.project.id,resume),true);
    resume.classList.add('glow-action');
  }else if(request?.status==='failed'){
    step.dataset.state='failed';text.textContent=`Кадри 1–${request.frames} не вдалися`;if(info)info.textContent=`${request.error || 'Невідома помилка'} Виберіть кадри й натисніть ще раз.`;
  }else if(request?.status==='done'){
    const all=request.frames>=request.total_frames;step.dataset.state=all?'done':'active';
    text.textContent=all?'Усі кадри готові':`Кадри 1–${request.frames} готові`;
    if(info){info.textContent=all?allMade:'Готові кадри вже на таймлайні в «Монтажі». Перегляньте їх і, якщо подобаються, виберіть наступні.';
      if(request.summary){const details=document.createElement('details');details.className='plan-script';const summary=document.createElement('summary');summary.textContent='Звіт агента';const body=document.createElement('div');body.className='plan-script-text';body.textContent=request.summary;details.append(summary,body);info.append(details);}
      renderTeam(info,'production',state.project.id,false);}
  }else if(madeFrames()>=(state.plan?.frames?.length || Infinity)){
    // frames made outside a Studio request (an older episode, or by hand) count as well
    step.dataset.state='done';text.textContent='Усі кадри готові';if(info)info.textContent=allMade;
  }else{step.dataset.state='active';text.textContent='Виберіть кадри';}
  // The frame picker stands open in this pane: its own «Створити N кадрів» confirms, so the heading's start button
  // and the picker's «Скасувати» are not needed.
  document.querySelector('.plan-heading .plan-start-button')?.remove();
  actions?.replaceChildren(...(resume?[resume]:[]));
  const picker=pane?.querySelector('.plan-start');
  if(picker){
    // One request at a time: while the agent draws, the confirm button turns into the progress of the run.
    // while paused, the one way on is «Продовжити кадри»: the strip only shows what is made
    picker.classList.toggle('busy',working||paused);picker.classList.toggle('paused',paused);
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

async function resumeFrames(id,button){
  button.disabled=true;
  try{
    const {project}=await api(`/api/projects/${encodeURIComponent(id)}/production-resume`,'POST',{});
    if(state.project?.id!==id)return;
    state.project=project;renderPlan();
  }catch(error){button.disabled=false;status(error.message,true);}
}

// In the video tab the frames are picked on a strip of the film itself: every frame is as wide as it is long, a drag
// across it takes the first frames up to the pointer, and «Макс» takes them all. The plan's slider stays the one source
// of the count, the strip only drives it.
function framePicker(picker){
  const slider=picker.querySelector('.plan-start-range'),frames=state.plan?.frames || [];
  if(!slider||!frames.length||picker.querySelector('.frame-strip'))return;
  const total=Number(frames[frames.length-1].end) || 1,row=document.createElement('div');row.className='frame-strip-row';
  const made=madeSet(frames),{strip,cells:segments}=filmStrip(frames,made);strip.setAttribute('role','slider');strip.tabIndex=0;
  strip.setAttribute('aria-label','Скільки перших кадрів створити');strip.setAttribute('aria-valuemin','1');strip.setAttribute('aria-valuemax',String(frames.length));
  segments.forEach((cell,index)=>{cell.title=`Кадр ${index+1} · ${clock(frames[index].start)}–${clock(frames[index].end)}${made.has(index)?' · готовий':''}`;});
  const handle=document.createElement('span');handle.className='frame-strip-handle';strip.append(handle);
  const max=document.createElement('button');max.type='button';max.className='secondary frame-strip-max';max.textContent='Макс';max.title=`Усі ${frames.length} кадрів`;
  row.append(strip,max);slider.after(row);
  const paint=()=>{const count=Number(slider.value);segments.forEach((cell,index)=>cell.classList.toggle('chosen',index<count&&!made.has(index)));
    handle.style.left=`${Number(frames[count-1].end)/total*100}%`;strip.setAttribute('aria-valuenow',String(count));max.classList.toggle('active',count===frames.length);};
  // Frames made from the start cannot be asked for again here: the strip starts at the first frame not made yet.
  let floor=0;while(made.has(floor))floor++;
  if(made.size){const legend=document.createElement('p');legend.className='frame-strip-legend';legend.innerHTML=`<span class="made"></span>Готові: ${made.size}${floor<frames.length?'<span class="chosen"></span>Вибрані для створення':''}`;row.after(legend);}
  const least=Math.min(frames.length,floor+1);
  const confirm=picker.querySelector('.plan-start-actions .primary');
  const label=()=>{
    if(!confirm||confirm.classList.contains('loading'))return;
    // every frame is a picture already: nothing is left to ask for
    if(floor>=frames.length){confirm.disabled=true;confirm.textContent='Усі кадри створені';return;}
    if(floor){const count=Number(slider.value);confirm.textContent=count===floor+1?`Створити кадр ${count}`:`Створити кадри ${floor+1}–${count}`;}};
  const set=count=>{slider.value=String(Math.max(least,Math.min(frames.length,count)));slider.dispatchEvent(new Event('input'));paint();label();};
  const at=event=>{const box=strip.getBoundingClientRect(),time=Math.max(0,Math.min(1,(event.clientX-box.left)/box.width))*total;
    const index=frames.findIndex(frame=>Number(frame.end)>=time);return index<0?frames.length:index+1;};
  strip.addEventListener('pointerdown',event=>{strip.setPointerCapture(event.pointerId);set(at(event));});
  strip.addEventListener('pointermove',event=>{if(strip.hasPointerCapture(event.pointerId))set(at(event));});
  strip.addEventListener('keydown',event=>{const step={ArrowRight:1,ArrowUp:1,ArrowLeft:-1,ArrowDown:-1}[event.key];if(step){event.preventDefault();set(Number(slider.value)+step);}});
  max.addEventListener('click',()=>set(frames.length));
  // while the agent draws, the picker only shows the state: it must not rewrite the button that shows the progress
  if(Number(slider.value)<least&&!picker.classList.contains('busy'))set(least);else{paint();label();}
  if(floor>=frames.length){strip.classList.add('complete');max.disabled=true;}
}

// Frames of the director's plan that are already pictures on the timeline, by their index.
function madeSet(frames){
  const pictures=(state.project?.tracks || []).flatMap(track=>track.clips || []).filter(clip=>['video','image'].includes(clip.kind)&&!/Логотип|Плашка/.test(clip.title || ''));
  return new Set(frames.map((frame,index)=>pictures.some(clip=>Math.abs(Number(clip.start)-Number(frame.start))<0.1)?index:-1).filter(index=>index>=0));
}
function madeFrames(){return madeSet(state.plan?.frames || []).size;}

// The film as a strip: every frame as wide as it sounds, frames already drawn in green. Step 1 shows on it the plan the
// director wrote, step 2 picks on the same strip the frames to make.
function filmStrip(frames,made){
  const strip=document.createElement('div');strip.className='frame-strip';
  const cells=frames.map((frame,index)=>{const cell=document.createElement('span');cell.className='frame-strip-cell';
    cell.style.flexGrow=String(Math.max(.2,Number(frame.end)-Number(frame.start)));cell.classList.toggle('made',made.has(index));strip.append(cell);return cell;});
  return {strip,cells};
}

// Step 1's result is the frame plan itself, on the strip of step 2: pointing at a frame reads its time and words below.
function framePlan(){
  const frames=state.plan?.frames || [];
  if(!frames.length||state.plan?.frame_source!=='razgon-direction')return null;
  const made=madeSet(frames),{strip,cells}=filmStrip(frames,made);strip.classList.add('static');
  const card=document.createElement('section');card.className='frame-plan';
  card.innerHTML=`<div class="plan-start-head"><h2>План кадрів</h2><div class="plan-start-readout"><strong>${frames.length}</strong><span>${planFrameWord(frames.length)}</span><span>${clock(Number(frames[frames.length-1].end) || 0)} озвучки</span></div></div>`;
  const row=document.createElement('div');row.className='frame-strip-row';row.append(strip);card.append(row);
  if(made.size){const legend=document.createElement('p');legend.className='frame-strip-legend';legend.innerHTML=`<span class="made"></span>Готові: ${made.size} з ${frames.length}`;card.append(legend);}
  const read=document.createElement('p');read.className='frame-plan-read';card.append(read);
  const hint='Наведіть на кадр, щоб побачити його час і текст.';read.textContent=hint;
  let shown=-1;
  const show=index=>{if(index===shown)return;cells[shown]?.classList.remove('pointed');shown=index;
    if(index<0){read.textContent=hint;return;}
    const frame=frames[index];cells[index].classList.add('pointed');
    read.innerHTML=`<b>Кадр ${index+1}${made.has(index)?' · готовий':''}</b> · ${clock(frame.start)}–${clock(frame.end)} · ${esc((frame.sentences || []).join(' '))}`;};
  strip.addEventListener('pointermove',event=>show(cells.indexOf(event.target.closest?.('.frame-strip-cell'))));
  strip.addEventListener('pointerleave',()=>show(-1));
  return card;
}

// The first step that is not done is where the episode stands: it is marked «Зараз», done ones turn green, later ones
// stay dim, and a line above says it in words.
function markStage(steps){
  const items=[...steps.querySelectorAll('.episode-step')],current=items.findIndex(item=>item.dataset.state!=='done');
  items.forEach((item,index)=>{item.classList.toggle('current',index===current);item.classList.toggle('upcoming',current>=0&&index>current);
    // a done step shows a green tick in place of its icon and number, so what is finished reads at a glance
    const done=item.dataset.state==='done',badge=item.querySelector('.episode-step-number');
    item.querySelector('.episode-step-icon').innerHTML=done?'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>':stepIcons[stepNames[index]];
    badge.textContent=String(index+1);badge.hidden=done;
    item.setAttribute('aria-label',`Етап ${index+1}${done?', готовий':''}`);});
  const line=steps.previousElementSibling;
  if(line?.classList.contains('episode-stage'))line.innerHTML=current<0?'<strong>Усі етапи пройдено</strong>':`Етап <strong>${current+1} з ${items.length}</strong> · ${esc(items[current].querySelector('strong').textContent)}`;
  showStepPane(steps);
}

function showStepPane(steps){
  if(!steps?.isConnected)return;
  const items=[...steps.querySelectorAll('.episode-step')],current=items.findIndex(item=>item.classList.contains('current'));
  const chosen=stepChoice.get(steps.dataset.project) ?? (current<0?items.length-1:current);
  items.forEach((item,index)=>{item.classList.toggle('selected',index===chosen);item.setAttribute('aria-selected',String(index===chosen));});
  stepNames.forEach((name,index)=>{const pane=paneOf(steps,name);if(pane)pane.hidden=index!==chosen;});
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
// The latest actions of a run, newest first, each with who did it: Opus directs, Codex draws props, Razgon renders,
// helpers are agents Opus sends off in parallel.
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
    const steps=humanFeed(teamFeeds[kind+id] || []);
    // only the latest actions, newest first: who did what is enough to see the work move
    if(!steps.length&&!live){box.remove();return;}
    box.innerHTML=(steps.length?`<ol class="team-feed">${steps.slice(-6).reverse().map(step=>`<li><time>${directorTime(step.t)}</time><b>${teamRoles[step.who]?.[0] || ''}</b>${esc(step.text)}</li>`).join('')}</ol>`:`<p class="plan-note">${live?'Режисер тільки починає, перші дії з’являться за кілька секунд.':''}</p>`);
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
  if(directorDone()&&!confirm('Переробити режисуру? Режисер заново розіб’є озвучку на шоти й перезапише план кадрів цього випуску.'))return;
  try{
    directorRuns[id]=(await api(`/api/projects/${encodeURIComponent(id)}/director`,'POST',{})).director;
    stepChoice.set(id,0);refreshSteps(document.querySelector('.episode-steps'));
  }catch(error){status(error.message,true);}
}
