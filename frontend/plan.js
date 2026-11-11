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

function scriptWordCount(text){return (String(text||'').match(/\p{L}+(?:['’]\p{L}+)*/gu)||[]).length;}
function updateScriptWordCount(panel,text){
  const count=panel.querySelector('.script-word-count') || panel.parentElement?.querySelector('.script-word-count');
  if(count){const n=scriptWordCount(text),last=n%10,lastTwo=n%100;const word=last===1&&lastTwo!==11?'слово':last>=2&&last<=4&&(lastTwo<12||lastTwo>14)?'слова':'слів';count.textContent=n.toLocaleString('uk-UA')+' '+word;}
}

const voiceScriptDraft={};
function narrationScriptValue(project,plan=null,job=null){
  const working=typeof scriptDraftValue==='function'?scriptDraftValue(project):undefined;
  if(working!==undefined)return working;
  if(voiceScriptDraft[project.id]!==undefined)return voiceScriptDraft[project.id];
  const saved=project.voice_script;
  if(typeof job?.script==='string'&&job.started_at>(saved?.saved_at||0)&&job.started_at>=(project.restarted_at||0))return job.script;
  return saved?.text??plan?.script??job?.script??'';
}
const createVideoIcon='<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="m4 20 11-11 3 3L7 23zM12 12l3 3M5 3v4M3 5h4M19 2v4M17 4h4M20 16v4M18 18h4"/></svg>';
function videoCreationCopy(){return directMontage()?{label:'Розпізнати аудіо',note:'Натисніть, щоб студія розпізнала аудіо й зберегла текст із таймінгами.'}:{label:'Створити відео',note:''};}
async function startVideoCreation(pid,payload){
  if(directMontage())return api(`/api/projects/${pid}/plan/analyze`,'POST',payload);
  const capabilities=await api('/api/health');
  if(!capabilities.create_video)throw new Error('Створення відео одним кроком стане доступним після безпечного перезапуску студії. Поточна робота продовжується.');
  return api(`/api/projects/${pid}/create-video`,'POST',payload);
}
function narrationInitialMode(data,profile,script=''){
  if(['queued','running','cancelling'].includes(data.job?.status))return 'script';
  if(data.job?.status==='done'&&data.job.asset_id)return data.source || 'script';
  if(profile&&!channelVoiceAvailable(profile))return 'file';
  return data.source || (String(script || data.job?.script || '').trim()?'script':null);
}
function narrationChoices(panel,ready,restore=true){
  const choices=document.createElement('div');choices.className='narration-choices';
  choices.innerHTML=`<button type="button" class="secondary narration-from-text"><span class="narration-choice-art narration-service-marks" aria-hidden="true">${['elevenlabs','heygen','fishaudio'].map(key=>`<span title="${{elevenlabs:'ElevenLabs',heygen:'HeyGen',fishaudio:'Fish Audio'}[key]}">${projectCostIcons[key]}</span>`).join('')}</span><span class="narration-choice-copy"><strong>Озвучити сценарій</strong><small>Створити голос із тексту</small></span></button><button type="button" class="secondary narration-from-file"><span class="narration-choice-art" aria-hidden="true"><svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21V4m-6 6 6-6 6 6M5 21v7h22v-7"/></svg></span><span class="narration-choice-copy"><strong>Завантажити озвучку</strong><small>Готове аудіо або відео</small></span></button>`;
  const buttons=choices.querySelectorAll('button'),pid=state.project.id;let selectionVersion=0;
  function showSelection(index){
    choices.classList.add('has-selection');
    buttons.forEach((button,i)=>{button.classList.toggle('selected',i===index);button.setAttribute('aria-pressed',String(i===index));});
    ready(index===1);
  }
  async function choose(index){
    selectionVersion++;
    try{await api(`/api/projects/${pid}/narration/source`,'POST',{source:index===1?'file':'script'});}catch(error){status(error.message,true);return;}
    if(choices.isConnected&&state.project?.id===pid)showSelection(index);
  }
  buttons.forEach((button,index)=>{button.setAttribute('aria-pressed','false');button.onclick=()=>choose(index);});
  panel.append(choices);
  let restoredChoice=null;
  const inferChoice=()=>{if(!restoredChoice||selectionVersion||choices.classList.contains('has-selection'))return;const [data,profile]=restoredChoice;const mode=narrationInitialMode(data,profile,panel.querySelector('textarea')?.value||'');if(mode)showSelection(mode==='file'?1:0);};
  panel.querySelector('textarea')?.addEventListener('input',inferChoice);
  if(restore)Promise.all([api(`/api/projects/${pid}/narration`),api(`/api/channels/${state.project.channel_id}/voice-lab`).catch(()=>null)]).then(([data,profile])=>{
    if(!choices.isConnected||state.project?.id!==pid||selectionVersion)return;
    restoredChoice=[data,profile];
    const running=['queued','running','cancelling'].includes(data.job?.status);
    const mode=narrationInitialMode(data,profile,panel.querySelector('textarea')?.value ?? state.project.voice_script?.text ?? state.plan?.script);
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
      ready.querySelectorAll('.narration-settings,.narration-plan-action').forEach(control=>control.disabled=false);
      const plan=ready.querySelector('.narration-plan-action');
      plan.disabled=false;
      const text=panel.querySelector('textarea') || panel.parentElement?.querySelector('.narration-script textarea');if(text)text.readOnly=false;
      const choices=panel.parentElement?.querySelector('.narration-choices');if(choices)choices.hidden=false;
    }
    if(job?.project_id===pid){
      const note=panel.querySelector('.narration-status-row p'),report=state.analysis?.report;
      if(note&&job.status==='failed')note.textContent=job.error||'Не вдалося розпізнати озвучку';
      else if(note&&job.status==='complete'&&report?.applied)note.textContent='';
      else if(note&&job.status==='complete'&&report&&!report.applied){
        const blocking=['missing_boundary','uncertain_boundary','missing_speech','repeated_speech','out_of_order',...(!report.sequence_verification?['low_phrase_match','number_difference']:[])];
        const phrases=(report.phrases||[]).filter(row=>(row.issues||[]).some(issue=>blocking.includes(issue))).map(row=>row.number);
        if(report.status==='needs_review')note.textContent=phrases.length?'Потрібно уточнити розпізнавання · фрази '+phrases.slice(0,8).join(', '):'Потрібно уточнити порядок речень в озвучці';
        else if(report.status==='script_changed')note.textContent='Сценарій змінився. Повторіть перевірку озвучки.';
        else if(report.status==='source_changed')note.textContent='Аудіо змінилося. Повторіть перевірку озвучки.';
      }
    }
    return false;
  }
  const stage=speechStageNames[job.stage]||'Розпізнаємо озвучку',percent=Number.isFinite(job.progress)?` · ${Math.round(job.progress)}%`:'';
  ready.setAttribute('aria-busy','true');
  ready.querySelector('.narration-ready-heading strong').innerHTML=`${exportSpinner} Whisper · ${esc(stage)}${percent}`;
  ready.querySelectorAll('.narration-settings,.narration-plan-action').forEach(control=>control.disabled=true);
  const note=panel.querySelector('.narration-status-row p');if(note)note.textContent='';
  const text=panel.querySelector('textarea') || panel.parentElement?.querySelector('.narration-script textarea');if(text)text.readOnly=true;
  const choices=panel.parentElement?.querySelector('.narration-choices');if(choices)choices.hidden=true;
  return true;
}
function narrationSpeedPreview(duration,currentSpeed,nextPercent){
  const seconds=Math.max(0,Number(duration)||0),speed=Number(currentSpeed)||1,next=Number(nextPercent)/100;
  const result=seconds*speed/next;
  return {duration:result,delta:result-seconds};
}
function openNarrationSpeed(pid,job,ready,refresh){
  const current=Math.round((job.speed||1)*100),asset=state.project?.assets?.find(item=>item.id===job.asset_id);
  const duration=Number(job.duration || asset?.duration || ready.querySelector('audio')?.duration)||0;
  ready.querySelector('audio')?.pause();
  modal('Налаштування озвучки',`<div class="narration-speed-settings voice-local-settings"><label for="narration-speed-range">Швидкість <output id="narration-speed-value">${current}%</output></label>${voiceTempoRange("narration-speed-range",current)}<p id="narration-speed-summary" aria-live="polite"></p>${voiceReverbControls(job.reverb,job.room_noise)}<div class="voice-local-preview"></div><p id="narration-speed-error" role="status"></p></div>`,[{label:'Застосувати',primary:true,run:async()=>{
    const range=$('narration-speed-range'),apply=$('modal-actions').querySelector('.primary');
    apply.disabled=true;range.disabled=true;apply.textContent='Змінюємо…';
    $('modal-body').querySelectorAll('[data-reverb],[data-noise]').forEach(control=>control.disabled=true);
    const plan=ready.querySelector('.narration-plan-action'),settings=ready.querySelector('.narration-settings');plan.disabled=true;settings.disabled=true;
    try{
      await api(`/api/projects/${pid}/narration/speed`,'POST',{speed:Number(range.value)/100,reverb:readVoiceReverb($('modal-body')),room_noise:readVoiceNoise($('modal-body'))});
      if($('narration-speed-range')===range)closeModal();
      if(ready.isConnected&&state.project?.id===pid){ready.remove();await refresh();}
    }catch(error){
      if($('narration-speed-range')===range){$('narration-speed-error').textContent=error.message;apply.disabled=false;range.disabled=false;apply.textContent='Застосувати';$('modal-body').querySelectorAll('[data-reverb],[data-noise]').forEach(control=>control.disabled=false);}
      plan.disabled=false;settings.disabled=false;
    }
  }}]);
  const range=$('narration-speed-range'),apply=$('modal-actions').querySelector('.primary');
  const box=$('modal-body'),player=voicePlayer(null,`/api/projects/${pid}/narration/original`,{playLabel:'Прослухати налаштування озвучки'});
  box.querySelector('.voice-local-preview').append(player);
  const failed=error=>{$('narration-speed-error').textContent=error.message;};
  const previewAudio=attachVoiceEffects(player.querySelector('audio'),()=>readVoiceReverb(box),job.local_preview_tempo?()=>1:()=>Number(range.value)/100/(job.original_speed||job.speed||1),failed,()=>readVoiceNoise(box),job.local_effects_version??2);
  const previewTempo=job.local_preview_tempo?attachVoiceTempo(player.querySelector('audio'),`/api/projects/${pid}/narration/original`,()=>Number(range.value)/100,failed):null;
  const noisePreview=bindVoiceNoisePreview(box,error=>{$('narration-speed-error').textContent=error.message;},job.local_effects_version??2);
  box.channelSettingsCleanup=()=>{previewTempo?.dispose();previewAudio.dispose();noisePreview.dispose();box.channelSettingsCleanup=null;};
  const update=()=>{
    const effect=syncVoiceReverb(box),speedChanged=Number(range.value)!==current,preview=narrationSpeedPreview(duration,job.speed||1,range.value),changed=!!job.audio_processing_stale||speedChanged||voiceReverbKey(effect)!==voiceReverbKey(job.reverb)||voiceNoiseKey(readVoiceNoise(box))!==voiceNoiseKey(job.room_noise);
    $('narration-speed-value').textContent=range.value+'%';apply.disabled=!changed;
    $('narration-speed-summary').textContent=speedChanged?`${clock(Math.floor(duration))} → ≈ ${clock(Math.round(preview.duration))} · на ${Math.round(Math.abs(preview.delta))} с ${preview.delta>0?'довше':'коротше'}`:`Тривалість ${clock(Math.floor(duration))}`;
    previewAudio.update();previewTempo?.update();
  };
  range.addEventListener('input',update);box.querySelectorAll('[data-reverb],[data-noise]').forEach(control=>control.addEventListener('input',update));update();
}
function appendReadyNarration(panel,pid,job,info,refresh){
  const ready=document.createElement('section');ready.className='narration-ready';
  ready.voicedScript=job.script||'';ready.dataset.asset=job.asset_id||'';
  const cost=job.estimated_usd===0?'Безкоштовно':job.estimated_usd!=null?`≈ $${job.estimated_usd.toFixed(3)}`:'';
  ready.innerHTML=`<header class="narration-ready-heading"><strong><span aria-hidden="true">✓</span> Озвучка готова</strong><div class="narration-ready-tools"><small>${esc(cost)}</small><button type="button" class="narration-settings" title="Налаштування озвучки" aria-label="Налаштування озвучки">${$('overview-channel-settings').innerHTML}</button></div></header>`;
  const headline=ready.querySelector('strong');
  const note=message=>{info.textContent=message;headline.textContent=message;};
  ready.append(voicePlayer(null,`/api/projects/${pid}/assets/${job.asset_id}/file`,{duration:job.duration,playLabel:'Прослухати готову озвучку'}));
  const copy=videoCreationCopy(),plan=document.createElement('button');plan.type='button';plan.className='secondary narration-plan-action';plan.innerHTML=createVideoIcon+`<span>${copy.label}</span>`;
  plan.onclick=async()=>{plan.disabled=true;try{await startVideoCreation(pid,{asset_id:job.asset_id,script:job.script});await selectProject(pid,{view:'plan'});}catch(error){note(error.message);plan.disabled=false;}};
  ready.querySelector('.narration-settings').onclick=()=>openNarrationSpeed(pid,job,ready,refresh);
  const actions=document.createElement('footer');actions.className='narration-ready-actions';
  const description=document.createElement('p');description.className='narration-create-note';description.textContent=copy.note;if(copy.note)actions.append(description);actions.append(plan);
  ready.append(actions);panel.classList.add('has-ready-narration');panel.append(ready);renderNarrationAnalysis(panel,pid);return ready;
}
function channelVoiceAvailable(profile){
  const settings=profile?.settings||{};
  return !!voiceLabVoiceId(settings)||(settings.provider!=='heygen'&&!!profile?.reference);
}

function renderNarrationGeneration(panel,scriptInput=null){
  const pid=state.project.id;const box=document.createElement('section');box.className='narration-generation';
  box.innerHTML=`${scriptInput?'':'<label class="voice-script"><span>Сценарій</span><textarea rows="6" placeholder="Вставте текст для озвучення"></textarea></label>'}<div class="narration-voice-card"><div class="narration-choice-profile">Завантажуємо голос…</div><div class="narration-status-row"><p role="status"></p><button class="secondary narration-action-icon" type="button" aria-label="Згенерувати озвучку" title="Згенерувати озвучку"></button></div></div>`;
  panel.append(box);
  const details=box.querySelector('.narration-choice-profile');
  const cid=state.project.channel_id;let profile=null,currentJob=null,voiceReady=false;
  api(`/api/channels/${cid}/voice-lab`).then(data=>{
    profile=data;voiceReady=channelVoiceAvailable(data);if(currentJob)renderRunning(currentJob);
    if(!details.isConnected)return;details.replaceChildren();
    actionState(busy?currentJob?.status:'idle');updateQuote();
    if(!voiceReady){details.innerHTML='<div class="narration-voice-missing" role="status"><span aria-hidden="true">⚠</span><div><strong>Зразок голосу</strong><small>Немає голосу каналу. Додайте зразок у налаштуваннях каналу.</small></div></div>';return;}
    const settings=data.settings||{},service=settings.provider==='heygen'?'HeyGen':settings.provider==='fishaudio'?'Fish Audio':'ElevenLabs';
    const model=(settings.provider==='heygen'?data.heygen_models:settings.provider==='fishaudio'?data.fish_models:data.models)?.find(x=>x.id===(settings.provider==='heygen'?settings.heygen_model:settings.provider==='fishaudio'?settings.fish_engine:settings.model))?.name || '';
    const heading=document.createElement('div');heading.className='narration-voice-heading';details.append(heading);
    const summary=document.createElement('small');summary.className='narration-choice-settings';summary.textContent=model.startsWith(service)?model:[service,model].filter(Boolean).join(' · ');heading.append(summary);
    if(data.reference){
      const toggle=document.createElement('button');toggle.type='button';toggle.className='narration-reference-toggle';toggle.setAttribute('aria-expanded','false');toggle.title='Приклад голосу';
      toggle.innerHTML='<span>Голос</span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m8 10 4 4 4-4"/></svg>';
      const sample=document.createElement('div');sample.className='narration-reference';sample.hidden=true;
      toggle.onclick=()=>{
        sample.hidden=!sample.hidden;toggle.setAttribute('aria-expanded',String(!sample.hidden));
        if(!sample.hidden&&!sample.firstChild)sample.append(voicePlayer(null,`/api/channels/${cid}/voice-lab/reference?v=${data.reference.stamp}`,{filename:'Приклад голосу',playLabel:'Прослухати голос каналу'}));
        if(sample.hidden)sample.querySelector('audio')?.pause();
      };
      heading.append(toggle);details.append(sample);
    }
  }).catch(()=>{if(details.isConnected)details.textContent='Не вдалося завантажити налаштування голосу';});
  const text=scriptInput || box.querySelector('textarea'),button=box.querySelector('.narration-action-icon'),info=box.querySelector('.narration-status-row p');
  if(!scriptInput){text.value=narrationScriptValue(state.project,state.plan);if(typeof bindScriptDraft==='function')bindScriptDraft(text,state.project,panel);}
  const estimate=document.createElement('small');estimate.className='narration-cost';box.querySelector('.narration-status-row').append(estimate);
  const count=document.createElement('small');count.className='narration-phrase-count';box.querySelector('.narration-status-row').append(count);
  const progress=document.createElement('div');progress.className='narration-progress-track';progress.setAttribute('role','progressbar');progress.setAttribute('aria-label','Готовність озвучення');progress.setAttribute('aria-valuemin','0');progress.setAttribute('aria-valuemax','100');progress.innerHTML='<span></span>';box.querySelector('.narration-status-row').append(progress);
  let quoteTimer=null,quoteVersion=0;
  const priceLabel=q=>{if(q.estimated_usd===0)return 'Безкоштовно';const usd=q.estimated_usd==null?'вартість у $ недоступна':`≈ $${q.estimated_usd.toFixed(3)}`;return q.estimated_credits==null?usd:`≈ ${q.estimated_credits.toLocaleString('uk-UA')} кредитів · ${usd}`;};
  async function updateQuote(){const version=++quoteVersion;if(!voiceReady||box.hidden){estimate.textContent='';return;}if(text.value.trim().length<10){estimate.textContent='Вставте сценарій, щоб побачити вартість';return;}estimate.textContent='Рахуємо вартість…';try{const quote=await api(`/api/projects/${pid}/narration/quote`,'POST',{text:text.value});if(version===quoteVersion&&box.isConnected)estimate.textContent=`${priceLabel(quote)} · ${quote.cached?`із кешу ${quote.cached}/${quote.total}`:quote.total} фраз${quote.tax_included?' · податок 20% включено':''}`;}catch(error){if(version===quoteVersion)estimate.textContent=error.message;}}
  text.oninput=()=>{box.classList.remove('has-ready-narration');const ready=box.querySelector('.narration-ready');if(ready)ready.hidden=text.value.trim()!==(ready.voicedScript||'').trim();button.hidden=false;voiceScriptDraft[pid]=text.value;quoteVersion++;clearTimeout(quoteTimer);actionState();estimate.textContent=voiceReady?'Оновлюємо оцінку…':'';quoteTimer=setTimeout(updateQuote,500);};
  updateScriptWordCount(panel,text.value);
  text.addEventListener('input',()=>updateScriptWordCount(panel,text.value));
  updateQuote();
  let busy=false;
  function actionState(mode='idle'){
    const running=mode==='running'||mode==='queued',waiting=mode==='cancelling';
    const label=waiting?'Зупиняємо озвучення':mode==='queued'?'Зняти з черги':running?'Зупинити озвучення':'Озвучити сценарій';
    box.querySelector('.narration-status-row').hidden=!running&&!waiting&&!voiceReady;
    button.hidden=false;button.setAttribute('aria-label',label);button.title=label;button.disabled=waiting||(!running&&(!voiceReady||text.value.trim().length<10));
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
    const queued=job.status==='queued',label=queued?`HeyGen · у черзі${job.queue_position?' · '+job.queue_position:''}`:job.status==='cancelling'?'Зупиняємо':'Озвучуємо';
    info.innerHTML=`<span class="narration-engine">${esc([service,model].filter(Boolean).join(' · '))}</span><span class="narration-progress-title">${exportSpinner}<strong>${esc(label)}</strong>${queued?'':`<b>${percent}%</b>`}</span>`;
    count.textContent=queued?'Очікуємо завершення попереднього проєкту':`${job.completed||0} із ${job.total||0} фраз`;
    progress.setAttribute('aria-valuenow',String(percent));progress.firstElementChild.style.width=percent+'%';
    estimate.textContent=job.estimated_usd===0?'Безкоштовно':priceLabel(job);
  }
  actionState();
  let narrationPollTimer=null,narrationPolling=false,narrationPollVersion=0;
  const narrationConnected=()=>box.isConnected&&state.project?.id===pid;
  const scheduleNarrationPoll=(delay=1500)=>{clearTimeout(narrationPollTimer);if(narrationConnected())narrationPollTimer=setTimeout(poll,delay);};
  async function poll(){
    if(!narrationConnected())return;
    if(narrationPolling){scheduleNarrationPoll();return;}
    narrationPolling=true;clearTimeout(narrationPollTimer);const version=narrationPollVersion;
    try{const {job}=await api(`/api/projects/${pid}/narration`);
      if(!narrationConnected())return;
      if(version!==narrationPollVersion){scheduleNarrationPoll(0);return;}
      if(['queued','running','cancelling'].includes(job?.status)){
        if(typeof channelActivity!=='undefined')channelActivity.add(state.project.channel_id);
        if(typeof projectActivities!=='undefined')projectActivities.set(pid,{kind:'озвучення сценарію',progress:job.total>0?Math.min(99,Math.floor((job.completed||0)/job.total*100)):0});
        if(!busy&&job.script){text.value=narrationScriptValue(state.project,state.plan,job);updateScriptWordCount(panel,text.value);}
        currentJob=job;busy=true;clearTimeout(quoteTimer);quoteVersion++;actionState(job.status);renderRunning(job);scheduleNarrationPoll();
      }
      else if(narrationResultVisible(job,state.project,busy)){
        busy=false;currentJob=null;actionState();if(voiceScriptDraft[pid]===undefined){text.value=narrationScriptValue(state.project,state.plan,job);updateScriptWordCount(panel,text.value);}button.hidden=text.value.trim()===(job.script||'').trim();estimate.textContent=job.estimated_usd===0?'Безкоштовно':priceLabel(job);info.textContent='Озвучка готова. Прослухайте її перед створенням кадрів.';
        let ready=box.querySelector('.narration-ready');if(ready&&ready.dataset.asset!==job.asset_id){ready.remove();ready=null;}
        ready??=appendReadyNarration(box,pid,job,info,poll);
        ready.hidden=text.value.trim()!==(job.script||'').trim();if(ready.hidden)info.textContent='Сценарій змінено. Озвучте нову версію.';
      }
      else if(job?.status==='cancelled'){busy=false;currentJob=null;actionState();info.textContent='Озвучення зупинено. Готові фрази збережені в кеші.';}
      else if(job?.status==='failed'){busy=false;currentJob=null;actionState();info.textContent=job.error;}
      else{busy=false;currentJob=null;info.textContent='';actionState();}
    }catch(error){if(narrationConnected()){info.textContent=error.message;if(busy)actionState(currentJob?.status||'running');else button.disabled=!voiceReady;if(error.httpStatus!==404)scheduleNarrationPoll(3000);}}
    finally{narrationPolling=false;}
  }
  button.onclick=async()=>{if(busy){narrationPollVersion++;actionState('cancelling');try{await api(`/api/projects/${pid}/narration/cancel`,'POST',{});await poll();}catch(error){info.textContent=error.message;actionState('running');}return;}if(!voiceReady)return;button.disabled=true;text.readOnly=true;narrationPollVersion++;const submittedScript=text.value,submittedProject=state.project;try{
    if(typeof flushScriptDraft==='function')await flushScriptDraft(submittedProject);
    if(!narrationConnected())return;
    const quote=await api(`/api/projects/${pid}/narration/quote`,'POST',{text:submittedScript});
    info.textContent=`Із кешу: ${quote.cached} з ${quote.total} фраз.`;
    const cost=priceLabel(quote);estimate.textContent=cost;
    if(!narrationConnected())return;
    const result=await api(`/api/projects/${pid}/narration/start`,'POST',{text:submittedScript,resume:true});if(!narrationConnected())return;if(result.voice_script){state.project.voice_script=result.voice_script;if(typeof commitScriptDraft==='function')commitScriptDraft(state.project,result.voice_script);}box.querySelector('.narration-ready')?.remove();box.classList.remove('has-ready-narration');busy=true;await poll();
  }catch(error){if(narrationConnected()){info.textContent=error.message;button.disabled=false;text.readOnly=false;scheduleNarrationPoll(0);}}};
  poll();return box;
}
function renderVoiceStart(panel){
  const project=state.project,direct=directMontage();
  const section=document.createElement('section');section.className='voice-start';
  section.innerHTML=`
    <label class="voice-drop"><input type="file" accept="audio/*,video/*,.m4a,.mkv,.aiff,.aif,.flac,.opus" hidden>
      <span class="voice-drop-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 15V4m0 0-4 4m4-4 4 4M5 15v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3"/></svg></span>
      <strong>Перетягніть аудіо сюди</strong><span class="voice-drop-hint">або натисніть, щоб вибрати файл озвучки</span><small>MP3, WAV, M4A, FLAC або відео з голосом</small><b class="voice-drop-file" hidden></b></label>
    <label class="voice-script narration-script"><span class="sr-only">Сценарій</span><textarea rows="3" placeholder="Вставте сценарій або залиште порожнім для розпізнавання аудіо"></textarea></label>
    <div class="voice-start-actions">${videoCreationCopy().note?`<p class="narration-create-note">${videoCreationCopy().note}</p>`:''}<div class="voice-progress" aria-live="polite"></div><button type="button" class="secondary" disabled>${createVideoIcon}<span>${videoCreationCopy().label}</span></button></div>`;
  const scriptLabel=section.querySelector('.narration-script'),text=scriptLabel.querySelector('textarea');
  panel.append(scriptLabel);
  section.hidden=true;let generated=null;
  narrationChoices(panel,upload=>{section.hidden=!upload;if(generated)generated.hidden=upload;if(!upload&&!generated)generated=renderNarrationGeneration(panel,text);});
  panel.append(section);
  const drop=section.querySelector('.voice-drop'),input=drop.querySelector('input'),fileLabel=drop.querySelector('.voice-drop-file');
  const start=section.querySelector('.voice-start-actions button'),progress=section.querySelector('.voice-progress');
  let file=null,busy=false;
  text.value=narrationScriptValue(project,direct?state.plan:null);
  updateScriptWordCount(panel,text.value);
  text.addEventListener('input',()=>{voiceScriptDraft[project.id]=text.value;updateScriptWordCount(panel,text.value);});
  if(typeof bindScriptDraft==='function')bindScriptDraft(text,project,panel);
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
      if(typeof flushScriptDraft==='function')await flushScriptDraft(project);
      if(!section.isConnected||state.project?.id!==project.id)return;
      show('Завантажуємо озвучку…');
      const response=await fetch(`/api/projects/${encodeURIComponent(project.id)}/assets/upload`,{method:'POST',headers:{'Content-Type':'application/octet-stream','X-File-Name':encodeURIComponent(file.name)},body:file});
      const result=await response.json();if(!response.ok)throw new Error(result.error || 'Не вдалося додати файл');
      if(!section.isConnected||state.project?.id!==project.id)return;
      // The saved script of an animated episode goes untouched; only an edited text is sent as the voice text.
      const payload={asset_id:result.asset.id},typed=text.value.trim();if(typed && typed!==(project.voice_script?.text || '').trim())payload.script=typed;
      await startVideoCreation(project.id,payload);await poll();
    }catch(error){lock(false);show(error.message);}
  });
  async function poll(){
    if(!section.isConnected)return;
    let result=await api(`/api/projects/${encodeURIComponent(project.id)}/analysis?compact=1`);
    if(!section.isConnected || state.project?.id!==project.id)return;
    state.analysis=result;
    const job=result.job;if(!job || !section.isConnected)return;
    if(job.status==='failed'){lock(false);show(job.error || 'Обробку зупинено');return;}
    if(job.status==='complete'){
      if(result.report?.applied){if(typeof acceptRecognizedScriptDraft==='function')acceptRecognizedScriptDraft(project.id,result.report,!!file);delete voiceScriptDraft[project.id];status(direct?'Озвучку й розпізнаний текст збережено.':'Озвучку розпізнано, план готовий.');await selectProject(project.id,{view:'plan'});return;}
      lock(false);show('Озвучку розпізнано, але текст не збігся з озвученим. Перевірте звіт нижче.');
      if(result.compact)result=await api(`/api/projects/${encodeURIComponent(project.id)}/analysis`);
      if(section.isConnected&&state.project?.id===project.id&&result.report)appendSpeechReport(section,result.report);return;
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
    api(`/api/projects/${encodeURIComponent(project.id)}/analysis?compact=1`).then(result=>{
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
  if(renderInlineEpisodeDraft(panel))return;
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
  heading.innerHTML='<h1><svg class="narration-heading-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 21v-4a7 7 0 1 1 7-10l2 4h-3v4h-3v6M19 8l2-1M19 12h3M19 16l2 1"/><path d="M13 11h1"/></svg>Сценарій</h1><small class="script-word-count"></small>';
  panel.append(heading);
  if(typeof bindScriptDraftStatus==='function'){bindScriptDraftStatus(heading,state.project);ensureScriptDraft(state.project).catch(()=>{});}
  updateScriptWordCount(panel,voiceScriptDraft[state.project.id] ?? state.project.voice_script?.text ?? state.plan?.script ?? '');

}

function projectAnimated(project=state.project){const kind=project?.project_kind ?? state.channel?.settings?.channel_kind;return kind==='animated';}
