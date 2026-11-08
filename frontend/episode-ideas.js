function episodeDraftPending(data){
  return !!data?.project_id&&!data.completed&&!data.cancelled&&['openings','script','metadata'].includes(data.stage);
}

async function openNewEpisodeWizard({projectId=null,draft=null}={}){
  if(!state.channel){status('Спершу додайте канал.',true);return;}
  const cid=state.channel.id;
  modal(projectId?'Зачини випуску':'Новий випуск',`<div class="episode-wizard"><label>Назва випуску<input id="new-project-name" maxlength="100" placeholder="Введіть власну назву або виберіть ідею нижче"></label><div id="episode-ideas"><p class="muted">Завантажуємо…</p></div></div>`,[
    {label:'Створити випуск',run:async()=>{try{
      const name=$('new-project-name').value.trim();if(!name)throw new Error('Введіть назву випуску.');
      const result=await api('/api/projects','POST',{channel_id:cid,name});closeModal();await selectChannel(cid);await selectProject(result.project.id,{view:'editor'});
    }catch(error){status(error.message,true);}}}
  ]);
  $('modal-backdrop').classList.add('episode-ideas-open');
  const root=$('episode-ideas'),input=$('new-project-name'),create=$('modal-actions').querySelector('button');
  const channelEndpoint=`/api/channels/${cid}/episode-ideas`;
  let sending=false,lastData=null,timer=null;
  const connected=()=>root.isConnected&&!$('modal-backdrop').hidden&&state.channel?.id===cid;
  const endpoint=()=>projectId?`/api/projects/${projectId}/episode-draft`:channelEndpoint;
  const errorBox=message=>`<p class="episode-error" role="alert">${esc(message)}</p>`;
  function showError(error,retry){
    if(!connected())return;
    if(lastData)draw(lastData,true);
    const note=document.createElement('div');note.innerHTML=errorBox(error.message)+'<button class="secondary">Спробувати ще раз</button>';
    note.querySelector('button').onclick=retry;root.prepend(note);
  }
  async function request(body){
    if(sending||!connected())return;body={...body,request_id:body.request_id||crypto.randomUUID()};sending=true;clearTimeout(timer);
    root.querySelectorAll('button').forEach(b=>b.disabled=true);create.disabled=true;
    try{
      const data=await api(endpoint(),'POST',body);sending=false;
      if(!connected())return;
      if(data.cancelled){closeModal();showProjectList();openNewEpisodeWizard();return;}
      if(data.project_id){projectId=data.project_id;refreshProjects().catch(()=>{});}
      draw(data);
    }catch(error){sending=false;showError(error,()=>request(body));}
    finally{sending=false;create.disabled=false;}
  }
  function chooseTopic(data,index){
    const topic=data.ideas[index];input.value=topic.title;input.readOnly=true;create.hidden=true;
    root.innerHTML=`${topic.uk?`<p class="muted">${esc(topic.uk)}</p>`:''}<label class="episode-word-count">Обсяг сценарію <input id="idea-words" type="number" min="200" max="15000" step="50" value="${data.target_words}"> слів</label><div class="episode-topic-actions"><button class="secondary" id="ideas-back">Скасувати</button><button class="primary glow-action thumb-writer-button" id="ideas-create-openings">${projectCostIcons.claude_code}<span>Створити зачини · Opus</span></button></div>`;
    root.querySelector('#ideas-back').onclick=()=>draw(data);
    root.querySelector('#ideas-create-openings').onclick=()=>request({action:'openings',index,ideas_id:data.id,target_words:Number(root.querySelector('#idea-words').value),new_episode:true});
  }
  async function poll(){
    if(!connected())return;
    try{draw(await api(projectId?endpoint():`${channelEndpoint}?view=topics`));}
    catch(error){showError(error,poll);}
  }
  function draftControls(){
    return `<div class="episode-draft-actions"><button class="secondary" id="ideas-cancel">Скасувати</button><button class="secondary" id="openings-refresh" title="Створити нові варіанти зачинів" aria-label="Оновити зачини"><span aria-hidden="true">↻</span> Нові зачини</button></div>`;
  }
  function bindDraftControls(){
    root.querySelector('#ideas-cancel').onclick=()=>request({action:'cancel'});
    root.querySelector('#openings-refresh').onclick=()=>request({action:'openings',refresh:true});
  }
  function draw(data,passive=false){
    if(!connected())return;lastData=data;clearTimeout(timer);
    input.value=data.selected?.title||'';input.readOnly=!!projectId;create.hidden=!!projectId;
    if(data.status==='running'&&data.stage==='script'&&data.project_id){
      projectActivities.set(data.project_id,'створення сценарію');
      closeModal();showProjectList();pollChannelActivity();return;
    }
    if(data.completed&&projectId){closeModal();selectProject(projectId).catch(error=>status(error.message,true));return;}
    if(data.stale&&!projectId&&data.status!=='failed'&&!passive){request({action:'ideas',refresh:true});return;}
    if(data.status==='running'){
      const label={ideas:'DeepSeek пропонує нові теми',openings:'Opus готує зачини',script:'Opus пише сценарій',metadata:'Opus готує метадані'}[data.stage];
      root.innerHTML=`<div class="episode-writing" role="status"><span class="export-spinner"></span><div><strong>${label}</strong><small>${data.target_words?data.target_words.toLocaleString('uk-UA')+' слів':'Для збереженого сценарію'}</small></div></div>`;
      timer=setTimeout(poll,2000);return;
    }
    const error=data.status==='failed'?errorBox(data.error||'Запит не завершено'):'';
    if(projectId&&(data.script_saved||data.stage==='metadata')){
      root.innerHTML=error+'<p class="muted">Сценарій збережено.</p><button class="secondary" id="metadata-retry">Дописати метадані · Opus</button>';
      root.querySelector('#metadata-retry').onclick=()=>request({action:'metadata'});return;
    }
    const openings=data.openings?.length?data.openings:data.previous_openings;
    if(projectId&&openings?.length){
      root.innerHTML=error+`<div class="episode-openings-head"><h3>Виберіть зачин</h3><span class="muted">${data.target_words.toLocaleString('uk-UA')} слів</span></div><div class="episode-options">${openings.map((row,i)=>`<button data-opening="${i}" ${data.openings?.length?'':'disabled'}><strong>Варіант ${i+1}</strong><span>${esc(row.text)}</span>${row.uk?`<small>${esc(row.uk)}</small>`:''}</button>`).join('')}</div>`+draftControls();
      root.querySelectorAll('[data-opening]').forEach(b=>b.onclick=()=>request({action:'script',index:Number(b.dataset.opening)}));
      bindDraftControls();return;
    }
    if(projectId){
      root.innerHTML=error+'<p class="muted">Зачини ще не готові.</p>'+draftControls();bindDraftControls();return;
    }
    if(!data.ideas){
      if(passive){root.innerHTML=error;return;}
      if(data.status==='failed'){root.innerHTML=error+'<button class="secondary" id="ideas-retry">Спробувати ще раз</button>';root.querySelector('#ideas-retry').onclick=()=>request({action:'ideas',refresh:true});}
      else request({action:'ideas'});
      return;
    }
    root.innerHTML=error+`<div class="episode-ideas-head"><strong><svg class="idea-provider-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-label="DeepSeek"><path d="M3 11c3-5 8-6 12-2l6-4-2 8c-1 6-10 8-14 3l-2-5Z"/><circle cx="12" cy="11" r=".6"/><path d="m15 15 3 4m-9-1-1 3"/></svg> Нові теми</strong><button class="secondary" id="ideas-refresh" title="Запросити інші ідеї" aria-label="Інші ідеї">↻</button></div><div class="episode-options">${data.ideas.map((row,i)=>(data.used_idea_indexes||[]).includes(i)?'':`<button data-idea="${i}"><span><strong>${esc(row.title)}</strong>${row.uk?`<small>${esc(row.uk)}</small>`:''}</span></button>`).join('')}</div>${(data.used_idea_indexes||[]).length>=data.ideas.length?'<p class="muted">Усі ці теми вже використані. Натисніть ↻, щоб отримати нові.</p>':''}`;
    root.querySelector('#ideas-refresh').onclick=()=>request({action:'ideas',refresh:true});
    root.querySelectorAll('[data-idea]').forEach(b=>b.onclick=()=>chooseTopic(data,Number(b.dataset.idea)));
  }
  if(draft)draw(draft);else await poll();
}
