// director.js — the plan page of an episode, the same for photo and animated channels, in one column: a short voice
// line on top (file, length, recognition and «почати заново»), the director's state while Claude Opus 5.5 splits an
// animated film into frames (backend/director.py), then «Створення ролика»: the film as a strip of its frames, the
// count picked by a drag across it (all frames by default), «Макс» and «Почати створення ролика», which hands the
// frames to the frame agent (backend/production.py) and goes back to the channel's projects, where the card shows the
// progress. The voice text with its recognition, the frame table and the reports of the director and the agent stay
// folded at the bottom. The film is exported by the header's «Експорт MP4».
const directorRuns={};
let directorTimer=null,productionTimer=null;

function directorAnimated(){return state.channel?.settings?.channel_kind==='animated';}

// An animated episode has no frames until the director writes them: the Studio's own split by sentences is only
// the timing behind them.
function directorAwaited(){return directorAnimated() && state.plan?.frame_source!=='razgon-direction';}
function directorDone(){return state.plan?.frame_source==='razgon-direction' && !state.plan?.director_stale;}

async function loadDirector(id){
  try{directorRuns[id]=(await api(`/api/projects/${encodeURIComponent(id)}/director`)).director || {status:'none'};}
  catch{directorRuns[id]={status:'none'};}
  return directorRuns[id];
}

// Money and time only; the token counts stay in the tooltip for whoever watches the limits.
function spentLine(run){return `Витрачено $${Number(run.cost_usd).toFixed(2)}${run.minutes?` · ${run.minutes} хв`:''}`;}
function spentTokens(run){return run.tokens_in?` ${tokenCount(run.tokens_in)} на вхід, ${tokenCount(run.tokens_out)} на вихід.`:'';}
function tokenCount(value){return value>=1e6?`${(value/1e6).toFixed(1).replace('.',',')} млн токенів`:`${Math.round(value/1000)} тис. токенів`;}
function directorTime(seconds){return new Date(seconds*1000).toLocaleTimeString('uk-UA',{hour:'2-digit',minute:'2-digit'});}

function stepButton(label,run,primary=false){const b=document.createElement('button');b.type='button';b.className=primary?'primary':'secondary';b.textContent=label;b.addEventListener('click',run);return b;}

function episodeFold(title){
  const fold=document.createElement('details');fold.className='plan-script episode-fold';
  const summary=document.createElement('summary');summary.textContent=title;fold.append(summary);return fold;
}

const makeCount={};
function renderEpisode(panel){
  if(!state.project)return;
  const id=state.project.id;
  const heading=document.createElement('div');heading.className='plan-heading';heading.innerHTML='<div class="plan-heading-label"><h1>План ролика</h1></div>';
  // a photo channel's plan from the Studio's planner can still be built again from the channel settings
  if(!directorAnimated()&&state.plan?.frame_source!=='razgon-direction'){
    const actions=document.createElement('div');actions.className='plan-actions';
    actions.append(stepButton('Перегенерувати план',openPlanBuilder));heading.append(actions);
  }
  panel.append(heading);
  if(state.planSettingsMatch===false&&!directorAnimated()){const warning=document.createElement('p');warning.className='plan-settings-warning';warning.setAttribute('role','status');warning.textContent='Налаштування каналу змінилися після створення цього плану. Перегенеруйте план, щоб застосувати їх.';panel.append(warning);}
  const episode=document.createElement('div');episode.className='episode';episode.dataset.project=id;
  panel.append(episode);
  arrangeEpisode(episode);
  if(directorAnimated()&&!directorRuns[id])loadDirector(id).then(()=>{if(state.project?.id===id)refreshEpisode(episode);});
  refreshEpisode(episode);
}

// The blocks of the page in their order; refreshEpisode fills what changes.
function arrangeEpisode(episode){
  const voice=document.createElement('div');voice.className='episode-voice';voice.setAttribute('aria-live','polite');
  const director=document.createElement('section');director.className='episode-director';director.hidden=true;
  const make=document.createElement('section');make.className='episode-make';buildMake(make);
  const folds=document.createElement('div');folds.className='episode-folds';
  episode.append(voice,director,make,folds);
  // Voice text and recognition: the text the frames follow and the recognition report under it.
  const words=episodeFold('Текст озвучки й розпізнавання');
  const frames=state.plan?.frames || [];
  const script=typeof state.plan?.script==='string'?state.plan.script:frames.map(frame=>(frame.sentences || []).join(' ')).join('\n\n');
  if(script.trim()){const text=document.createElement('div');text.className='plan-script-text';text.textContent=script;words.append(text);}
  const reportSlot=document.createElement('div');reportSlot.className='episode-report';words.append(reportSlot);
  const report=episodeAnalysis()?.report;
  if(report)appendSpeechReport(reportSlot,report);
  else if(state.project){
    // a plan opened by its link has not loaded the recognition yet: fetch it and fill the fold and the voice line
    const id=state.project.id;
    api(`/api/projects/${encodeURIComponent(id)}/analysis`).then(result=>{
      if(state.project?.id!==id||!reportSlot.isConnected)return;
      state.analysis=result;if(result.report&&!reportSlot.children.length)appendSpeechReport(reportSlot,result.report);refreshEpisode(episode);
    }).catch(()=>{});
  }
  const table=episodeFold(`Таблиця кадрів (${frames.length})`);table.append(planTable(frames,!!state.project.production?.plan_ready));
  const reports=document.createElement('div');reports.className='episode-reports';
  folds.append(words,table,reports);
}

function episodeAnalysis(){return state.analysis?.job?.project_id===state.project?.id?state.analysis:null;}

function refreshEpisode(episode=document.querySelector('.episode')){
  if(!episode?.isConnected||episode.dataset.project!==state.project?.id)return;
  fillVoiceLine(episode.querySelector('.episode-voice'));
  fillDirectorLine(episode.querySelector('.episode-director'));
  fillMake(episode.querySelector('.episode-make'));
  fillReports(episode.querySelector('.episode-reports'));
}

const voiceIcon='<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6"/></svg>';
// One line: the voice file, its length, how it was recognised, and the bin that starts the episode over.
function fillVoiceLine(box){
  const id=state.project.id,analysis=episodeAnalysis(),report=analysis?.report,job=analysis?.job,synced=!!state.project.production?.plan_ready;
  const audio=state.plan?.timing?.audio || {},frames=state.plan?.frames || [];
  const name=report?.source?.name || audio.name || (audio.path?String(audio.path).split('/').pop():'') || 'Озвучка';
  const length=Number(audio.duration) || Number(frames[frames.length-1]?.end) || 0;
  const working=!!job&&['queued','running'].includes(job.status);
  const percent=report?`${Number(report.word_match_percent).toFixed(1).replace('.',',')}%`:'';
  let state_,text;
  if(working){state_='working';text=`${speechStageNames[job.stage] || 'Обробка'}: ${job.progress}%`;}
  else if(synced||state.plan?.timing?.status==='audio_synced'){state_='done';text=percent?`розпізнано, збіг ${percent}`:'розпізнано';}
  else if(report){state_='warn';text=`текст не збігся з озвучкою (${percent}): перевірте звіт нижче`;}
  else if(job?.status==='failed'){state_='warn';text=job.error || 'не вдалося розпізнати';}
  else{state_='empty';text='озвучку ще не додано';}
  box.dataset.state=state_;
  box.innerHTML=`<span class="episode-voice-icon">${voiceIcon}</span><span class="episode-voice-text">${state_==='empty'?'':`<b>${esc(name)}</b>`}${state_!=='empty'&&length?`<span>${clock(length)}</span>`:''}<span class="episode-voice-state">${esc(text)}</span></span>`;
  if(!synced&&!working)box.append(stepButton('Додати озвучку',openNarrationBinding,state_==='empty'));
  // Once the voice is in, the only way to another voice is to start the episode over (user, 30 October 2026)
  if(synced||report||job)box.append(restartButton(id));
}

// «Почати заново»: the episode goes back to an empty one that waits for its script and voice. The agents stop, and what
// the Studio held moves into a backup next to the project (backend/episode_restart.py); drawn files stay in the episode.
function restartButton(id){
  const button=document.createElement('button');button.type='button';button.className='history-button episode-restart';
  setTrashButton(button,'Почати випуск заново',true);button.title='Почати заново';
  button.addEventListener('click',()=>confirmRestart(id));return button;
}

function confirmRestart(id){
  modal('Почати випуск заново?','<p>Студія зупинить режисера й агента, прибере план кадрів, озвучку й кадри з таймлайну. Випуск відкриється порожнім, і ви додасте сценарій та озвучку наново.</p><p>Нічого не зникне назавжди: попередній стан збережеться в резервній копії проєкту, а створені файли лишаться в папці випуску.</p>',
    [{label:'Скасувати',run:closeModal},{label:'Почати заново',icon:'trash',danger:true,run:async()=>{
      const button=$('modal-actions').querySelector('.danger');button.disabled=true;
      try{
        await api(`/api/projects/${encodeURIComponent(id)}/restart`,'POST',{});
        clearTimeout(directorTimer);clearTimeout(productionTimer);
        delete directorRuns[id];delete makeCount[id];delete voiceScriptDraft[id];
        for(const kind of ['director','production'])delete teamFeeds[kind+id];
        state.analysis=null;closeModal();await selectProject(id,{view:'plan'});status('Випуск почато заново. Додайте сценарій та озвучку.');
      }catch(error){button.disabled=false;status(error.message,true);}
    }}]);
}

// The director shows only while it works, or when it needs the author: a stop, a pause on the limit, a changed text.
function fillDirectorLine(box){
  clearTimeout(directorTimer);
  const id=state.project.id,run=directorRuns[id],synced=!!state.project.production?.plan_ready;
  box.replaceChildren();box.hidden=true;box.classList.remove('working');
  if(!directorAnimated()||!synced||!run)return;
  const line=(text,note)=>{const head=document.createElement('p');head.className='episode-director-line';head.innerHTML=`<strong>${esc(text)}</strong>${note?`<span>${esc(note)}</span>`:''}`;box.append(head);box.hidden=false;};
  if(run.status==='queued'||run.status==='running'){
    box.classList.add('working');
    line('Режисер розкладає озвучку на кадри','Claude Opus 5.5. Кадри з’являться тут, щойно режисер закінчить.');
    renderTeam(box,'director',id,true);
    directorTimer=setTimeout(()=>pollDirector(id),8000);
  }else if(run.status==='failed'){
    // the subscription limit only pauses the director: once it resets, the same button goes on
    line(run.limit?'Режисер на паузі: закінчився ліміт підписки':'Режисура не вдалася',run.limit?`${run.error || ''} Коли ліміт оновиться, натисніть «Продовжити режисуру».`:(run.error || ''));
    box.append(stepButton(run.limit?'Продовжити режисуру':'Спробувати ще раз',()=>startDirector(id),true));
  }else if(state.plan?.director_stale){
    line('Сценарій змінився після режисури','Режисер має заново розбити озвучку на кадри.');
    box.append(stepButton('Запустити режисуру',()=>startDirector(id),true));
  }else if(directorAwaited()&&run.status!=='done'){
    line('Режисер ще не розклав озвучку на кадри');
    box.append(stepButton('Запустити режисуру',()=>startDirector(id),true));
  }
}

// «Створення ролика»: the strip, the count, «Макс» and the start button, built once and refreshed by fillMake.
function buildMake(make){
  make.innerHTML='<div class="episode-make-head"><h2>Створення ролика</h2><div class="episode-make-readout" aria-live="polite"></div></div>';
  const frames=state.plan?.frames || [];
  const row=document.createElement('div');row.className='frame-strip-row';
  const {strip,cells}=filmStrip(frames);strip.setAttribute('role','slider');strip.tabIndex=0;
  strip.setAttribute('aria-label','Скільки кадрів створити');strip.setAttribute('aria-valuemin','1');strip.setAttribute('aria-valuemax',String(frames.length));
  const handle=document.createElement('span');handle.className='frame-strip-handle';strip.append(handle);
  const max=document.createElement('button');max.type='button';max.className='secondary frame-strip-max';max.textContent='Макс';max.title=`Усі ${frames.length} ${planFrameWord(frames.length)}`;
  row.append(strip,max);
  const legend=document.createElement('p');legend.className='frame-strip-legend';
  const read=document.createElement('p');read.className='frame-plan-read';
  const actions=document.createElement('div');actions.className='episode-make-actions';
  const hint=document.createElement('p');hint.className='episode-make-hint';
  const start=document.createElement('button');start.type='button';start.className='primary episode-make-start';start.textContent='Почати створення ролика';
  actions.append(hint,start);
  const feed=document.createElement('div');feed.className='episode-make-feed';
  make.append(row,legend,read,actions,feed);
  if(!frames.length)return;
  const total=Number(frames[frames.length-1].end) || 1,id=state.project.id;
  const at=event=>{const box=strip.getBoundingClientRect(),time=Math.max(0,Math.min(1,(event.clientX-box.left)/box.width))*total;
    const index=frames.findIndex(frame=>Number(frame.end)>=time);return index<0?frames.length:index+1;};
  const set=count=>{if(make.classList.contains('locked'))return;const floor=Number(make.dataset.floor) || 0;
    makeCount[id]=Math.max(Math.min(frames.length,floor+1),Math.min(frames.length,count));fillMake(make);};
  strip.addEventListener('pointerdown',event=>{if(make.classList.contains('locked'))return;strip.setPointerCapture(event.pointerId);set(at(event));});
  strip.addEventListener('pointermove',event=>{if(strip.hasPointerCapture(event.pointerId))set(at(event));else show(cells.indexOf(event.target.closest?.('.frame-strip-cell')));});
  strip.addEventListener('pointerleave',()=>show(-1));
  strip.addEventListener('keydown',event=>{const step={ArrowRight:1,ArrowUp:1,ArrowLeft:-1,ArrowDown:-1}[event.key];if(step){event.preventDefault();set((makeCount[id] || frames.length)+step);}});
  max.addEventListener('click',()=>set(frames.length));
  start.addEventListener('click',()=>startMaking(start));
  // pointing at a frame reads its time, format and words below the strip
  let shown=-1;
  const hintText='Потягніть по смужці, щоб вибрати, скільки кадрів створити. Наведіть на кадр, щоб побачити його текст.';
  function show(index){
    if(index===shown)return;cells[shown]?.classList.remove('pointed');shown=index;
    if(index<0){read.textContent=hintText;return;}
    const frame=frames[index];cells[index].classList.add('pointed');
    const format=directorAnimated()?'':` · ${planFormatNames[frame.format] || frame.format}`;
    read.innerHTML=`<b>Кадр ${index+1}${cells[index].classList.contains('made')?' · готовий':''}</b> · ${clock(frame.start)}–${clock(frame.end)}${esc(format)} · ${esc(planFrameSpeech(frame))}`;
  }
  read.textContent=hintText;
}

// The film as a strip: every frame as wide as it sounds. On a photo channel each frame takes its format's colour.
function filmStrip(frames){
  const strip=document.createElement('div');strip.className='frame-strip';
  const formats=!directorAnimated();strip.classList.toggle('formats',formats);
  const cells=frames.map((frame,index)=>{const cell=document.createElement('span');cell.className='frame-strip-cell';
    cell.style.flexGrow=String(Math.max(.2,Number(frame.end)-Number(frame.start)));cell.dataset.frame=String(frame.number || index+1);
    if(formats)cell.style.setProperty('--format-color',planFormatVisuals[frame.format]?.color || '#b8bec9');
    strip.append(cell);return cell;});
  return {strip,cells};
}

function fillMake(make){
  if(!make)return;
  clearTimeout(productionTimer);
  const id=state.project.id,frames=state.plan?.frames || [],request=state.project.production_request;
  const strip=make.querySelector('.frame-strip'),cells=[...make.querySelectorAll('.frame-strip-cell')],handle=make.querySelector('.frame-strip-handle');
  const max=make.querySelector('.frame-strip-max'),start=make.querySelector('.episode-make-start'),hint=make.querySelector('.episode-make-hint');
  const readout=make.querySelector('.episode-make-readout'),legend=make.querySelector('.frame-strip-legend'),feed=make.querySelector('.episode-make-feed');
  if(!frames.length||!start)return;
  const made=madeSet(frames);
  let floor=0;while(made.has(floor))floor++;
  make.dataset.floor=String(floor);
  const working=['requested','in_progress'].includes(request?.status);
  // a run the subscription limit stopped is a pause: what it made stays, and «Продовжити кадри» picks its session up
  const paused=request?.status==='failed'&&(request.limit||/hit your \w+ limit/i.test(request.error || ''));
  // Why the button can not start yet, in the author's words; empty when it can.
  const blocked=!state.project.production?.plan_ready?(state.plan?.timing?.status==='audio_synced'?(state.project.production?.reason || 'Сценарій розходиться з озвучкою. Додайте озвучку, що відповідає тексту.'):'Спершу додайте озвучку: кадри підлаштуються під неї.')
    :state.plan?.director_stale?'Сценарій розходиться з озвучкою. Режисер має заново розбити кадри.'
    :directorAwaited()?'Кадри з’являться, коли режисер розкладе озвучку.'
    :floor>=frames.length?'Усі кадри створені. Готовий ролик збирає «Експорт MP4» угорі.':'';
  const locked=working||paused||!!blocked;
  make.classList.toggle('locked',locked);make.classList.toggle('waiting',directorAwaited());
  const count=Math.max(Math.min(frames.length,floor+1),Math.min(frames.length,Number(makeCount[id]) || frames.length));
  const shownCount=working||paused?Number(request.frames):count;
  cells.forEach((cell,index)=>{cell.classList.toggle('made',made.has(index));cell.classList.toggle('chosen',index<shownCount&&!made.has(index)&&!blocked);
    cell.title=`Кадр ${index+1} · ${clock(frames[index].start)}–${clock(frames[index].end)}${made.has(index)?' · готовий':''}`;});
  handle.hidden=!!blocked;
  if(shownCount)handle.style.left=`${Number(frames[shownCount-1].end)/(Number(frames[frames.length-1].end) || 1)*100}%`;
  strip.setAttribute('aria-valuenow',String(shownCount));strip.setAttribute('aria-disabled',String(locked));
  max.disabled=locked;max.classList.toggle('active',!locked&&count===frames.length);
  const end=Number(frames[shownCount-1]?.end) || 0,all=Number(frames[frames.length-1].end) || 0;
  readout.innerHTML=blocked&&!working&&!paused?`<strong>${frames.length}</strong><span>${planFrameWord(frames.length)} · ${clock(all)}</span>`
    :`<strong>${floor&&!working&&!paused?`${floor+1}–${shownCount}`:shownCount}</strong><span>${planFrameWord(shownCount)} з ${frames.length} · ${clock(end)} з ${clock(all)}</span>`;
  fillLegend(legend,frames,made.size);
  hint.textContent=blocked;hint.hidden=!blocked||working||paused;
  feed.replaceChildren();
  // While the agent works the button turns into its progress; the steps of the work read in the feed below.
  start.classList.remove('loading','glow-action');start.onclick=null;start.disabled=!!blocked;
  if(working){
    const done=[...made].filter(index=>index<request.frames).length;
    start.disabled=true;start.classList.add('loading');
    start.innerHTML=`${typeof exportSpinner==='string'?exportSpinner:''}<span>Створюємо кадри · ${done} з ${request.frames}</span>`;
    renderTeam(feed,'production',id,true);
    productionTimer=setTimeout(()=>pollProduction(id),8000);
  }else if(paused){
    start.disabled=false;start.classList.add('glow-action');
    start.textContent=`Продовжити кадри ${Math.min(floor+1,request.frames)}–${request.frames}`;
    start.onclick=event=>{event.stopImmediatePropagation();resumeFrames(id,start);};
    const note=document.createElement('p');note.className='plan-note';note.textContent=`${request.limit?request.error:'Закінчився ліміт підписки Claude.'} Усе зроблене збережено. Коли ліміт оновиться, натисніть «Продовжити кадри».`;feed.append(note);
  }else{
    start.textContent='Почати створення ролика';
    if(request?.status==='failed'){const note=document.createElement('p');note.className='plan-note';note.textContent=`Кадри 1–${request.frames} не вдалися. ${request.error || ''} Виберіть кадри й почніть ще раз.`;feed.append(note);}
  }
}

function fillLegend(legend,frames,made){
  const parts=[];
  if(!directorAnimated()){
    const formats=[...new Set(frames.map(frame=>frame.format))];
    for(const format of formats)parts.push(`<span><b style="--format-color:${planFormatVisuals[format]?.color || '#b8bec9'}"></b>${esc(planFormatNames[format] || format)}</span>`);
  }
  if(made)parts.push(`<span><b class="made"></b>Готові: ${made} з ${frames.length}</span>`);
  legend.innerHTML=parts.join('');legend.hidden=!parts.length;
}

// «Почати створення ролика»: the request goes to the agent and the author goes back to the channel's projects, where
// the episode's card shows how the frames are made.
async function startMaking(button){
  if(!state.project||button.disabled||button.onclick)return;
  const id=state.project.id,frames=state.plan?.frames || [];
  const count=Math.max(1,Math.min(frames.length,Number(makeCount[id]) || frames.length));
  button.disabled=true;
  try{
    await api(`/api/projects/${encodeURIComponent(id)}/production-request`,'POST',{frames:count});
    delete makeCount[id];
    showProjectList();status(`Агент почав створювати ${count} ${planFrameWord(count)}. Хід видно на картці випуску.`);
  }catch(error){button.disabled=false;status(error.message,true);}
}

function fillReports(slot){
  if(!slot)return;
  slot.replaceChildren();
  const id=state.project.id,run=directorRuns[id],request=state.project.production_request;
  const add=(title,text,cost)=>{const fold=episodeFold(title);const body=document.createElement('div');body.className='plan-script-text';body.textContent=text;fold.append(body);
    if(cost){const line=document.createElement('p');line.className='plan-note episode-fold-cost';line.textContent=cost.text;line.title=cost.title;fold.append(line);}
    slot.append(fold);return fold;};
  if(directorAnimated()&&run?.status==='done'&&run.summary)
    add('Звіт режисера',run.summary,run.cost_usd?{text:spentLine(run),title:`Режисура йде за підпискою Claude; сума показує, скільки це коштувало б через API.${spentTokens(run)}`}:null);
  if(request?.summary&&!['requested','in_progress'].includes(request.status)){
    const fold=add('Звіт агента',request.summary,request.cost_usd?{text:spentLine(request),title:`Кадри створюються за підпискою Claude; сума показує, скільки це коштувало б через API.${spentTokens(request)}`}:null);
    renderTeam(fold,'production',id,false);
  }
}

async function resumeFrames(id,button){
  button.disabled=true;
  try{
    await api(`/api/projects/${encodeURIComponent(id)}/production-resume`,'POST',{});
    if(state.project?.id!==id)return;
    showProjectList();status('Агент продовжує створювати кадри. Хід видно на картці випуску.');
  }catch(error){button.disabled=false;status(error.message,true);}
}

// Frames of the plan that are made, by their index: a clip of the film covering the frame's middle (as
// store.made_frames counts them), or a frame of an animated film drawn as code. Code is a made frame the author
// reviews live; «Експорт MP4» only converts it into video (user, 30 October 2026).
function productionWorking(){return ['requested','in_progress'].includes(state.project?.production_request?.status);}
function madeSet(frames){
  const drawn=framesDrawn(),clips=filmClips(state.project);
  return new Set(frames.map((frame,index)=>{
    const number=Number(frame.number || index+1);
    if(directorAnimated())return drawn?.has(number)?index:-1;
    const middle=(Number(frame.start)+Number(frame.end))/2;
    const found=clips.some(clip=>Number(clip.start)<=middle&&middle<Number(clip.start)+Number(clip.duration)&&(!/^Razgon · кадр \d{3}$/.test(clip.title || '')||clip.kind!=='animation'||drawn?.has(number)));
    return found?index:-1;
  }).filter(index=>index>=0));
}
function madeFrames(){return madeSet(state.plan?.frames || []).size;}

// Frames the agent has drawn as scenes (backend/frame_progress.py): they are made, green on the strip and on the
// timeline, though only the export renders them.
const drawnFrames={};
function framesDrawn(){
  // an animated channel's film, or a mixed episode whose timeline holds Razgon frame blocks among photos and text
  const id=state.project?.id,blocks=(state.project?.tracks || []).some(track=>(track.clips || []).some(clip=>/^Razgon · кадр/.test(clip.title || '')));
  if(!id || !(directorAnimated() || blocks))return null;
  if(!(id in drawnFrames)){drawnFrames[id]=null;loadDrawn(id);}
  return drawnFrames[id];
}
async function loadDrawn(id){
  let numbers;
  try{numbers=(await api(`/api/projects/${encodeURIComponent(id)}/frames-drawn`)).drawn || [];}catch{return;}
  const before=[...(drawnFrames[id] || [])].join();drawnFrames[id]=new Set(numbers);
  if(state.project?.id!==id || before===numbers.join())return;
  if(state.view==='plan')refreshEpisode();
  if(state.view==='editor'&&typeof renderTimeline==='function')renderTimeline();
}

async function pollDirector(id){
  if(state.project?.id!==id)return;
  const before=directorRuns[id]?.status,run=await loadDirector(id);
  if(state.project?.id!==id)return;
  // The frames arrive with the finished run: reload the plan so the new frames show at once.
  if(before!==run.status && run.status==='done' && state.view==='plan'){await setProjectView('plan');return;}
  refreshEpisode();
}

// The latest actions of a run, newest first, each with who did it: Opus directs, Codex draws, Razgon renders,
// helpers are agents Opus sends off in parallel.
const teamRoles={opus:['Режисер','Claude Opus 5.5, керує всім'],codex:['Художник','Codex, малює картинки'],razgon:['Рендер','Razgon, збирає кадри'],helper:['Помічник','паралельне завдання']};
// The author never sees file names or the agent's English notes: reading and preparing read as one plain line, files
// written read as what they are for, and real steps keep their own words.
function humanStep(text){
  const own=/^Команда: (.*)/.exec(text);
  if(own)return /[а-яіїєґ]/i.test(own[1])?own[1]:'Вивчає матеріали й готує роботу';
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
    if(!steps.length&&!live){box.remove();return;}
    box.innerHTML=(steps.length?`<ol class="team-feed">${steps.slice(-6).reverse().map(step=>`<li><time>${directorTime(step.t)}</time><b>${teamRoles[step.who]?.[0] || ''}</b>${esc(step.text)}</li>`).join('')}</ol>`:`<p class="plan-note">${live?'Агент тільки починає, перші дії з’являться за кілька секунд.':''}</p>`);
  };
  draw();
  api(`/api/projects/${encodeURIComponent(id)}/activity/${kind}`).then(({activity})=>{teamFeeds[kind+id]=activity;if(box.isConnected)draw();}).catch(()=>{});
}

// While the agent works, the project is read again now and then: the request carries its state and spend.
async function pollProduction(id){
  if(state.project?.id!==id)return;
  try{const {project}=await api(`/api/projects/${encodeURIComponent(id)}`);if(state.project?.id!==id)return;
    const before=state.project.production_request?.status;state.project=project;loadDrawn(id);
    if(before!==project.production_request?.status&&state.view==='plan'){renderPlan();return;}}catch{}
  refreshEpisode();
}

async function startDirector(id){
  if(directorDone()&&!confirm('Переробити режисуру? Режисер заново розіб’є озвучку на кадри й перезапише план кадрів цього випуску.'))return;
  try{
    directorRuns[id]=(await api(`/api/projects/${encodeURIComponent(id)}/director`,'POST',{})).director;
    refreshEpisode();
  }catch(error){status(error.message,true);}
}
