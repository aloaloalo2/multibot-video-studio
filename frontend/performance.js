// This panel reads saved local timings only. It never starts production work.
function performanceTime(ms){
  const value=Number(ms);
  if(!Number.isFinite(value)||value<0)return '0 с';
  const seconds=Math.round(value/1000);
  if(seconds<60)return seconds<1&&value>0?'<1 с':`${seconds} с`;
  const minutes=Math.floor(seconds/60),rest=seconds%60;
  return minutes<60?`${minutes} хв${rest?` ${rest} с`:''}`:`${Math.floor(minutes/60)} год ${minutes%60} хв`;
}
function performanceBars(values,labels){
  const rows=Object.entries(labels).map(([key,label])=>({key,label,ms:Number(values?.[key])||0})).filter(row=>row.ms>0);
  const longest=Math.max(...rows.map(row=>row.ms),1);
  return `<div class="performance-stages">${rows.map(row=>`<div class="performance-stage"><span>${esc(row.label)}</span><strong>${esc(performanceTime(row.ms))}</strong><span class="performance-bar" aria-hidden="true"><i style="width:${Math.max(1,100*row.ms/longest).toFixed(2)}%"></i></span></div>`).join('')}</div>`;
}
function performanceMarkup(data){
  if(!data.runs?.length)return '<p class="muted">Час з’явиться після наступного запуску задачі.</p>';
  const statuses={running:'Триває',complete:'Готово',failed:'Помилка',cancelled:'Скасовано',stopped:'Зупинено',interrupted:'Перервано',unknown:'Статус невідомий'};
  return `<div class="performance-summary"><span class="muted">Час задач · ${data.runs.length}</span><span class="muted" title="Паралельні задачі можуть виконуватись одночасно. Тут додається час кожної задачі.">Сума окремих запусків</span></div>${performanceBars(data.stage_totals_ms,data.stages)}<div class="performance-runs">${data.runs.map(row=>`<details class="performance-run"><summary><span><strong>${esc(data.workflows[row.workflow]||row.workflow)}${row.language?` · ${esc(row.language.toUpperCase())}`:''}</strong><small class="muted">${esc(statuses[row.status]||statuses.unknown)}${row.active_stage?` · ${esc(data.stages[row.active_stage]||'')}`:''}</small></span><strong>${esc(performanceTime(row.elapsed_ms))}</strong></summary>${performanceBars(Object.fromEntries(Object.entries(row.stages||{}).map(([key,value])=>[key,value.ms])),data.stages)}</details>`).join('')}</div>`;
}
function updatePerformanceButton(){
  const button=$('project-performance');
  if(button)button.hidden=!state.project;
}
function openPerformance(){
  const pid=state.project?.id,navigation=state.navigation;
  if(!pid)return;
  modal('Час роботи','<div class="performance-panel"><p class="muted">Завантажуємо…</p></div>');
  const generation=state.modalGeneration,body=$('modal-body'),panel=body.querySelector('.performance-panel');
  let timer=null,disposed=false;
  const current=()=>!disposed&&panel.isConnected&&state.project?.id===pid&&state.navigation===navigation&&state.modalGeneration===generation;
  body.channelSettingsCleanup=()=>{disposed=true;clearTimeout(timer);};
  const read=async()=>{
    if(!current())return;
    try{
      const data=await api(`/api/projects/${encodeURIComponent(pid)}/performance`);
      if(!current())return;
      const opened=[...panel.querySelectorAll('.performance-run[open]')].map(element=>element.dataset.id);
      panel.innerHTML=performanceMarkup(data);
      panel.querySelectorAll('.performance-run').forEach((element,index)=>{element.dataset.id=data.runs[index].id;element.open=opened.includes(element.dataset.id);});
      if(data.runs.some(row=>row.status==='running'))timer=setTimeout(read,3000);
    }catch{
      if(current()){panel.innerHTML='<p class="muted">Не вдалося прочитати час роботи. Повторюємо…</p>';timer=setTimeout(read,5000);}
    }
  };
  read();
}
$('project-performance')?.addEventListener('click',openPerformance);
updatePerformanceButton();
