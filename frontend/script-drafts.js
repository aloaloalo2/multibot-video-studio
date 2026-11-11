// Working scripts are local first, then saved independently of accepted narration.
const scriptDraftCache=new Map();
const scriptDraftIcon='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 10a9 9 0 1 1 1 7M3 4v6h6M12 7v5l3 2"/></svg>';
function scriptDraftWriter(pid){
  const key='videokey-script-writer:'+pid;let value;
  try{value=sessionStorage.getItem(key);}catch{}
  if(!value){value=typeof crypto!=='undefined'&&crypto.randomUUID?crypto.randomUUID():Date.now().toString(36)+Math.random().toString(36).slice(2);try{sessionStorage.setItem(key,value);}catch{}}
  return value;
}
function scriptDraftLocalKey(entry){return 'videokey-script-draft:'+entry.pid+':'+entry.writer;}
function scriptDraftEntry(project){
  let entry=scriptDraftCache.get(project.id);
  const epoch=project.restarted_at||0;
  if(entry&&entry.epoch!==epoch){clearTimeout(entry.timer);scriptDraftCache.delete(project.id);entry=null;}
  if(entry?.localOnly&&!entry.dirty&&entry.pending&&project.voice_script?.text===entry.text)commitScriptDraft(project,project.voice_script);
  if(entry?.loaded&&project.voice_script?.sha256&&entry.base_sha256!==project.voice_script.sha256&&!entry.dirty&&!entry.pending&&!entry.saving){entry.loaded=false;entry.text=undefined;entry.originalSHA=project.voice_script.sha256;}
  if(!entry){
    entry={pid:project.id,epoch,writer:scriptDraftWriter(project.id),originalSHA:project.voice_script?.sha256,text:undefined,version:null,base_sha256:null,loaded:false,dirty:false,pending:false,sequence:0,fields:new Set(),labels:new Set(),timer:null,retries:0};
    try{
      const legacyKey='videokey-script-draft:'+project.id,own=localStorage.getItem(scriptDraftLocalKey(entry)),legacy=localStorage.getItem(legacyKey),local=JSON.parse(own||legacy||'null');
      if([1,2].includes(local?.format)&&local.epoch===epoch&&typeof local.text==='string'){
        Object.assign(entry,{text:local.text,version:local.version,base_sha256:local.base_sha256,sequence:local.sequence||0,dirty:true,localSaved:true});
        if(!own&&legacy){scriptDraftLocal(entry);if(localStorage.getItem(legacyKey)===legacy)localStorage.removeItem(legacyKey);}
      }
    }catch{}
    scriptDraftCache.set(project.id,entry);
  }
  return entry;
}
function scriptDraftValue(project){const entry=scriptDraftEntry(project);return entry.dirty||entry.pending?entry.text:undefined;}
function scriptDraftLocal(entry){
  try{localStorage.setItem(scriptDraftLocalKey(entry),JSON.stringify({format:2,epoch:entry.epoch,text:entry.text,version:entry.version,base_sha256:entry.base_sha256,sequence:entry.sequence}));entry.localSaved=true;}
  catch{entry.localSaved=false;}
}
function scriptDraftNotify(entry){
  if(typeof voiceScriptDraft!=='undefined'){
    if(entry.dirty||entry.pending)voiceScriptDraft[entry.pid]=entry.text;
    else delete voiceScriptDraft[entry.pid];
  }
  for(const field of entry.fields){
    if(!field.isConnected){entry.fields.delete(field);continue;}
    if(entry.text!==undefined&&field.value!==entry.text){field.value=entry.text;field.dispatchEvent(new Event('input',{bubbles:true}));}
  }
  for(const box of entry.labels){
    if(!box.isConnected){entry.labels.delete(box);continue;}
    const text=entry.conflict?'Конфлікт правок':entry.error?(entry.localSaved?'Збережено в браузері':'Не збережено'):entry.dirty||entry.saving?'Зберігаємо…':entry.localOnly?'Збереження в браузері':entry.loaded?'Збережено':'Завантажуємо…';
    const label=box.querySelector('.script-draft-status');label.textContent=text;label.title=entry.error||'';
    const retry=box.querySelector('.script-draft-retry');retry.hidden=!entry.error;retry.title=entry.conflict?'Зберегти мою версію':'Повторити збереження';retry.setAttribute('aria-label',retry.title);
    box.querySelector('.script-draft-history').hidden=!entry.history_count;
  }
  if(typeof updateProjectNextAction==='function')updateProjectNextAction();
}
async function ensureScriptDraft(project){
  const entry=scriptDraftEntry(project);
  if(entry.loaded)return entry;
  if(entry.loading)return entry.loading;
  entry.loading=(async()=>{
    try{
      const data=await api(`/api/projects/${entry.pid}/script-draft`);
      if(scriptDraftCache.get(entry.pid)!==entry)return entry;
      if(entry.dirty){
        const changedBase=entry.base_sha256&&entry.base_sha256!==data.base_sha256||!entry.base_sha256&&entry.originalSHA&&entry.originalSHA!==data.base_sha256;
        const ownPrevious=data.writer_id===entry.writer&&entry.sequence>(data.client_sequence||0);
        if(data.epoch!==entry.epoch||changedBase||entry.version!==null&&entry.version!==data.version&&entry.text!==data.text&&!ownPrevious){entry.conflict=true;entry.error='Сценарій змінено в іншій вкладці. Збережіть свою версію або перегляньте історію.';}
        else if(entry.text===data.text){entry.dirty=false;entry.pending=data.pending;entry.error=null;try{localStorage.removeItem(scriptDraftLocalKey(entry));}catch{}}
      }else{entry.text=data.text;entry.pending=data.pending;}
      entry.version=data.version;entry.base_sha256=data.base_sha256;entry.sha256=data.sha256;entry.history_count=data.history_count;entry.loaded=true;
      if(data.writer_id===entry.writer)entry.sequence=Math.max(entry.sequence,data.client_sequence||0);
      if(!entry.conflict)entry.error=null;
      if(entry.dirty){scriptDraftLocal(entry);if(!entry.conflict)scheduleScriptDraft(entry);}
      return entry;
    }catch(error){
      // Updated static files can precede a safe restart of a busy older server.
      if(error.httpStatus===404&&error.message==='Сторінку не знайдено'){
        entry.localOnly=true;entry.loaded=true;entry.error=null;
        if(entry.base_sha256&&entry.originalSHA&&entry.base_sha256!==entry.originalSHA){entry.conflict=true;entry.error='Основний сценарій уже змінено. Правки залишились у браузері.';}
        else entry.base_sha256=entry.base_sha256||entry.originalSHA;
        if(entry.dirty)scheduleScriptDraft(entry);
        return entry;
      }
      entry.error=error.message;throw error;
    }
    finally{entry.loading=null;scriptDraftNotify(entry);}
  })();
  return entry.loading;
}
function scheduleScriptDraft(entry,delay=800){
  clearTimeout(entry.timer);
  if(entry.conflict)return;
  entry.timer=setTimeout(()=>saveScriptDraft(entry).catch(()=>{}),delay);
}
function editScriptDraft(project,text){
  const entry=scriptDraftEntry(project);
  if(entry.text===text)return;
  entry.text=text;entry.dirty=true;entry.pending=true;entry.sequence++;entry.retries=0;if(!entry.conflict)entry.error=null;
  scriptDraftLocal(entry);scriptDraftNotify(entry);
  if(entry.loaded)scheduleScriptDraft(entry);else ensureScriptDraft(project).catch(()=>{});
}
async function saveScriptDraft(entry){
  if(entry.saving)return entry.saving;
  if(!entry.loaded||!entry.dirty)return entry;
  if(entry.conflict)throw Error(entry.error);
  clearTimeout(entry.timer);
  if(entry.localOnly){
    scriptDraftLocal(entry);
    if(!entry.localSaved){entry.error='Не вдалося зберегти правки в браузері.';scriptDraftNotify(entry);throw Error(entry.error);}
    entry.dirty=false;scriptDraftNotify(entry);return entry;
  }
  const sequence=entry.sequence,text=entry.text;
  entry.saving=(async()=>{
    try{
      const data=await api(`/api/projects/${entry.pid}/script-draft`,'PATCH',{text,expected_version:entry.version,base_sha256:entry.base_sha256,epoch:entry.epoch,writer_id:entry.writer,client_sequence:sequence});
      if(scriptDraftCache.get(entry.pid)!==entry)return entry;
      entry.version=data.version;entry.base_sha256=data.base_sha256;entry.sha256=data.sha256;entry.history_count=data.history_count;entry.error=null;entry.retries=0;
      if(sequence===entry.sequence){entry.dirty=false;entry.pending=data.pending;try{localStorage.removeItem(scriptDraftLocalKey(entry));}catch{}}
      else scriptDraftLocal(entry);
      return entry;
    }catch(error){
      entry.error=error.message;entry.conflict=error.httpStatus===409;
      if(!entry.conflict&&entry.retries++<3)scheduleScriptDraft(entry,Math.min(10000,2000*entry.retries));
      throw error;
    }finally{entry.saving=null;scriptDraftNotify(entry);if(entry.dirty&&!entry.error)scheduleScriptDraft(entry);}
  })();
  scriptDraftNotify(entry);return entry.saving;
}
async function flushScriptDraft(project){
  const entry=await ensureScriptDraft(project);
  while(entry.dirty){if(entry.conflict)throw Error(entry.error);await saveScriptDraft(entry);}
  return entry;
}
async function retryScriptDraft(project){
  const entry=scriptDraftEntry(project);
  try{
    if(entry.conflict){
      const data=await api(`/api/projects/${entry.pid}/script-draft`);
      if(data.epoch!==entry.epoch)throw Error('Випуск почато заново. Оновіть сторінку.');
      entry.version=data.version;entry.base_sha256=data.base_sha256;
    }
    entry.conflict=false;entry.error=null;entry.loaded=entry.version!==null;entry.retries=0;
    if(!entry.loaded)await ensureScriptDraft(project);
    await flushScriptDraft(project);
  }catch(error){entry.error=error.message;scriptDraftNotify(entry);}
}
function commitScriptDraft(project,record){
  const entry=scriptDraftCache.get(project.id);
  if(!entry||entry.text!==record.text)return;
  entry.base_sha256=record.sha256;entry.originalSHA=record.sha256;entry.dirty=false;entry.pending=false;entry.error=null;
  try{localStorage.removeItem(scriptDraftLocalKey(entry));}catch{}
  scriptDraftNotify(entry);
}
function acceptRecognizedScriptDraft(pid,report,acceptEmpty=false){
  const entry=scriptDraftCache.get(pid);
  if(!entry||entry.dirty||!report?.applied||entry.sha256!==report.script_sha256&&!(acceptEmpty&&entry.text===''))return;
  clearTimeout(entry.timer);scriptDraftCache.delete(pid);
  try{localStorage.removeItem(scriptDraftLocalKey(entry));}catch{}
}
function bindScriptDraft(field,project,panel){
  const entry=scriptDraftEntry(project);entry.fields.add(field);
  field.addEventListener('input',()=>editScriptDraft(project,field.value));
  if(entry.text!==undefined)field.value=entry.text;
  ensureScriptDraft(project).catch(()=>{});
  if(panel&&!panel.querySelector('.script-draft-tools'))bindScriptDraftStatus(panel.querySelector('.project-plan-heading')||panel,project);
}
function bindScriptDraftStatus(heading,project){
  const entry=scriptDraftEntry(project),box=document.createElement('div');box.className='script-draft-tools';
  box.innerHTML=`<small class="script-draft-status" role="status"></small><button type="button" class="script-draft-retry history-button outline" hidden>${scriptDraftIcon}</button><button type="button" class="script-draft-history history-button outline" hidden title="Історія правок сценарію" aria-label="Історія правок сценарію">${scriptDraftIcon}</button>`;
  box.querySelector('.script-draft-retry').onclick=()=>retryScriptDraft(project);
  box.querySelector('.script-draft-history').onclick=()=>openScriptDraftHistory(project);
  heading.append(box);entry.labels.add(box);scriptDraftNotify(entry);
}
async function openScriptDraftHistory(project){
  const pid=project.id,navigation=state.navigation;
  let selected=null,selection=0;
  modal('Історія сценарію','<div class="script-history"><p class="muted">Завантажуємо…</p></div>',[{label:'Повернути версію',icon:'refresh',primary:true,enabled:()=>!!selected,run:async()=>{
    if(!selected||!current())return;
    const entry=await flushScriptDraft(project);
    if(!current())return;
    const data=await api(`/api/projects/${pid}/script-draft/restore`,'POST',{version_id:selected,expected_version:entry.version,base_sha256:entry.base_sha256,epoch:entry.epoch});
    if(!current())return;
    Object.assign(entry,data,{dirty:false,error:null,conflict:false});scriptDraftNotify(entry);closeModal();
  }}]);
  const generation=state.modalGeneration,root=$('modal-body').querySelector('.script-history'),action=$('modal-actions').querySelector('button');action.disabled=true;
  const current=()=>root.isConnected&&state.project?.id===pid&&state.navigation===navigation&&state.modalGeneration===generation;
  try{
    await flushScriptDraft(project);if(!current())return;
    const data=await api(`/api/projects/${pid}/script-draft/history`);if(!current())return;
    if(!data.versions.length){root.innerHTML='<p class="muted">Попередніх версій ще немає.</p>';return;}
    root.innerHTML='<label>Версія<select></select></label><textarea rows="7" readonly aria-label="Попередня версія сценарію"></textarea><small class="muted script-history-count"></small>';
    const select=root.querySelector('select');
    for(const item of data.versions){const option=document.createElement('option');option.value=item.id;option.textContent=item.stale?'Попередня чернетка':item.baseline?'Початкова версія':new Date(item.saved_at*1000).toLocaleString('uk-UA');select.append(option);}
    const choose=async()=>{
      const version=++selection;selected=null;action.disabled=true;
      try{const value=await api(`/api/projects/${pid}/script-draft/${select.value}`);if(!current()||version!==selection)return;root.querySelector('textarea').value=value.text;root.querySelector('.script-history-count').textContent=scriptWordCount(value.text).toLocaleString('uk-UA')+' слів';selected=select.value;action.disabled=false;}
      catch(error){if(current())root.querySelector('.script-history-count').textContent=error.message;}
    };
    select.addEventListener('change',choose);await choose();
  }catch(error){if(current())root.textContent=error.message;}
}
