// One decision point; dispatch keeps the established workflow handlers and guards.
function projectNextAction(model){
  const action=(kind,label,extra={})=>({kind,label,disabled:false,reason:'',...extra});
  if(model.exporting)return action('export',model.exportLabel||'Експорт триває');
  if(model.writing)return action('wait',model.writingLabel||'Пишемо сценарій',{disabled:true});
  if(model.narrating)return action('wait',model.narrationLabel||'Озвучуємо сценарій',{disabled:true});
  if(model.analyzing)return action('wait','Розпізнаємо озвучку',{disabled:true});
  if(model.planning)return action('wait','Режисер планує кадри',{disabled:true});
  if(model.producing)return action('wait','Створюємо кадри',{disabled:true});
  if(model.metadataPending)return action('metadata','Доповнити метадані',{reason:model.draftError||''});
  if(model.hooksPending)return model.hasHooks?action('hook','Обрати зачин'):action('openings','Створити зачини',{reason:model.draftError||''});
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
    return action('frames',model.resume?'Продовжити створення ролика':'Створити відео',{disabled:!model.framesEnabled,reason:model.productionReason||(!model.framesEnabled?'Перевірте озвучку та план кадрів':''),settings:!model.framesEnabled?'montage':null});
  }
  if(!model.script.trim())return action('script','Додати сценарій');
  if(!model.hasScriptField)return action('edit','Переглянути правки',{reason:model.pendingScript?'Озвучка потребує нової версії сценарію':''});
  if(model.voiceLoading)return action('wait','Завантажуємо голос',{disabled:true});
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
    analyzing:['queued','running'].includes(state.analysis?.job?.status),planning:['queued','running'].includes(direction?.status),producing:['requested','in_progress'].includes(project.production_request?.status),
    direct:directMontage(),hasPictures:filmClips(project).length>0,canExport:!!project.production?.export_ready,
    hasFrames:!!state.plan?.frames?.length,allFrames:!!state.plan?.frames?.length&&madeSet(state.plan.frames).size>=state.plan.frames.length,
    framesEnabled:!!frames&&!frames.disabled&&!make.hidden,resume:project.production_request?.status==='failed'||filmClips(project).length>0,
    productionReason:root.querySelector('.episode-make-hint')?.textContent||project.production?.reason||'',
    fileMode:root.querySelector('.narration-from-file')?.getAttribute('aria-pressed')==='true',hasFile:!!root.querySelector('.voice-drop.has-file'),uploadEnabled:!!upload&&!upload.disabled,
    readyVoice:!!ready&&!ready.hidden&&!ready.closest('[hidden]'),createEnabled:!!ready?.querySelector('.narration-plan-action:not([disabled])'),createReason:root.querySelector('.narration-create-error')?.textContent||'',
    directionRecovery:!!root.querySelector('.episode-director:not([hidden]) button:not([disabled])'),directionRecoveryLabel:root.querySelector('.episode-director button')?.textContent,directionRecoveryReason:direction?.creation_error||direction?.error,
    voiceLoading:voice?.querySelector('.narration-choice-profile')?.textContent==='Завантажуємо голос…',hasVoice:!!voice&&!voice.querySelector('.narration-voice-missing')&&voice.querySelector('.narration-choice-settings'),narrationEnabled:!!narrate&&!narrate.disabled,
  };
  return {model,root,field,targets:{narrate,create:ready?.querySelector('.narration-plan-action'),frames,upload,openings:root.querySelector('#episode-draft-refresh'),metadata:root.querySelector('#episode-draft-metadata'),direction:root.querySelector('.episode-director:not([hidden]) button:not([disabled])')}};
}
function updateProjectNextAction(){
  const box=$('project-next-step');if(!box)return;
  const context=projectNextContext(),visible=!!context&&state.view==='editor';box.hidden=!visible;
  if(!visible){delegatedWorkflowTarget?.classList.remove('workflow-action-target');delegatedWorkflowTarget=null;return;}
  $('export-open').hidden=true;
  const decision=projectNextAction(context.model),button=$('project-next-action'),reason=$('project-next-reason'),settings=$('project-next-settings');
  const key=['hook','openings'].includes(decision.kind)?'hook':['narrate','file'].includes(decision.kind)?'narrate':['create','frames','upload'].includes(decision.kind)?'create':decision.kind==='export'?'export':'script';
  const markup=(decision.kind==='wait'?exportSpinner:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${projectNextIcons[key]}</svg>`)+`<span>${esc(decision.label)}</span>`;
  if(button.innerHTML!==markup)button.innerHTML=markup;
  button.disabled=decision.disabled||projectNextBusy;reason.textContent=decision.reason;reason.title=decision.reason;reason.hidden=!decision.reason;settings.hidden=!decision.settings;
  settings.dataset.section=decision.settings||'';
  const target=context.targets[decision.kind]||null;
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
    new MutationObserver(schedule).observe(root,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['disabled','hidden','class','aria-pressed']});
    root.addEventListener('input',schedule);
  }
}
