const episodeIconPaths={
  episode:'<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M8 4v16m8-16v16M3 9h5m8 0h5M3 15h5m8 0h5m-10-5 4 2-4 2Z"/>',
  title:'<path d="M4 5h16M12 5v15m-4 0h8"/>',
  topics:'<path d="M9 18h6m-6 3h6M8 14a6 6 0 1 1 8 0c-1 .8-1 2-1 2H9s0-1.2-1-2Z"/>',
  link:'<path d="M10 13a5 5 0 0 0 7.07 0l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.07 0l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
  magic:'<path d="m21.6 3.6-1.2-1.2a1.2 1.2 0 0 0-1.7 0L2.4 18.6a1.2 1.2 0 0 0 0 1.7l1.2 1.2a1.2 1.2 0 0 0 1.7 0L21.6 5.4a1.2 1.2 0 0 0 0-1.8M14 7l3 3M5 6v4M19 14v4M10 2v2M7 8H3M21 16h-4M11 3H9"/>',
  add:'<path d="M12 5v14M5 12h14"/>',
  close:'<path d="m6 6 12 12M18 6 6 18"/>',
  refresh:'<path d="M3 12a9 9 0 1 0 9-9 9.8 9.8 0 0 0-6.7 2.7L3 8M3 3v5h5"/>',
  open:'<path d="M14 3h7v7m0-7L10 14M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5"/>',
  stop:'<rect x="6" y="6" width="12" height="12" rx="2"/>',
  count:'<path d="M9 3 7 21m10-18-2 18M4 9h17M3 15h17"/>'
};
function episodeIcon(name){return `<svg class="episode-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${episodeIconPaths[name]||episodeIconPaths.episode}</svg>`;}

function episodeDraftPending(data){
  return !!data?.project_id&&!data.completed&&!data.cancelled&&data.status!=='cancelled'&&['openings','script','metadata','editing'].includes(data.stage);
}

async function openNewEpisodeWizard({projectId=null,draft=null}={}){
  if(!state.channel){status('Спершу додайте канал.',true);return;}
  if(projectId){
    if(state.project?.id!==projectId)return selectProject(projectId);
    const navigation=state.navigation;
    const data=draft||await api(`/api/projects/${encodeURIComponent(projectId)}/episode-draft`);
    if(state.project?.id!==projectId||state.navigation!==navigation)return;
    state.episodeDraft=data;
    renderMontageMake();return;
  }
  const cid=state.channel.id;
  modal('Новий випуск',`<div class="episode-wizard"><div class="episode-name-field" id="episode-name-field">${episodeIcon('title')}<input id="new-project-name" aria-label="Назва випуску" maxlength="100" placeholder="Назва випуску"></div><div class="episode-entry-tools" id="episode-entry-tools"><div class="episode-entry-options" id="episode-entry-options" role="group" aria-label="Спосіб створення"><button type="button" data-entry="title" aria-pressed="true">${episodeIcon('title')}<span>Власна назва</span></button><button type="button" data-entry="topics" aria-pressed="false">${episodeIcon('topics')}<span>Ідеї</span></button><button type="button" data-entry="reference" aria-pressed="false">${episodeIcon('link')}<span>Клонувати ідею</span></button></div><button class="secondary" id="ideas-refresh" title="Оновити ідеї" aria-label="Оновити ідеї">${episodeIcon('refresh')}</button></div><div class="episode-reference" id="episode-reference" hidden><div class="episode-reference-input">${episodeIcon('link')}<input id="episode-reference-url" aria-label="Клонування ідеї" type="url" placeholder="Вставте посилання на YouTube" autocomplete="off"><button type="button" class="secondary" id="episode-reference-copy" disabled>${episodeIcon('magic')}<span>Клонувати</span></button></div><div id="episode-reference-status" role="status"></div></div><div id="episode-ideas"><p class="muted">Завантажуємо…</p></div></div>`,[
    {label:'Створити випуск',enabled:()=>connected()&&!!input.value.trim(),run:async()=>{if(!connected())return;try{
      const name=input.value.trim();if(!name)throw new Error('Введіть назву випуску.');
      const result=await api('/api/projects','POST',{channel_id:cid,name});
      if(!connected())return;
      closeModal();await selectProject(result.project.id,{view:'editor'});
    }catch(error){if(connected())status(error.message,true);}}}
  ]);
  $('modal-backdrop').classList.add('episode-ideas-open');
  const root=$('episode-ideas'),input=$('new-project-name'),create=$('modal-actions').querySelector('button');
  $('modal-title').innerHTML=episodeIcon('episode')+`<span>Новий випуск</span>`;
  create.innerHTML=episodeIcon('add')+'<span>Створити випуск</span>';
  create.classList.add('episode-action','secondary');
  $('episode-name-field')?.append(create);
  const channelEndpoint=`/api/channels/${cid}/episode-ideas`;
  const generation=state.modalGeneration,navigation=state.navigation;
  let sending=false,translating=false,titleTranslator=null,lastData=null,timer=null,reference=null,referenceVersion=0,readVersion=0,entry='title',topicSelected=false,dailyRequested=false;
  const entryTitles={title:'',topics:'',reference:''};
  const entryChoices=$('episode-entry-options'),entryButtons=entryChoices?[...entryChoices.querySelectorAll('button')]:[];
  const entryTools=$('episode-entry-tools'),ideasRefresh=$('ideas-refresh');
  if(entryTools)$('modal-title').after(entryTools);
  if(ideasRefresh)ideasRefresh.onclick=()=>request({action:'ideas',refresh:true});
  $('modal-body').channelSettingsCleanup=()=>{clearTimeout(timer);referenceVersion++;titleTranslator?.dispose();(entryTools||entryChoices)?.remove();$('modal-actions').hidden=false;};
  const connected=()=>root.isConnected&&!$('modal-backdrop').hidden&&state.channel?.id===cid&&state.modalGeneration===generation&&state.navigation===navigation;
  titleTranslator=bindTitleTranslation(input,{channelId:()=>cid,live:connected,available:()=>entry==='reference'&&!!reference,enabled:()=>!sending,context:()=>reference?.id||'',onBusy:value=>{translating=value;const start=root.querySelector('#reference-openings');if(start)start.disabled=value||sending;}});
  const errorBox=message=>`<p class="episode-error" role="alert">${esc(message)}</p>`;
  function showCreate(visible){create.hidden=!visible;create.disabled=visible&&!input.value.trim();$('modal-actions').hidden=true;}
  function selectEntry(value){
    readVersion++;entryTitles[entry]=input.value;entry=value;input.value=entryTitles[entry]||'';clearTimeout(timer);
    topicSelected=false;
    entryButtons.forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.entry===entry)));
    $('episode-reference').hidden=entry!=='reference';
    if(ideasRefresh)ideasRefresh.hidden=entry!=='topics';
    root.hidden=entry==='title'||entry==='reference'&&!reference;showCreate(entry==='title');input.hidden=entry!=='title';titleTranslator.refresh();
    if(entry==='reference'){
      if(reference){input.value=entryTitles.reference||reference.title;input.hidden=false;drawReference();}
      $('episode-reference-url').focus();
    }else if(entry==='topics'){showLoading('Завантажуємо ідеї');return poll();}
    else if(entry==='title')input.focus();
  }
  entryButtons.forEach(button=>button.onclick=()=>selectEntry(button.dataset.entry));
  input.oninput=()=>{
    if(entry==='topics'&&!topicSelected)selectEntry('title');
    if(entry==='title')create.disabled=!input.value.trim();
  };
  input.onkeydown=event=>{if(event.key==='Enter'&&entry==='title'&&!create.disabled){event.preventDefault();create.click();}};
  function showError(error,retry){
    if(!connected())return;
    if(lastData&&!topicSelected&&entry!=='reference')draw(lastData,true);
    if(ideasRefresh)ideasRefresh.disabled=sending;
    const note=document.createElement('div');note.innerHTML=errorBox(error.message)+`<button class="secondary episode-action">${episodeIcon('refresh')}<span>Спробувати ще раз</span></button>`;
    note.querySelector('button').onclick=retry;root.prepend(note);
  }
  async function request(body){
    if(sending||translating||!connected())return;body={...body,request_id:body.request_id||crypto.randomUUID()};sending=true;readVersion++;clearTimeout(timer);entryButtons.forEach(button=>button.disabled=true);titleTranslator.refresh();
    root.querySelectorAll('button').forEach(b=>b.disabled=true);create.disabled=true;
    if(body.action==='ideas'){dailyRequested=true;showLoading('DeepSeek пропонує нові теми');}
    try{
      const data=await api(channelEndpoint,'POST',body);sending=false;
      if(!connected())return;
      if(data.cancelled){closeModal();showProjectList();openNewEpisodeWizard();return;}
      if(data.project_id){closeModal();refreshProjects().catch(()=>{});await selectProject(data.project_id);return;}
      draw(data);
    }catch(error){sending=false;showError(error,()=>request(body));}
    finally{sending=false;if(connected()){create.disabled=!input.value.trim();entryButtons.forEach(button=>button.disabled=false);root.querySelectorAll('button').forEach(button=>button.disabled=false);titleTranslator.refresh();}}
  }
  function chooseTopic(data,index){
    readVersion++;topicSelected=true;
    const topic=data.ideas[index];input.value=topic.title;input.readOnly=false;input.hidden=false;showCreate(false);
    root.innerHTML=`${topic.uk?`<p class="muted">${esc(topic.uk)}</p>`:''}<label class="episode-word-count">${episodeIcon('count')}Обсяг сценарію <input id="idea-words" type="number" min="200" max="15000" step="1" value="${data.target_words}"> слів</label><div class="episode-topic-actions"><button class="primary glow-action thumb-writer-button" id="ideas-create-openings">${projectCostIcons.claude_code}<span>Створити зачини · Opus</span></button></div>`;
    root.querySelector('#ideas-create-openings').onclick=()=>{
      const title=input.value.trim();if(!title){status('Введіть назву випуску.',true);return;}
      return request({action:'openings',index,title,ideas_id:data.id,target_words:Number(root.querySelector('#idea-words').value),new_episode:true});
    };
  }
  function drawReference(){
    if(!reference||!connected())return;
    showCreate(false);input.readOnly=false;input.hidden=false;
    root.innerHTML=`<div class="episode-reference-card"><img src="${esc(reference.thumbnail_url)}" alt="Прев’ю референсу"><span>${esc(reference.author)}</span></div><label class="episode-word-count">${episodeIcon('count')}Обсяг сценарію <input id="idea-words" type="number" min="200" max="15000" step="1" value="${lastData?.target_words||2000}"> слів</label><div class="episode-topic-actions"><button class="primary glow-action thumb-writer-button" id="reference-openings">${projectCostIcons.claude_code}<span>Створити зачини · Opus</span></button></div>`;
    root.querySelector('#reference-openings').onclick=()=>request({action:'clone_openings',reference_id:reference.id,title:input.value.trim(),target_words:Number(root.querySelector('#idea-words').value)});
    root.querySelector('#reference-openings').disabled=sending||translating;titleTranslator.refresh();
  }
  async function importReference(){
    const field=$('episode-reference-url'),note=$('episode-reference-status');
    if(!field||!connected()||sending||entry!=='reference'||reference||$('episode-reference-copy').disabled)return;
    const url=field.value.trim(),version=++referenceVersion;
    if(!url){note.textContent='';return;}
    const copy=$('episode-reference-copy');copy.disabled=true;
    clearTimeout(timer);note.innerHTML='<span class="export-spinner"></span> Отримуємо ідею…';
    try{
      const data=await api(`/api/channels/${cid}/idea-reference`,'POST',{url});
      if(!connected()||version!==referenceVersion||field.value.trim()!==url||entry!=='reference')return;
      reference=data;entryTitles.reference=data.title;input.value=data.title;note.textContent='';root.hidden=false;drawReference();
    }catch(error){if(connected()&&version===referenceVersion)note.textContent=error.message;}
    finally{if(copy.isConnected&&version===referenceVersion)copy.disabled=!!reference||!field.value.trim();}
  }
  const referenceInput=$('episode-reference-url');
  if(referenceInput){
    referenceInput.oninput=()=>{referenceVersion++;reference=null;root.hidden=true;input.hidden=true;$('episode-reference-status').textContent='';$('episode-reference-copy').disabled=!referenceInput.value.trim();};
    $('episode-reference-copy').onclick=importReference;
    referenceInput.onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();importReference();}};
  }
  async function poll(){
    if(!connected())return;
    const version=++readVersion;
    try{const data=await api(`${channelEndpoint}?view=topics`);if(connected()&&version===readVersion)draw(data);}
    catch(error){if(connected()&&version===readVersion)showError(error,poll);}
  }
  function showLoading(label,targetWords=lastData?.target_words){
    if(ideasRefresh)ideasRefresh.disabled=true;
    root.innerHTML=`<div class="episode-writing" role="status"><span class="export-spinner"></span><div><strong>${label}</strong><small>${targetWords?targetWords.toLocaleString('uk-UA')+' слів':'Готуємо список ідей'}</small></div></div>`;
  }
  function prepareIdeas(){
    if(dailyRequested){showError(new Error('Не вдалося оновити список ідей. Спробуйте ще раз.'),()=>request({action:'ideas',refresh:true}));return;}
    return request({action:'ideas',if_stale:true});
  }
  function draw(data,passive=false){
    if(!connected())return;lastData=data;clearTimeout(timer);
    if(entry==='reference'){if(reference)drawReference();return;}
    if(entry==='title')return;
    if(ideasRefresh){ideasRefresh.hidden=entry!=='topics';ideasRefresh.disabled=sending||data.status==='running';}
    topicSelected=false;
    input.value=data.selected?.title||'';input.readOnly=false;input.hidden=true;showCreate(false);
    if(data.stale&&!passive){prepareIdeas();return;}
    if(data.status==='running'){
      const label={ideas:'DeepSeek пропонує нові теми',openings:'Opus готує зачини',script:'Opus пише сценарій',metadata:'Opus готує метадані'}[data.stage];
      showLoading(label,data.target_words);
      timer=setTimeout(poll,2000);return;
    }
    const error=data.status==='failed'?errorBox(data.error||'Запит не завершено'):'';
    if(!data.ideas){
      if(passive){root.innerHTML=error;return;}
      if(data.status==='failed'){root.innerHTML=error+`<button class="secondary episode-action" id="ideas-retry">${episodeIcon('refresh')}<span>Спробувати ще раз</span></button>`;root.querySelector('#ideas-retry').onclick=()=>request({action:'ideas',refresh:true});}
      else prepareIdeas();
      return;
    }
    root.innerHTML=error+`<div class="episode-options episode-topic-options">${data.ideas.map((row,i)=>(data.used_idea_indexes||[]).includes(i)?'':`<button data-idea="${i}">${episodeIcon('episode')}<span><strong>${esc(row.title)}</strong>${row.uk?`<small>${esc(row.uk)}</small>`:''}</span></button>`).join('')}</div>${(data.used_idea_indexes||[]).length>=data.ideas.length?'<p class="muted">Усі ці теми вже використані. Натисніть ↻, щоб отримати нові.</p>':''}`;
    root.querySelectorAll('[data-idea]').forEach(b=>b.onclick=()=>chooseTopic(data,Number(b.dataset.idea)));
  }
  selectEntry('title');
  if(draft)draw(draft);else await poll();
}
