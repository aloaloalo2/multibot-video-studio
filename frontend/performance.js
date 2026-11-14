// Saved local work and billing only. Opening this panel never starts a job or a paid request.
const performanceWorkflows={openings:'Зачини',script:'Сценарій',metadata:'Метадані',narration:'Озвучка',analysis:'Розпізнавання озвучки',planning:'План кадрів',production:'Створення кадрів',export:'Експорт',translation:'Переклад',language_voice:'Озвучка перекладів'};
const performanceAliases={language_sample:'language_voice',language_save:'language_voice',language_refit:'language_voice'};
function performanceWorkflow(value){const key=performanceAliases[value]||value;return Object.hasOwn(performanceWorkflows,key)?key:null;}
function performanceTime(ms){
  // Minutes and hours only: 57 s reads as 1 хв, anything under half a minute as <1 хв.
  const value=Number(ms);
  if(!Number.isFinite(value)||value<=0)return '0 хв';
  const minutes=Math.round(value/60000);
  if(minutes<1)return '<1 хв';
  return minutes<60?`${minutes} хв`:`${Math.floor(minutes/60)} год${minutes%60?` ${minutes%60} хв`:''}`;
}
const performanceLost=new Set(['failed','cancelled','interrupted','unknown']);
function performanceRows(data){
  // Time comes from the saved runs, so a busy older backend shows the same honest split: finished, running and paused
  // runs are useful time, failed and interrupted attempts are listed apart.
  const order=Object.keys(performanceWorkflows),groups=new Map(),costs=new Map((data.processes||[]).map(row=>[row.workflow,row.cost]));
  for(const run of data.runs||[]){
    const workflow=performanceWorkflow(run.workflow);if(!workflow)continue;
    const row=groups.get(workflow)||{id:workflow,workflow,label:performanceWorkflows[workflow],active_ms:0,lost_ms:0,lost_runs:0,running:false,cost:costs.get(workflow)||{recorded:['analysis','export'].includes(workflow)}};
    const excluded=['queue','pause'].reduce((sum,key)=>sum+Math.max(0,Number(run.stages?.[key]?.ms)||0),0);
    const spent=Math.max(0,(Number(run.elapsed_ms)||0)-excluded);
    if(performanceLost.has(run.status)){row.lost_ms+=spent;row.lost_runs++;}else row.active_ms+=spent;
    row.running||=run.status==='running';groups.set(workflow,row);
  }
  return [...groups.values()].filter(row=>row.active_ms+row.lost_ms>1000).sort((a,b)=>order.indexOf(a.workflow)-order.indexOf(b.workflow));
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
  return {amount,approximate:amount>0&&(estimated||unknown),unknown,label:unknown&&!amount?'Немає даних':`${amount>0&&(estimated||unknown)?'≈ ':''}${money(amount)}${unknown&&amount?'+':''}`,title:notes.join(' ')||'Локальна обробка без витрат API.'};
}
const performanceIcons={
  openings:'<path d="M5 4h14M5 9h14M5 14h9"/><path d="m16 17 2 2 3-4"/>',
  script:'<path d="M7 3h8l4 4v14H7z"/><path d="M15 3v4h4M10 12h6M10 16h6"/>',
  metadata:'<path d="M4 12V5h7l9 9-7 7z"/><circle cx="8.5" cy="9.5" r="1.3"/>',
  narration:'<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M6 11a6 6 0 0 0 12 0M12 17v4"/>',
  analysis:'<path d="M3 12h2M7 8v8M11 5v14M15 9v6M19 11v2"/>',
  planning:'<rect x="3" y="4" width="7" height="7" rx="1.5"/><rect x="14" y="4" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="6" rx="1.5"/><rect x="14" y="14" width="7" height="6" rx="1.5"/>',
  production:'<rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="m3 15 5-4 4 3 3-2 6 5"/><circle cx="15.5" cy="9.5" r="1.4"/>',
  export:'<path d="M12 4v11M8 11l4 4 4-4M5 19h14"/>',
  translation:'<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>',
  language_voice:'<path d="M4 10v4h4l5 4V6L8 10z"/><path d="M16.5 9a4 4 0 0 1 0 6M19 6.5a8 8 0 0 1 0 11"/>',
};
function performanceIcon(workflow){return `<svg class="performance-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${performanceIcons[workflow]||'<circle cx="12" cy="12" r="8"/>'}</svg>`;}
function performanceMarkup(data){
  const rows=performanceRows(data);
  if(!rows.length)return '<p class="muted">Ще немає основних процесів тривалістю понад секунду.</p>';
  const money=value=>`$${value.toFixed(value>0&&value<.01?4:2)}`;
  const attempts=row=>row.lost_runs?`<small class="performance-lost">${row.active_ms>1000?'ще ':''}${esc(performanceTime(row.lost_ms))} у ${row.lost_runs===1?'невдалій спробі':row.lost_runs+' невдалих спробах'}</small>`:'';
  const line=row=>{const cost=performanceCost(row.cost);return `<div class="performance-row" role="row" data-id="${esc(row.id)}"><span class="performance-name" role="cell">${performanceIcon(row.workflow)}<span class="performance-label"><strong>${esc(row.label||performanceWorkflows[row.workflow])}${row.running?' <em>триває</em>':''}</strong>${attempts(row)}</span></span><span class="performance-duration" role="cell">${row.active_ms>1000?esc(performanceTime(row.active_ms)):'—'}</span><span class="performance-cost" role="cell" title="${esc(cost.title)}">${esc(cost.label)}</span></div>`;};
  const main=rows.filter(row=>row.active_ms>=60000),small=rows.filter(row=>row.active_ms<60000);
  let total=0,approximate=false,unknown=false;
  for(const row of rows){const cost=performanceCost(row.cost);if(row.cost?.recorded){total+=cost.amount||0;approximate||=!!cost.approximate;unknown||=!!cost.unknown;}}
  const time=rows.reduce((sum,row)=>sum+row.active_ms,0),lost=rows.reduce((sum,row)=>sum+row.lost_ms,0),smallTime=small.reduce((sum,row)=>sum+row.active_ms,0);
  const head='<div class="performance-columns" role="row"><span role="columnheader">Процес</span><span role="columnheader" title="Час вдалих запусків без черг і пауз. Паралельні процеси можуть виконуватись одночасно.">Час</span><span role="columnheader">Витрати</span></div>';
  return `<div class="performance-table" role="table" aria-label="Час і витрати за процесами">${head}${main.map(line).join('')}</div>`
    +(small.length?`<details class="performance-small"><summary><span>Менше хвилини · ${small.length}</span><span class="performance-duration">${esc(performanceTime(smallTime))}</span></summary><div class="performance-table" role="table" aria-label="Короткі процеси">${small.map(line).join('')}</div></details>`:'')
    +`<div class="performance-total"><strong>Разом</strong><span class="performance-duration">${esc(performanceTime(time))}</span><span class="performance-cost">${approximate?'≈ ':''}${money(total)}${unknown?'+':''}</span></div>`
    +`<p class="performance-note muted">${lost>1000?`Невдалі спроби: ще ${esc(performanceTime(lost))}, у підсумок не входять. `:''}Без прев’ю.</p>`;
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
