// Project-bound openings and script jobs live in the script area, independently of the New episode dialog.
function renderInlineEpisodeDraft(panel){
  const project=state.project,data=state.episodeDraft;
  const pending=project&&data?.project_id===project.id&&episodeDraftPending(data)&&(!project.voice_script?.text||data.script_saved||data.stage==='metadata');
  if(!pending){panel.episodeDraftDispose?.();return false;}
  const mounted=panel.querySelector('.episode-draft-panel');
  if(mounted?.dataset.project===project.id){mounted.updateDraft(data);return true;}
  panel.episodeDraftDispose?.();panel.replaceChildren();renderPlanSwitch(panel);
  const count=panel.querySelector('.script-word-count');
  if(count)count.textContent=data.target_words?`Обсяг ${Number(data.target_words).toLocaleString('uk-UA')} слів`:'';
  const root=document.createElement('section');root.className='episode-draft-panel';root.dataset.project=project.id;panel.append(root);
  mountEpisodeDraftPanel(root,project.id,data,panel);
  return true;
}

function mountEpisodeDraftPanel(root,pid,initial,panel){
  let current=initial,timer=null,disposed=false,sending=false,signature='',generation=0;
  const endpoint=`/api/projects/${encodeURIComponent(pid)}/episode-draft`;
  const connected=()=>!disposed&&root.isConnected&&state.project?.id===pid&&['editor','plan'].includes(state.view);
  const dispose=()=>{disposed=true;clearTimeout(timer);if(panel.episodeDraftDispose===dispose)panel.episodeDraftDispose=null;};
  panel.episodeDraftDispose=dispose;
  const button=(id,label,icon='refresh',primary=false)=>`<button type="button" class="${primary?'primary':'secondary'} episode-action" id="${id}">${episodeIcon(icon)}<span>${label}</span></button>`;
  const lock=()=>root.querySelectorAll('button').forEach(item=>item.disabled=true);
  const report=(error,retry)=>{
    if(!connected())return;
    const old=root.querySelector('.episode-draft-request-error');old?.remove();
    const note=document.createElement('div');note.className='episode-draft-request-error';
    note.innerHTML=`<p class="episode-error" role="alert">${esc(error.message)}</p>${button('episode-draft-retry','Спробувати ще раз')}`;
    note.querySelector('button').onclick=retry;root.prepend(note);
  };
  async function accept(next,expected=generation){
    if(!connected()||expected!==generation)return;
    if(next.project_id&&next.project_id!==pid)throw Error('Відповідь належить іншому випуску.');
    if(!episodeDraftPending(next)){
      // The saved project is the source for narration. Never copy a hook into the script field.
      const fresh=await api(`/api/projects/${encodeURIComponent(pid)}`);
      if(!connected()||expected!==generation)return;
      const before=state.project.voice_script?.text||'';
      if(voiceScriptDraft[pid]===before)delete voiceScriptDraft[pid];
      if(typeof acceptScriptRevision==='function')acceptScriptRevision(state.project,next);
      state.episodeDraft=next;current=next;state.project=fresh.project;dispose();delete panel.dataset.planKey;renderProject();return;
    }
    state.episodeDraft=next;current=next;draw(next);
  }
  async function poll(){
    if(!connected()||sending)return;
    clearTimeout(timer);const expected=++generation;
    try{const next=await api(endpoint);if(!connected()||expected!==generation)return;root.querySelector('.episode-draft-request-error')?.remove();await accept(next,expected);}
    catch(error){if(expected!==generation)return;report(error,poll);if(connected()&&error.httpStatus!==404&&['queued','running','cancelling'].includes(current.status))timer=setTimeout(poll,4000);}
  }
  async function request(payload){
    if(!connected()||sending)return;
    payload={...payload,request_id:payload.request_id||crypto.randomUUID()};
    sending=true;clearTimeout(timer);lock();const expected=++generation;
    try{
      const next=await api(endpoint,'POST',payload);
      sending=false;signature='';await accept(next,expected);
      refreshProjects().catch(()=>{});
    }catch(error){sending=false;signature='';draw(current);report(error,()=>request(payload));}
    finally{sending=false;}
  }
  function controls(data,hasHooks){
    const footer=document.createElement('div');footer.className='episode-draft-actions';
    footer.innerHTML=button('episode-draft-cancel','Скасувати задачу','close')+button('episode-draft-refresh',hasHooks?'Нові зачини':'Створити зачини','refresh',!hasHooks);
    footer.querySelector('#episode-draft-cancel').onclick=()=>request({action:'cancel'});
    footer.querySelector('#episode-draft-refresh').onclick=()=>request({action:'openings',refresh:true});root.append(footer);
  }
  function draw(data){
    if(!connected())return;
    clearTimeout(timer);
    const nextSignature=JSON.stringify(data);
    if(signature===nextSignature){if(['queued','running','cancelling'].includes(data.status))timer=setTimeout(poll,2000);return;}
    signature=nextSignature;
    const error=data.status==='failed'?`<p class="episode-error" role="alert">${esc(data.error||'Не вдалося завершити запит.')}</p>`:'';
    if(['queued','running','cancelling'].includes(data.status)){
      const label=data.status==='cancelling'?'Зупиняємо роботу':data.manual_revision?'Opus вносить ваші правки':data.editing_status==='running'||data.stage==='editing'?(data.author_session?'Opus перевіряє й редагує свій сценарій':'Редактура сценарію'):{openings:'Opus готує зачини',script:'Opus пише сценарій',metadata:'Opus готує метадані'}[data.stage]||'Готуємо сценарій';
      root.innerHTML=`<div class="episode-writing-card"><div class="episode-writing" role="status"><span class="export-spinner" aria-hidden="true"></span><strong>${label}</strong></div>${button('episode-draft-stop','Зупинити','stop')}</div>`;
      root.querySelector('#episode-draft-stop').disabled=data.status==='cancelling';
      root.querySelector('#episode-draft-stop').onclick=()=>request({action:'cancel'});
      timer=setTimeout(poll,2000);return;
    }
    if(data.script_saved||data.stage==='metadata'){
      const unfinished=data.editing_status&&data.editing_status!=='done';
      root.innerHTML=error+`<h3>${unfinished?'Чернетку збережено, саморедактуру не завершено':'Сценарій готовий'}</h3><div class="episode-draft-actions">${button('episode-draft-show-script','Показати сценарій','open')}${button('episode-draft-metadata','Дописати метадані · Opus','title',true)}</div>`;
      root.querySelector('#episode-draft-metadata').onclick=()=>request({action:'metadata'});
      if(unfinished){const retry=root.querySelector('#episode-draft-metadata');retry.textContent='Продовжити саморедактуру · Opus';retry.disabled=!data.author_session;retry.onclick=()=>request({action:'editing'});}
      if(unfinished&&data.manual_revision){const retry=root.querySelector('#episode-draft-metadata');retry.textContent='Внести правки · Opus';retry.onclick=()=>openScriptRevision(state.project);}
      if(data.editing_status){
        root.append(createScriptEditingReportButton(state.project));
      }
      root.querySelector('#episode-draft-show-script').onclick=()=>{state.episodeDraft=null;dispose();delete panel.dataset.planKey;renderProject();};return;
    }
    const hooks=data.openings?.length?data.openings:data.previous_openings;
    root.innerHTML=`<div class="episode-openings-head"><h3>Оберіть зачин</h3></div>${error}`;
    if(hooks?.length){
      const list=document.createElement('div');list.className='episode-hook-options';
      list.innerHTML=hooks.map((hook,index)=>`<button type="button" class="episode-hook-option" data-hook="${index}" ${data.openings?.length?'':'disabled'}><strong>Варіант ${index+1}${episodeIcon('open')}</strong><span>${esc(hook.text)}</span>${hook.uk?`<small>${esc(hook.uk)}</small>`:''}</button>`).join('');
      list.querySelectorAll('button').forEach(item=>item.onclick=()=>request({action:'script',index:Number(item.dataset.hook)}));root.append(list);
    }else if(!error){const empty=document.createElement('p');empty.className='muted';empty.textContent='Зачини ще не створені.';root.append(empty);}
    controls(data,!!hooks?.length);
  }
  root.updateDraft=next=>{if(sending)return;generation++;current=next;draw(next);};
  draw(initial);
}


async function openManualProjectOpenings(project){
  const pid=project.id,navigation=state.navigation;
  if(state.project?.id!==pid)return;
  const health=await api('/api/health');
  const supported=health.manual_project_openings===true;
  const entry=await flushScriptDraft(project);
  if(state.project?.id!==pid||state.navigation!==navigation)return;
  if((entry.text||'').trim())throw Error('У проєкті вже є сценарій.');
  const existing=state.episodeDraft;
  if(existing?.project_id===pid&&episodeDraftPending(existing)){renderProject();return;}
  const requestId=crypto.randomUUID();let modalGeneration;
  const current=()=>state.project?.id===pid&&state.navigation===navigation&&state.modalGeneration===modalGeneration;
  modal('Створити зачини',`<p>${esc(project.name)}</p><label class="episode-word-count">Обсяг сценарію <input id="manual-opening-words" type="number" min="200" max="15000" step="1" value="2000"> слів</label>${supported?'':'<p class="muted">Оновлення буде доступне після завершення поточної роботи студії. Потім оновіть сторінку.</p>'}`,[{
    label:'Створити зачини · Opus',icon:'magic',primary:true,enabled:()=>supported,run:async()=>{
      const input=$('manual-opening-words'),count=Number(input?.value);
      if(!Number.isInteger(count)||count<200||count>15000)throw Error('Задайте від 200 до 15000 слів.');
      if(!current())return;
      const latest=await flushScriptDraft(project);
      if((latest.text||'').trim())throw Error('У проєкті вже є сценарій.');
      if(!current())return;
      const data=await api(`/api/projects/${encodeURIComponent(pid)}/episode-draft`,'POST',{action:'openings',target_words:count,request_id:requestId});
      if(!current())return;
      state.episodeDraft=data;closeModal();renderProject();
    }
  }]);
  modalGeneration=state.modalGeneration;
}
