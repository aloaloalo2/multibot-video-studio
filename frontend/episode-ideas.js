async function openNewEpisodeWizard(){
  if(!state.channel){status('Спершу додайте канал.',true);return;}
  const cid=state.channel.id;
  modal('Новий випуск',`<div class="episode-wizard"><label>Назва випуску<input id="new-project-name" maxlength="100" placeholder="Введіть власну назву або виберіть ідею нижче"></label><div id="episode-ideas"><p class="muted">Завантажуємо ідеї…</p></div></div>`,[
    {label:'Створити випуск',run:async()=>{try{
      const name=$('new-project-name').value.trim();if(!name)throw new Error('Введіть назву випуску.');
      const result=await api('/api/projects','POST',{channel_id:cid,name});closeModal();await selectChannel(cid);await selectProject(result.project.id,{view:'editor'});
    }catch(error){status(error.message,true);}}}
  ]);
  $('modal-backdrop').classList.add('episode-ideas-open');
  const root=$('episode-ideas'),input=$('new-project-name');
  let sending=false;
  const endpoint=`/api/channels/${cid}/episode-ideas`;
  async function request(body){
    if(sending||!root.isConnected)return;sending=true;
    root.querySelectorAll('button').forEach(b=>b.disabled=true);
    try{draw(await api(endpoint,'POST',body));}catch(error){if(root.isConnected)root.innerHTML=`<p class="episode-error">${esc(error.message)}</p><button id="ideas-reload">Спробувати ще раз</button>`;root.querySelector('#ideas-reload')?.addEventListener('click',()=>request(body));}
    finally{sending=false;}
  }
  function chooseTopic(data,index){
    const topic=data.ideas[index];
    input.value=topic.title;input.readOnly=true;
    $('modal-actions').querySelector('button').hidden=true;
    root.innerHTML=`${topic.uk?`<p class="muted">${esc(topic.uk)}</p>`:''}<label class="episode-word-count">Обсяг сценарію <input id="idea-words" type="number" min="200" max="15000" step="50" value="${data.target_words}"> слів</label><div class="episode-topic-actions"><button class="secondary" id="ideas-back">Скасувати</button><button class="primary glow-action thumb-writer-button" id="ideas-create-openings">${projectCostIcons.claude_code}<span>Створити зачини · Opus</span></button></div>`;
    root.querySelector('#ideas-back').onclick=()=>{input.value='';draw(data);};
    root.querySelector('#ideas-create-openings').onclick=()=>request({action:'openings',index,target_words:Number(root.querySelector('#idea-words').value)});
  }
  async function poll(){if(!root.isConnected||$('modal-backdrop').hidden)return;try{draw(await api(endpoint));}catch(error){if(root.isConnected){root.innerHTML=`<p class="episode-error">${esc(error.message)}</p><button id="ideas-status">Оновити стан</button>`;root.querySelector('#ideas-status').addEventListener('click',poll);}}}
  function draw(data){
    if(!root.isConnected)return;
    input.readOnly=!!data.selected;
    $('modal-actions').querySelector('button').hidden=!!data.project_id;
    if(data.stale){request({action:'ideas',refresh:true});return;}
    if(data.completed){
      root.innerHTML=`<p>Сценарій готовий · ${data.actual_words.toLocaleString('uk-UA')} слів</p><button id="ideas-open">Відкрити випуск</button><button id="ideas-again">Нові ідеї</button>`;
      root.querySelector('#ideas-open').onclick=async()=>{closeModal();await selectChannel(cid);await selectProject(data.project_id,{view:'editor'});};
      root.querySelector('#ideas-again').onclick=()=>request({action:'ideas',refresh:true});return;
    }
    if(data.status==='running'){
      const label={ideas:'DeepSeek пропонує нові теми',openings:'Opus готує п’ять зачинів',script:'Opus пише сценарій'}[data.stage];
      if(data.selected)input.value=data.selected.title;
      root.innerHTML=`<div class="episode-writing"><span class="export-spinner"></span><div><strong>${label}</strong><small>${data.selected?esc(data.selected.title)+' · '+data.target_words.toLocaleString('uk-UA')+' слів':'На основі попередніх випусків каналу'}</small></div></div><p class="muted">Вікно можна закрити. Результат збережеться в студії.</p>`;
      setTimeout(poll,2000);return;
    }
    let error=data.status==='failed'?`<p class="episode-error">${esc(data.error||'Запит не завершено')}</p>`:'';
    if(data.status==='failed'&&data.project_id){
      root.innerHTML=error+'<button id="ideas-retry">Повторити запит</button>';
      root.querySelector('#ideas-retry').onclick=()=>request({action:data.stage,index:data.stage==='script'?data.openings.findIndex(r=>r.text===data.opening):data.selected_index});return;
    }
    if(data.openings){
      input.value=data.selected.title;
      root.innerHTML=error+`<h3>Виберіть зачин</h3><p class="muted">Opus напише сценарій приблизно на ${data.target_words.toLocaleString('uk-UA')} слів.</p><div class="episode-options">${data.openings.map((row,i)=>`<button data-opening="${i}"><strong>Варіант ${i+1}</strong><span>${esc(row.text)}</span>${row.uk?`<small>${esc(row.uk)}</small>`:''}</button>`).join('')}</div>`;
      root.querySelectorAll('[data-opening]').forEach(b=>b.onclick=()=>request({action:'script',index:Number(b.dataset.opening)}));return;
    }
    if(!data.ideas){request({action:'ideas'});return;}
    root.innerHTML=error+`<div class="episode-ideas-head"><strong><svg class="idea-provider-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-label="DeepSeek"><path d="M3 11c3-5 8-6 12-2l6-4-2 8c-1 6-10 8-14 3l-2-5Z"/><circle cx="12" cy="11" r=".6"/><path d="m15 15 3 4m-9-1-1 3"/></svg> Нові теми</strong><button class="secondary" id="ideas-refresh" title="Запросити інші ідеї" aria-label="Інші ідеї">↻</button></div><div class="episode-options">${data.ideas.map((row,i)=>`<button data-idea="${i}"><span><strong>${esc(row.title)}</strong>${row.uk?`<small>${esc(row.uk)}</small>`:''}</span></button>`).join('')}</div>`;
    root.querySelector('#ideas-refresh').onclick=()=>request({action:'ideas',refresh:true});
    root.querySelectorAll('[data-idea]').forEach(b=>b.onclick=()=>chooseTopic(data,Number(b.dataset.idea)));
  }
  try{draw(await api(endpoint));}catch(error){if(root.isConnected)root.innerHTML=`<p class="episode-error">${esc(error.message)}</p>`;}
}
