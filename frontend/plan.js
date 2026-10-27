async function setProjectView(view){
  if(!state.project)return;
  if(view==='editor' && state.plan && !state.project.production?.plan_ready){status('Монтаж стане доступним після додавання таймінгів готової озвучки.',true);return;}
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
    `<p>Перший кадр завжди має формат відео. Студія збереже попередню версію карти. Після зміни сценарію потрібно оновити таймінги фраз.</p><label>TXT-файл сценарію<input id="plan-script-file" type="file" accept=".txt,text/plain"></label><label>Сценарій<textarea id="plan-script-input" rows="12" placeholder="Вставте готовий сценарій"></textarea></label><label>Орієнтовна тривалість, с<input id="plan-audio-duration" type="number" min="0.1" step="0.001" placeholder="Можна залишити порожнім"></label><label class="check"><input id="plan-own-weights" type="checkbox" ${project.plan_weights?'checked':''}>Власні пропорції для цього проєкту</label><section id="plan-weights-panel" ${project.plan_weights?'':'hidden'}><div class="weights-grid">${formats.map(format=>`<label>${planFormatNames[format]}, %<input data-plan-weight="${format}" type="number" min="0" max="100" step="1" value="${values[format] || 0}"></label>`).join('')}</div><p id="plan-weight-total"></p><button id="plan-normalize-weights" class="secondary" type="button">Привести до 100%</button><p>Налаштування каналу збережуться.</p></section>`,
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

const planFormatNames={stock_video:'Стокове відео',generated_video:'Створене відео',stock_photo:'Стокове фото',generated_photo:'Створене фото',animation:'Анімація',text:'Текстові тези',host:'Ведучий'};
const planZoomByProject={};
function planClock(value){const milliseconds=Math.round(Number(value)*1000);return clock(milliseconds/1000)+(milliseconds%1000?','+String(milliseconds%1000).padStart(3,'0'):'');}

const planFormatVisuals={
  generated_video:{color:'#ffd429',symbol:'▶'},
  stock_video:{color:'#20b6ff',symbol:'▥'},
  generated_photo:{color:'#ff7b24',symbol:'◆'},
  stock_photo:{color:'#2be181',symbol:'●'},
  animation:{color:'#b46cff',symbol:'✦'},
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
      const speech=(frame.sentences || []).join(' ');
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
  for(const {format} of shares)addRow(format,names[format] || format,frames.filter(frame=>frame.format===format));
  timeline.append(detail);panel.append(timeline);
  for(const button of formatButtons){
    const format=button.dataset.format;
    button.addEventListener('mouseenter',()=>highlight(format));
    button.addEventListener('mouseleave',()=>highlight(pinned));
    button.addEventListener('focus',()=>highlight(format));
    button.addEventListener('blur',()=>highlight(pinned));
    button.addEventListener('click',()=>{pinned=pinned===format?null:format;highlight(pinned);});
  }
}

function renderPlan(){
  $('view-plan').classList.toggle('active',state.view==='plan');
  $('view-editor').classList.toggle('active',state.view==='editor');
  $('view-plan').setAttribute('aria-pressed',String(state.view==='plan'));
  $('view-editor').setAttribute('aria-pressed',String(state.view==='editor'));
  const panel=$('project-plan');panel.replaceChildren();
  if(!state.project || state.view!=='plan')return;
  const heading=document.createElement('div');heading.className='plan-heading';
  heading.innerHTML='<div class="plan-heading-label"><h1>План ролика</h1></div>';
  const actions=document.createElement('div');actions.className='plan-actions';
  const build=document.createElement('button');build.type='button';build.className='primary';build.textContent=state.plan?.frames?.length?'Перегенерувати план':'Створити план';build.addEventListener('click',openPlanBuilder);actions.append(build);
  heading.append(actions);panel.append(heading);
  const frames=state.plan?.frames;
  if(!frames?.length){const empty=document.createElement('div');empty.className='overview-empty';empty.textContent=state.planError || 'Додайте готовий сценарій через кнопку «Створити план».';panel.append(empty);return;}
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
  const bind=document.createElement('button');bind.type='button';bind.className='secondary plan-bind-audio';bind.textContent='Додати озвучку / таймінги';bind.addEventListener('click',openNarrationBinding);summary.append(bind);panel.append(summary);
  if(typeof renderSpeechReport==='function')renderSpeechReport(panel);
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
  renderPlanTimeline(panel,frames,shares,names,total,formatButtons);
  if(state.plan.settings_snapshot){
    const settings=document.createElement('p');settings.className='plan-note';
    const snapshot=state.plan.settings_snapshot;
    settings.textContent=(state.plan.settings_scope==='project'?'Пропорції цього проєкту: ':'Налаштування каналу для цієї карти: ')+Object.entries(snapshot.weights).filter(([,value])=>value>0).map(([key,value])=>`${names[key] || key} ${value}%`).join(' · ')+`. Перший кліп: ${snapshot.first_clip_seconds>0?snapshot.first_clip_seconds+' с':'за загальним планом'}. Фактичні частки показані вище.`;
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
    const row=document.createElement('tr');const speech=(frame.sentences || []).join(' ');
    const visual=frame.visual || frame.description || frame.notes || '';
    const phrases=synced?(frame.sentence_timings || []).map(phrase=>`<li><time>${planClock(phrase.start)} - ${planClock(phrase.end)}</time> ${esc(phrase.text)}</li>`).join(''):'';
    row.innerHTML=`<td><strong>${esc(frame.number ?? index+1)}</strong><span>${planClock(frame.start)} - ${planClock(frame.end)}</span><small>${Number((Number(frame.end)-Number(frame.start)).toFixed(3))} с</small></td><td>${esc(names[frame.format] || frame.format)}</td><td><p>${esc(speech)}</p>${phrases?`<details class="plan-phrases"><summary>Час кожної фрази</summary><ul>${phrases}</ul></details>`:''}${visual?`<small>${esc(visual)}</small>`:''}</td>`;body.append(row);
  });
  table.append(body);panel.append(table);
}

$('view-plan').addEventListener('click',()=>setProjectView('plan'));
$('view-editor').addEventListener('click',()=>setProjectView('editor'));
