// One decision point; dispatch keeps the established workflow handlers and guards.
function projectNextAction(model){
  const action=(kind,label,extra={})=>({kind,label,disabled:false,reason:'',...extra});
  if(model.exporting)return action('export',model.exportLabel||'Експорт триває');
  if(model.writing)return action('wait',model.writingLabel||'Пишемо сценарій',{disabled:true});
  if(model.narrating)return action('wait',model.narrationLabel||'Озвучуємо сценарій',{disabled:true});
  if(model.analyzing)return action('wait','Розпізнаємо озвучку',{disabled:true});
  if(model.planning)return action('wait','Режисер планує кадри',{disabled:true});
  if(model.producing)return action('wait','Створюємо кадри',{disabled:true});
  // Missing titles, description and tags never stand in the way of the voice (user, 14 November 2026): the script block
  // keeps its own «Спробувати ще раз», the main button goes on to the next real step.
  if(model.hooksPending)return model.hasHooks?action('hook','Обрати зачин',{hidden:true}):action('openings','Створити зачини',{reason:model.draftError||''});
  if(model.draftReadError)return action('save','Завантажити сценарій',{reason:model.draftReadError});
  if(model.draftLoading)return action('wait','Завантажуємо чернетку',{disabled:true});
  if(model.canExport&&!model.pendingScript)return action('export','Експорт MP4');
  if(model.directionRecovery&&!model.pendingScript)return action('direction',model.directionRecoveryLabel||'Оновити план кадрів',{reason:model.directionRecoveryReason||''});
  if(model.draftConflict)return action('save','Зберегти мою версію',{reason:'Є інші правки. Попередня версія залишиться в історії.'});
  if(model.draftSaveError)return action('save','Зберегти правки',{reason:model.draftSaveError});
  if(model.direct&&model.hasPictures)return action('export','Експорт MP4',{disabled:!model.canExport,reason:model.productionReason||'',settings:!model.canExport?'voice':null});
  if(model.fileMode)return model.hasFile?action('upload',model.direct?'Розпізнати аудіо':'Створити відео',{disabled:!model.uploadEnabled,reason:model.uploadEnabled?'':'Завантажуємо озвучку'}):action('file','Завантажити озвучку');
  if(model.readyVoice&&!model.pendingScript)return action('create',model.direct?'Розпізнати аудіо':'Створити відео',{disabled:!model.createEnabled,reason:model.createReason||(!model.createEnabled?'Завантажуємо стан випуску':''),settings:!model.createEnabled?'audio':null});
  if(model.direct&&!model.hasPictures)return action('media','Додати матеріали');
  if(model.hasFrames&&!model.pendingScript){
    if(model.allFrames)return action('export','Експорт MP4',{disabled:!model.canExport,reason:model.productionReason||'',settings:!model.canExport?'voice':null});
    // the export's reason («Тривалість монтажу…») is no reason not to make frames: shown only when frames can not start
    return action('frames',model.resume||model.paused?'Продовжити створення ролика':'Створити відео',{disabled:!model.framesEnabled,reason:!model.framesEnabled?(model.productionReason||'Перевірте озвучку та план кадрів'):'',settings:!model.framesEnabled?'montage':null});
  }
  if(!model.script.trim())return action('script','Додати сценарій');
  if(!model.hasScriptField)return action('edit','Переглянути правки',{reason:model.pendingScript?'Озвучка потребує нової версії сценарію':''});
  if(model.voiceLoading)return action('wait','Завантажуємо голос',{disabled:true});
  if(model.voiceError)return action('narrate','Озвучити',{disabled:true,reason:'Не вдалося завантажити налаштування голосу. Повторіть завантаження в блоці озвучення.',settings:'voice'});
  if(!model.hasVoice)return action('narrate','Озвучити',{disabled:true,reason:'Немає голосу каналу',settings:'voice'});
  return action('narrate','Озвучити',{disabled:!model.narrationEnabled,reason:!model.narrationEnabled?'Підготовка озвучки':''});
}
const projectNextIcons={
  hook:'<path d="M9 18h6m-5 3h4M8 14a7 7 0 1 1 8 0l-1 3H9z"/>',
  script:'<path d="M6 3h8l4 4v14H6zM14 3v5h4M9 12h6m-6 4h6"/>',
  narrate:'<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M6 11v1a6 6 0 0 0 12 0v-1M12 18v3M9 21h6"/>',
  create:'<rect x="3" y="4" width="18" height="16" rx="3"/><path d="m10 8 5 4-5 4zM7 4v16M17 4v16"/>',
  export:'<path d="M12 3v12m-4-4 4 4 4-4M4 15v5h16v-5"/>',
};
let delegatedWorkflowTarget=null,projectNextBusy=false;
function heygenVideoEstimate(project, plan, analysis){
  if(directMontage())return '';
  const channel=state.channels.find(item=>item.id===project.channel_id);
  const weights=project.plan_weights||channel?.settings?.weights||{};
  const share=Number(weights.host)||0;
  const autoHost=!project.plan_weights&&channel?.settings?.weights_auto?.includes('host');
  if(share<=0&&!autoHost)return '';
  const source=analysis?.report?.source;
  const audio=plan?.timing?.audio||{};
  const asset=project.assets?.find(item=>item.id===(source?.asset_id||audio.asset_id));
  const drop=document.querySelector('.voice-drop.has-file');
  if(drop?.dataset.mediaKind==='video'||!drop&&(source?.kind==='video'||asset?.kind==='video'))return '';
  const frames=!drop&&plan?.timing?.status==='audio_synced'?plan.frames||[]:[];
  if(!frames.length&&autoHost)return 'HeyGen · ціна після плану';
  let seconds=0;
  if(frames.length){
    const made=madeSet(frames);
    seconds=frames.reduce((sum,frame,index)=>sum+(frame.format==='host'&&!made.has(index)?Math.max(0,Number(frame.end)-Number(frame.start)):0),0);
  }else{
    const player=document.querySelector('.narration-ready audio');
    const duration=Number(drop?.dataset.mediaDuration||audio.duration||asset?.duration||player?.duration)||0;
    seconds=duration*share/100;
  }
  if(!seconds)return '';
  // one price, by the kind of the channel's avatar: $0.60 a minute for a digital twin, $0.99 for a photo or studio
  // avatar (user, 25 November 2026: «одну ціну»); the kind is read once a channel
  const rate=heygenAvatarRate(project.channel_id);
  if(rate===undefined)return '';
  return `HeyGen ≈ $${(seconds*(rate??.99)/60).toFixed(2)}`;
}
var heygenAvatarRates=new Map();   // var: the node tests read it from the context
function heygenAvatarRate(channelId){
  if(heygenAvatarRates.has(channelId))return heygenAvatarRates.get(channelId);
  heygenAvatarRates.set(channelId,undefined);
  api(`/api/channels/${encodeURIComponent(channelId)}/heygen-avatar-rate`)
    .then(data=>{heygenAvatarRates.set(channelId,Number(data.usd_per_minute)||null);updateProjectNextAction();})
    .catch(()=>{heygenAvatarRates.set(channelId,null);updateProjectNextAction();});
  return undefined;
}
function projectNextContext(){
  const project=state.project,root=$('editor-production');
  if(!project||!root)return null;
  const field=root.querySelector('.narration-script textarea,.voice-script textarea'),voice=root.querySelector('.narration-generation'),narrate=voice?.querySelector('.narration-action-icon');
  const ready=root.querySelector('.narration-ready'),make=root.querySelector('.episode-make'),frames=make?.querySelector('.episode-make-start'),upload=root.querySelector('.voice-start-actions button');
  const pending=root.querySelector('.episode-draft-panel')&&state.episodeDraft?.project_id===project.id&&episodeDraftPending(state.episodeDraft)?state.episodeDraft:null;
  const working=scriptDraftEntry(project),accepted=project.voice_script?.text??state.plan?.script??'',script=field?.value??scriptDraftValue(project)??accepted;
  const direction=typeof directorRuns!=='undefined'?directorRuns[project.id]:null;
  const exporting=state.job?.project_id===project.id&&['queued','running','cancelling'].includes(state.job.status);
  const model={
    script,hasScriptField:!!field,pendingScript:!!(working.dirty||working.pending)&&script.trim()!==accepted.trim(),
    draftLoading:!!working.loading,draftReadError:!working.loaded&&working.error,draftConflict:!!working.conflict,draftSaveError:working.dirty&&working.error,
    exporting,exportLabel:$('export-open')?.textContent,
    writing:pending&&['queued','running','cancelling'].includes(pending.status),writingLabel:{openings:'Готуємо зачини',script:'Пишемо сценарій',metadata:'Готуємо метадані'}[pending?.stage],
    hooksPending:!!pending&&!pending.script_saved&&pending.stage!=='metadata',metadataPending:!!pending&&(pending.script_saved||pending.stage==='metadata'),hasHooks:!!root.querySelector('.episode-hook-option:not([disabled])'),draftError:pending?.error,
    narrating:voice?.classList.contains('is-generating'),narrationLabel:voice?.querySelector('.narration-progress-title strong')?.textContent,
    analyzing:['queued','running'].includes(state.analysis?.job?.status)&&!String(state.analysis?.job?.stage||'').startsWith('waiting_'),
    // a recognition done and waiting for the director's plan is the director's work: «Режисер планує кадри»
    planning:['queued','running'].includes(direction?.status)||(['queued','running'].includes(state.analysis?.job?.status)&&String(state.analysis?.job?.stage||'').startsWith('waiting_')),producing:['requested','in_progress'].includes(project.production_request?.status),
    direct:directMontage(),hasPictures:filmClips(project).length>0,canExport:!!project.production?.export_ready,
    hasFrames:!!state.plan?.frames?.length,allFrames:!!state.plan?.frames?.length&&madeSet(state.plan.frames).size>=state.plan.frames.length,
    framesEnabled:!!frames&&!frames.disabled&&!make.hidden,paused:!!project.episode_paused,resume:project.production_request?.status==='failed'||filmClips(project).length>0,
    productionReason:root.querySelector('.episode-make-hint')?.textContent||project.production?.reason||'',
    fileMode:root.querySelector('.narration-from-file')?.getAttribute('aria-pressed')==='true',hasFile:!!root.querySelector('.voice-drop.has-file'),uploadEnabled:!!upload&&!upload.disabled,
    readyVoice:!!ready&&!ready.hidden&&!ready.closest('[hidden]'),createEnabled:!!ready?.querySelector('.narration-plan-action:not([disabled])'),createReason:root.querySelector('.narration-create-error')?.textContent||'',
    directionRecovery:!!root.querySelector('.episode-director:not([hidden]) button:not([disabled])'),directionRecoveryLabel:directionButtonLabel(root.querySelector('.episode-director:not([hidden]) button:not([disabled])')),directionRecoveryReason:direction?.status==='paused'?'Режисер на паузі':direction?.creation_error||direction?.error,
    voiceLoading:voice?.querySelector('.narration-choice-profile')?.textContent==='Завантажуємо голос…',voiceError:voice?.querySelector('.narration-choice-profile')?.dataset.voiceState==='error',hasVoice:!!voice&&!voice.querySelector('.narration-voice-missing')&&voice.querySelector('.narration-choice-settings'),narrationEnabled:!!narrate&&!narrate.disabled,
  };
  return {model,root,field,targets:{narrate,create:ready?.querySelector('.narration-plan-action'),frames,upload,openings:root.querySelector('#episode-draft-refresh'),metadata:root.querySelector('#episode-draft-metadata'),direction:root.querySelector('.episode-director:not([hidden]) button:not([disabled])')}};
}
function updateProjectNextAction(){
  const box=$('project-next-step');if(!box)return;
  // while the voice is made on a plan from the script, the director's line says what waits; the header stays empty
  // (user, 16 November 2026: «удали це» about «Це чернетка. Додайте таймінги…» and a grey «Створити відео»)
  const waitingVoice=state.plan?.timing?.status==='script_estimate';
  const context=projectNextContext(),visible=!!context&&state.view==='editor'&&!waitingVoice;box.hidden=!visible;
  if(!visible){delegatedWorkflowTarget?.classList.remove('workflow-action-target');delegatedWorkflowTarget=null;return;}
  $('export-open').hidden=true;
  const decision=projectNextAction(context.model),button=$('project-next-action'),reason=$('project-next-reason'),settings=$('project-next-settings');
  // the openings are on the page to be picked: no button saying so (user, 16 November 2026: «и так ясно що обрати зачин нада»)
  if(decision.hidden){box.hidden=true;delegatedWorkflowTarget?.classList.remove('workflow-action-target');delegatedWorkflowTarget=null;return;}
  const key=['hook','openings'].includes(decision.kind)?'hook':['narrate','file'].includes(decision.kind)?'narrate':['create','frames','upload'].includes(decision.kind)?'create':decision.kind==='export'?'export':'script';
  const estimate=['create','frames','upload'].includes(decision.kind)&&typeof heygenVideoEstimate==='function'?heygenVideoEstimate(state.project,state.plan,state.analysis):'';
  const markup=(decision.kind==='wait'?exportSpinner:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${projectNextIcons[key]}</svg>`)+`<span>${esc(decision.label)}</span>`;
  // the HeyGen estimate sits on the grey «Створити відео» in the page, not on the gold one in the header (user,
  // 25 November 2026: «в кнопці зеленій… Хейген… це видали і в сіру кнопку засунь»)
  for(const grey of [context.targets.create,context.targets.frames,context.targets.upload]){
    if(!grey?.querySelector)continue;
    let note=grey.querySelector('.heygen-estimate');
    if(!estimate){note?.remove();continue;}
    if(!note){note=document.createElement('small');note.className='heygen-estimate';note.title='Орієнтовно: хвилини кадрів ведучого × тариф Avatar III для типу вашого аватара';grey.append(note);}
    if(note.textContent!==estimate)note.textContent=estimate;
  }
  if(button.innerHTML!==markup)button.innerHTML=markup;
  button.disabled=decision.disabled||projectNextBusy;reason.textContent=decision.reason;reason.title=decision.reason;reason.hidden=!decision.reason;settings.hidden=true;   // the sliders live on the channel's settings button now (user, 16 November 2026)
  settings.dataset.section=decision.settings||'';
  // Keep voice actions beside the file or provider quote as well as in the header.
  // the frames' button stays in «Створення ролика» as well, where the author looks for it (16 November 2026)
  const target=['upload','narrate','frames'].includes(decision.kind)?null:context.targets[decision.kind]||null;
  if(delegatedWorkflowTarget!==target){delegatedWorkflowTarget?.classList.remove('workflow-action-target');delegatedWorkflowTarget=target;target?.classList.add('workflow-action-target');}
  if(!context.root.classList.contains('workflow-guided'))context.root.classList.add('workflow-guided');
}
function focusWorkflowScript(root){
  const field=root.querySelector('textarea');if(field){field.scrollIntoView({block:'center',behavior:'smooth'});field.focus();}
}
async function runProjectNextAction(){
  const context=projectNextContext();if(!context||projectNextBusy)return;
  const decision=projectNextAction(context.model);if(decision.disabled)return;
  projectNextBusy=true;updateProjectNextAction();
  try{
    const target=context.targets[decision.kind];
    if(target){if(!target.disabled)target.click();}
    else if(decision.kind==='export')await openExport();
    else if(decision.kind==='save')await retryScriptDraft(state.project);
    else if(decision.kind==='file')context.root.querySelector('.voice-drop input')?.click();
    else if(decision.kind==='media')$('add-file')?.click();
    else if(decision.kind==='hook'){const hook=context.root.querySelector('.episode-hook-option:not([disabled])');hook?.scrollIntoView({block:'center',behavior:'smooth'});hook?.focus();}
    else if(decision.kind==='script')focusWorkflowScript(context.root);
    else if(decision.kind==='edit'){
      modal('Сценарій','<div class="working-script-editor"></div>');const body=$('modal-body').querySelector('.working-script-editor');
      renderPlanSwitch(body);renderNarrationGeneration(body);focusWorkflowScript(body);
    }
  }catch(error){status(error.message,true);}
  finally{projectNextBusy=false;updateProjectNextAction();}
}
if(typeof document!=='undefined'){
  $('project-next-action')?.addEventListener('click',runProjectNextAction);
  $('project-next-settings')?.addEventListener('click',()=>{const section=$('project-next-settings').dataset.section;if(section==='audio'){openNarrationBinding();return;}const channel=state.channels.find(item=>item.id===state.project?.channel_id);if(!channel)return;openChannelSettings(channel);$(`channel-settings-tab-${section||'voice'}`)?.click();});
  const root=$('editor-production');
  if(root&&typeof MutationObserver!=='undefined'){
    let scheduled=false;
    const schedule=()=>{if(scheduled)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;updateProjectNextAction();});};
    new MutationObserver(schedule).observe(root,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['disabled','hidden','class','aria-pressed','data-voice-state']});
    root.addEventListener('input',schedule);
    root.addEventListener('durationchange',schedule,true);
  }
}
// the round play of a paused director has no words, only its label: the header says what it does («Продовжити режисуру»)
function directionButtonLabel(button){
  return button?(button.textContent.trim()||button.getAttribute('aria-label')||''):'';
}
