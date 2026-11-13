// Saved local work and billing only. Opening this panel never starts a job or a paid request.
const performanceWorkflows={openings:'Зачини',script:'Сценарій',metadata:'Метадані',narration:'Озвучка',analysis:'Розпізнавання озвучки',planning:'План кадрів',production:'Створення кадрів',export:'Експорт',translation:'Переклад',language_voice:'Озвучка перекладів'};
const performanceAliases={language_sample:'language_voice',language_save:'language_voice',language_refit:'language_voice'};
function performanceWorkflow(value){const key=performanceAliases[value]||value;return Object.hasOwn(performanceWorkflows,key)?key:null;}
function performanceTime(ms){
  const value=Number(ms);
  if(!Number.isFinite(value)||value<0)return '0 с';
  const seconds=Math.round(value/1000);
  if(seconds<60)return seconds<1&&value>0?'<1 с':`${seconds} с`;
  const minutes=Math.floor(seconds/60),rest=seconds%60;
  return minutes<60?`${minutes} хв${rest?` ${rest} с`:''}`:`${Math.floor(minutes/60)} год ${minutes%60} хв`;
}
function performanceRows(data){
  if(Array.isArray(data.processes))return data.processes.filter(row=>performanceWorkflow(row.workflow)&&Number(row.active_ms)>1000).sort((a,b)=>b.active_ms-a.active_ms||String(a.label).localeCompare(String(b.label),'uk'));
  // A busy older backend can keep running while the new static UI is already available.
  const groups=new Map();
  for(const run of data.runs||[]){
    const workflow=performanceWorkflow(run.workflow);if(!workflow)continue;
    const row=groups.get(workflow)||{id:workflow,workflow,label:performanceWorkflows[workflow],active_ms:0,cost:{recorded:['analysis','export'].includes(workflow)}};
    const excluded=['queue','pause'].reduce((sum,key)=>sum+Math.max(0,Number(run.stages?.[key]?.ms)||0),0);
    row.active_ms+=Math.max(0,(Number(run.elapsed_ms)||0)-excluded);groups.set(workflow,row);
  }
  return [...groups.values()].filter(row=>row.active_ms>1000).sort((a,b)=>b.active_ms-a.active_ms||a.label.localeCompare(b.label,'uk'));
}
function performanceCost(cost){
  if(!cost?.recorded)return {label:'Немає даних',title:'Збережених витрат для цього процесу ще немає.'};
  let amount=0,estimated=false,unknown=false;const notes=[];
  const divisor=typeof claudeSubscriptionDivisor==='number'?claudeSubscriptionDivisor:35;
  const money=value=>`$${value.toFixed(value>0&&value<.001?6:value>0&&value<.01?4:2)}`;
  const names={claude_code:'Claude Code',openrouter:'OpenRouter',heygen:'HeyGen',fishaudio:'Fish Audio',elevenlabs:'ElevenLabs'};
  for(const [provider,row] of Object.entries(cost.providers||{})){
    if(!row.requests&&!row.unknown)continue;
    const value=typeof row.usd==='number'&&Number.isFinite(row.usd)?Math.max(0,row.usd):null;
    if(row.unknown||value===null)unknown=true;
    if(value!==null){amount+=provider==='claude_code'?value/divisor:value;estimated||=!!row.estimated||provider==='claude_code';}
    if(provider==='claude_code'&&value!==null)notes.push(`Claude Code: API-еквівалент ${money(value)} ÷ ${divisor}, орієнтовна частка підписки.`);
    else notes.push(`${names[provider]||provider}: ${value===null?'вартість невідома':money(value)}.`);
  }
  const tokens=cost.tokens||{},labels={input:'вхід',output:'вихід',cache_read:'читання кешу',cache_write:'запис кешу'};
  const parts=Object.entries(labels).filter(([key])=>Number(tokens[key])>0).map(([key,label])=>`${label} ${Number(tokens[key]).toLocaleString('uk-UA')}`);
  if(parts.length)notes.push('Токени: '+parts.join(', ')+'.');
  if(unknown)notes.push('Частину витрат не виміряно.');
  return {label:unknown&&!amount?'Немає даних':`${amount>0&&(estimated||unknown)?'≈ ':''}${money(amount)}${unknown&&amount?'+':''}`,title:notes.join(' ')||'Локальна обробка без витрат API.'};
}
function performanceMarkup(data){
  const rows=performanceRows(data);
  if(!rows.length)return '<p class="muted">Ще немає основних процесів тривалістю понад секунду.</p>';
  return `<div class="performance-table" role="table" aria-label="Час і витрати за процесами"><div class="performance-columns" role="row"><span role="columnheader">Процес</span><span role="columnheader" title="Сума виміряного часу запусків без черг і пауз. Паралельні процеси можуть виконуватись одночасно.">Час</span><span role="columnheader">Витрати</span></div>${rows.map(row=>{const cost=performanceCost(row.cost);return `<div class="performance-row" role="row" data-id="${esc(row.id)}"><strong role="cell">${esc(row.label||performanceWorkflows[row.workflow])}</strong><span class="performance-duration" role="cell">${esc(performanceTime(row.active_ms))}</span><span class="performance-cost" role="cell" title="${esc(cost.title)}">${esc(cost.label)}</span></div>`;}).join('')}</div><p class="performance-note muted">Без черг, пауз і прев’ю.</p>`;
}
function updatePerformanceButton(){const button=$('project-performance');if(button)button.hidden=!state.project;}
function openPerformance(){
  const pid=state.project?.id,navigation=state.navigation;if(!pid)return;
  modal('Час роботи','<div class="performance-panel"><p class="muted">Завантажуємо…</p></div>');
  const generation=state.modalGeneration,body=$('modal-body'),panel=body.querySelector('.performance-panel');
  let timer=null,disposed=false;
  const current=()=>!disposed&&panel.isConnected&&state.project?.id===pid&&state.navigation===navigation&&state.modalGeneration===generation;
  body.channelSettingsCleanup=()=>{disposed=true;clearTimeout(timer);};
  const read=async()=>{
    if(!current())return;
    try{
      const data=await api(`/api/projects/${encodeURIComponent(pid)}/performance`);if(!current())return;
      const markup=performanceMarkup(data);if(panel._markup!==markup){panel.innerHTML=markup;panel._markup=markup;}
      const running=typeof data.running==='boolean'?data.running:(data.runs||[]).some(row=>performanceWorkflow(row.workflow)&&row.status==='running');
      if(running)timer=setTimeout(read,3000);
    }catch{
      if(current()){panel.innerHTML='<p class="muted">Не вдалося прочитати час роботи. Повторюємо…</p>';delete panel._markup;timer=setTimeout(read,5000);}
    }
  };
  read();
}
$('project-performance')?.addEventListener('click',openPerformance);
updatePerformanceButton();
