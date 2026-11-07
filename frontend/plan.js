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
// Direct montage starts on an empty timeline; planned episodes keep their existing frame gate.
function editorUnlocked(project=state.project){return !!project && (projectAnimated(project) || directMontage(project) || filmClips(project).length>0);}
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
  stopPlayback();state.view=view;syncRoute();renderProject();
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
    const running=data.job?.status==='running';
    const mode=running?'script':data.source || (data.job?.script?'script':null);
    if(mode)showSelection(mode==='file'?1:0);
    if(running){buttons.forEach(button=>button.disabled=true);choices.setAttribute('aria-busy','true');}
  }).catch(error=>{if(choices.isConnected)status(error.message,true);});
}
function renderNarrationGeneration(panel){
  const pid=state.project.id;const box=document.createElement('section');box.className='narration-generation';
  box.innerHTML=`<label>Сценарій<textarea rows="9" placeholder="Вставте текст для озвучення"></textarea></label><small>Готові фрази зберігаються в кеші. Після правок оновляться тільки змінені.</small><p role="status"></p><button class="secondary" type="button">Згенерувати озвучку</button>`;
  panel.append(box);
  const details=document.createElement('div');details.className='narration-choice-profile';details.textContent='Завантажуємо голос…';box.prepend(details);
  const cid=state.project.channel_id;
  api(`/api/channels/${cid}/voice-lab`).then(data=>{
    if(!details.isConnected)return;details.replaceChildren();
    if(data.reference){const player=voicePlayer(null,`/api/channels/${cid}/voice-lab/reference?v=${data.reference.stamp}`,{filename:data.reference.filename,playLabel:'Прослухати голос каналу'});details.append(player);}
    else{const missing=document.createElement('small');missing.textContent='Додайте зразок голосу в налаштуваннях каналу';details.append(missing);}
    const settings=data.settings||{},service=settings.provider==='heygen'?'HeyGen':settings.provider==='fishaudio'?'Fish Audio':'ElevenLabs';
    const model=(settings.provider==='heygen'?data.heygen_models:settings.provider==='fishaudio'?data.fish_models:data.models)?.find(x=>x.id===(settings.provider==='heygen'?settings.heygen_model:settings.provider==='fishaudio'?settings.fish_engine:settings.model))?.name || '';
    const summary=document.createElement('small');summary.className='narration-choice-settings';summary.textContent=[service,model].filter(Boolean).join(' · ');details.append(summary);
  }).catch(()=>{if(details.isConnected)details.textContent='Не вдалося завантажити налаштування голосу';});
  const text=box.querySelector('textarea'),button=box.querySelector('button'),info=box.querySelector('p');
  text.value=voiceScriptDraft[pid] || state.project.voice_script?.text || state.plan?.script || '';
  const estimate=document.createElement('small');estimate.className='narration-cost';button.after(estimate);
  let quoteTimer=null,quoteVersion=0;
  const priceLabel=q=>{const usd=q.estimated_usd==null?'вартість у $ недоступна':`≈ $${q.estimated_usd.toFixed(3)}`;return q.estimated_credits==null?usd:`≈ ${q.estimated_credits.toLocaleString('uk-UA')} кредитів · ${usd}`;};
  async function updateQuote(){const version=++quoteVersion;if(text.value.trim().length<10){estimate.textContent='Вставте сценарій, щоб побачити вартість';return;}estimate.textContent='Рахуємо вартість…';try{const quote=await api(`/api/projects/${pid}/narration/quote`,'POST',{text:text.value});if(version===quoteVersion&&box.isConnected)estimate.textContent=`${priceLabel(quote)} · із кешу ${quote.cached}/${quote.total} фраз${quote.tax_included?' · податок 20% включено':''}`;}catch(error){if(version===quoteVersion)estimate.textContent=error.message;}}
  text.oninput=()=>{voiceScriptDraft[pid]=text.value;quoteVersion++;clearTimeout(quoteTimer);estimate.textContent='Оновлюємо оцінку…';quoteTimer=setTimeout(updateQuote,500);};
  updateQuote();
  const stop=document.createElement('button');stop.type='button';stop.className='secondary narration-stop';stop.textContent='Зупинити озвучення';stop.hidden=true;button.after(stop);
  stop.onclick=async()=>{stop.disabled=true;try{await api(`/api/projects/${pid}/narration/cancel`,'POST',{});info.textContent='Зупиняємо. Поточний запит може завершитися, нові не запускатимуться.';}catch(error){info.textContent=error.message;stop.disabled=false;}};
  let busy=false;
  async function poll(){
    if(!box.isConnected || state.project?.id!==pid)return;
    try{const {job}=await api(`/api/projects/${pid}/narration`);
      if(['running','cancelling'].includes(job?.status)){stop.hidden=false;stop.disabled=job.status==='cancelling';if(typeof channelActivity!=='undefined')channelActivity.add(state.project.channel_id);if(typeof projectActivities!=='undefined')projectActivities.set(pid,'озвучення сценарію');if(!busy&&job.script)text.value=job.script;busy=true;button.disabled=true;text.disabled=true;info.innerHTML=`${exportSpinner}<span>Озвучуємо · ${job.completed} з ${job.total} фраз</span>`;setTimeout(poll,1500);}
      else if(job?.status==='done'&&busy){info.textContent='Озвучка готова. Розпізнаємо й додаємо до плану…';await api(`/api/projects/${pid}/plan/analyze`,'POST',{asset_id:job.asset_id,script:text.value});await selectProject(pid,{view:'plan'});}
      else if(job?.status==='cancelled'){busy=false;stop.hidden=true;button.disabled=false;text.disabled=false;info.textContent='Озвучення зупинено. Готові фрази збережені в кеші.';}
      else if(job?.status==='failed'){stop.hidden=true;busy=false;button.disabled=false;text.disabled=false;info.textContent=job.error;}
    }catch(error){info.textContent=error.message;button.disabled=false;}
  }
  button.onclick=async()=>{if(busy)return;button.disabled=true;try{
    const quote=await api(`/api/projects/${pid}/narration/quote`,'POST',{text:text.value});
    info.textContent=`Із кешу: ${quote.cached} з ${quote.total} фраз.`;
    const cost=priceLabel(quote);estimate.textContent=cost;
    if(!window.confirm(`Озвучити ${quote.total-quote.cached} нових або змінених фраз? ${cost}. Готові фрагменти використаємо з кешу.`)){button.disabled=false;return;}
    await api(`/api/projects/${pid}/narration/start`,'POST',{text:text.value,resume:true});busy=true;await poll();
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
    <label class="voice-script"><span>Текст озвучки <em>необов’язково</em></span><textarea rows="7" placeholder="Вставте текст, який звучить в озвучці"></textarea>
      <small>${direct?'Сценарій допоможе точніше розпізнати озвучку й звірити текст.':'Сценарій можна не додавати: студія сама розпізнає мову. Але з текстом розпізнавання точніше, і в кадрах буде саме ваш текст без помилок.'}</small></label>
    <div class="voice-start-actions"><div class="voice-progress" aria-live="polite"></div><button type="button" class="primary" disabled>Розпізнати озвучку</button></div>`;
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
  function show(stage,value){progress.innerHTML=`<span class="voice-progress-stage">${exportSpinner}<span>${esc(stage)}</span></span>${value===undefined?'':`<progress max="100" value="${value}"></progress>`}`;}
  function lock(value){busy=value;start.disabled=value || !file;text.disabled=value;drop.classList.toggle('is-busy',value);}
  start.addEventListener('click',async()=>{
    if(!file || busy)return;lock(true);
    try{
      show('Завантажуємо озвучку…');
      const response=await fetch(`/api/projects/${encodeURIComponent(project.id)}/assets/upload`,{method:'POST',headers:{'Content-Type':'application/octet-stream','X-File-Name':encodeURIComponent(file.name)},body:file});
      const result=await response.json();if(!response.ok)throw new Error(result.error || 'Не вдалося додати файл');
      // The saved script of an animated episode goes untouched; only an edited text is sent as the voice text.
      const payload={asset_id:result.asset.id},typed=text.value.trim();if(typed && typed!==(project.voice_script?.text || '').trim())payload.script=typed;
      await api(`/api/projects/${encodeURIComponent(project.id)}/plan/analyze`,'POST',payload);await poll();
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
  heading.innerHTML=`<h1>План ролика</h1><label class="project-plan-switch"><input type="checkbox" role="switch" aria-label="Увімкнути план ролика" ${directMontage()?'':'checked'}><span aria-hidden="true"></span></label>`;
  const input=heading.querySelector('input'),id=state.project.id;
  input.disabled=state.project.plan_mode_editable!==true;
  if(input.disabled)heading.title='Перемикач запрацює після безпечного перезапуску студії';
  input.onchange=async()=>{input.disabled=true;try{await action('set_plan_mode',{mode:input.checked?'director':'direct'});if(state.project?.id===id)await selectProject(id,{view:'plan'});}catch{input.checked=!input.checked;input.disabled=false;}};
  panel.append(heading);
  if(state.plan?.timing?.audio || state.plan?.timing?.status==='audio_synced'){
    const fold=document.createElement('details');fold.className='narration-change-fold';
    const summary=document.createElement('summary');summary.textContent='Змінити озвучку або сценарій';fold.append(summary);panel.append(fold);
    fold.addEventListener('toggle',()=>{if(!fold.open||fold.dataset.loaded)return;fold.dataset.loaded='true';
      let generation=null;narrationChoices(fold,upload=>{if(upload){if(generation)generation.hidden=true;openNarrationBinding();}else{if(!generation)generation=renderNarrationGeneration(fold);generation.hidden=false;}},false);
    });
  }
}

function projectAnimated(project=state.project){const kind=project?.project_kind ?? state.channel?.settings?.channel_kind;return kind==='animated';}
