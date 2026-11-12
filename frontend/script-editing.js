function scriptEditingCost(data){
  const value=typeof data.cost_usd==='number'?data.cost_usd:data.known_cost_usd;
  if(typeof value!=='number')return 'Витрата невідома';
  const label=data.provider==='claude_code'?`≈$${(value/35).toFixed(6)} (API $${value.toFixed(6)})`:`$${value.toFixed(6)}`;
  return label+(data.cost_usd==null&&data.unknown_request_costs?' + невідома частина':'');
}
const scriptEditingIcon='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M13.5 5.5 18.5 10.5M4 20l4.5-1 12-12a2.1 2.1 0 0 0-4-4l-12 12L4 20Z"/><path d="M12 20h8"/></svg>';
function createScriptEditingButton(project){
  const button=document.createElement('button');button.type='button';button.className='history-button outline script-editing-open';button.innerHTML=scriptEditingIcon;button.disabled=true;
  const describe=text=>{button.title=text;button.setAttribute('aria-label',text);};
  describe('Редактури сценарію ще немає');
  button.onclick=()=>{if(!button.disabled)openScriptEditing(project);};
  api(`/api/projects/${project.id}/script-editing/status`).then(data=>{
    if(!button.isConnected||state.project?.id!==project.id)return;
    button.disabled=!data.available;
    describe(data.available?'Редактура сценарію':'Редактури сценарію ще немає');
  }).catch(()=>{if(button.isConnected)describe('Не вдалося перевірити наявність редактури');});
  return button;
}
function scriptEditingTokens(tokens,side){
  return (tokens||[]).map(part=>part.changed?`<${side==='before'?'del':'ins'}>${esc(part.text)}</${side==='before'?'del':'ins'}>`:esc(part.text)).join('');
}
function scriptEditingAssessment(report){
  if(!report)return '';
  const labels={clarity:'Зрозумілість на слух',grammar:'Граматика й синтаксис',naturalness:'Природність',logic:'Логіка й структура',originality:'Відсутність шаблонності',title_promise:'Обіцянка заголовка'};
  const scores=Object.entries(labels).map(([key,label])=>{
    const cell=row=>`<td>${esc(row?.score??'?')}/10<br><small>${esc(row?.reason||'')}</small></td>`;
    return `<tr><td>${label}</td>${cell(report.before_scores?.[key])}${report.intermediate_scores?cell(report.intermediate_scores[key]):''}${cell(report.after_scores?.[key])}</tr>`;
  }).join('');
  const list=(heading,items,format)=>items?.length?`<h4>${heading}</h4><ul>${items.map(row=>`<li>${format(row)}</li>`).join('')}</ul>`:'';
  return `<details class="script-editing-assessment"><summary>Оцінки та редакторський звіт Opus</summary><p class="muted">Суб’єктивна самооцінка автора. Вона не є незалежною перевіркою фактів або гарантією якості.</p><table class="script-editing-requests"><thead><tr><th>Критерій</th><th>Чернетка</th>${report.intermediate_scores?'<th>Після основної редактури</th>':''}<th>Фінал</th></tr></thead><tbody>${scores}</tbody></table>`+
    list('Знайдені слабкі місця',report.weaknesses,row=>`${esc(row.location)}: ${esc(row.problem)}`)+
    list('Приклади правок',report.changes,row=>`${row.comparison_verified===false?'Цитати потребують звірки. ':''}Було: «${esc(row.before)}». Стало: «${esc(row.after)}». ${esc(row.reason)}`)+
    list('Невирішені питання',report.unresolved,row=>`${esc(row.location)}: ${esc(row.issue)}${row.needs_fact_check?' · Потрібна перевірка фактів':''}`)+'</details>';
}
function scriptEditingRefinement(report){
  if(!report)return '';
  const list=(heading,items,format)=>items?.length?`<h4>${heading}</h4><ul>${items.map(row=>`<li>${format(row)}</li>`).join('')}</ul>`:'';
  return '<details><summary>Що доопрацьовано після оцінки основної редакції</summary>'+`<p>${esc(report.summary||'')}</p>`+
    list('Залишкові слабкі місця після основного проходу',report.remaining_weaknesses,row=>`${esc(row.location)}: ${esc(row.problem)}`)+
    list('Цільові правки до фіналу',report.actions,row=>`Було: «${esc(row.before)}». Стало: «${esc(row.after)}». ${esc(row.reason)}${row.comparison_verified===false?' · Цитати потребують звірки':''}`)+'</details>';
}
function scriptEditingReceiptRows(data){
  const phaseName={main:'Основний слоп-чек',refinement:'Оцінка й доопрацювання'};
  return (data.requests||[]).map(item=>{
    const usage=item.usage||{},input=usage.prompt_tokens??(usage.input_tokens!=null?usage.input_tokens+(usage.cache_read_input_tokens||0)+(usage.cache_creation_input_tokens||0):'?');
    return `<tr><td>${item.phase?esc(phaseName[item.phase]||item.phase):Number(item.paragraph_id)}</td><td>${esc(item.request_id||item.attempt_id||'Чек недоступний')}</td><td>${input} / ${usage.completion_tokens??usage.output_tokens??'?'}</td><td>${usage.completion_tokens_details?.reasoning_tokens??usage.output_tokens_details?.thinking_tokens??'невідомо'}</td><td>${esc(scriptEditingCost(item))}</td></tr>`;
  }).join('');
}
async function openScriptEditing(project,identity=null){
  const pid=project.id,navigation=state.navigation;
  modal('Редактура сценарію','<div class="script-editing-report"><p class="muted">Завантажуємо звіт…</p></div>',[]);
  const generation=state.modalGeneration,root=$('modal-body').querySelector('.script-editing-report');
  const current=()=>root.isConnected&&state.project?.id===pid&&state.navigation===navigation&&state.modalGeneration===generation;
  try{
    const data=await api(`/api/projects/${pid}/script-editing${identity?'/'+identity:''}`);if(!current())return;
    if(!data.available){root.innerHTML='<p class="muted">Редактура з’явиться тут після написання нового сценарію. Готові попередні випуски автоматично не змінюються.</p>';return;}
    const editorName=data.provider==='claude_code'?'Opus, саморедактура':'DeepSeek (історичний звіт)';
    const amount=scriptEditingCost(data);
    const statusLabel={running:'Редагування триває',done:'Редакція готова',failed:'Редагування не завершено',cancelled:'Редагування зупинено'}[data.status]||data.status;
    root.innerHTML=`<div class="script-editing-summary"><strong>${esc(statusLabel)}</strong><span>${esc(editorName)} · ${esc(amount)}</span><span>${data.before_words??'невідомо'} → ${data.after_words??'невідомо'} слів</span><span>Змінено ${data.comparison_unit==='fragment'?'фрагментів':'абзаців'}: ${data.changed_paragraphs||0} · Видалено: ${data.deleted_paragraphs||0}</span>${data.total_paragraphs?`<span>Перевірено ${data.completed_paragraphs||0} з ${data.total_paragraphs} · Окремих запитів: ${data.requests?.length||0}${data.reused_paragraphs?` · Відновлено: ${data.reused_paragraphs}`:''}</span><span>Міркування: ${esc(data.reasoning_effort||'невідомо')}</span>`:''}</div>${data.required_passes?`<p class="muted">Завершено етапів: ${Number(data.completed_passes||0)} з ${Number(data.required_passes)}</p>`:''}${data.error?`<p class="episode-error" role="alert">${esc(data.error)}</p>`:''}${data.status==='done'&&!data.matches_current?'<p class="muted">Поточний текст відрізняється від цієї редакції. Звіт зберігає результат саме цього запуску.</p>':''}${data.editorial_summary?`<p class="script-editing-reason">${esc(data.editorial_summary)}</p>`:''}${data.provider==='claude_code'?'<p class="muted">Витрата Claude показана як приблизний розподіл підписки: API-еквівалент ÷ 35. Чек містить API-еквівалент, це не окреме списання з балансу.</p>':''}<p class="muted">Вилучений текст підсвічено червоним, доданий зеленим.</p><label class="check"><input type="checkbox" class="script-editing-only-changed" checked>Показувати лише змінені абзаци</label><div class="script-editing-rows"></div>`;
    const assessment=scriptEditingAssessment(data.editorial_report);
    if(assessment)root.insertAdjacentHTML('beforeend',assessment);
    const refinement=scriptEditingRefinement(data.refinement_report);if(refinement)root.insertAdjacentHTML('beforeend',refinement);
    if(data.intermediate)root.insertAdjacentHTML('beforeend',`<details><summary>Збережена основна редакція перед доопрацюванням · ${Number(data.intermediate_words)} слів</summary><div class="script-editing-intermediate">${esc(data.intermediate)}</div></details>`);
    if(data.runs?.length>1){
      const label=document.createElement('label');label.textContent='Запуск редактора';const select=document.createElement('select');
      for(const run of data.runs){const option=document.createElement('option');option.value=run.id;option.textContent=new Date(run.started_at*1000).toLocaleString('uk-UA')+' · '+scriptEditingCost(run);option.selected=run.id===data.id;select.append(option);}
      select.onchange=()=>openScriptEditing(project,select.value);label.append(select);root.prepend(label);
      const total=document.createElement('p');total.className='muted';total.textContent='Усі запуски: '+(data.cost_totals||[]).map(item=>(item.provider==='claude_code'?'Opus: ':'DeepSeek: ')+scriptEditingCost(item)).join('; ')+(data.unknown_charges?' + невідомі витрати':'');root.append(total);
    }
    const rows=root.querySelector('.script-editing-rows'),toggle=root.querySelector('.script-editing-only-changed');
    function render(){
      const selected=(data.paragraphs||[]).filter(row=>!toggle.checked||row.changed);
      rows.innerHTML=selected.length?selected.map(row=>`<article class="script-editing-paragraph"><header>${data.comparison_unit==='fragment'?'Фрагмент':'Абзац'} ${row.id}${row.status==='pending'?' · Очікує перевірки':!row.after?' · Видалено':''}</header>${row.status==='done'&&data.total_paragraphs?`<small class="script-editing-paragraph-cost">${typeof row.cost_usd==='number'?'$'+row.cost_usd.toFixed(6):'Витрата невідома'}${row.reused_from_run?' · З попереднього запуску, повторно не оплачено':''}</small>`:''}${row.reason?`<p class="script-editing-reason">${esc(row.reason)}${row.criteria?.length?` · Критерії ${row.criteria.map(Number).join(', ')}`:''}</p>`:''}<div class="script-editing-columns"><section><h4>Було</h4><div>${scriptEditingTokens(row.before_tokens,'before')}</div></section><section><h4>Стало</h4><div>${row.after?scriptEditingTokens(row.after_tokens,'after'):'<span class="muted">Абзац вилучено</span>'}</div></section></div></article>`).join(''):'<p class="muted">Змінених абзаців немає. Вимкніть фільтр, щоб переглянути весь текст.</p>';
      if(!(data.paragraphs||[]).length)rows.innerHTML=`<div class="script-editing-columns"><section><h4>Збережений оригінал</h4><div>${esc(data.before||'')}</div></section>${data.after?`<section><h4>Збережена редакція</h4><div>${esc(data.after)}</div></section>`:''}</div>`;
    }
    toggle.onchange=render;render();
    if(['failed','cancelled'].includes(data.status)&&data.mode==='author_self_review_v1'){
      const retry=document.createElement('button');retry.type='button';retry.className='secondary';retry.textContent='Повторити саморедактуру · Opus';
      retry.onclick=async()=>{retry.disabled=true;try{await api(`/api/projects/${pid}/episode-draft`,'POST',{action:'editing',request_id:crypto.randomUUID()});if(!current())return;closeModal();await refreshProjects();status('Opus продовжує саморедактуру у сесії автора.');}catch(error){if(current()){retry.disabled=false;const note=document.createElement('p');note.className='episode-error';note.textContent=error.message;root.append(note);}}};root.append(retry);
    }
    const details=document.createElement('details');details.className='script-editing-receipt';details.innerHTML=`<summary>Дані запиту й витрати</summary><p>${esc(data.model||'DeepSeek')} · ${esc(data.reasoning_effort||'')}</p>${data.session_id?`<p>Сесія автора: ${esc(data.session_id)}</p>`:''}<p>${data.requests?'Запуск':'Запит'}: ${esc(data.request_id||data.id)}</p><p>Вхідні токени: ${data.usage?.prompt_tokens??(data.usage?.input_tokens!=null?data.usage.input_tokens+(data.usage.cache_creation_input_tokens||0)+(data.usage.cache_read_input_tokens||0):'невідомо')} · Вихідні: ${data.usage?.completion_tokens??data.usage?.output_tokens??'невідомо'}</p>`;if(data.requests?.length){
      const table=document.createElement('table');table.className='script-editing-requests';
      table.innerHTML='<thead><tr><th>'+(data.required_passes?'Етап':'Абзац')+'</th><th>Запит</th><th>Вхідні / вихідні токени</th><th>Токени міркування</th><th>Витрата</th></tr></thead><tbody>'+scriptEditingReceiptRows(data)+'</tbody>';
      details.append(table);
    }
    root.append(details);
  }catch(error){if(current())root.textContent=error.message;}
}
