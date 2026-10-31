let agentDisplayedProject=null,agentPoll=null,agentRequesting=false,agentSettingsSaving=false,agentAppliedJob=null;

function renderAgent(){
  const panel=$('project-agent'),projectId=state.project?.id;
  if(!projectId)return;
  if(agentDisplayedProject===projectId && panel.querySelector('.agent-chat')){if(!agentPoll && !agentRequesting)refreshAgent(projectId);return;}
  if(agentPoll){clearTimeout(agentPoll);agentPoll=null;}
  agentDisplayedProject=projectId;
  panel.innerHTML=`<div class="agent-chat"><header class="agent-header"><div><span class="agent-eyebrow">ВАШ ПОМІЧНИК</span><h1>Агент проєкту</h1><p class="agent-subtitle">DeepSeek · OpenRouter</p></div><div class="agent-cost" id="agent-cost"></div></header><p class="agent-info">Агент отримує повідомлення, план і пам’ять каналу через OpenRouter. Запити платні, до 20 звернень до моделі за раз.</p><div class="agent-messages" id="agent-messages" aria-live="polite"></div><div class="agent-progress"><p id="agent-feedback" role="status"></p><button id="agent-cancel" class="secondary" type="button" hidden>Зупинити агента</button></div><div class="agent-composer"><label class="sr-only" for="agent-input">Повідомлення агенту</label><textarea id="agent-input" rows="3" maxlength="30000" placeholder="Напишіть, що потрібно зробити..."></textarea><div class="agent-composer-bottom"><label class="agent-image-permission"><input id="agent-allow-images" type="checkbox"><span>Генерація зображень <small>до 3 за запит · платно</small></span></label><button id="agent-send" class="primary" type="button">Надіслати <span aria-hidden="true">↑</span></button></div></div><p class="agent-hint">Enter - надіслати · Shift + Enter - новий рядок</p></div>`;
  const options=document.createElement('label');options.className='agent-reasoning';options.innerHTML='<span>Мислення</span><select id="agent-reasoning" disabled><option value="auto">Автоматично</option><option value="low">Low</option><option value="high">High</option><option value="max">Max</option></select>';
  $('agent-send').before(options);
  $('agent-reasoning').addEventListener('change',()=>saveAgentReasoning(projectId));
  $('agent-send').disabled=true;
  $('agent-send').addEventListener('click',()=>sendAgent(projectId));
  $('agent-input').addEventListener('keydown',event=>{if(event.key==='Enter' && !event.shiftKey && !event.isComposing && !event.ctrlKey && !event.altKey && !event.metaKey){event.preventDefault();if(!$('agent-send').disabled)sendAgent(projectId);}});
  $('agent-cancel').addEventListener('click',async()=>{try{await api(`/api/projects/${encodeURIComponent(projectId)}/agent/cancel`,'POST',{});refreshAgent(projectId);}catch(error){$('agent-feedback').textContent=error.message;}});
  refreshAgent(projectId);
}

async function refreshAgent(projectId){
  if(agentPoll){clearTimeout(agentPoll);agentPoll=null;}
  if(agentDisplayedProject!==projectId || state.project?.id!==projectId || state.view!=='agent')return;
  try{
    const data=await api(`/api/projects/${encodeURIComponent(projectId)}/agent`);
    if(agentDisplayedProject!==projectId || state.project?.id!==projectId || state.view!=='agent')return;
    const messages=$('agent-messages'),wasAtBottom=messages.scrollHeight-messages.scrollTop-messages.clientHeight<=48,previousScroll=messages.scrollTop;messages.replaceChildren();
    for(const item of data.messages || []){const row=document.createElement('div');row.className='agent-message '+(item.role==='user'?'user':'assistant');if(item.role!=='user'){const label=document.createElement('strong');label.textContent='Агент';row.append(label);}const text=document.createElement('p');text.textContent=item.content;row.append(text);messages.append(row);}
    if(!(data.messages || []).length)messages.innerHTML='<div class="agent-empty"><span aria-hidden="true">✦</span><strong>З чого почнемо?</strong><p>Напишіть агенту, що потрібно зробити в цьому проєкті.</p></div>';
    messages.scrollTop=wasAtBottom?messages.scrollHeight:previousScroll;
    const costs=data.costs || {},unknown=costs.unknown_count || 0;
    $('agent-cost').textContent=costs.request_count?`Зафіксовані витрати: $${Number(costs.known_total_usd || 0).toFixed(4)}${unknown?` · невідома вартість ${unknown} запитів`:''}`:'Витрати агента ще не зафіксовані.';
    const working=['queued','running','cancelling'].includes(data.job?.status);
    if(data.job?.id && !working && agentAppliedJob!==data.job.id){
      const latest=await api(`/api/projects/${encodeURIComponent(projectId)}`);
      if(agentDisplayedProject!==projectId || state.project?.id!==projectId || state.view!=='agent')return;
      state.project=latest.project;agentAppliedJob=data.job.id;
      const selection=data.job.selection;
      if(selection){
        const clips=new Set(state.project.tracks.flatMap(layer=>layer.clips.map(clip=>clip.id)));
        const ids=(selection.clip_ids || []).filter(id=>clips.has(id));
        state.selected=null;state.selectedGroup=null;state.selectedTransition=null;state.selectedStack=null;state.expandedGroup=null;
        state.multiSelection=ids;
        state.compactTimeline=false;
        const group=state.project.scene_groups?.find(group=>group.id===selection.group_ids?.[0]);
        if(group && selection.group_ids.length===1 && !selection.layer_ids?.length && ids.length===group.clip_ids.length){state.selectedGroup=group.id;state.compactTimeline=true;state.multiSelection=[];}
        state.activeLayer=selection.layer_ids?.find(id=>state.project.tracks.some(layer=>layer.id===id)) || state.activeLayer;
      }
      renderTimeline();renderInspector();renderPreview();
    }
    const reasoning=$('agent-reasoning');
    if(!agentSettingsSaving){reasoning.value=data.settings?.reasoning_effort || 'auto';reasoning.dataset.saved=reasoning.value;reasoning.dataset.loaded='true';}
    reasoning.disabled=working || agentRequesting || agentSettingsSaving;
    $('agent-send').disabled=working || agentRequesting || agentSettingsSaving || !reasoning.dataset.loaded;
    $('agent-cancel').hidden=!working;$('agent-cancel').disabled=data.job?.status==='cancelling';
    $('agent-feedback').textContent=data.job?.status==='cancelling'?'Зупиняємо агента після поточного запиту.':working?'Агент працює. Це може зайняти кілька хвилин.':data.job?.status==='failed'?data.job.error || 'Помилка агента.':data.job?.status==='cancelled'?'Агента зупинено. Уже зроблені зміни збережені.':'';
    if(working){agentPoll=setTimeout(()=>refreshAgent(projectId),2000);}
  }catch(error){if(agentDisplayedProject===projectId && state.view==='agent')$('agent-feedback').textContent=error.message;}
}

async function saveAgentReasoning(projectId){
  const select=$('agent-reasoning'), previous=select.dataset.saved || 'auto', effort=select.value;
  agentSettingsSaving=true;select.disabled=true;$('agent-send').disabled=true;
  try{
    const data=await api(`/api/projects/${encodeURIComponent(projectId)}/agent/settings`,'POST',{reasoning_effort:effort});
    if(agentDisplayedProject===projectId && state.view==='agent'){select.value=data.settings.reasoning_effort;select.dataset.saved=select.value;}
  }catch(error){
    if(agentDisplayedProject===projectId && state.view==='agent'){select.value=previous;$('agent-feedback').textContent=error.message;}
  }finally{
    agentSettingsSaving=false;
    if(agentDisplayedProject===projectId && state.view==='agent'){select.disabled=false;$('agent-send').disabled=false;}
  }
}

async function sendAgent(projectId){
  const text=$('agent-input').value.trim();if(!text){$('agent-feedback').textContent='Напишіть повідомлення агенту.';return;}
  const images=$('agent-allow-images').checked;agentRequesting=true;$('agent-send').disabled=true;$('agent-reasoning').disabled=true;$('agent-feedback').textContent='Надсилаємо...';
  try{
    await api(`/api/projects/${encodeURIComponent(projectId)}/agent/start`,'POST',{message:text,allow_images:images});
    if(agentDisplayedProject===projectId && state.view==='agent'){$('agent-input').value='';$('agent-allow-images').checked=false;}
  }catch(error){if(agentDisplayedProject===projectId && state.view==='agent')$('agent-feedback').textContent=error.message;agentRequesting=false;if(agentDisplayedProject===projectId && state.view==='agent'){$('agent-send').disabled=false;$('agent-reasoning').disabled=false;}return;}
  agentRequesting=false;refreshAgent(projectId);
}
