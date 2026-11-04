// All translated scripts are available together, independently of the voice tab.
const langScriptDrafts=new Map();
let langScriptDialog=null;
const langTranslateIcon='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 5h12M9 3v2M5 5c1 5 4 8 9 10M13 5c-1 5-4 8-9 10M13 21l4-10 4 10m-6.7-3h5.4"/></svg>';
const langScriptCheck='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6"/></svg>';

function langScriptJob(code){
  return langJobs().filter(job=>job.code===code&&job.kind==='translate')
    .sort((a,b)=>(b.started_at||b.finished_at||0)-(a.started_at||a.finished_at||0))[0];
}

function langScriptStatus(item){
  const job=langScriptJob(item.code);
  if(job?.status==='running')return {kind:'working',label:'Перекладаємо',detail:job.stage||'',progress:job.progress||0};
  if(job?.status==='failed'||item.translation_resumable)return {kind:'attention',label:item.translation_resumable?'Переклад призупинено':'Перевірити переклад'};
  if(item.language_check&&item.language_check.state!=='ok')return {kind:'attention',label:'Потрібна перевірка'};
  return item.text?{kind:'ready',label:'Перекладено'}:{kind:'empty',label:'Перекласти'};
}

function langScriptLibrary(id,holder,data){
  holder.innerHTML=`<div class="lang-script-grid">${data.items.map(item=>{
    const status=langScriptStatus(item);
    return `<button type="button" class="lang-script-file ${status.kind}" data-script-code="${item.code}" aria-label="Відкрити сценарій: ${esc(item.name)}" title="${esc(item.name)}: ${status.label}">
      <span class="lang-script-file-head">${langFlag(item.code)}<span class="lang-script-fold" aria-hidden="true"></span></span>
      <strong>${esc(item.name)}</strong><span class="lang-script-file-title">${esc(item.title||'Сценарій ролика')}</span>
      <span class="lang-script-file-status">${langTranslateIcon}<span>${status.label}</span></span>
      <progress max="100" value="${status.progress||0}"${status.kind==='working'?'':' hidden'}></progress></button>`;
  }).join('')}<button type="button" class="lang-script-add" aria-label="Додати мову перекладу"><span aria-hidden="true">+</span>Додати мову</button></div>`;
  holder.querySelectorAll('[data-script-code]').forEach(button=>button.addEventListener('click',()=>langOpenScript(id,button.dataset.scriptCode)));
  const used=new Set(data.items.map(item=>item.code));
  const free=data.languages.filter(item=>!used.has(item.code)&&item.code!==data.source.language);
  holder.querySelector('.lang-script-add').hidden=!free.length;
  holder.querySelector('.lang-script-add').addEventListener('click',()=>{
    const dialog=document.createElement('dialog');dialog.className='lang-script-picker';
    dialog.innerHTML=`<div class="lang-script-dialog-head"><h2>Додати мову</h2><button type="button" class="lang-script-close" aria-label="Закрити">×</button></div><div class="lang-script-language-list">${free.map(item=>`<button type="button" data-code="${item.code}">${langFlag(item.code)}<span>${esc(item.name)}</span><small>${esc(item.label)}</small></button>`).join('')}</div><p class="lang-script-message" role="status"></p>`;
    document.body.append(dialog);dialog.showModal();
    dialog.querySelector('.lang-script-close').onclick=()=>dialog.close();
    dialog.addEventListener('click',event=>{if(event.target===dialog)dialog.close();});
    dialog.addEventListener('close',()=>dialog.remove(),{once:true});
    dialog.querySelector('.lang-script-language-list').addEventListener('click',async event=>{
      const button=event.target.closest('[data-code]');if(!button)return;
      dialog.querySelectorAll('[data-code]').forEach(entry=>entry.disabled=true);
      try{
        const result=await api(`/api/projects/${encodeURIComponent(id)}/languages/${button.dataset.code}`,'POST',{});
        dialog.close();if(state.project?.id!==id)return;
        langData=result;langChoose(id,button.dataset.code);drawLangs(id);langOpenScript(id,button.dataset.code);
      }catch(error){dialog.querySelector('.lang-script-message').textContent=error.message;dialog.querySelectorAll('[data-code]').forEach(entry=>entry.disabled=false);}
    });
  });
}

function langPaintScriptJobs(){
  document.querySelectorAll('#project-langs [data-script-code]').forEach(button=>{
    const item=langData?.items.find(entry=>entry.code===button.dataset.scriptCode);if(!item)return;
    const status=langScriptStatus(item);
    for(const kind of ['working','attention','ready','empty'])button.classList.toggle(kind,status.kind===kind);
    button.querySelector('.lang-script-file-status span').textContent=status.label;
    const progress=button.querySelector('progress');progress.hidden=status.kind!=='working';progress.value=status.progress||0;
    button.title=`${item.name}: ${status.label}${status.detail?' · '+status.detail:''}`;
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
    dialog.querySelector('.lang-script-chars').textContent=`${text.value.length.toLocaleString('uk-UA')} символів`;
    const comparison=dialog.querySelector('.lang-number-comparison');comparison.textContent=langNumberComparison(item);comparison.hidden=dirty()||!comparison.textContent;
    const info=dialog.querySelector('.lang-translation-info');info.textContent=langTranslationInfo(item);info.hidden=!info.textContent;
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
    action.classList.toggle('primary',!item.text);action.classList.toggle('secondary',!!item.text);
    action.querySelector('span').textContent=item.translation_resumable?'Продовжити переклад':item.text?'Перекласти заново':'Перекласти';
    dialog.querySelector('.lang-script-dialog-status span').textContent=status.label;
    dialog.querySelector('.lang-script-fields').hidden=!item.text&&!draft;
    dialog.querySelector('.lang-script-empty').hidden=!!item.text||!!draft;
    dialog.querySelector('.lang-text-quality').innerHTML=langQualityNotice(item.language_check);
    const jobBox=dialog.querySelector('.lang-script-job');
    jobBox.innerHTML=job?.status==='running'?`<span>${esc(job.stage||'Перекладаємо…')}</span><progress max="100" value="${job.progress||0}"></progress><button type="button" class="secondary lang-cancel">Скасувати</button>`:job?.status==='failed'?`<span class="lang-warn">${esc(job.error||'Не вдалося завершити переклад.')}</span>`:'';
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
