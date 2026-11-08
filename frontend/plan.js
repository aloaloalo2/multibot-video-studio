// Clips that are frames of the film itself: anything but sound, the channel's logo and plate (groups with the role
// «overlay» and clips titled «Логотип» or «Плашка»), as store.film_clips counts them.
function filmClips(project=state.project){
  const overlay=new Set((project?.scene_groups || []).filter(group=>group.role==='overlay').flatMap(group=>group.clip_ids || []));
  return (project?.tracks || []).flatMap(track=>track.clips || []).filter(clip=>clip.kind!=='audio'&&!overlay.has(clip.id)&&!/Логотип|Плашка/.test(clip.title || ''));
}
function projectPlanMode(project=state.project){
  const channel=state.channels?.find(item=>item.id===project?.channel_id) || (state.channel?.id===project?.channel_id?state.channel:null);
  const mode=project?.plan_mode || project?.production?.plan_mode || project?.settings?.plan_mode || channel?.settings?.plan_mode;
  return mode==='direct'?'direct':'director';
}
function directMontage(project=state.project){return projectPlanMode(project)==='direct';}
function sourceForProject(result,project=state.project){return directMontage(project)?result.source || result.plan:result.plan;}
// Every project opens the combined voice, planning and montage workspace, including an empty timeline.
function editorUnlocked(project=state.project){return !!project;}
const editorLockedHint='Монтаж відкриється з першими кадрами ролика';

async function setProjectView(view){
  if(!state.project)return;
  if(view==='editor' && !editorUnlocked()){status(editorLockedHint+'.',true);return;}
  if(view==='editor' && state.view==='agent'){await selectProject(state.project.id,{view:'editor'});return;}
  if(view==='plan'){
    const id=state.project.id;
    try{
      const [result,analysis]=await Promise.all([api(`/api/projects/${encodeURIComponent(id)}/plan`),api(`/api/projects/${encodeURIComponent(id)}/analysis`)]);
      if(state.project?.id!==id)return;
      state.plan=sourceForProject(result);state.planSettingsMatch=result.settings_match ?? null;state.analysis=analysis;
    }catch(error){status(error.message,true);return;}
  }
  stopPlayback();state.view=view==='plan'?'editor':view;syncRoute();renderProject();
}


async function openNarrationBinding(){
  return openMediaTimingImport();
}

const planFormatNames={stock_video:'Стокове відео',generated_video:'Створене відео',stock_photo:'Стокове фото',generated_photo:'Створені зображення',animation:'Анімація',razgon_2d:'2D-анімація Razgon',text:'Текстові тези',host:'Ведучий'};
function planFrameSpeech(frame){
  const text=(frame.sentences || []).join(' ');
  if(frame.continuation?.text)return `Продовження фрази: ${frame.continuation.text}${text?' '+text:''}`;
  return text || (frame.opening_tail?'Пауза між фразами':'');
}
// Time on the plan to a tenth of a second, the Ukrainian way: 00:04,1 (the rounding of the whole seconds stays clock's).
function planClock(value){const tenths=Math.round(Number(value)*10);return clock(Math.floor(tenths/10))+(tenths%10?','+(tenths%10):'');}
function planSeconds(value){return `${String(Number(Number(value).toFixed(1))).replace('.',',')} с`;}

const planFormatVisuals={
  generated_video:{color:'#ffd429',symbol:'▶'},
  stock_video:{color:'#20b6ff',symbol:'▥'},
  generated_photo:{color:'#ff7b24',symbol:'◆'},
  stock_photo:{color:'#2be181',symbol:'●'},
  animation:{color:'#b46cff',symbol:'✦'},
  razgon_2d:{color:'#ff4fd8',symbol:'✎'},
  text:{color:'#ff4da1',symbol:'Т'},
  host:{color:'#ff4242',symbol:'●'}
};
function planFrameWord(count){
  const last=count%10,lastTwo=count%100;
  if(last===1&&lastTwo!==11)return 'кадр';
  if(last>=2&&last<=4&&(lastTwo<12||lastTwo>14))return 'кадри';
  return 'кадрів';
}

const voiceScriptDraft={};
const createVideoIcon='<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="m4 20 11-11 3 3L7 23zM12 12l3 3M5 3v4M3 5h4M19 2v4M17 4h4M20 16v4M18 18h4"/></svg>';
function videoCreationCopy(){return directMontage()?{label:'Розпізнати аудіо',note:'Натисніть, щоб студія розпізнала аудіо й зберегла текст із таймінгами.'}:{label:'Створити відео',note:'Натисніть «Створити відео». Студія розпізнає аудіо, складе план і створить усі кадри.'};}
async function startVideoCreation(pid,payload){
  if(directMontage())return api(`/api/projects/${pid}/plan/analyze`,'POST',payload);
  const capabilities=await api('/api/health');
  if(!capabilities.create_video)throw new Error('Створення відео одним кроком стане доступним після безпечного перезапуску студії. Поточна робота продовжується.');
  return api(`/api/projects/${pid}/create-video`,'POST',payload);
}
function narrationChoices(panel,ready,restore=true){
  const choices=document.createElement('div');choices.className='narration-choices';
  choices.innerHTML=`<button type="button" class="secondary narration-from-text"><span class="narration-choice-art" aria-hidden="true"><span class="narration-paper"><b>Текст</b><i></i><i></i><i></i><span>▶</span></span></span><strong>Озвучити сценарій</strong><small>Вставити текст → створити голос</small></button><button type="button" class="secondary narration-from-file"><span class="narration-choice-art" aria-hidden="true"><span class="narration-upload"><svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M24 30V10m-8 8 8-8 8 8M10 30v9h28v-9"/></svg><b>MP3 · WAV · MP4</b></span></span><strong>Завантажити файл</strong><small>Додати готове аудіо або відео</small></button>`;
  const buttons=choices.querySelectorAll('button'),pid=state.project.id;
  function showSelection(index){
    choices.classList.add('has-selection');
    buttons.forEach((button,i)=>{button.classList.toggle('selected',i===index);button.setAttribute('aria-pressed',String(i===index));});
    ready(index===1);
  }
  async function choose(index){
    try{await api(`/api/projects/${state.project.id}/narration/source`,'POST',{source:index===1?'file':'script'});}catch(error){status(error.message,true);return;}
    showSelection(index);
  }
  buttons.forEach((button,index)=>{button.setAttribute('aria-pressed','false');button.onclick=()=>choose(index);});
  panel.append(choices);
  if(restore)api(`/api/projects/${pid}/narration`).then(data=>{
    if(!choices.isConnected||state.project?.id!==pid)return;
    const running=['running','cancelling'].includes(data.job?.status);
    const mode=running?'script':data.source || (data.job?.script?'script':null);
    if(mode)showSelection(mode==='file'?1:0);
    if(running){choices.hidden=true;choices.setAttribute('aria-busy','true');}
  }).catch(error=>{if(choices.isConnected)status(error.message,true);});
}
function narrationResultVisible(job,project,justGenerated=false){
  return job?.status==='done' && (project?.restarted_at||0)<=(job.started_at||0) && (justGenerated || (project?.assets||[]).some(asset=>asset.id===job.asset_id));
}
function renderNarrationAnalysis(panel,pid){
  const job=state.analysis?.job;
  const ready=panel.querySelector('.narration-ready');if(!ready)return false;
  if(job?.project_id!==pid||!['queued','running'].includes(job.status)){
    if(ready.getAttribute('aria-busy')==='true'){
      ready.removeAttribute('aria-busy');ready.querySelector('.narration-ready-heading strong').textContent='✓ Озвучка готова';
      ready.querySelectorAll('.narration-tempo button,.narration-tempo input,.narration-plan-action').forEach(control=>control.disabled=false);
      const range=ready.querySelector('input'),plan=ready.querySelector('.narration-plan-action');
      plan.disabled=Number(range.value)!==Number(ready.dataset.speed);
      const text=panel.querySelector('textarea');if(text)text.readOnly=false;
      const choices=panel.parentElement?.querySelector('.narration-choices');if(choices)choices.hidden=false;
      if(job?.status==='failed'){const note=panel.querySelector('.narration-status-row p');if(note)note.textContent=job.error||'Не вдалося розпізнати озвучку';}
    }
    return false;
  }
  const stage=speechStageNames[job.stage]||'Розпізнаємо озвучку',percent=Number.isFinite(job.progress)?` · ${Math.round(job.progress)}%`:'';
  ready.setAttribute('aria-busy','true');
  ready.querySelector('.narration-ready-heading strong').innerHTML=`${exportSpinner} Whisper · ${esc(stage)}${percent}`;
  ready.querySelectorAll('.narration-tempo button,.narration-tempo input,.narration-plan-action').forEach(control=>control.disabled=true);
  const note=panel.querySelector('.narration-status-row p');if(note)note.textContent='';
  const text=panel.querySelector('textarea');if(text)text.readOnly=true;
  const choices=panel.parentElement?.querySelector('.narration-choices');if(choices)choices.hidden=true;
  return true;
}
function appendReadyNarration(panel,pid,job,info,refresh){
  const ready=document.createElement('section');ready.className='narration-ready';
  ready.dataset.speed=String(Math.round((job.speed||1)*100));
  const cost=job.estimated_usd===0?'Безкоштовно':job.estimated_usd!=null?`≈ $${job.estimated_usd.toFixed(3)}`:'';
  ready.innerHTML=`<header class="narration-ready-heading"><strong><span aria-hidden="true">✓</span> Озвучка готова</strong><small>${esc(cost)}</small></header>`;
  const headline=ready.querySelector('strong');
  const note=message=>{info.textContent=message;headline.textContent=message;};
  ready.append(voicePlayer(null,`/api/projects/${pid}/assets/${job.asset_id}/file`,{filename:`Озвучка · ${Math.round((job.speed||1)*100)}%`,playLabel:'Прослухати готову озвучку'}));
  const copy=videoCreationCopy(),plan=document.createElement('button');plan.type='button';plan.className='secondary narration-plan-action';plan.innerHTML=createVideoIcon+`<span>${copy.label}</span>`;
  plan.onclick=async()=>{plan.disabled=true;try{await startVideoCreation(pid,{asset_id:job.asset_id,script:job.script});await selectProject(pid,{view:'plan'});}catch(error){note(error.message);plan.disabled=false;}};
  const tempo=document.createElement('div');tempo.className='narration-tempo';
  tempo.innerHTML=`<label>Швидкість<input type="range" min="90" max="110" step="1" value="${Math.round((job.speed||1)*100)}"><output>${Math.round((job.speed||1)*100)}%</output></label><button type="button" class="secondary" hidden>Застосувати</button><small>Використовується швидкість ${Math.round((job.speed||1)*100)}% · без зміни тону</small>`;
  const range=tempo.querySelector('input'),apply=tempo.querySelector('button');
  range.oninput=()=>{tempo.querySelector('output').textContent=range.value+'%';const changed=Number(range.value)!==Math.round((job.speed||1)*100);plan.disabled=changed;apply.hidden=!changed;apply.disabled=false;tempo.querySelector('small').textContent=changed?`Використовується ${Math.round((job.speed||1)*100)}% · обрано ${range.value}%`:`Використовується швидкість ${Math.round((job.speed||1)*100)}% · без зміни тону`;};
  apply.onclick=async()=>{apply.disabled=true;range.disabled=true;plan.disabled=true;note('Змінюємо швидкість…');try{await api(`/api/projects/${pid}/narration/speed`,'POST',{speed:Number(range.value)/100});ready.remove();await refresh();}catch(error){note(error.message);apply.disabled=false;range.disabled=false;}};
  const actions=document.createElement('footer');actions.className='narration-ready-actions';
  const description=document.createElement('p');description.className='narration-create-note';description.textContent=copy.note;actions.append(description,plan);
  ready.append(tempo,actions);panel.classList.add('has-ready-narration');panel.append(ready);renderNarrationAnalysis(panel,pid);return ready;
}
function renderNarrationGeneration(panel){
  const pid=state.project.id;const box=document.createElement('section');box.className='narration-generation';
  box.innerHTML=`<div class="voice-start-head narration-script-heading"><h1>Озвучка сценарію</h1><p>Прослухайте готову озвучку й налаштуйте швидкість перед створенням кадрів.</p></div><label class="voice-script"><span>Сценарій</span><textarea rows="9" placeholder="Вставте текст для озвучення"></textarea></label><small class="narration-cache-note">Готові фрази зберігаються в кеші. Після правок оновляться тільки змінені.</small><div class="narration-status-row"><p role="status"></p><button class="secondary narration-action-icon" type="button" aria-label="Згенерувати озвучку" title="Згенерувати озвучку"></button></div>`;
  panel.append(box);
  const details=document.createElement('div');details.className='narration-choice-profile';details.textContent='Завантажуємо голос…';box.prepend(details);
  const cid=state.project.channel_id;let profile=null,currentJob=null;
  api(`/api/channels/${cid}/voice-lab`).then(data=>{
    profile=data;if(currentJob)renderRunning(currentJob);
    if(!details.isConnected)return;details.replaceChildren();
    if(data.reference){const player=voicePlayer(null,`/api/channels/${cid}/voice-lab/reference?v=${data.reference.stamp}`,{filename:data.reference.filename,playLabel:'Прослухати голос каналу'});details.append(player);}
    else{const missing=document.createElement('small');missing.textContent='Додайте зразок голосу в налаштуваннях каналу';details.append(missing);}
    const settings=data.settings||{},service=settings.provider==='heygen'?'HeyGen':settings.provider==='fishaudio'?'Fish Audio':'ElevenLabs';
    const model=(settings.provider==='heygen'?data.heygen_models:settings.provider==='fishaudio'?data.fish_models:data.models)?.find(x=>x.id===(settings.provider==='heygen'?settings.heygen_model:settings.provider==='fishaudio'?settings.fish_engine:settings.model))?.name || '';
    const summary=document.createElement('small');summary.className='narration-choice-settings';summary.textContent=[service,model].filter(Boolean).join(' · ');details.append(summary);
  }).catch(()=>{if(details.isConnected)details.textContent='Не вдалося завантажити налаштування голосу';});
  const text=box.querySelector('textarea'),button=box.querySelector('.narration-action-icon'),info=box.querySelector('.narration-status-row p');
  text.value=voiceScriptDraft[pid] || state.project.voice_script?.text || state.plan?.script || '';
  const estimate=document.createElement('small');estimate.className='narration-cost';box.querySelector('.narration-status-row').append(estimate);
  const count=document.createElement('small');count.className='narration-phrase-count';box.querySelector('.narration-status-row').append(count);
  const progress=document.createElement('div');progress.className='narration-progress-track';progress.setAttribute('role','progressbar');progress.setAttribute('aria-label','Готовність озвучення');progress.setAttribute('aria-valuemin','0');progress.setAttribute('aria-valuemax','100');progress.innerHTML='<span></span>';box.querySelector('.narration-status-row').append(progress);
  let quoteTimer=null,quoteVersion=0;
  const priceLabel=q=>{if(q.estimated_usd===0)return 'Безкоштовно';const usd=q.estimated_usd==null?'вартість у $ недоступна':`≈ $${q.estimated_usd.toFixed(3)}`;return q.estimated_credits==null?usd:`≈ ${q.estimated_credits.toLocaleString('uk-UA')} кредитів · ${usd}`;};
  async function updateQuote(){const version=++quoteVersion;if(text.value.trim().length<10){estimate.textContent='Вставте сценарій, щоб побачити вартість';return;}estimate.textContent='Рахуємо вартість…';try{const quote=await api(`/api/projects/${pid}/narration/quote`,'POST',{text:text.value});if(version===quoteVersion&&box.isConnected)estimate.textContent=`${priceLabel(quote)} · ${quote.cached?`із кешу ${quote.cached}/${quote.total}`:quote.total} фраз${quote.tax_included?' · податок 20% включено':''}`;}catch(error){if(version===quoteVersion)estimate.textContent=error.message;}}
  text.oninput=()=>{box.classList.remove('has-ready-narration');button.hidden=false;voiceScriptDraft[pid]=text.value;quoteVersion++;clearTimeout(quoteTimer);estimate.textContent='Оновлюємо оцінку…';quoteTimer=setTimeout(updateQuote,500);};
  updateQuote();
  let busy=false;
  function actionState(mode='idle'){
    const running=mode==='running',waiting=mode==='cancelling';
    const label=waiting?'Зупиняємо озвучення':running?'Зупинити озвучення':'Озвучити сценарій';
    button.hidden=false;button.setAttribute('aria-label',label);button.title=label;button.disabled=waiting;
    button.innerHTML=waiting?exportSpinner:running?'<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="1" fill="currentColor"/></svg>':'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="9" y="3" width="6" height="12" rx="3"/><path d="M6 10v2a6 6 0 0 0 12 0v-2M12 18v3M9 21h6"/></svg>';
    if(!running&&!waiting)button.innerHTML+='<span>Озвучити сценарій</span>';
    const choices=panel.querySelector('.narration-choices');if(choices)choices.hidden=running||waiting;
    box.classList.toggle('is-generating',running||waiting);text.readOnly=running||waiting;
  }
  function renderRunning(job){
    const settings=job.render_settings||{...profile?.settings,provider:job.provider};
    const service={heygen:'HeyGen',fishaudio:'Fish Audio',elevenlabs:'ElevenLabs'}[settings.provider]||settings.provider||'';
    const key=settings.provider==='heygen'?settings.heygen_model:settings.provider==='fishaudio'?settings.fish_engine:settings.model;
    const models=[...(profile?.heygen_models||[]),...(profile?.fish_models||[]),...(profile?.models||[])];
    const model=models.find(m=>m.id===key)?.name||key||'';
    const percent=job.total>0?Math.min(99,Math.max(0,Math.floor((job.completed||0)/job.total*100))):0;
    info.innerHTML=`<span class="narration-engine">${esc([service,model].filter(Boolean).join(' · '))}</span><span class="narration-progress-title">${exportSpinner}<strong>${job.status==='cancelling'?'Зупиняємо':'Озвучуємо'}</strong><b>${percent}%</b></span>`;
    count.textContent=`${job.completed||0} із ${job.total||0} фраз`;
    progress.setAttribute('aria-valuenow',String(percent));progress.firstElementChild.style.width=percent+'%';
    estimate.textContent=job.estimated_usd===0?'Безкоштовно':priceLabel(job);
  }
  actionState();
  async function poll(){
    if(!box.isConnected || state.project?.id!==pid)return;
    try{const {job}=await api(`/api/projects/${pid}/narration`);
      if(['running','cancelling'].includes(job?.status)){
        if(typeof channelActivity!=='undefined')channelActivity.add(state.project.channel_id);
        if(typeof projectActivities!=='undefined')projectActivities.set(pid,{kind:'озвучення сценарію',progress:job.total>0?Math.min(99,Math.floor((job.completed||0)/job.total*100)):0});
        if(!busy&&job.script)text.value=job.script;
        currentJob=job;busy=true;clearTimeout(quoteTimer);quoteVersion++;actionState(job.status);renderRunning(job);setTimeout(poll,1500);
      }
      else if(narrationResultVisible(job,state.project,busy)){
        busy=false;currentJob=null;actionState();if(!text.value.trim()&&job.script)text.value=job.script;button.hidden=text.value.trim()===(job.script||'').trim();estimate.textContent=job.estimated_usd===0?'Безкоштовно':priceLabel(job);info.textContent='Озвучка готова. Прослухайте її перед створенням кадрів.';
        if(!box.querySelector('.narration-ready')){
          appendReadyNarration(box,pid,job,info,poll);
        }
      }
      else if(job?.status==='cancelled'){busy=false;currentJob=null;actionState();info.textContent='Озвучення зупинено. Готові фрази збережені в кеші.';}
      else if(job?.status==='failed'){busy=false;currentJob=null;actionState();info.textContent=job.error;}
    }catch(error){info.textContent=error.message;button.disabled=false;}
  }
  button.onclick=async()=>{if(busy){actionState('cancelling');try{await api(`/api/projects/${pid}/narration/cancel`,'POST',{});await poll();}catch(error){info.textContent=error.message;actionState('running');}return;}button.disabled=true;try{
    const quote=await api(`/api/projects/${pid}/narration/quote`,'POST',{text:text.value});
    info.textContent=`Із кешу: ${quote.cached} з ${quote.total} фраз.`;
    const cost=priceLabel(quote);estimate.textContent=cost;
    if(!window.confirm(`Озвучити ${quote.total-quote.cached} нових або змінених фраз? ${cost}. Готові фрагменти використаємо з кешу.`)){button.disabled=false;return;}
    await api(`/api/projects/${pid}/narration/start`,'POST',{text:text.value,resume:true});box.querySelector('.narration-ready')?.remove();box.classList.remove('has-ready-narration');busy=true;await poll();
  }catch(error){info.textContent=error.message;button.disabled=false;}};
  poll();return box;
}
function renderVoiceStart(panel){
  const project=state.project,direct=directMontage();
  const section=document.createElement('section');section.className='voice-start';
  section.innerHTML=`<div class="voice-start-head"><h1>Додайте озвучку ролика</h1><p>${direct?'Студія розпізнає озвучку й збереже текст із таймінгами. Монтаж уже доступний.':'Студія локально розпізнає мову, режисер розіб’є ролик на кадри, а ви оберете, скільки кадрів створити першими.'}</p></div>
    <label class="voice-drop"><input type="file" accept="audio/*,video/*,.m4a,.mkv,.aiff,.aif,.flac,.opus" hidden>
      <span class="voice-drop-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 15V4m0 0-4 4m4-4 4 4M5 15v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3"/></svg></span>
      <strong>Перетягніть аудіо сюди</strong><span class="voice-drop-hint">або натисніть, щоб вибрати файл озвучки</span><small>MP3, WAV, M4A, FLAC або відео з голосом</small><b class="voice-drop-file" hidden></b></label>
    <label class="voice-script"><span>Сценарій <em>необов’язково</em></span><textarea rows="7" placeholder="Вставте текст, який звучить в озвучці"></textarea>
      <small>${direct?'Сценарій допоможе точніше розпізнати озвучку й звірити текст.':'Сценарій можна не додавати: студія сама розпізнає мову. Але з текстом розпізнавання точніше, і в кадрах буде саме ваш текст без помилок.'}</small></label>
    <div class="voice-start-actions"><p class="narration-create-note">${videoCreationCopy().note}</p><div class="voice-progress" aria-live="polite"></div><button type="button" class="secondary" disabled>${createVideoIcon}<span>${videoCreationCopy().label}</span></button></div>`;
  section.hidden=true;let generated=null;
  narrationChoices(panel,upload=>{section.hidden=!upload;if(generated)generated.hidden=upload;if(!upload&&!generated)generated=renderNarrationGeneration(panel);});
  panel.append(section);
  const drop=section.querySelector('.voice-drop'),input=drop.querySelector('input'),fileLabel=drop.querySelector('.voice-drop-file');
  const text=section.querySelector('textarea'),start=section.querySelector('.voice-start-actions button'),progress=section.querySelector('.voice-progress');
  let file=null,busy=false;
  text.value=voiceScriptDraft[project.id] || project.voice_script?.text || (direct?state.plan?.script:'') || '';
  text.addEventListener('input',()=>{voiceScriptDraft[project.id]=text.value;});
  function choose(next){
    if(busy || !next)return;
    if(!/^(audio|video)\//.test(next.type) && !/\.(mp3|wav|m4a|aac|flac|ogg|opus|aif|aiff|mp4|mov|mkv|webm)$/i.test(next.name)){status('Потрібен аудіо- або відеофайл з озвучкою.',true);return;}
    file=next;fileLabel.hidden=false;fileLabel.textContent=next.name;drop.classList.add('has-file');start.disabled=false;
  }
  input.addEventListener('change',()=>choose(input.files[0]));
  for(const name of ['dragenter','dragover'])drop.addEventListener(name,event=>{event.preventDefault();drop.classList.add('is-over');});
  for(const name of ['dragleave','drop'])drop.addEventListener(name,()=>drop.classList.remove('is-over'));
  drop.addEventListener('drop',event=>{event.preventDefault();choose(event.dataTransfer.files[0]);});
  function show(stage,value){progress.innerHTML=`<span class="voice-progress-stage">${exportSpinner}<span>${esc(stage)}</span></span>${value===undefined?'':`<progress max="100" value="${value}"></progress>`}`;if(generated)renderNarrationAnalysis(generated,project.id);}
  function lock(value){busy=value;start.disabled=value || !file;text.disabled=value;drop.classList.toggle('is-busy',value);}
  start.addEventListener('click',async()=>{
    if(!file || busy)return;lock(true);
    try{
      show('Завантажуємо озвучку…');
      const response=await fetch(`/api/projects/${encodeURIComponent(project.id)}/assets/upload`,{method:'POST',headers:{'Content-Type':'application/octet-stream','X-File-Name':encodeURIComponent(file.name)},body:file});
      const result=await response.json();if(!response.ok)throw new Error(result.error || 'Не вдалося додати файл');
      // The saved script of an animated episode goes untouched; only an edited text is sent as the voice text.
      const payload={asset_id:result.asset.id},typed=text.value.trim();if(typed && typed!==(project.voice_script?.text || '').trim())payload.script=typed;
      await startVideoCreation(project.id,payload);await poll();
    }catch(error){lock(false);show(error.message);}
  });
  async function poll(){
    if(!section.isConnected)return;
    const result=await api(`/api/projects/${encodeURIComponent(project.id)}/analysis`);
    if(!section.isConnected || state.project?.id!==project.id)return;
    state.analysis=result;
    const job=result.job;if(!job || !section.isConnected)return;
    if(job.status==='failed'){lock(false);show(job.error || 'Обробку зупинено');return;}
    if(job.status==='complete'){
      if(result.report?.applied){delete voiceScriptDraft[project.id];status(direct?'Озвучку й розпізнаний текст збережено.':'Озвучку розпізнано, план готовий.');await selectProject(project.id,{view:'plan'});return;}
      lock(false);show('Озвучку розпізнано, але текст не збігся з озвученим. Перевірте звіт нижче.');if(result.report)appendSpeechReport(section,result.report);return;
    }
    lock(true);show(speechStageNames[job.stage] || 'Обробка',job.progress);setTimeout(()=>poll().catch(error=>{lock(false);show(error.message);}),1200);
  }
  // A recognition already running shows here too, started in another tab or by an agent through the API. An opening
  // project draws this page before its recognition has loaded (selectProject asks for it afterwards), so wait for it.
  const watch=job=>{if(job && job.project_id===project.id && (job.status==='queued' || job.status==='running'))poll().catch(error=>{lock(false);show(error.message);});};
  // A page left open keeps looking too: a recognition an agent starts later through the API shows its progress here,
  // and a voice applied that way opens the plan. The job seen when the page opened is not taken for a new one.
  let seen=null;
  function idle(){
    if(!section.isConnected || state.project?.id!==project.id)return;
    if(busy){setTimeout(idle,3000);return;}
    api(`/api/projects/${encodeURIComponent(project.id)}/analysis`).then(result=>{
      if(!section.isConnected || state.project?.id!==project.id || busy)return;
      const job=result.job;
      if(job && job.id!==seen){
        if(job.status==='queued' || job.status==='running'){state.analysis=result;watch(job);}
        else if(job.status==='complete' && result.report?.applied){state.analysis=result;selectProject(project.id,{view:'plan'});return;}
      }
      setTimeout(idle,3000);
    }).catch(()=>setTimeout(idle,3000));
  }
  const begin=result=>{seen=result?.job?.status==='queued' || result?.job?.status==='running'?null:(result?.job?.id || null);watch(result?.job);setTimeout(idle,3000);};
  if(state.analysis)begin(state.analysis);
  else loadAnalysis(project.id).then(result=>{if(section.isConnected && state.project?.id===project.id)begin(result);}).catch(error=>show(error.message));
}

function renderPlan(){
  const direct=directMontage();
  $('view-plan-label').textContent=direct?'Озвучка':'План ролика';
  $('project-plan').setAttribute('aria-label',direct?'Озвучка, сценарій і розпізнаний текст':'Карта ролика');
  $('view-plan').classList.toggle('active',state.view==='plan');
  $('view-editor').classList.toggle('active',state.view==='editor');
  $('view-agent').classList.toggle('active',state.view==='agent');
  $('view-plan').setAttribute('aria-pressed',String(state.view==='plan'));
  $('view-editor').setAttribute('aria-pressed',String(state.view==='editor'));
  $('view-agent').setAttribute('aria-pressed',String(state.view==='agent'));
  const panel=$('project-plan');panel.replaceChildren();
  if(!state.project || state.view!=='plan')return;
  renderPlanSwitch(panel);
  if(direct){
    if(state.plan?.timing?.audio || state.plan?.timing?.status==='audio_synced')renderEpisode(panel);
    else renderVoiceStart(panel);
    return;
  }
  if(!state.plan?.frames?.length){renderVoiceStart(panel);return;}
  // one page for photo and animated channels (director.js)
  renderEpisode(panel);
}

// The frames of the plan as a table: number and time, format, the spoken words and the idea of the frame.
function planTable(frames,synced,made=new Set()){
  const names=planFormatNames;
  const table=document.createElement('table');table.className='plan-table';table.innerHTML='<thead><tr><th scope="col">Кадр і час</th><th scope="col">Формат</th><th scope="col">Репліка й задум кадру</th></tr></thead>';
  const body=document.createElement('tbody');
  frames.forEach((frame,index)=>{
    const row=document.createElement('tr');const speech=planFrameSpeech(frame);
    const visual=frame.visual || frame.description || frame.notes || '';
    const phraseItems=frame.continuation?[frame.continuation,...(frame.sentence_timings || [])]:(frame.sentence_timings || []);
    const phrases=synced?phraseItems.map(phrase=>`<li><time>${planClock(phrase.start)}–${planClock(phrase.end)}</time> ${esc(phrase.text)}</li>`).join(''):'';
    row.innerHTML=`<td><strong>${esc(frame.number ?? index+1)}${made.has(index)?'<span class="plan-made" title="Кадр готовий">✓</span>':''}</strong><span>${planClock(frame.start)}–${planClock(frame.end)}</span><small>${planSeconds(Number(frame.end)-Number(frame.start))}</small></td><td><span class="plan-format" style="--format-color:${planFormatVisuals[frame.format]?.color || '#b8bec9'}">${esc(names[frame.format] || frame.format)}</span></td><td><p>${esc(speech)}</p>${phrases?`<details class="plan-phrases"><summary>Час кожної фрази</summary><ul>${phrases}</ul></details>`:''}${visual?`<small>${esc(visual)}</small>`:''}</td>`;body.append(row);
  });
  table.append(body);
  return table;
}

$('view-plan').addEventListener('click',()=>setProjectView('plan'));
$('view-editor').addEventListener('click',()=>setProjectView('editor'));
$('view-agent').addEventListener('click',()=>setProjectView('agent'));

function renderPlanSwitch(panel){
  const heading=document.createElement('div');heading.className='project-plan-heading';
  heading.innerHTML='<h1><svg class="narration-heading-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12c3-1 4.5-4 6.5-3.5L12 10l2.5-1.5C16.5 8 18 11 21 12c-2 4-5 6-9 6s-7-2-9-6Z"/><path d="M3 12c3 1 6 .5 9 .5s6 .5 9-.5"/></svg>Озвучка</h1>';
  panel.append(heading);

}

function projectAnimated(project=state.project){const kind=project?.project_kind ?? state.channel?.settings?.channel_kind;return kind==='animated';}
