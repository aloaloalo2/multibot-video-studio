// Clips that are frames of the film itself: anything but sound, the channel's logo and plate (groups with the role
// «overlay» and clips titled «Логотип» or «Плашка»), as store.film_clips counts them.
function filmClips(project=state.project){
  const overlay=new Set((project?.scene_groups || []).filter(group=>group.role==='overlay').flatMap(group=>group.clip_ids || []));
  return (project?.tracks || []).flatMap(track=>track.clips || []).filter(clip=>clip.kind!=='audio'&&!overlay.has(clip.id)&&!/Логотип|Плашка/.test(clip.title || ''));
}
// «Монтаж» opens with the first frame of the film on the timeline; until then the plan is the episode's page.
function editorUnlocked(project=state.project){return !!project && filmClips(project).length>0;}
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
  // one page for photo and animated channels (director.js)
  renderEpisode(panel);
}

// The frames of the plan as a table: number and time, format, the spoken words and the idea of the frame.
function planTable(frames,synced){
  const names=planFormatNames;
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
  return table;
}

$('view-plan').addEventListener('click',()=>setProjectView('plan'));
$('view-editor').addEventListener('click',()=>setProjectView('editor'));
$('view-agent').addEventListener('click',()=>setProjectView('agent'));
