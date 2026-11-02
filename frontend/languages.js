// languages.js — the «Мови» tab after «Прев’ю» (backend/languages.py): the episode's voice in other languages with the
// author's own cloned voice, and the thumbnail with its words translated. The video itself is not changed (user,
// 2 November 2026: «відео ролик перекладати я поки не хочу, лише аудіо і превью»). Each language goes in three steps:
// the text (translated by DeepSeek, editable), the voice (a cheap sample first, then the whole with its price shown
// before) and the thumbnail (before and after).
const langDrafts={};
let langData=null,langPolling=false;

function langCost(spec,value){return spec?.free?'безкоштовно':value===null?'ціна на fish.audio':langMoney(value || 0);}
function langMoney(value){return value>=0.01?`≈ $${value.toFixed(2).replace('.',',')}`:'менше $0,01';}
function langUrl(id,code,kind,stamp){return `/api/projects/${encodeURIComponent(id)}/languages/${code}/file/${kind}?v=${stamp || Date.now()}`;}

function renderLangView(){
  const tab=$('view-langs'),section=$('project-langs');if(!tab||!section)return;
  const project=state.project,open=!!project&&state.view==='langs';
  tab.hidden=!project;tab.classList.toggle('active',open);tab.setAttribute('aria-pressed',String(open));
  section.hidden=!open;
  if(!open){if(section.childElementCount){section.querySelectorAll('audio').forEach(audio=>audio.pause());section.replaceChildren();}delete section.dataset.project;return;}
  if(section.dataset.project!==project.id){section.dataset.project=project.id;section.innerHTML='<div class="lang-view"><h1>Мови</h1><p class="lang-lead">Завантаження…</p></div>';loadLangs(project.id);}
}

async function loadLangs(id){
  try{langData=await api(`/api/projects/${encodeURIComponent(id)}/languages`);}
  catch(error){const lead=document.querySelector('#project-langs .lang-lead');if(lead)lead.textContent=error.message;return;}
  if(state.project?.id!==id || state.view!=='langs')return;
  drawLangs(id);
  if(langData.job?.status==='running')pollLangs(id);
}

function langBusy(){return langData?.job?.status==='running';}

function drawLangs(id){
  const section=$('project-langs');if(!section||section.dataset.project!==id)return;
  section.querySelectorAll('audio').forEach(audio=>audio.pause());
  const data=langData,provider=data.provider,spec=data.providers.find(item=>item.id===provider) || data.providers[0];
  const used=new Set(data.items.map(item=>item.code));
  section.innerHTML=`<div class="lang-view">
    <div class="lang-head"><h1>Мови</h1>
      <p class="lang-lead">Озвучка ролика іншими мовами вашим голосом і прев’ю з перекладеним текстом. Відео не змінюється: готову озвучку завантажте на YouTube як додаткову аудіодоріжку.</p></div>
    <div class="lang-cards"></div>
    <div class="lang-add"><label><span>Нова мова</span><select><option value="">Оберіть мову…</option>${data.languages.filter(item=>!used.has(item.code)&&item.code!==data.source.language).map(item=>`<option value="${item.code}">${esc(item.name)} · ${esc(item.label)}</option>`).join('')}</select></label><button type="button" class="primary lang-add-run" disabled>Додати</button></div>
  </div>`;
  // listeners go on the page's own root, drawn anew each time, so they never pile up on the section
  const view=section.querySelector('.lang-view'),cards=section.querySelector('.lang-cards');
  if(!data.items.length)cards.innerHTML='<p class="lang-empty">Ще немає жодної мови. Оберіть мову нижче й натисніть «Додати».</p>';
  cards.prepend(langOriginal(id,data.source));
  for(const item of data.items)cards.append(langCard(id,item,spec));
  const pick=section.querySelector('.lang-add select'),go=section.querySelector('.lang-add-run');
  pick.addEventListener('change',()=>{go.disabled=!pick.value || langBusy();});
  go.addEventListener('click',async()=>{
    const code=pick.value;if(!code)return;
    try{langData=await api(`/api/projects/${encodeURIComponent(id)}/languages/${code}`,'POST',{});drawLangs(id);
      document.querySelector(`#project-langs .lang-card[data-code="${code}"]`)?.scrollIntoView({behavior:'smooth',block:'start'});
    }catch(error){langNote(go,error.message,true);}
  });
  view.addEventListener('change',async event=>{
    const select=event.target.closest('.lang-engine select');if(!select)return;
    try{langData=await api(`/api/projects/${encodeURIComponent(id)}/languages/provider`,'POST',{provider:'fishaudio',engine:select.value});drawLangs(id);}catch(error){langNote(select,error.message,true);}
  });
  showLangJob();
}

// The author's own voice in this language (user, 2 November 2026: the clone carried the original's accent, and stock
// voices are not wanted): a passage of the translation to read aloud, recorded here or as a file; the clone takes its
// voice and the right pronunciation from it.
const micIcon='<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>';
function langOwnBlock(item){
  const own=item.own_voice;
  return `<div class="lang-own${own?' has-voice':''}"><div class="lang-own-head"><b>Ваш голос цією мовою</b><small>${own?'клон бере голос і вимову з вашого запису':'щоб не було чужого акценту'}</small></div>
    ${own?`<div class="lang-player" data-kind="own"></div>
      <div class="lang-own-actions"><button type="button" class="secondary lang-own-record">${micIcon}Записати заново</button><button type="button" class="secondary lang-own-remove">Прибрати запис</button></div>`
    :`<p>Прочитайте вголос цей уривок, спокійно, як у ролику (20–30 секунд). Без запису голос клонується з оригіналу, разом з його акцентом.</p>
      <blockquote class="lang-own-passage">${esc(item.passage)}</blockquote>
      <div class="lang-own-actions"><button type="button" class="primary lang-own-record">${micIcon}Записати</button><label class="secondary lang-own-file">Завантажити запис<input type="file" accept="audio/*,video/*" hidden></label></div>`}
</div>`;
}
async function langOwnUpload(id,item,blob,name,holder){
  langNote(holder,'Зберігаємо запис…');
  try{
    const response=await fetch(`/api/projects/${encodeURIComponent(id)}/languages/${item.code}/own-voice`,{method:'POST',
      headers:{'Content-Type':'application/octet-stream','X-File-Name':encodeURIComponent(name),'X-Said-Text':encodeURIComponent(item.own_voice?.text || item.passage)},body:blob});
    const data=await response.json();if(!response.ok)throw new Error(data.error || 'Не вдалося зберегти запис');
    langData=data;drawLangs(id);
  }catch(error){langNote(holder,error.message,true);}
}
let langRecorder=null;
function langOwnWire(id,card,item){
  const box=card.querySelector('.lang-own');if(!box)return;
  const record=box.querySelector('.lang-own-record'),file=box.querySelector('.lang-own-file input');
  file?.addEventListener('change',()=>{const chosen=file.files[0];if(chosen)langOwnUpload(id,item,chosen,chosen.name,box);});
  box.querySelector('.lang-own-remove')?.addEventListener('click',async()=>{
    try{langData=await api(`/api/projects/${encodeURIComponent(id)}/languages/${item.code}/own-voice/remove`,'POST',{});drawLangs(id);}catch(error){langNote(box,error.message,true);}
  });
  record?.addEventListener('click',async()=>{
    if(langRecorder){langRecorder.stop();return;}
    if(item.own_voice){
      // recording again shows the passage once more: the same words as before
      const quote=document.createElement('blockquote');quote.className='lang-own-passage';quote.textContent=item.own_voice.text;box.querySelector('.lang-own-actions').before(quote);
    }
    let stream;
    try{stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:false,noiseSuppression:true,autoGainControl:true}});}
    catch{langNote(box,'Браузер не дав доступ до мікрофона. Дозвольте його в адресному рядку або завантажте запис файлом.',true);return;}
    const chunks=[],recorder=new MediaRecorder(stream);langRecorder=recorder;
    const started=Date.now(),label=()=>{const s=Math.floor((Date.now()-started)/1000);record.innerHTML=`<span class="lang-rec-dot"></span>Зупинити · ${clock(s)}`;};
    record.classList.add('is-recording');label();const tick=setInterval(label,500);
    recorder.ondataavailable=event=>{if(event.data.size)chunks.push(event.data);};
    recorder.onstop=()=>{clearInterval(tick);stream.getTracks().forEach(track=>track.stop());langRecorder=null;
      const blob=new Blob(chunks,{type:recorder.mimeType || 'audio/webm'});
      if(Date.now()-started<5000){record.classList.remove('is-recording');record.innerHTML=`${micIcon}Записати`;langNote(box,'Запис закороткий: прочитайте весь уривок.',true);return;}
      langOwnUpload(id,item,blob,'Мій голос.webm',box);};
    recorder.start(1000);
  });
}

// The episode's own voice on top, to compare with (user, 2 November 2026: «має бути ще один блок оригінал… аудіо
// оригінала, длительність, послухати можна»).
function langOriginal(id,src){
  const original=langData.languages.find(item=>item.code===src.language);
  const card=document.createElement('article');card.className='lang-card lang-original';
  // one compact line (user, 2 November 2026: «компактніше… не хочу, щоб акцент був великий»): the name with the
  // language and the text's size, the player beside them; its length is in the player
  card.innerHTML=`<div class="lang-original-row"><div class="lang-original-name"><b>Оригінал${original?` (${esc(original.label)})`:''}</b>
      <small>${src.chars?`${src.chars.toLocaleString('uk-UA')} символів · `:''}ваша озвучка</small></div>
    ${src.voice?'<div class="lang-player"></div>':'<p class="lang-off">Озвучку випуску не знайдено. Додайте її на вкладці «План ролика».</p>'}</div>`;
  const slot=card.querySelector('.lang-player');
  if(slot){const player=voicePlayer(id,`/api/projects/${encodeURIComponent(id)}/languages/original`);if(player)slot.replaceWith(player);}
  return card;
}

function langCard(id,item,spec){
  const card=document.createElement('article');card.className='lang-card';card.dataset.code=item.code;
  const text=langDrafts[`${id}:${item.code}`] ?? item.text,price=item.prices[spec.id],voice=item.voice || {};
  const hasSample=(item.files.samples || []).includes(langData.voice_key);
  const fit=voice.speed?`прискорено в ${String(voice.speed).replace('.',',')} раза, щоб влізти в ролик`:voice.padded?`наприкінці ${String(voice.padded).replace('.',',')} с тиші до довжини ролика`:'';
  card.innerHTML=`<header><h2>${esc(item.name)}</h2><span>${esc(item.label)}</span><button type="button" class="lang-remove" title="Прибрати мову" aria-label="Прибрати мову ${esc(item.name)}">${typeof trashIcon==='string'?trashIcon:'×'}</button></header>
    <section class="lang-step"><h3><em>1</em>Текст</h3>
      ${item.text?`<label class="lang-title"><span>Заголовок</span><input type="text" maxlength="200" value="${esc(item.title)}"></label>
        <label class="lang-text"><span>Текст озвучки <small class="lang-text-hint">${item.chars.toLocaleString('uk-UA')} символів · правки зберігаються самі</small></span><textarea rows="9" spellcheck="false">${esc(text)}</textarea></label>`
      :`<div class="lang-actions"><p>Студія перекладе текст і заголовок ролика: кілька центів, зазвичай до хвилини.${langData.openrouter===true?'':' <span class="lang-warn">Потрібен ключ OpenRouter у налаштуваннях студії.</span>'}</p><button type="button" class="primary lang-translate">Перекласти</button></div>`}
    <div class="lang-job" role="status" aria-live="polite" hidden></div></section>
    <section class="lang-step${item.text?'':' is-off'}"><h3><em>2</em>Озвучка вашим голосом</h3>
      ${item.text?`<div class="lang-provider">
          ${spec.engines?`<label class="lang-engine"><span>Рушій</span><select>${spec.engines.map(engine=>`<option value="${engine.id}"${engine.id===spec.engine?' selected':''}>${esc(engine.name)} · ${esc(engine.note)}</option>`).join('')}</select></label>`:''}
          <small>${esc(spec.note)}${spec.configured===true?'':` <span class="lang-warn">Додайте ключ ${esc(spec.name)}: налаштування студії → «Ключі сервісів».</span>`}</small></div>
        ${langOwnBlock(item)}
        <p class="lang-price">Весь текст через ${esc(spec.name)}: <b>${langCost(spec,price)}</b> <small>(${item.chars.toLocaleString('uk-UA')} символів)</small>.${spec.free?'':' Спершу послухайте зразок, він коштує майже нічого.'}</p>
        <div class="lang-sample">${hasSample?`<div class="lang-player" data-kind="sample-${esc(langData.voice_key)}"></div>`:''}<button type="button" class="secondary lang-sample-run"${hasSample?' hidden':''}>Послухати зразок</button></div>
        ${item.files.voice?`<div class="lang-voice"><b>Готова озвучка</b><div class="lang-player" data-kind="voice"></div>
          <small>${voice.duration?clock(voice.duration):''}${voice.source_duration?` · ролик ${clock(voice.source_duration)}`:''}${fit?` · ${fit}`:''}${voice.longer?` · довша за ролик на ${String(voice.longer).replace('.',',')} с`:''}</small>
          ${item.folder?`<small class="lang-folder">Файл у папці випуску: ${esc(item.folder)}</small>`:''}
          <a class="lang-download" href="${langUrl(id,item.code,'voice',voice.made_at)}" download="Озвучка ${esc(item.name)}.mp3">Завантажити MP3</a></div>`:''}
        <div class="lang-actions"><button type="button" class="primary lang-voice-run">${item.files.voice?'Озвучити заново':'Озвучити весь ролик'} · ${langCost(spec,price)}</button></div>`
      :'<p class="lang-off">Спершу перекладіть текст.</p>'}
    <div class="lang-job" role="status" aria-live="polite" hidden></div></section>
    <section class="lang-step"><h3><em>3</em>Прев’ю</h3>
      ${langData.thumbnail?`<div class="lang-thumbs"><figure><img src="/api/projects/${encodeURIComponent(id)}/cover?v=${Date.now()}" alt="Прев’ю до перекладу" loading="lazy"><figcaption>До</figcaption></figure>
        <figure><button type="button" class="lang-thumb-run${item.files.thumbnail?' has-picture':''}" aria-label="${item.files.thumbnail?'Перекласти прев’ю ще раз':'Перекласти прев’ю'}">${item.files.thumbnail?`<img src="${langUrl(id,item.code,'thumbnail')}" alt="Прев’ю після перекладу" loading="lazy">`:''}<span class="lang-thumb-wand">${typeof thumbnailIcon==='string'?thumbnailIcon:''}<small>${item.files.thumbnail?'Перекласти ще раз':'Натисніть, щоб перекласти'}</small></span></button><figcaption>Після · ${esc(item.name)} · Codex змінить тільки слова на картинці</figcaption></figure></div>`
      :'<p class="lang-off">У випуску ще немає прев’ю. Створіть його на вкладці «Прев’ю».</p>'}
    <div class="lang-job" role="status" aria-live="polite" hidden></div></section>`;
  for(const box of card.querySelectorAll('.lang-player')){
    const player=voicePlayer(id,langUrl(id,item.code,box.dataset.kind,box.dataset.kind==='voice'?voice.made_at:undefined));
    if(player)box.replaceWith(player);
  }
  // edits are saved by themselves a moment after typing stops and when the field is left (user, 2 November 2026:
  // «має зразу змінювати як правку»), without redrawing the card; the old sample was of the old text and goes
  const area=card.querySelector('textarea'),title=card.querySelector('.lang-title input'),hint=card.querySelector('.lang-text-hint'),key=`${id}:${item.code}`;
  let timer=null;
  const flush=async()=>{
    clearTimeout(timer);timer=null;
    if(!area || (area.value===item.text&&title.value===item.title))return true;
    if(!area.value.trim()){langNote(area,'Текст не може бути порожнім.',true);return false;}
    const text=area.value,name=title.value;
    try{
      langData=await api(`/api/projects/${encodeURIComponent(id)}/languages/${item.code}/text`,'POST',{text,title:name});
      item.text=text;item.title=name;if(area.value===text)delete langDrafts[key];
      if(hint)hint.textContent=`${text.length.toLocaleString('uk-UA')} символів · збережено`;
      const old=card.querySelector('.lang-sample .voice-player');if(old){old.querySelector('audio')?.pause();old.remove();}
      const again=card.querySelector('.lang-sample-run');if(again)again.hidden=false;
      const fresh=langData.items.find(entry=>entry.code===item.code);
      if(fresh){const cost=langCost(spec,fresh.prices?.[spec.id]),line=card.querySelector('.lang-price');
        if(line){line.querySelector('b').textContent=cost;line.querySelector('small').textContent=`(${fresh.chars.toLocaleString('uk-UA')} символів)`;}
        const run=card.querySelector('.lang-voice-run');if(run)run.textContent=run.textContent.replace(/ · .*$/,` · ${cost}`);}
      card.querySelector('.lang-text')?.closest('.lang-step')?.querySelector(':scope > .lang-note.is-error')?.remove();
      return true;
    }catch(error){langNote(area,error.message,true);return false;}
  };
  if(area){
    const later=()=>{if(area.value!==item.text)langDrafts[key]=area.value;else delete langDrafts[key];
      if(hint)hint.textContent='зберігаємо…';clearTimeout(timer);timer=setTimeout(flush,1200);};
    for(const field of [area,title]){field.addEventListener('input',later);field.addEventListener('blur',()=>{if(timer)flush();});}
    if(area.value!==item.text)later();
  }
  card.querySelector('.lang-remove').addEventListener('click',()=>modal(`Прибрати ${item.name}?`,
    `<p>Переклад і озвучка цієї мови зникнуть зі студії.${item.folder?' Файли в папці випуску залишаться.':''}</p>`,
    [{label:'Скасувати',run:closeModal},{label:'Прибрати мову',danger:true,run:async()=>{closeModal();
      try{langData=await api(`/api/projects/${encodeURIComponent(id)}/languages/${item.code}/remove`,'POST',{});delete langDrafts[`${id}:${item.code}`];drawLangs(id);}catch(error){langNote(card,error.message,true);}}}]));
  card.querySelector('.lang-translate')?.addEventListener('click',()=>langStart(id,'translate',item.code));
  card.querySelector('.lang-sample-run')?.addEventListener('click',async()=>{if(!(await flush()))return;langStart(id,'sample',item.code);});
  card.querySelector('.lang-voice-run')?.addEventListener('click',async()=>{
    if(!(await flush()))return;
    const fresh=langData.items.find(entry=>entry.code===item.code) || item,cost=fresh.prices&&spec.id in fresh.prices?fresh.prices[spec.id]:price,chars=fresh.chars ?? item.chars;
    modal(`Озвучити ${item.name}?`,`<p>${esc(spec.name)} озвучить весь текст вашим голосом: ${chars.toLocaleString('uk-UA')} символів, ${spec.free?`<b>безкоштовно</b> (рушій ${esc(spec.engines.find(engine=>engine.id===spec.engine)?.name || '')})`:cost===null?`за ціною ${esc(spec.name)} (дивіться на fish.audio). Гроші спишуться з вашого рахунку ${esc(spec.name)}`:`орієнтовно <b>${langMoney(cost)}</b>. Гроші спишуться з вашого рахунку ${esc(spec.name)}`}.</p>
      <p>Студія склеїть частини, вирівняє гучність і піджене довжину під ролик. Зазвичай це кілька хвилин.</p>`,
      [{label:'Скасувати',run:closeModal},{label:`Озвучити · ${langCost(spec,cost)}`,primary:true,run:()=>{closeModal();langStart(id,'voice',item.code);}}]);
  });
  card.querySelector('.lang-thumb-run')?.addEventListener('click',()=>langStart(id,'thumbnail',item.code));
  langOwnWire(id,card,item);
  return card;
}

// Messages of this tab stand where the author pressed, not in the studio's banner at the top (user, 2 November 2026:
// «сповіщення… мають бути там, де я нажимаю кнопку»): a short line at the end of that step, or under «Нова мова».
const langStepOf={translate:0,sample:1,voice:1,thumbnail:2};
function langPlace(code,kind){
  const card=document.querySelector(`#project-langs .lang-card[data-code="${code}"]`);
  return card?.querySelectorAll('.lang-step')[langStepOf[kind] ?? 0] || document.querySelector('#project-langs .lang-add');
}
function langNote(where,message,error=false){
  const holder=where?.closest?.('.lang-step, .lang-add, .lang-card') || where;
  if(!holder){status(message,error);return;}
  holder.querySelector(':scope > .lang-note')?.remove();
  const note=document.createElement('p');note.className='lang-note'+(error?' is-error':'');note.setAttribute('role',error?'alert':'status');note.textContent=message;
  const job=holder.querySelector(':scope > .lang-job');if(job)job.before(note);else holder.append(note);
  if(!error)setTimeout(()=>note.remove(),8000);
}

async function langCancel(id){
  const button=document.querySelector('#project-langs .lang-cancel');if(button){button.disabled=true;button.textContent='Скасовуємо…';}
  try{await api(`/api/projects/${encodeURIComponent(id)}/languages/cancel`,'POST',{});}catch(error){langNote(button,error.message,true);}
}

async function langStart(id,kind,code){
  try{
    const {job}=await api(`/api/projects/${encodeURIComponent(id)}/languages/${code}/${kind}`,'POST',{provider:langData.provider});
    langPlace(code,kind)?.querySelector(':scope > .lang-note')?.remove();
    langData.job=job;showLangJob();pollLangs(id);
  }catch(error){langNote(langPlace(code,kind),error.message,true);}
}

function showLangJob(){
  // the line sits in the step it works on, inside the language's own card (user, 2 November 2026: «не треба розкидати
  // блоки… все в один блок»): the text for a translation, the voice for a sample or the whole, the thumbnail
  const job=langData?.job,busy=langBusy();
  const step={translate:0,sample:1,voice:1,thumbnail:2}[job?.kind];
  const card=job?.code?document.querySelector(`#project-langs .lang-card[data-code="${job.code}"]`):null;
  const box=card&&step!==undefined?card.querySelectorAll('.lang-step')[step]?.querySelector('.lang-job'):null;
  for(const other of document.querySelectorAll('#project-langs .lang-job'))if(other!==box){other.hidden=true;other.closest('.lang-step')?.classList.remove('is-working');}
  document.querySelectorAll('#project-langs .lang-card button:not(.voice-player-play):not(.voice-player-mute), #project-langs .lang-add select').forEach(button=>{
    button.disabled=busy;});
  const go=document.querySelector('#project-langs .lang-add-run');if(go)go.disabled=busy || !document.querySelector('#project-langs .lang-add select')?.value;
  // the «after» window of the language being redrawn says so in place of its wand
  for(const tile of document.querySelectorAll('#project-langs .lang-thumb-run')){
    const drawing=busy&&job.kind==='thumbnail'&&tile.closest('.lang-card')?.dataset.code===job.code;
    tile.classList.toggle('is-drawing',drawing);
    const label=tile.querySelector('.lang-thumb-wand small');
    if(label){label.dataset.idle??=label.textContent;label.textContent=drawing?'Codex перекладає, 1–3 хвилини…':label.dataset.idle;}
  }
  if(!box)return;
  // a finished job shows itself in the card (the text, the player, the picture): only a failure or a cancel says so here
  const recent=job&&['failed','cancelled'].includes(job.status)&&job.finished_at&&Date.now()/1000-job.finished_at<120;
  box.hidden=!job || (!busy && !recent);
  box.dataset.status=job?.status || '';
  box.closest('.lang-step').classList.toggle('is-working',busy);
  if(box.hidden)return;
  // the poll redraws this line every 2 s: a cancel already asked for stays shown
  const asked=box.querySelector('.lang-cancel')?.disabled;
  box.innerHTML=busy?`${typeof exportSpinner==='string'?exportSpinner:''}<span>${esc(job.stage || '')}</span><progress max="100" value="${job.progress || 0}"></progress><button type="button" class="secondary lang-cancel"${asked||job.stage==='Скасовуємо…'?' disabled':''}>${asked||job.stage==='Скасовуємо…'?'Скасовуємо…':'Скасувати'}</button>`
    :job.status==='cancelled'?`<span>Скасовано, нічого не збережено.</span>`
    :job.status==='done'?`<span>Готово.${job.cost?` Витрачено ${langMoney(job.cost)}.`:''}</span>`
    :`<span>Не вдалося: ${esc(job.error || '')}</span>`;
  box.querySelector('.lang-cancel')?.addEventListener('click',()=>langCancel(state.project.id));
}

async function pollLangs(id){
  if(langPolling)return;langPolling=true;
  try{
    while(langBusy() && state.project?.id===id){
      await new Promise(resolve=>setTimeout(resolve,2000));
      try{const data=await api(`/api/projects/${encodeURIComponent(id)}/languages`);
        const finished=data.job?.status!=='running';langData=data;
        if(finished && state.view==='langs' && state.project?.id===id)drawLangs(id);else showLangJob();
      }catch{}
    }
  }finally{langPolling=false;}
}

$('view-langs')?.addEventListener('click',()=>setProjectView('langs'));
