// The editor opens once the plan follows a real voice, or for an older project that already has a montage.
function editorUnlocked(project=state.project){return !!project && (!!project.production?.plan_ready || (project.tracks || []).some(track=>(track.clips || []).length));}

async function setProjectView(view){
  if(!state.project)return;
  if(view==='editor' && !editorUnlocked()){status('Монтаж відкриється, коли план буде за озвучкою.',true);return;}
  if(view==='editor' && state.view==='agent'){await selectProject(state.project.id,{view:'editor'});return;}
  if(view==='plan'){
    const id=state.project.id;
    try{
      const [result,analysis]=await Promise.all([api(`/api/projects/${encodeURIComponent(id)}/plan`),api(`/api/projects/${encodeURIComponent(id)}/analysis`)]);
      if(state.project?.id!==id)return;
      state.plan=result.plan;state.planSettingsMatch=result.settings_match ?? null;state.analysis=analysis;
    }catch(error){status(error.message,true);return;}
  }
  stopPlayback();state.view=view;syncRoute();renderProject();
}

function openPlanBuilder(){
  if(!state.project)return;
  const project=state.project,previous=state.plan;
  const formats=Object.keys(planFormatVisuals),values={...(project.plan_weights || state.channel.settings.weights)};
  modal(previous?'Перегенерувати план':'Створити план ролика',
    `<p>Початкові кадри формуються за налаштуваннями каналу. Студія збереже попередню версію карти. Після зміни сценарію потрібно оновити таймінги фраз.</p><label>TXT-файл сценарію<input id="plan-script-file" type="file" accept=".txt,text/plain"></label><label>Сценарій<textarea id="plan-script-input" rows="12" placeholder="Вставте готовий сценарій"></textarea></label><label>Орієнтовна тривалість, с<input id="plan-audio-duration" type="number" min="0.1" step="0.001" placeholder="Можна залишити порожнім"></label><label class="check"><input id="plan-own-weights" type="checkbox" ${project.plan_weights?'checked':''}>Власні пропорції для цього проєкту</label><section id="plan-weights-panel" ${project.plan_weights?'':'hidden'}><div class="weights-grid">${formats.map(format=>`<label>${planFormatNames[format]}, %<input data-plan-weight="${format}" type="number" min="0" max="100" step="1" value="${values[format] || 0}"></label>`).join('')}</div><p id="plan-weight-total"></p><button id="plan-normalize-weights" class="secondary" type="button">Привести до 100%</button><p>Налаштування каналу збережуться.</p></section>`,
    [{label:'Скасувати',run:closeModal},{label:previous?'Перегенерувати план':'Створити чернетку',primary:true,run:async()=>{
      const button=$('modal-actions').querySelector('.primary');button.disabled=true;
      try{
        const script=$('plan-script-input').value,duration=$('plan-audio-duration').value;
        if(!script.trim())throw new Error('Додайте текст сценарію.');
        const payload={script};if(duration)payload.duration=Number(duration);
        if($('plan-own-weights').checked)payload.weights=Object.fromEntries([...document.querySelectorAll('[data-plan-weight]')].map(input=>[input.dataset.planWeight,Number(input.value)]));
        else payload.use_channel_weights=true;
        if(script===previous?.script && previous.hints)payload.hints=previous.hints;
        if(script===previous?.script && previous?.timing?.status==='audio_synced')payload.timings={duration:previous.timing.audio.duration,audio_sha256:previous.timing.audio.sha256,sentences:previous.timing.sentences};
        const result=await api(`/api/projects/${encodeURIComponent(project.id)}/plan/generate`,'POST',payload);
        closeModal();await selectProject(result.project.id,{view:'plan'});status('Нову версію плану збережено.');
      }catch(error){button.disabled=false;status(error.message,true);}
    }}]);
  $('plan-script-input').value=previous?.script || '';
  if(previous?.timing?.status==='audio_synced')$('plan-audio-duration').disabled=true;
  function drawTotal(){const sum=[...document.querySelectorAll('[data-plan-weight]')].reduce((sum,input)=>sum+Number(input.value),0);$('plan-weight-total').textContent=`Разом ${sum}%`;$('plan-weight-total').classList.toggle('invalid',sum!==100);}
  $('plan-own-weights').addEventListener('change',()=>{$('plan-weights-panel').hidden=!$('plan-own-weights').checked;});
  document.querySelectorAll('[data-plan-weight]').forEach(input=>input.addEventListener('input',drawTotal));
  $('plan-normalize-weights').addEventListener('click',()=>{try{const inputs=[...document.querySelectorAll('[data-plan-weight]')],weights=normalizeWeights(Object.fromEntries(inputs.map(input=>[input.dataset.planWeight,Number(input.value)])),formats);inputs.forEach(input=>input.value=weights[input.dataset.planWeight]);drawTotal();}catch(error){status(error.message,true);}});drawTotal();
  $('plan-script-file').addEventListener('change',async event=>{
    try{const file=event.target.files[0];if(file)$('plan-script-input').value=await file.text();}catch(error){status(error.message,true);}
  });
}

async function openNarrationBinding(){
  return openMediaTimingImport();
}

const planFormatNames={stock_video:'Стокове відео',generated_video:'Створене відео',stock_photo:'Стокове фото',generated_photo:'Створене фото',animation:'Анімація',razgon_2d:'2D-анімація Razgon',text:'Текстові тези',host:'Ведучий'};
function planFrameSpeech(frame){
  const text=(frame.sentences || []).join(' ');
  if(frame.continuation?.text)return `Продовження фрази: ${frame.continuation.text}${text?' '+text:''}`;
  return text || (frame.opening_tail?'Пауза між фразами':'');
}
const planZoomByProject={};
function planClock(value){const milliseconds=Math.round(Number(value)*1000);return clock(milliseconds/1000)+(milliseconds%1000?','+String(milliseconds%1000).padStart(3,'0'):'');}

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

function renderPlanTimeline(panel,frames,shares,names,total,formatButtons){
  if(!Number.isFinite(total)||total<=0)return;
  const timeline=document.createElement('section');timeline.className='plan-timeline';timeline.setAttribute('aria-label','Таймлайн плану');
  const heading=document.createElement('div');heading.className='plan-timeline-heading';
  const title=document.createElement('h2');title.textContent=state.project.production?.plan_ready?'Таймлайн за озвучкою':'Попередній таймлайн';
  const zoomControls=document.createElement('div');zoomControls.className='plan-zoom';
  const minus=document.createElement('button'),plus=document.createElement('button'),level=document.createElement('span');
  minus.type=plus.type='button';minus.textContent='−';plus.textContent='+';minus.setAttribute('aria-label','Зменшити масштаб плану');plus.setAttribute('aria-label','Збільшити масштаб плану');level.setAttribute('aria-live','polite');
  zoomControls.append(minus,level,plus);heading.append(title,zoomControls);timeline.append(heading);
  const scroll=document.createElement('div');scroll.className='plan-timeline-scroll';
  const inner=document.createElement('div');inner.className='plan-timeline-inner';scroll.append(inner);timeline.append(scroll);
  let zoom=planZoomByProject[state.project.id] || 3.38;
  function applyZoom(){inner.style.width=`${zoom*100}%`;level.textContent=`${Math.round(zoom*100)}%`;minus.disabled=zoom<=1;plus.disabled=zoom>=16;planZoomByProject[state.project.id]=zoom;}
  minus.addEventListener('click',()=>{zoom=Math.max(1,zoom/1.5);applyZoom();});plus.addEventListener('click',()=>{zoom=Math.min(16,zoom*1.5);applyZoom();});applyZoom();
  const axis=document.createElement('div');axis.className='plan-timeline-axis';
  const axisLabel=document.createElement('span');axisLabel.textContent='Час';
  const scale=document.createElement('div');scale.className='plan-timeline-scale';
  for(let tick=0;tick<=4;tick++){const mark=document.createElement('span');mark.textContent=clock(total*tick/4);scale.append(mark);}
  axis.append(axisLabel,scale);inner.append(axis);
  const detail=document.createElement('p');detail.className='plan-timeline-detail';detail.setAttribute('aria-live','polite');detail.textContent='Наведи на смужку, щоб побачити номер і час кадру.';
  const bars=[],rows=[],counts={};
  for(const frame of frames)counts[frame.format]=(counts[frame.format] || 0)+1;
  let pinned=null;
  function highlight(format,frame){
    timeline.classList.toggle('is-filtered',!!format);
    for(const bar of bars)bar.classList.toggle('is-highlighted',bar.dataset.format===format);
    for(const row of rows){row.classList.toggle('is-dimmed',!!format && row.dataset.format!==format && row.dataset.format!=='all');row.classList.toggle('is-highlighted',row.dataset.format===format);}
    for(const button of formatButtons){button.classList.toggle('is-dimmed',!!format && button.dataset.format!==format);button.classList.toggle('is-highlighted',button.dataset.format===format);button.setAttribute('aria-pressed',String(button.dataset.format===pinned));}
    if(frame){
      const speech=planFrameSpeech(frame);
      detail.textContent=`Кадр ${frame.number ?? frames.indexOf(frame)+1} · ${clock(frame.start)} - ${clock(frame.end)} · ${names[frame.format] || frame.format}${speech?' · '+speech.slice(0,110):''}`;
    }else if(format){const count=counts[format] || 0;detail.textContent=`${names[format] || format}: ${count} ${planFrameWord(count)} у плані.`;}
    else detail.textContent='Наведи на смужку, щоб побачити номер і час кадру.';
  }
  function addRow(format,label,rowFrames){
    const row=document.createElement('div');row.className='plan-timeline-row';row.dataset.format=format;
    if(format==='all')row.classList.add('plan-timeline-overview');
    const rowLabel=document.createElement('span');rowLabel.className='plan-timeline-label';
    if(format!=='all'){
      const symbol=document.createElement('b');symbol.className='plan-format-symbol';symbol.dataset.format=format;symbol.setAttribute('aria-hidden','true');
      symbol.style.setProperty('--format-color',planFormatVisuals[format]?.color || '#b8bec9');
      symbol.textContent=planFormatVisuals[format]?.symbol || '•';rowLabel.append(symbol);
    }
    rowLabel.append(document.createTextNode(label));
    const rail=document.createElement('div');rail.className='plan-timeline-rail';
    for(const frame of rowFrames){
      const start=Number(frame.start),end=Number(frame.end);
      if(!Number.isFinite(start)||!Number.isFinite(end)||end<=start)continue;
      const bar=document.createElement('span');bar.className='plan-frame-bar';bar.dataset.format=frame.format;
      bar.style.left=`${Math.max(0,Math.min(100,start/total*100))}%`;
      bar.style.width=`${Math.max(0,Math.min(100,(end-start)/total*100))}%`;
      bar.style.setProperty('--format-color',planFormatVisuals[frame.format]?.color || '#b8bec9');
      bar.title=`Кадр ${frame.number ?? frames.indexOf(frame)+1}, ${planClock(start)} - ${planClock(end)}, ${names[frame.format] || frame.format}`;
      if(format==='all')bar.dataset.index=String(frames.indexOf(frame));
      bar.addEventListener('mouseenter',()=>highlight(frame.format,frame));
      bar.addEventListener('mouseleave',()=>highlight(format==='all'?pinned:format));
      rail.append(bar);bars.push(bar);
    }
    row.append(rowLabel,rail);inner.append(row);rows.push(row);
    if(format==='all')row.addEventListener('mouseleave',()=>highlight(pinned));
    else{
      row.addEventListener('mouseenter',()=>highlight(format));
      row.addEventListener('mouseleave',()=>highlight(pinned));
    }
  }
  addRow('all','Усі кадри',frames);
  const overviewRail=rows[0].querySelector('.plan-timeline-rail');
  const selection=document.createElement('span');selection.className='plan-selection';selection.hidden=true;
  const selectionLabel=document.createElement('b');selection.append(selectionLabel);overviewRail.prepend(selection);
  for(const {format} of shares)addRow(format,names[format] || format,frames.filter(frame=>frame.format===format));
  timeline.append(detail);panel.append(timeline);
  // The start panel marks the first N frames: the overview rail shows the stretch and its length.
  timeline.selectFrames=count=>{
    timeline.classList.toggle('has-selection',count>0);selection.hidden=!count;
    for(const bar of bars)if(bar.dataset.index!==undefined)bar.classList.toggle('is-selected',Number(bar.dataset.index)<count);
    if(!count)return;
    const end=Number(frames[count-1].end);
    selection.style.width=`${Math.max(0,Math.min(100,end/total*100))}%`;
    selection.classList.toggle('is-wide',end/total>.85);
    selectionLabel.textContent=`${count} ${planFrameWord(count)} · ${clock(end)}`;
  };
  return timeline;
  for(const button of formatButtons){
    const format=button.dataset.format;
    button.addEventListener('mouseenter',()=>highlight(format));
    button.addEventListener('mouseleave',()=>highlight(pinned));
    button.addEventListener('focus',()=>highlight(format));
    button.addEventListener('blur',()=>highlight(pinned));
    button.addEventListener('click',()=>{pinned=pinned===format?null:format;highlight(pinned);});
  }
}

const voiceScriptDraft={};
function renderVoiceStart(panel){
  const project=state.project;
  const section=document.createElement('section');section.className='voice-start';
  section.innerHTML=`<div class="voice-start-head"><h1>Додайте озвучку ролика</h1><p>Студія локально розпізнає мову, режисер розіб’є ролик на кадри, а ви оберете, скільки кадрів створити першими.</p></div>
    <label class="voice-drop"><input type="file" accept="audio/*,video/*,.m4a,.mkv,.aiff,.aif,.flac,.opus" hidden>
      <span class="voice-drop-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 15V4m0 0-4 4m4-4 4 4M5 15v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3"/></svg></span>
      <strong>Перетягніть аудіо сюди</strong><span class="voice-drop-hint">або натисніть, щоб вибрати файл озвучки</span><small>MP3, WAV, M4A, FLAC або відео з голосом</small><b class="voice-drop-file" hidden></b></label>
    <label class="voice-script"><span>Текст озвучки <em>необов’язково</em></span><textarea rows="7" placeholder="Вставте текст, який звучить в озвучці"></textarea>
      <small>Сценарій можна не додавати: студія сама розпізнає мову. Але з текстом розпізнавання точніше, і в кадрах буде саме ваш текст без помилок.</small></label>
    <div class="voice-start-actions"><div class="voice-progress" aria-live="polite"></div><button type="button" class="primary" disabled>Розпізнати озвучку</button></div>`;
  panel.append(section);
  const drop=section.querySelector('.voice-drop'),input=drop.querySelector('input'),fileLabel=drop.querySelector('.voice-drop-file');
  const text=section.querySelector('textarea'),start=section.querySelector('.voice-start-actions button'),progress=section.querySelector('.voice-progress');
  let file=null,busy=false;
  text.value=voiceScriptDraft[project.id] || project.voice_script?.text || '';
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
  function show(stage,value){progress.innerHTML=`<span>${esc(stage)}</span>${value===undefined?'':`<progress max="100" value="${value}"></progress>`}`;}
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
    const result=await api(`/api/projects/${encodeURIComponent(project.id)}/analysis`);state.analysis=result;
    const job=result.job;if(!job || !section.isConnected)return;
    if(job.status==='failed'){lock(false);show(job.error || 'Обробку зупинено');return;}
    if(job.status==='complete'){
      if(result.report?.applied){delete voiceScriptDraft[project.id];status('Озвучку розпізнано, план готовий.');await selectProject(project.id,{view:'plan'});return;}
      lock(false);show('Озвучку розпізнано, але текст не збігся з озвученим. Перевірте звіт нижче.');if(result.report)appendSpeechReport(section,result.report);return;
    }
    lock(true);show(speechStageNames[job.stage] || 'Обробка',job.progress);setTimeout(()=>poll().catch(error=>{lock(false);show(error.message);}),1200);
  }
  const job=state.analysis?.job;
  if(job && job.project_id===project.id && (job.status==='queued' || job.status==='running'))poll().catch(error=>show(error.message));
}

const planStartOpen={};
function isDirectorPlan(plan){return plan?.frame_source==='razgon-direction';}
function renderProductionStart(section,frames,getTimeline){
  const project=state.project,total=frames.length,request=project.production_request;
  section.className='plan-start';section.replaceChildren();section.hidden=!planStartOpen[project.id];
  let count=Math.max(1,Math.min(total,Number(planStartOpen[project.id]?.count) || request?.frames || Math.min(3,total)));
  const head=document.createElement('div');head.className='plan-start-head';
  head.innerHTML='<div><h2>Скільки кадрів створити зараз</h2><p>Почніть з кількох кадрів, перегляньте їх і продовжуйте, коли все подобається. Вибрані кадри підсвічені на таймлайні.</p></div>';
  const readout=document.createElement('div');readout.className='plan-start-readout';readout.setAttribute('aria-live','polite');head.append(readout);
  const slider=document.createElement('input');slider.type='range';slider.min='1';slider.max=String(total);slider.step='1';slider.className='plan-start-range';slider.setAttribute('aria-label','Кількість перших кадрів');
  const quick=document.createElement('div');quick.className='plan-start-quick';
  const presets=[...new Set([1,3,5,10].filter(value=>value<total)),total];
  const chips=presets.map(value=>{const chip=document.createElement('button');chip.type='button';chip.className='plan-start-chip';chip.textContent=value===total?`Усі ${total}`:String(value);chip.addEventListener('click',()=>update(value));quick.append(chip);return [value,chip];});
  const actions=document.createElement('div');actions.className='plan-start-actions';
  const cancel=document.createElement('button');cancel.type='button';cancel.className='secondary';cancel.textContent='Скасувати';
  const start=document.createElement('button');start.type='button';start.className='primary';
  actions.append(cancel,start);
  section.append(head,slider,quick,actions);
  function update(value){
    count=Math.max(1,Math.min(total,Number(value)));slider.value=String(count);
    planStartOpen[project.id]={count};
    const end=Number(frames[count-1].end),all=Number(frames[total-1].end);
    readout.innerHTML=`<strong>${count}</strong> ${planFrameWord(count)} з ${total}<span>${clock(end)} з ${clock(all)}</span>`;
    slider.style.setProperty('--fill',`${total>1?(count-1)/(total-1)*100:100}%`);
    for(const [preset,chip] of chips)chip.classList.toggle('active',preset===count);
    start.textContent=`Створити ${count} ${planFrameWord(count)}`;
    if(!section.hidden)getTimeline()?.selectFrames(count);
  }
  slider.addEventListener('input',()=>update(slider.value));
  cancel.addEventListener('click',()=>{delete planStartOpen[project.id];section.hidden=true;getTimeline()?.selectFrames(0);});
  start.addEventListener('click',async()=>{
    start.disabled=true;
    try{
      const result=await api(`/api/projects/${encodeURIComponent(project.id)}/production-request`,'POST',{frames:count});
      state.project=result.project;delete planStartOpen[project.id];
      status(`Запит надіслано агенту: кадри 1–${count}.`);renderPlan();
    }catch(error){start.disabled=false;status(error.message,true);}
  });
  section.open=()=>{planStartOpen[project.id]={count};section.hidden=false;update(count);section.scrollIntoView({block:'nearest',behavior:'smooth'});};
  update(count);
}

const planEstimateCache=new WeakMap();
function renderPlanCostEstimate(panel,plan,projectId){
  const section=document.createElement('section');section.className='plan-cost-estimate';section.setAttribute('aria-label','Попередня оцінка витрат');
  const heading=document.createElement('h2');heading.textContent='Орієнтовна вартість';
  const content=document.createElement('div');content.setAttribute('aria-live','polite');content.textContent='Завантажуємо тарифи...';section.append(heading,content);panel.append(section);
  let request=planEstimateCache.get(plan);
  if(!request){request=api(`/api/projects/${encodeURIComponent(projectId)}/plan/cost-estimate`).then(result=>({estimate:result.estimate})).catch(error=>({error:error.message}));planEstimateCache.set(plan,request);}
  request.then(result=>{
    if(!section.isConnected)return;
    content.replaceChildren();
    if(result.error){const message=document.createElement('p');message.textContent=`Оцінка недоступна: ${result.error}`;content.append(message);const retry=document.createElement('button');retry.type='button';retry.className='secondary';retry.textContent='Спробувати ще раз';retry.addEventListener('click',()=>{planEstimateCache.delete(plan);if(state.plan===plan)renderPlan();});content.append(retry);return;}
    const e=result.estimate,price=value=>'$'+Number(value).toFixed(3),range=(a,b)=>Math.abs(a-b)<.000001?price(a):`${price(a)} - ${price(b)}`;
    const total=document.createElement('p');total.className='plan-cost-total';total.textContent=`Розрахунковий приклад: ${range(e.subtotal_min_usd,e.subtotal_max_usd)}`;
    const details=document.createElement('p');details.textContent=`DeepSeek: ${range(e.agent_min_usd,e.agent_max_usd)}; зображення: ${price(e.images_usd)} (${e.image_count} шт. × ${price(e.image_price_usd)}).`;
    const assumptions=document.createElement('p');assumptions.className='plan-cost-note';assumptions.textContent=`Припущення: один запит DeepSeek на кожен кадр, ${e.input_tokens_per_frame} вхідних і ${e.output_tokens_per_frame} вихідних токенів; одне зображення FLUX.3 Image Klein 1K на кожен кадр формату «Створене фото». Фактична кількість запитів, моделі та ціни можуть відрізнятися.`;
    const limitations=document.createElement('p');limitations.className='plan-cost-note';limitations.textContent=`Це приклад для FLUX.3; наразі агент створює картинки через GPT Image 1 Mini, тому фактична ціна буде іншою. У суму не входять повторні спроби, додаткові PNG, стоки, озвучка та створене відео${e.generated_video_count?` (${e.generated_video_count} ${planFrameWord(e.generated_video_count)} у плані)`:''}. Повна вартість ролика поки невідома.`;
    const actual=document.createElement('p');actual.className='plan-cost-note';actual.textContent=e.actual.request_count?`Витрати агента, зафіксовані в студії: ${price(e.actual.known_total_usd)}${e.actual.unknown_count?`; без суми для ${e.actual.unknown_count} запитів`:''}.`:'Витрат агента в студії ще не зафіксовано.';
    content.append(total,details,assumptions,limitations,actual);
  });
}

function renderPlan(){
  $('view-plan').classList.toggle('active',state.view==='plan');
  $('view-editor').classList.toggle('active',state.view==='editor');
  $('view-agent').classList.toggle('active',state.view==='agent');
  $('view-plan').setAttribute('aria-pressed',String(state.view==='plan'));
  $('view-editor').setAttribute('aria-pressed',String(state.view==='editor'));
  $('view-agent').setAttribute('aria-pressed',String(state.view==='agent'));
  const panel=$('project-plan');panel.replaceChildren();
  if(!state.project || state.view!=='plan')return;
  if(!state.plan?.frames?.length){renderVoiceStart(panel);return;}
  if(typeof directorAwaited==='function' && directorAwaited()){renderDirectorWait(panel);return;}
  const heading=document.createElement('div');heading.className='plan-heading';
  heading.innerHTML='<div class="plan-heading-label"><h1>План ролика</h1></div>';
  const actions=document.createElement('div');actions.className='plan-actions';
  const director=isDirectorPlan(state.plan),startSection=document.createElement('section');
  if(director){
    // An animated film: the director owns the frames, so the author starts production instead of rebuilding the plan.
    const begin=document.createElement('button');begin.type='button';begin.className='primary plan-start-button';begin.textContent='Почати створення відео';
    begin.disabled=!state.project.production?.plan_ready;if(begin.disabled)begin.title='Спершу додайте озвучку';
    begin.addEventListener('click',()=>startSection.open?.());actions.append(begin);
  }else{
    const build=document.createElement('button');build.type='button';build.className='primary';build.textContent='Перегенерувати план';build.addEventListener('click',openPlanBuilder);actions.append(build);
  }
  heading.append(actions);panel.append(heading);
  const frames=state.plan?.frames;
  if(state.planSettingsMatch===false){const warning=document.createElement('p');warning.className='plan-settings-warning';warning.setAttribute('role','status');warning.textContent='Збережені налаштування змінилися після створення цієї карти. Перегенеруйте план, щоб застосувати їх.';panel.append(warning);}
  const synced=state.project.production?.plan_ready;
  const stage=document.createElement('span');stage.className='plan-stage-tag '+(synced?'audio-synced':'draft');stage.textContent=synced?'За озвучкою':'Чернетка';stage.title=synced?'Кадри прив’язані до фраз готової озвучки':state.project.production?.reason || 'Час приблизний';heading.querySelector('.plan-heading-label').append(stage);
  const names=planFormatNames;
  const total=Math.max(...frames.map(frame=>Number(frame.end))),amounts={};
  for(const frame of frames)amounts[frame.format]=(amounts[frame.format] || 0)+Number(frame.end)-Number(frame.start);
  const covered=Object.values(amounts).reduce((sum,value)=>sum+value,0);
  const shares=Object.entries(amounts).map(([format,amount])=>({format,exact:amount/covered*1000,units:Math.floor(amount/covered*1000)}));
  const remainder=1000-shares.reduce((sum,item)=>sum+item.units,0);
  [...shares].sort((a,b)=>(b.exact-b.units)-(a.exact-a.units)).slice(0,remainder).forEach(item=>item.units++);
  const summary=document.createElement('div');summary.className='plan-summary';summary.innerHTML=`<span><strong>${frames.length}</strong> ${planFrameWord(frames.length)}</span><span><strong>${synced?planClock(total):clock(total)}</strong> ${synced?'тривалість озвучки':'орієнтовна тривалість'}</span>`;
  const request=director?state.project.production_request:null;
  if(request){const sent=document.createElement('span');sent.className='plan-request-tag';sent.textContent=`Запит агенту: кадри 1–${request.frames} · ${clock(request.end)} · ${request.status==='requested'?'очікує':request.status}`;summary.append(sent);}
  const bind=document.createElement('button');bind.type='button';bind.className='secondary plan-bind-audio';bind.textContent='Додати озвучку / таймінги';bind.addEventListener('click',openNarrationBinding);summary.append(bind);panel.append(summary);
  if(state.plan.director_stale){const warning=document.createElement('p');warning.className='plan-settings-warning';warning.setAttribute('role','status');warning.textContent='Сценарій змінився після режисури. Режисер має заново розбити кадри, перш ніж починати створення.';panel.append(warning);}
  renderPlanCostEstimate(panel,state.plan,state.project.id);
  if(typeof renderSpeechReport==='function')renderSpeechReport(panel);
  if(typeof renderDirectorStatus==='function')renderDirectorStatus(panel);
  const formats=document.createElement('div');formats.className='plan-formats';
  const formatButtons=[];
  for(const {format,units} of shares){
    const item=document.createElement('button');item.type='button';item.className='plan-format-chip';item.dataset.format=format;
    item.setAttribute('aria-pressed','false');
    const symbol=document.createElement('b');symbol.className='plan-format-symbol';symbol.dataset.format=format;symbol.setAttribute('aria-hidden','true');
    symbol.style.setProperty('--format-color',planFormatVisuals[format]?.color || '#b8bec9');
    symbol.textContent=planFormatVisuals[format]?.symbol || '•';
    item.append(symbol,document.createTextNode(`${names[format] || format}: ${(units/10).toFixed(1)}%`));
    formats.append(item);formatButtons.push(item);
  }
  panel.append(formats);
  let timeline=null;
  if(director&&synced){panel.append(startSection);renderProductionStart(startSection,frames,()=>timeline);}
  timeline=renderPlanTimeline(panel,frames,shares,names,total,formatButtons);
  if(director&&synced&&!startSection.hidden)timeline?.selectFrames(Number(planStartOpen[state.project.id]?.count) || 0);
  if(state.plan.settings_snapshot){
    const settings=document.createElement('p');settings.className='plan-note';
    const snapshot=state.plan.settings_snapshot;
    settings.textContent=(state.plan.settings_scope==='project'?'Пропорції цього проєкту: ':'Налаштування каналу для цієї карти: ')+Object.entries(snapshot.weights).filter(([,value])=>value>0).map(([key,value])=>`${names[key] || key} ${value}%`).join(' · ')+`. Початок: ${snapshot.first_clip_format && snapshot.first_clip_format!=='auto' ? (names[snapshot.first_clip_format] || (snapshot.first_clip_format==='video'?'відео':snapshot.first_clip_format)) + ', ' + (snapshot.first_clip_count || 1) + ' кадрів' : (snapshot.first_clip_format==='auto' ? 'автоматично' : 'за попередніми налаштуваннями')}. Перший кадр: ${snapshot.first_clip_seconds>0?snapshot.first_clip_seconds+' с':'тривалість за загальним планом'}. Фактичні частки показані вище.`;
    panel.append(settings);
  }
  const note=document.createElement('p');note.className='plan-note';note.textContent='План збережений у цьому проєкті. Типи кадрів, зокрема текстові тези, перевіряються за змістом перед монтажем. Погодження та зміни обговорюються в ChatGPT.';panel.append(note);
  const script=typeof state.plan.script==='string'?state.plan.script:frames.map(frame=>(frame.sentences || []).join(' ')).join('\n\n');
  if(script.trim()){
    const section=document.createElement('details');section.className='plan-script';
    const summary=document.createElement('summary');summary.textContent='Сценарій';
    const text=document.createElement('div');text.className='plan-script-text';text.textContent=script;section.append(summary,text);panel.append(section);
  }
  const table=document.createElement('table');table.className='plan-table';table.innerHTML='<thead><tr><th scope="col">Кадр і час</th><th scope="col">Формат</th><th scope="col">Репліка й задум кадру</th></tr></thead>';
  const body=document.createElement('tbody');
  frames.forEach((frame,index)=>{
    const row=document.createElement('tr');const speech=planFrameSpeech(frame);
    const visual=frame.visual || frame.description || frame.notes || '';
    const phraseItems=frame.continuation?[frame.continuation,...(frame.sentence_timings || [])]:(frame.sentence_timings || []);
    const phrases=synced?phraseItems.map(phrase=>`<li><time>${planClock(phrase.start)} - ${planClock(phrase.end)}</time> ${esc(phrase.text)}</li>`).join(''):'';
    row.innerHTML=`<td><strong>${esc(frame.number ?? index+1)}</strong><span>${planClock(frame.start)} - ${planClock(frame.end)}</span><small>${Number((Number(frame.end)-Number(frame.start)).toFixed(3))} с</small></td><td>${esc(names[frame.format] || frame.format)}</td><td><p>${esc(speech)}</p>${phrases?`<details class="plan-phrases"><summary>Час кожної фрази</summary><ul>${phrases}</ul></details>`:''}${visual?`<small>${esc(visual)}</small>`:''}</td>`;body.append(row);
  });
  table.append(body);
  // Once the frames follow the voice the table is reference: it opens on demand instead of filling the page.
  if(synced){const fold=document.createElement('details');fold.className='plan-table-fold';const label=document.createElement('summary');label.textContent=`Таблиця кадрів (${frames.length})`;fold.append(label,table);panel.append(fold);}
  else panel.append(table);
}

$('view-plan').addEventListener('click',()=>setProjectView('plan'));
$('view-editor').addEventListener('click',()=>setProjectView('editor'));
$('view-agent').addEventListener('click',()=>setProjectView('agent'));
