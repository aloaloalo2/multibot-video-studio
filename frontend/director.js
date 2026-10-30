// director.js — the steps of an animated episode on its plan: the voice, then the director. Once the voice is recognised the Studio hands the
// episode to Claude Opus 5.5 (high effort), which directs it and writes the frame plan back (backend/director.py). The card
// shows where that run stands, refreshes itself while it runs, reloads the plan when the frames arrive, and starts a new
// pass on request.
const directorRuns={};
let directorTimer=null;

function directorAnimated(){return state.channel?.settings?.channel_kind==='animated';}

// An animated episode has no frames until the director writes them: the Studio's own split by sentences is only
// the timing behind them, so the plan shows the director instead of those frames.
function directorAwaited(){return directorAnimated() && state.plan?.frame_source!=='razgon-direction';}

// The episode's steps on its plan: 1 — the voice, 2 — the director, 3 — making the video. The wait view (no director frames yet) carries the
// voice buttons in step 1; a directed plan has them in its summary row already.
const stepIcons={voice:'<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6"/></svg>',
  video:'<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 5v14M17 5v14M3 9.5h4M3 14.5h4M17 9.5h4M17 14.5h4"/></svg>',
  director:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 10h16v9a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1zM4 10l-.6-3.3a1 1 0 0 1 .8-1.2L17 3.2a1 1 0 0 1 1.2.8L18.7 7M8 4.8l2.4 3.6M13.2 3.9l2.4 3.6"/></svg>'};

function renderDirectorWait(panel){
  const heading=document.createElement('div');heading.className='plan-heading';heading.innerHTML='<div class="plan-heading-label"><h1>План ролика</h1></div>';
  panel.append(heading);
  renderDirectorStatus(panel,true);
}

async function loadDirector(id){
  try{directorRuns[id]=(await api(`/api/projects/${encodeURIComponent(id)}/director`)).director || {status:'none'};}
  catch{directorRuns[id]={status:'none'};}
  return directorRuns[id];
}

function directorTime(seconds){return new Date(seconds*1000).toLocaleTimeString('uk-UA',{hour:'2-digit',minute:'2-digit'});}

function episodeStep(number,icon,title){
  const step=document.createElement('section');step.className='episode-step';
  step.innerHTML=`<div class="episode-step-head"><span class="episode-step-icon">${stepIcons[icon]}</span><span class="episode-step-number">${number}</span><strong>${title}</strong></div><p></p><div class="episode-step-actions"></div>`;
  return step;
}

function fillVoiceStep(step,withButtons){
  const analysis=state.analysis?.job?.project_id===state.project?.id?state.analysis:null,report=analysis?.report,job=analysis?.job;
  const text=step.querySelector('p'),actions=step.querySelector('.episode-step-actions');
  const percent=report?`${Number(report.word_match_percent).toFixed(1)}%`:'';
  if(state.project?.production?.plan_ready){step.dataset.state='done';text.textContent=percent?`Розпізнано: ${percent} слів збіглося зі сценарієм.`:'Розпізнано, таймінги застосовано.';}
  else if(job && ['queued','running'].includes(job.status)){step.dataset.state='active';text.textContent=`${(typeof speechStageNames!=='undefined'&&speechStageNames[job.stage]) || 'Обробка файлу'}: ${job.progress}%`;}
  else if(report){step.dataset.state='failed';text.textContent=`Потрібна перевірка: ${percent} слів збіглося.`;}
  else if(job?.status==='failed'){step.dataset.state='failed';text.textContent=job.error;}
  else{step.dataset.state='waiting';text.textContent='Перетягніть аудіо озвучки в студію або додайте його кнопкою.';}
  if(!withButtons)return;
  const bind=document.createElement('button');bind.type='button';bind.className='secondary';bind.textContent='Додати озвучку';bind.addEventListener('click',openNarrationBinding);actions.append(bind);
  if(report){const open=document.createElement('button');open.type='button';open.className='secondary';open.textContent='Звіт розпізнавання';
    open.addEventListener('click',()=>{modal('Розпізнавання мовлення','<div id="speech-report-modal"></div>',[{label:'Закрити',run:closeModal}]);appendSpeechReport($('speech-report-modal'),report);});actions.append(open);}
}

function renderDirectorStatus(panel,withVoiceButtons=false){
  if(!state.project || !directorAnimated())return;
  const id=state.project.id,steps=document.createElement('div');steps.className='episode-steps';
  const voice=episodeStep(1,'voice','Озвучка'),card=episodeStep(2,'director','Режисура');
  card.classList.add('director-card');card.setAttribute('role','status');card.setAttribute('aria-live','polite');
  fillVoiceStep(voice,withVoiceButtons);
  const video=episodeStep(3,'video','Створення відео');fillVideoStep(video);
  steps.append(voice,card,video);panel.append(steps);
  if(!directorRuns[id]){card.querySelector('p').textContent='Перевіряємо режисуру...';loadDirector(id).then(()=>{if(state.project?.id===id&&card.isConnected)fillDirector(card,id);});return;}
  fillDirector(card,id);
}

// Step 3 follows the production request: the author picks the first frames, the agent draws their scenes.
function fillVideoStep(step){
  const text=step.querySelector('p'),actions=step.querySelector('.episode-step-actions'),request=state.project?.production_request;
  const directed=state.plan?.frame_source==='razgon-direction'&&!state.plan?.director_stale;
  if(!directed){step.dataset.state='waiting';text.textContent='Після режисури: виберіть кадри, і агент намалює їхні сцени.';return;}
  if(request){step.dataset.state='active';text.textContent=`Запит агенту: кадри 1–${request.frames}, ${request.status==='requested'?'чекає агента':request.status}.`;return;}
  step.dataset.state='active';text.textContent='Виберіть, скільки перших кадрів зробити, і агент намалює їхні сцени.';
  const begin=document.querySelector('.plan-start-button');
  if(begin){const b=document.createElement('button');b.type='button';b.className='secondary';b.textContent='Почати створення відео';b.disabled=begin.disabled;b.addEventListener('click',()=>begin.click());actions.append(b);}
}

function fillDirector(card,id){
  const run=directorRuns[id],synced=!!state.project?.production?.plan_ready,directed=state.plan?.frame_source==='razgon-direction'&&!state.plan?.director_stale;
  const head=card.querySelector('.episode-step-head'),text=card.querySelector('p'),actions=card.querySelector('.episode-step-actions');
  card.querySelector('details')?.remove();actions.replaceChildren();
  if(!head.querySelector('.director-model')){const who=document.createElement('span');who.className='director-model';who.textContent='Claude Opus 5.5 · високий';head.append(who);}
  const button=label=>{const b=document.createElement('button');b.type='button';b.className='secondary';b.textContent=label;b.addEventListener('click',()=>startDirector(id));actions.append(b);return b;};
  clearTimeout(directorTimer);
  card.dataset.status=run.status;
  if(run.status==='queued' || run.status==='running'){
    card.dataset.state='active';
    text.textContent=`Ділить озвучку на шоти й пише план кадрів${run.started_at?`, почав о ${directorTime(run.started_at)}`:''}. Сцени не малює. Сторінку можна закрити.`;
    directorTimer=setTimeout(()=>pollDirector(id),10000);
  }else if(run.status==='failed'){
    card.dataset.state='failed';text.textContent=run.error || 'Невідома помилка';button('Спробувати ще раз');
  }else if(run.status==='done' || directed){
    card.dataset.state='done';
    text.textContent=run.status==='done'?`${run.frames?`${run.frames} кадрів у плані. `:''}Готово о ${directorTime(run.finished_at)}${run.cost_usd?` · за підпискою, еквівалент $${Number(run.cost_usd).toFixed(2)}`:''}.`:'Кадри цього плану розбив режисер.';
    if(run.summary){const details=document.createElement('details');const summary=document.createElement('summary');summary.textContent='Звіт режисера';const body=document.createElement('p');body.textContent=run.summary;details.append(summary,body);actions.before(details);}
    button('Переробити режисуру');
  }else{
    card.dataset.state=synced?'active':'waiting';
    text.textContent=synced?'Озвучку розпізнано. Режисер розіб’є її на шоти й запише план кадрів.':'Почнеться сама, щойно озвучку буде розпізнано.';
    const b=button('Запустити режисуру');b.disabled=!synced;
  }
}

async function pollDirector(id){
  if(state.project?.id!==id)return;
  const before=directorRuns[id]?.status,run=await loadDirector(id);
  if(state.project?.id!==id)return;
  // The frames arrive with the finished run: reload the plan so the new frames show at once.
  if(before!==run.status && run.status==='done' && state.view==='plan'){await setProjectView('plan');return;}
  const card=document.querySelector('.director-card');
  if(card)fillDirector(card,id);
}

async function startDirector(id){
  if(!confirm('Запустити режисуру Claude Opus 5.5? Агент розіб’є озвучку на шоти й перезапише план кадрів цього випуску.'))return;
  try{
    directorRuns[id]=(await api(`/api/projects/${encodeURIComponent(id)}/director`,'POST',{})).director;
    const card=document.querySelector('.director-card');if(card)fillDirector(card,id);
  }catch(error){status(error.message,true);}
}
