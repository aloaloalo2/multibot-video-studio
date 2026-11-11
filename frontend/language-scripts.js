// All translated scripts are available together, independently of the voice tab.
const langScriptDrafts=new Map();
const langScriptStarting=new Set();
let langScriptDialog=null;
const langTranslateIcon='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 5h12M9 3v2M5 5c1 5 4 8 9 10M13 5c-1 5-4 8-9 10M13 21l4-10 4 10m-6.7-3h5.4"/></svg>';
const langScriptCheck='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6"/></svg>';
const langCharactersIcon='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5h14M12 5v14M9 19h6"/></svg>';

function langShortCharacters(count){
  return count>=1000?`${(count/1000).toLocaleString('uk-UA',{maximumFractionDigits:1})}K`:String(count);
}
function langScriptCharacters(item){
  const count=item.display_chars;
  return Number.isInteger(count)&&count>0?`<span class="lang-script-characters" title="${count.toLocaleString('uk-UA')} порівняльних літер: без пробілів і пунктуації, з урахуванням чисел">${langCharactersIcon}${langShortCharacters(count)}${langScriptDifferenceMarkup(item)}</span>`:'';
}

function langScriptDifference(item){
  const value=item.translation_length?.number_comparison;
  if(!value?.available||!Number.isFinite(value.difference_percent))return null;
  const percent=value.difference_percent,limit=item.translation_length?.script_comparison?.tolerance_percent||7;
  return {label:`${percent>0?'+':''}${percent.toLocaleString('uk-UA',{maximumFractionDigits:2})}%`,over:Math.abs(percent)>limit,
    title:`З урахуванням чисел: ${value.translated_chars.toLocaleString('uk-UA')} проти ${value.source_chars.toLocaleString('uk-UA')} літер оригіналу. Орієнтир ±${limit}%.`};
}
function langScriptDifferenceMarkup(item){
  const value=langScriptDifference(item);
  return value?`<span class="lang-script-difference${value.over?' is-over':''}" title="${esc(value.title)}">(${esc(value.label)})</span>`:'';
}

function langScriptJob(code){
  return langJobs().filter(job=>job.code===code&&job.kind==='translate')
    .sort((a,b)=>(b.started_at||b.finished_at||0)-(a.started_at||a.finished_at||0))[0];
}

function langScriptCost(item){
  const cost=item.translate_cost;
  return typeof cost==='number'&&Number.isFinite(cost)&&cost>=0?`$${cost.toFixed(3)}`:'';
}

function langScriptLanguageWarning(item){
  const report=item.language_check;
  if(report?.state!=='blocked')return '';
  const phrases=(report.issues||[]).slice(0,8).map(issue=>issue.index+1).join(', ');
  return `Інша мова${phrases?` · фрази ${phrases}`:''}. Озвучення заблоковано`;
}
function langScriptWarningMarkup(item){
  const text=langScriptLanguageWarning(item);
  return `<span class="lang-script-language-warning" role="img" aria-label="${esc(text)}" title="${esc(text)}"${text?'':' hidden'}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 10 18H2L12 3zM12 9v5m0 3v.1"/></svg></span>`;
}

function langTranslationProgress(job,now=Date.now()/1000){
  if(typeof langStopping==='function'&&langStopping(job))return {label:'Скасовуємо…',detail:'Зберігаємо поточну відповідь. Нові запити не запускаємо.',progress:job.progress||0,indeterminate:true};
  const review=job.translation_review,comparison=job.translation_length?.phrase_comparison;
  const reviewing=job.status==='running'&&Number(job.progress)===95;
  let label='Перекладаємо',detail=job.stage||'Перекладаємо…';
  if(reviewing){
    label=({audit:'Перевірка',meaning:'Уточнення',length:'Узгодження',pacing:'Темп голосу',linguist:'Лінгвіст'})[review?.phase]||'Уточнення';
    const parts=[];
    if(comparison?.available&&Number.isInteger(comparison.total)&&Number.isInteger(comparison.outside_count)){
      parts.push(`Довжина узгоджена: ${comparison.total-comparison.outside_count} з ${comparison.total} фраз`);
    }
    const whole=job.translation_length?.script_comparison;
    if(whole?.available&&!whole.within_budget)parts.push(`Весь сценарій: ${whole.difference_percent>0?'+':''}${whole.difference_percent}% · ціль ±${whole.tolerance_percent}%`);
    if(review?.phase==='audit')parts.push(`Зміст перевірено: ${review.audited} з ${review.total} фраз`);
    if(review?.batch_size)parts.push(`Зараз опрацьовуємо ${review.batch_size} фраз`);
    // Compatibility with a job started before structured review progress existed.
    if(!review){
      const batch=(job.stage||'').match(/Уточнюємо переклад: готово \d+ з (\d+) фраз/);
      parts.push(batch?`Зараз опрацьовуємо ${batch[1]} фраз`:detail);
    }
    if(review?.waiting){
      const elapsed=Math.max(0,Math.floor(now-review.request_started_at));
      parts.push(`Очікуємо відповідь ${review.model_name||'MiniMax'} · ${Math.floor(elapsed/60)}:${String(elapsed%60).padStart(2,'0')}`);
    }else if(!review)parts.push('Очікуємо відповідь MiniMax');
    detail=parts.join(' · ');
  }
  // Keep one metric while audit/rewriting phases alternate. Switching to the
  // audit counter here made the same job appear to jump backwards repeatedly.
  const counted=comparison?.available?comparison.total-comparison.outside_count:null;
  const compact=reviewing&&Number.isInteger(counted)?`${counted}/${comparison.total}`:
    reviewing?'Очікуємо відповідь':`${Math.round(job.progress||0)}%`;
  return {label,detail,compact,progress:job.progress||0,indeterminate:reviewing};
}

function langScriptStatus(item){
  if(typeof state!=='undefined'&&langScriptStarting.has(`${state.project?.id}:${item.code}`))return {kind:'working',label:'Запускаємо переклад…',progress:0,indeterminate:true};
  const job=langScriptJob(item.code);
  if(job?.status==='running')return {kind:'working',...langTranslationProgress(job)};
  if(job?.status==='failed'||item.translation_resumable)return {kind:'attention',label:item.translation_resumable?'Переклад призупинено':'Переклад не завершено'};
  if(item.language_check&&item.language_check.state!=='ok')return {kind:'attention',label:'Потрібно оновити переклад'};
  return item.text?{kind:'ready',label:'Перекладено'}:{kind:'empty',label:'Перекласти'};
}

async function langActivateScript(id,code,button){
  if(state.project?.id!==id)return;
  const item=langData?.items.find(entry=>entry.code===code);if(!item)return;
  const key=`${id}:${code}`;if(langScriptStarting.has(key))return;
  if(item.text||item.translation_resumable||langRunning(code,'voice'))return langOpenScript(id,code);
  langScriptStarting.add(key);button.disabled=true;button.setAttribute('aria-busy','true');
  button.querySelector('.lang-script-status-label').textContent='Запускаємо переклад…';
  const progress=button.querySelector('progress');progress.hidden=false;progress.removeAttribute('value');
  try{await langStart(id,'translate',code);}
  finally{
    langScriptStarting.delete(key);button.disabled=false;button.removeAttribute('aria-busy');
    if(state.project?.id===id)langPaintScriptJobs();
  }
}

function langScriptLibrary(id,holder,data){
  holder.innerHTML=`<div class="lang-language-board"><div class="lang-original-slot"></div><div class="lang-translations-carousel"><div class="lang-script-grid">${data.items.map(item=>{
    const status=langScriptStatus(item);
    return `<div class="lang-language-column" data-language="${item.code}"><h3 class="lang-language-heading">${langFlag(item.code)}${esc(item.name)}</h3><div class="lang-script-entry"><button type="button" class="lang-script-file ${status.kind}" data-script-code="${item.code}" aria-label="${status.kind==='empty'?'Перекласти':'Відкрити переклад'}: ${esc(item.name)}" title="${esc(item.name)}: ${status.label}">
      <span class="lang-script-file-head">${langTranslateIcon}<strong>Переклад</strong><span class="lang-script-fold" aria-hidden="true"></span></span>
      <span class="lang-script-file-title">${esc(item.title||(status.kind==='working'?'Створюємо переклад сценарію…':'Сценарій ролика'))}</span>
      <span class="lang-script-metrics">${langScriptCharacters(item)}<span class="lang-script-job-detail" title="Фрази, узгоджені за довжиною"${status.kind==='working'?'':' hidden'}>${esc(status.compact||'')}</span></span>
      <span class="lang-script-file-status" title="Переклад сценарію"><span class="lang-script-complete"${status.kind==='ready'?'':' hidden'}>${langScriptCheck}</span>${langScriptWarningMarkup(item)}<span class="lang-script-cost" role="button" tabindex="0" aria-label="Вартість перекладу: ${esc(item.name)}"${status.kind!=='working'&&langScriptCost(item)?'':' hidden'}>${langScriptCost(item)}</span><span class="lang-script-status-label"${status.kind==='ready'?' hidden':''}>${status.label}</span></span>
      <progress max="100"${status.indeterminate?'':` value="${status.progress||0}"`}${status.kind==='working'?'':' hidden'}></progress></button><div class="lang-script-controls" data-script-controls="${item.code}"></div></div><button type="button" class="lang-language-remove" data-code="${item.code}" aria-label="Прибрати мову ${esc(item.name)}" title="Прибрати мову">${langIcons.trash}</button><div class="lang-setup-slot"></div></div>`;
  }).join('')}</div></div></div>`;
  holder.querySelectorAll('[data-script-code]').forEach(button=>{
    button.addEventListener('click',()=>langActivateScript(id,button.dataset.scriptCode,button));
    const cost=button.querySelector('.lang-script-cost');
    const open=event=>{event.preventDefault();event.stopPropagation();langOpenTranslationCost(id,button.dataset.scriptCode);};
    cost.addEventListener('click',open);cost.addEventListener('keydown',event=>{if(['Enter',' '].includes(event.key))open(event);});
  });
  holder.querySelectorAll('[data-language]').forEach(column=>{
    const item=data.items.find(entry=>entry.code===column.dataset.language);
    column.querySelector('.lang-setup-slot').replaceWith(langVoiceSummary(id,item));
    column.append(langVoiceTile(id,item));
    column.append(langThumbnailTile(id,item));
    column.querySelector('.lang-language-remove').onclick=()=>langRemoveLanguage(id,item.code);
  });
  holder.querySelector('.lang-original-slot').replaceWith(langOriginalColumn(id,data));

  langWireColumnScroll(holder.querySelector('.lang-translations-carousel'));
}

function langScriptAvailable(data){
  const ready=new Set(data.items.filter(item=>item.text).map(item=>item.code));
  return data.languages.filter(item=>item.code!==data.source.language&&!ready.has(item.code)&&!langRunning(item.code,'voice'));
}

async function langRequestTranslations(id,codes){
  // Each language has an independent server job. Never wait for one translation
  // to finish before starting the others, or retry a successful paid request.
  return Promise.all([...new Set(codes)].map(async code=>{
    try{
      const base=`/api/projects/${encodeURIComponent(id)}/languages/${code}`;
      const data=await api(base,'POST',{});
      const {job}=await api(`${base}/translate`,'POST',{});
      return {code,job,item:data.items.find(item=>item.code===code)};
    }catch(error){return {code,error:error.message};}
  }));
}

function langOpenScriptPicker(id){
  if(state.project?.id!==id||document.querySelector('.lang-script-picker'))return;
  const free=langScriptAvailable(langData);if(!free.length)return;
  const dialog=document.createElement('dialog');dialog.className='lang-script-picker';
  dialog.setAttribute('aria-labelledby','lang-script-picker-title');
  dialog.innerHTML=`<div class="lang-script-dialog-head"><h2 id="lang-script-picker-title">Виберіть мови перекладу</h2><button type="button" class="lang-script-close" aria-label="Закрити вибір мов">×</button></div>
    <div class="lang-script-language-list">${free.map(item=>`<label><input type="checkbox" value="${item.code}">${langFlag(item.code)}<span>${esc(item.name)}</span><small>${esc(item.label)}</small></label>`).join('')}</div>
    <div class="lang-script-picker-footer"><span class="lang-script-picked">Оберіть мови</span><button type="button" class="primary lang-script-batch" disabled>Перекласти</button></div><p class="lang-script-message" role="status"></p>`;
  let starting=false;
  const inputs=[...dialog.querySelectorAll('input')],run=dialog.querySelector('.lang-script-batch');
  const selected=()=>inputs.filter(input=>input.checked&&!input.disabled).map(input=>input.value);
  const sync=()=>{const count=selected().length;run.disabled=starting||!count;dialog.querySelector('.lang-script-picked').textContent=count?`Вибрано: ${count}`:'Оберіть мови';};
  dialog.addEventListener('change',sync);
  const close=()=>{if(!starting)dialog.close();};
  dialog.querySelector('.lang-script-close').onclick=close;
  dialog.addEventListener('click',event=>{if(event.target===dialog)close();});
  dialog.addEventListener('cancel',event=>{if(starting)event.preventDefault();});
  dialog.addEventListener('close',()=>dialog.remove(),{once:true});
  run.onclick=async()=>{
    if(starting)return;const codes=selected();if(!codes.length)return;
    starting=true;inputs.forEach(input=>input.disabled=true);run.disabled=true;run.textContent='Запускаємо…';
    dialog.querySelector('.lang-script-close').disabled=true;
    const results=await langRequestTranslations(id,codes);
    const failed=results.filter(result=>result.error),started=new Set(results.filter(result=>result.job).map(result=>result.code));
    // Keep accepted jobs visible even if the final overview refresh is offline.
    if(state.project?.id===id){
      for(const result of results.filter(result=>result.job)){
        if(result.item&&!langData.items.some(item=>item.code===result.code))langData.items.push(result.item);
        langData.jobs=[...langJobs().filter(job=>job.slot!==result.job.slot),result.job];
      }
      if(state.view==='langs')drawLangs(id);if(langBusy())pollLangs(id);
    }
    try{
      const data=await api(`/api/projects/${encodeURIComponent(id)}/languages`);
      if(state.project?.id===id){langData=data;if(state.view==='langs')drawLangs(id);if(langBusy())pollLangs(id);}
    }catch(error){failed.push({error:error.message});}
    starting=false;
    if(!failed.length){dialog.close();return;}
    inputs.forEach(input=>{input.disabled=started.has(input.value);if(input.disabled)input.checked=false;});
    dialog.querySelector('.lang-script-close').disabled=false;run.textContent='Перекласти';sync();
    const message=dialog.querySelector('.lang-script-message');message.classList.add('is-error');
    message.textContent=failed.map(result=>`${free.find(item=>item.code===result.code)?.name||''}: ${result.error}`).join('\n');
  };
  document.body.append(dialog);dialog.showModal();inputs[0]?.focus();
}

function langPaintScriptJobs(){
  document.querySelectorAll('#project-langs [data-script-code]').forEach(button=>{
    const item=langData?.items.find(entry=>entry.code===button.dataset.scriptCode);if(!item)return;
    const status=langScriptStatus(item);
    button.setAttribute('aria-label',`${status.kind==='empty'?'Перекласти':'Відкрити переклад'}: ${item.name}`);
    for(const kind of ['working','attention','ready','empty'])button.classList.toggle(kind,status.kind===kind);
    button.querySelector('.lang-script-status-label').textContent=status.label;
    button.querySelector('.lang-script-status-label').hidden=status.kind==='ready';
    button.querySelector('.lang-script-metrics').innerHTML=`${langScriptCharacters(item)}<span class="lang-script-job-detail"></span>`;
    const detail=button.querySelector('.lang-script-job-detail');
    detail.textContent=status.compact||'';detail.hidden=status.kind!=='working';
    button.querySelector('.lang-script-complete').hidden=status.kind!=='ready';
    const cost=button.querySelector('.lang-script-cost');cost.textContent=langScriptCost(item);cost.hidden=status.kind==='working'||!cost.textContent;
    const warning=button.querySelector('.lang-script-language-warning'),notice=langScriptLanguageWarning(item);
    warning.hidden=!notice;warning.title=notice;warning.setAttribute('aria-label',notice);
    const progress=button.querySelector('progress');progress.hidden=status.kind!=='working';
    if(status.indeterminate)progress.removeAttribute('value');else progress.value=status.progress||0;
    button.title=`${item.name}: ${status.label}${status.detail?' · '+status.detail:''}`;
  });
  document.querySelectorAll('#project-langs [data-script-controls]').forEach(controls=>{
    const job=langScriptJob(controls.dataset.scriptControls);
    controls.innerHTML=job?.status==='running'?langCancelButton(job):'';
    const cancel=controls.querySelector('button');
    if(cancel){cancel.title=cancel.disabled?'Скасовуємо переклад':'Скасувати переклад';cancel.setAttribute('aria-label',cancel.title);cancel.textContent='×';
      cancel.addEventListener('click',event=>langCancel(state.project.id,job.slot,event.currentTarget));}
  });
  langScriptDialog?.sync();
}

function langFlushScript(id,code){
  return langScriptDialog?.project===id&&langScriptDialog?.code===code?langScriptDialog.flush():Promise.resolve(true);
}

function langOpenScript(id,code){
  if(langScriptDialog)return;
  let item=langData?.items.find(entry=>entry.code===code);if(!item)return;
  const key=`${id}:${code}`,draft=langScriptDrafts.get(key);
  const dialog=document.createElement('dialog');dialog.className='lang-script-dialog';
  dialog.setAttribute('aria-labelledby','lang-script-dialog-title');
  dialog.innerHTML=`<div class="lang-script-dialog-head"><div>${langFlag(code)}<h2 id="lang-script-dialog-title">${esc(item.name)}</h2><span class="lang-script-dialog-status">${langTranslateIcon}<span></span></span></div><button type="button" class="lang-script-close" aria-label="Закрити сценарій">×</button></div>
    <div class="lang-script-dialog-body"><div class="lang-script-fields"><label class="lang-title"><span>Заголовок</span><input type="text" maxlength="200" value="${esc(draft?.title??item.title)}"></label>
      <label class="lang-text"><span>Текст озвучки <small class="lang-script-chars"></small><small class="lang-text-lines"></small></span><textarea rows="14" spellcheck="false">${esc(draft?.text??item.text)}</textarea></label></div>
      <p class="lang-script-empty">Створіть переклад заголовка та сценарію цією мовою.</p>
      <small class="lang-number-comparison"></small><small class="lang-translation-info"></small><div class="lang-text-quality"></div>
      <div class="lang-script-job" role="status" aria-live="polite"></div>
      <div class="lang-script-confirm" hidden><p>Перекласти сценарій заново? Поточні правки заміняться після завершення перекладу.</p><button type="button" class="secondary" data-confirm="no">Скасувати</button><button type="button" class="primary" data-confirm="yes">Перекласти заново</button></div></div>
    <div class="lang-script-dialog-footer"><span class="lang-script-message" role="status">Правки зберігаються автоматично</span><button type="button" class="secondary lang-script-translate">${langTranslateIcon}<span></span></button></div>`;
  const text=dialog.querySelector('textarea'),title=dialog.querySelector('input'),message=dialog.querySelector('.lang-script-message');
  const action=dialog.querySelector('.lang-script-translate'),confirm=dialog.querySelector('.lang-script-confirm');
  let baseline={text:item.text,title:item.title},timer=null,saving=null,closed=false,starting=false;
  const dirty=()=>text.value!==baseline.text||title.value!==baseline.title;
  const keepDraft=()=>{if(dirty())langScriptDrafts.set(key,{text:text.value,title:title.value});else langScriptDrafts.delete(key);};
  function metrics(){
    dialog.querySelector('.lang-script-chars').textContent=dirty()?'Оновлюємо підрахунок…':`${(item.display_chars??langLetters(text.value)).toLocaleString('uk-UA')} літер з урахуванням чисел`;
    const comparison=dialog.querySelector('.lang-number-comparison');comparison.textContent=langNumberComparison(item);comparison.hidden=dirty()||!comparison.textContent;
    const info=dialog.querySelector('.lang-translation-info');info.textContent=langTranslationInfo(item);info.hidden=!info.textContent;info.setAttribute('role','button');info.tabIndex=0;info.onclick=()=>langOpenTranslationCost(id,code);
    const lines=dialog.querySelector('.lang-text-lines');lines.textContent=item.lines?`${item.lines} рядків у таймінгах оригіналу. Змінюйте слова, зберігаючи кількість рядків.`:'';
  }
  function sync(){
    if(closed||state.project?.id!==id)return;
    const fresh=langData?.items.find(entry=>entry.code===code);
    if(fresh&&!dirty()&&!saving){
      item=fresh;baseline={text:item.text,title:item.title};text.value=item.text;title.value=item.title;
    }
    const busy=langRunning(code,'voice'),job=langScriptJob(code),status=langScriptStatus(item);
    text.readOnly=busy;title.readOnly=busy;action.disabled=busy||starting;
    action.hidden=busy||starting;
    action.classList.toggle('primary',!item.text);action.classList.toggle('secondary',!!item.text);
    action.title=item.translation_resumable?'Продовжує автоматичну перевірку й точкові виправлення. Це не схвалення тексту й не запуск озвучення.':'';
    action.querySelector('span').textContent=item.translation_resumable?'Продовжити переклад':item.text?'Перекласти заново':'Перекласти';
    dialog.querySelector('.lang-script-dialog-status span').textContent=status.label;
    dialog.querySelector('.lang-script-dialog-status').hidden=status.kind==='ready';
    dialog.querySelector('.lang-script-fields').hidden=!item.text&&!draft;
    dialog.querySelector('.lang-script-empty').hidden=!!item.text||!!draft;
    dialog.querySelector('.lang-text-quality').innerHTML=langQualityNotice(item.language_check);
    const jobBox=dialog.querySelector('.lang-script-job');
    jobBox.innerHTML=job?.status==='running'?`<span>${esc(status.detail)}</span><progress max="100"${status.indeterminate?'':` value="${status.progress}"`}></progress>${langCancelButton(job)}`:job?.status==='failed'?`<span class="lang-warn">${esc(job.error||'Не вдалося завершити переклад.')}</span>`:'';
    jobBox.hidden=!jobBox.innerHTML;
    jobBox.querySelector('button')?.addEventListener('click',event=>langCancel(id,job.slot,event.currentTarget));
    metrics();
  }
  const flush=()=>{
    clearTimeout(timer);
    if(saving)return saving;
    if(!dirty())return Promise.resolve(true);
    saving=(async()=>{
      while(dirty()){
        if(!text.value.trim()){message.textContent='Текст не може бути порожнім.';message.classList.add('is-error');return false;}
        const sent={text:text.value,title:title.value};message.textContent='Зберігаємо…';message.classList.remove('is-error');
        try{
          const data=await api(`/api/projects/${encodeURIComponent(id)}/languages/${code}/text`,'POST',sent);
          const fresh=data.items.find(entry=>entry.code===code);
          baseline={text:fresh.text,title:fresh.title};item=fresh;
          if(text.value===sent.text)text.value=fresh.text;if(title.value===sent.title)title.value=fresh.title;
          keepDraft();
          if(state.project?.id===id){langData=data;if(state.view==='langs')drawLangs(id);}
          metrics();
        }catch(error){message.textContent=error.message;message.classList.add('is-error');keepDraft();return false;}
      }
      message.innerHTML=`${langScriptCheck}Збережено`;return true;
    })().finally(()=>{saving=null;sync();});
    return saving;
  };
  async function close(){if(await flush()){closed=true;clearTimeout(timer);dialog.close();}}
  async function translate(){
    if(!(await flush()))return;
    confirm.hidden=true;starting=true;sync();await langStart(id,'translate',code);starting=false;sync();
  }
  action.addEventListener('click',async()=>{
    if(item.text&&!item.translation_resumable){if(await flush())confirm.hidden=false;}
    else translate();
  });
  dialog.querySelector('[data-confirm="no"]').onclick=()=>confirm.hidden=true;
  dialog.querySelector('[data-confirm="yes"]').onclick=translate;
  for(const field of [title,text])field.addEventListener('input',()=>{
    keepDraft();metrics();message.textContent='Зберігаємо…';clearTimeout(timer);timer=setTimeout(flush,1000);
  });
  dialog.querySelector('.lang-script-close').onclick=close;
  dialog.addEventListener('cancel',event=>{event.preventDefault();close();});
  dialog.addEventListener('click',event=>{if(event.target===dialog)close();});
  dialog.addEventListener('close',()=>{clearTimeout(timer);closed=true;dialog.remove();if(langScriptDialog?.element===dialog)langScriptDialog=null;},{once:true});
  langScriptDialog={project:id,code,element:dialog,flush,sync,error:error=>{message.textContent=error;message.classList.add('is-error');}};
  document.body.append(dialog);sync();dialog.showModal();dialog.querySelector('.lang-script-close').focus();
}

let langColumnResize=null;
function langWireColumnScroll(holder){
  langColumnResize?.disconnect();
  const grid=holder.querySelector('.lang-script-grid');
  const update=()=>{holder.classList.toggle('has-before',grid.scrollLeft>1);holder.classList.toggle('has-after',grid.scrollLeft+grid.clientWidth<grid.scrollWidth-2);};
  grid.addEventListener('scroll',update,{passive:true});
  langColumnResize=new ResizeObserver(update);langColumnResize.observe(grid);requestAnimationFrame(update);
}

async function langOpenTranslationCost(id,code){
  if(state.project?.id!==id)return;
  const item=langData.items.find(entry=>entry.code===code);if(!item)return;
  try{
    const cost=await api(`/api/projects/${encodeURIComponent(id)}/languages/${code}/cost`);
    if(state.project?.id!==id)return;
    const money=value=>`$${Number(value).toFixed(4)}`;
    const names={translation:'Переклад',title:'Заголовок',checks:'Перевірки',repairs:'Виправлення',unattributed:'Інші збережені витрати'};
    const rows=Object.entries(cost.categories).map(([key,value])=>`<div><span>${names[key]||esc(key)}</span><b>${money(value)}</b></div>`).join('');
    const models=Object.entries(cost.models).map(([key,value])=>`<div><span>${esc(key.toLowerCase().includes('deepseek')?'DeepSeek':key.toLowerCase().includes('minimax')?'MiniMax':key)}</span><b>${money(value)}</b></div>`).join('');
    document.querySelector('.lang-cost-dialog')?.close();
    const dialog=document.createElement('dialog');dialog.className='lang-script-dialog lang-cost-dialog';
    dialog.setAttribute('aria-label',`Вартість перекладу: ${item.name}`);
    dialog.innerHTML=`<div class="lang-script-dialog-head"><h2>Переклад · ${esc(item.name)}</h2><button type="button" class="lang-script-close" aria-label="Закрити вартість">×</button></div><div class="lang-script-dialog-body"><div class="lang-cost-breakdown">${rows}<hr>${models}<hr><div class="lang-cost-total"><strong>Усього за цю мову</strong><b>${money(cost.total_usd)}</b></div></div></div>`;
    dialog.querySelector('button').onclick=()=>dialog.close();dialog.addEventListener('click',event=>{if(event.target===dialog)dialog.close();});dialog.addEventListener('close',()=>dialog.remove(),{once:true});document.body.append(dialog);dialog.showModal();
  }catch(error){modal('Вартість перекладу',`<p>${esc(error.message)}</p>`,[]);}
}
