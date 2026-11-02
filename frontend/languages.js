// languages.js — the «Мови» tab after «Прев’ю» (backend/languages.py): the episode's voice in other languages with the
// author's own cloned voice, and the thumbnail with its words translated. The video itself is not changed (user,
// 2 November 2026: «відео ролик перекладати я поки не хочу, лише аудіо і превью»). Each language goes in three steps:
// the text (translated by DeepSeek, editable), the voice (a cheap sample first, then the whole with its price shown
// before) and the thumbnail (before and after).
const langDrafts={};
let langData=null,langPolling=false;

const langDownloadIcon='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11m0 0-4.5-4.5M12 15l4.5-4.5M5 19h14"/></svg>';
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
  if(langBusy())pollLangs(id);
}

function langBusy(){return langJobs().some(job=>job.status==='running');}

// A flag for each language, shown in its capsule and in the «+» menu.
const langFlags={en:'🇬🇧',uk:'🇺🇦',ru:'🇷🇺',de:'🇩🇪',es:'🇪🇸',fr:'🇫🇷',pt:'🇵🇹',it:'🇮🇹',pl:'🇵🇱',tr:'🇹🇷',nl:'🇳🇱',hi:'🇮🇳',ar:'🇸🇦',ja:'🇯🇵',ko:'🇰🇷',zh:'🇨🇳',id:'🇮🇩',cs:'🇨🇿',ro:'🇷🇴',kk:'🇰🇿'};
// what a language already has, as small grey marks in its capsule (user, 2 November 2026: «значок текста… прев'ю…
// озвучка… сіреньке… означає, що там зроблено»): only the made ones show
const langMarkIcons={text:'<svg viewBox="0 0 24 24"><path d="M14 3H6v18h12V7zM14 3v5h4M9 12h6m-6 4h6"/></svg>',
  thumbnail:'<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 16 5-5 4 4 3-3 6 6"/></svg>',
  voice:'<svg viewBox="0 0 24 24"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>'};
function langMarks(item){
  const made=[['text',!!item.text,'Текст перекладено'],['thumbnail',!!item.files?.thumbnail,'Прев’ю перекладено'],['voice',!!item.files?.voice&&item.voice_current!==false,'Озвучку зроблено']].filter(mark=>mark[1]);
  return made.length?`<span class="lang-marks">${made.map(([kind,,title])=>`<i class="lang-mark" title="${title}" aria-label="${title}">${langMarkIcons[kind]}</i>`).join('')}</span>`:'';
}
function langFlag(code){return `<span class="lang-flag" aria-hidden="true">${langFlags[code] || '🌐'}</span>`;}
// the language open below the capsules, per episode, remembered in the browser
function langChosen(id){
  let code=null;try{code=localStorage.getItem(`langTab:${id}`);}catch{}
  const codes=(langData?.items || []).map(item=>item.code);
  return codes.includes(code)?code:codes[0] || null;
}
function langChoose(id,code){try{localStorage.setItem(`langTab:${id}`,code);}catch{}}

// The languages stand on top as capsules with their flags (user, 2 November 2026: «мови… зверху… капсулами… прапор…
// плюсик, щоб додати… хрестик… видалити»): a click opens that language's card below, «+» adds one, × removes one.
function drawLangs(id){
  const section=$('project-langs');if(!section||section.dataset.project!==id)return;
  section.querySelectorAll('audio').forEach(audio=>audio.pause());
  const data=langData,provider=data.provider,spec=data.providers.find(item=>item.id===provider) || data.providers[0];
  const used=new Set(data.items.map(item=>item.code)),chosen=langChosen(id);
  const free=data.languages.filter(item=>!used.has(item.code)&&item.code!==data.source.language);
  section.innerHTML=`<div class="lang-view">
    <div class="lang-head"><h1>Мови</h1>
      <p class="lang-lead">Озвучка ролика іншими мовами вашим голосом і прев’ю з перекладеним текстом. Відео не змінюється: готову озвучку завантажте на YouTube як додаткову аудіодоріжку.</p></div>
    <div class="lang-original-slot"></div>
    <div class="lang-pills" role="tablist" aria-label="Мови випуску">
      ${data.items.map(item=>`<div class="lang-pill${item.code===chosen?' active':''}" data-code="${item.code}"><button type="button" class="lang-pill-pick" role="tab" aria-selected="${item.code===chosen}" title="${esc(item.label)}">${langFlag(item.code)}<span>${esc(item.name)}</span>${langMarks(item)}<i class="lang-pill-busy" aria-hidden="true"></i></button><button type="button" class="lang-pill-x" title="Прибрати мову" aria-label="Прибрати мову ${esc(item.name)}">×</button></div>`).join('')}
      ${free.length?`<div class="lang-plus-wrap"><button type="button" class="lang-plus" aria-haspopup="true" aria-expanded="false" title="Додати мову" aria-label="Додати мову">+${data.items.length?'':'<span>Додати мову</span>'}</button>
        <div class="lang-menu" role="menu" hidden>${free.map(item=>`<button type="button" role="menuitem" data-code="${item.code}">${langFlag(item.code)}<span>${esc(item.name)}</span><small>${esc(item.label)}</small></button>`).join('')}</div></div>`:''}
    </div>
    <div class="lang-cards"></div>
  </div>`;
  // listeners go on the page's own root, drawn anew each time, so they never pile up on the section
  const view=section.querySelector('.lang-view'),cards=section.querySelector('.lang-cards');
  section.querySelector('.lang-original-slot').replaceWith(langOriginal(id,data.source));
  const item=data.items.find(entry=>entry.code===chosen);
  if(item)cards.append(langCard(id,item,spec));
  else cards.innerHTML='<p class="lang-empty">Ще немає жодної мови. Натисніть «+» угорі й оберіть мову.</p>';
  const plus=view.querySelector('.lang-plus'),menu=view.querySelector('.lang-menu');
  const closeMenu=()=>{if(menu){menu.hidden=true;plus.setAttribute('aria-expanded','false');}};
  plus?.addEventListener('click',event=>{event.stopPropagation();menu.hidden=!menu.hidden;plus.setAttribute('aria-expanded',String(!menu.hidden));});
  view.addEventListener('click',event=>{if(menu&&!menu.hidden&&!event.target.closest('.lang-plus-wrap'))closeMenu();});
  view.addEventListener('keydown',event=>{if(event.key==='Escape')closeMenu();});
  menu?.addEventListener('click',async event=>{
    const option=event.target.closest('button[data-code]');if(!option)return;closeMenu();
    try{langData=await api(`/api/projects/${encodeURIComponent(id)}/languages/${option.dataset.code}`,'POST',{});langChoose(id,option.dataset.code);drawLangs(id);}
    catch(error){langNote(view.querySelector('.lang-pills'),error.message,true);}
  });
  view.querySelectorAll('.lang-pill').forEach(pill=>{
    const code=pill.dataset.code,entry=data.items.find(entry=>entry.code===code);
    pill.querySelector('.lang-pill-pick').addEventListener('click',()=>{if(code===langChosen(id))return;langChoose(id,code);drawLangs(id);});
    pill.querySelector('.lang-pill-x').addEventListener('click',()=>modal(`Прибрати ${entry.name}?`,
      `<p>Переклад і озвучка цієї мови зникнуть зі студії.${entry.folder?' Файли в папці випуску залишаться.':''}</p>`,
      [{label:'Скасувати',run:closeModal},{label:'Прибрати мову',danger:true,run:async()=>{closeModal();
        try{langData=await api(`/api/projects/${encodeURIComponent(id)}/languages/${code}/remove`,'POST',{});delete langDrafts[`${id}:${code}`];drawLangs(id);}
        catch(error){langNote(view.querySelector('.lang-pills'),error.message,true);}}}]));
  });
  view.addEventListener('change',async event=>{
    const select=event.target.closest('.lang-chip-select select[data-field], .lang-engine select[data-field]');if(!select)return;
    try{langData=await api(`/api/projects/${encodeURIComponent(id)}/languages/provider`,'POST',{provider:'fishaudio',[select.dataset.field || 'engine']:select.value});drawLangs(id);}catch(error){langNote(select,error.message,true);}
  });
  showLangJob();
}

// The voice of a language always comes from an example in that language (user, 2 November 2026: «переклад будемо брати
// завжди від прикладу ролика на мові… або запис, або закинути приклад носія»): the channel's example serves every
// episode («в настройках каналу»), an episode's own wins («якщо ні, то можна закинути свій»). No example, no voicing.
const langIcons={play:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l11-6.5z"/></svg>',redo:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/></svg>',upload:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16V4m0 0-4.5 4.5M12 4l4.5 4.5M5 20h14"/></svg>',trash:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M10 4h4m-8 3 1 13h10l1-13"/></svg>',back:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 14 4 9l5-5M4 9h11a5 5 0 0 1 0 10h-3"/></svg>'};
const micIcon='<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>';
function langSampleSize(){let n=5;try{n=Number(localStorage.getItem('langSampleSentences')) || 5;}catch{}return [3,5,10,20].includes(n)?n:5;}
function langHasVoice(item){return !!(item.own_voice || item.channel_voice || langData?.source?.voice);}
function langHeardWarn(example){return example?.heard===false?'<p class="lang-warn">Студія не змогла розпізнати слова в записі, тому Fish вважає, що прозвучав показаний уривок. Якщо в записі інші слова, голос може звучати дивно: запишіть заново, прочитавши саме уривок.</p>':'';}
function langAddButtons(primary){
  return `<div class="lang-own-actions"><button type="button" class="${primary?'primary':'secondary'} lang-own-record">${micIcon}Записати себе</button><label class="secondary lang-own-file">Закинути запис<input type="file" accept="audio/*,video/*" hidden></label></div>`;
}
function langOwnBlock(item){
  const own=item.own_voice,shared=item.channel_voice,fromOriginal=!!langData?.source?.voice;
  // an example in hand is a small line (user, 2 November 2026: «не виділяй її так… просто маленький приклад, основа
  // акценту на створенні аудіо»; «кнопки… просто значки»): its label, a compact player and icons
  const model=item.fish_model?'<i class="lang-model-mark" title="Збережена модель голосу у Fish: звучить чистіше, ніж швидкий клон">✓ модель</i>':'';
  const add=(again)=>`<button type="button" class="lang-icon lang-own-record" title="${again?'Записати заново':'Записати себе'}" aria-label="${again?'Записати заново':'Записати себе'}">${micIcon}</button><label class="lang-icon lang-own-file" title="Закинути запис" aria-label="Закинути запис">${langIcons.upload}<input type="file" accept="audio/*,video/*" hidden></label>`;
  if(own)return `<div class="lang-own has-voice"><span class="lang-own-label">Приклад голосу<small>свій для цього випуску ${model}</small></span><div class="lang-player" data-kind="own"></div>
    <div class="lang-own-actions">${add(true)}<button type="button" class="lang-icon lang-own-remove" title="${shared?'Повернути голос каналу':'Прибрати приклад'}" aria-label="${shared?'Повернути голос каналу':'Прибрати приклад'}">${shared?langIcons.back:langIcons.trash}</button></div>${langHeardWarn(own)}</div>`;
  if(shared)return `<div class="lang-own has-voice"><span class="lang-own-label">Приклад голосу<small>з налаштувань каналу ${model}</small></span><div class="lang-player" data-kind="channel"></div>
    <div class="lang-own-actions" title="Інший голос лише для цього випуску">${add(false)}</div>${langHeardWarn(shared)}</div>`;
  return `<div class="lang-own needs-voice"><div class="lang-own-head"><b>Приклад голосу</b><small>${fromOriginal?'немає, тому голос з оригіналу, з його акцентом':'потрібен, щоб озвучити'}</small><span class="lang-own-actions">${add(false)}</span></div>
    <p>Запишіть себе цією мовою або закиньте запис носія, 20–60 секунд: озвучка скопіює цей голос і вимову. Для всіх випусків каналу приклад додається в налаштуваннях каналу. Можна прочитати:</p>
    <blockquote class="lang-own-passage">${esc(item.passage)}</blockquote></div>`;
}
// a recording from the microphone: the button turns into «Зупинити · 0:12»; the blob goes to `done`
let langRecorder=null;
async function langRecord(button,holder,done){
  if(langRecorder){langRecorder.stop();return;}
  let stream;
  try{stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:false,noiseSuppression:false,autoGainControl:false,channelCount:1,sampleRate:48000}});}
  catch{langNote(holder,'Браузер не дав доступ до мікрофона. Дозвольте його в адресному рядку або закиньте запис файлом.',true);return;}
  const chunks=[],recorder=new MediaRecorder(stream,{audioBitsPerSecond:256000}),idle=button.innerHTML;langRecorder=recorder;
  const started=Date.now(),label=()=>{const s=Math.floor((Date.now()-started)/1000);button.innerHTML=`<span class="lang-rec-dot"></span>Зупинити · ${clock(s)}`;};
  button.classList.add('is-recording');label();const tick=setInterval(label,500);
  recorder.ondataavailable=event=>{if(event.data.size)chunks.push(event.data);};
  recorder.onstop=()=>{clearInterval(tick);stream.getTracks().forEach(track=>track.stop());langRecorder=null;
    button.classList.remove('is-recording');button.innerHTML=idle;
    if(Date.now()-started<8000){langNote(holder,'Запис закороткий: говоріть хоча б 10 секунд.',true);return;}
    done(new Blob(chunks,{type:recorder.mimeType || 'audio/webm'}),'Голос.webm');};
  recorder.start(1000);
}
async function langSendExample(url,blob,name,said,holder){
  langNote(holder,'Зберігаємо й розпізнаємо запис, кілька секунд…');
  const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/octet-stream','X-File-Name':encodeURIComponent(name),'X-Said-Text':encodeURIComponent(said || '')},body:blob});
  const data=await response.json();if(!response.ok)throw new Error(data.error || 'Не вдалося зберегти запис');
  return data;
}
function langOwnWire(id,card,item){
  const box=card.querySelector('.lang-own');if(!box)return;
  const send=async(blob,name)=>{
    try{langData=await langSendExample(`/api/projects/${encodeURIComponent(id)}/languages/${item.code}/own-voice`,blob,name,item.passage,box);drawLangs(id);}
    catch(error){langNote(box,error.message,true);}
  };
  box.querySelectorAll('.lang-own-file input').forEach(file=>file.addEventListener('change',()=>{const chosen=file.files[0];if(chosen)send(chosen,chosen.name);}));
  box.querySelector('.lang-own-record')?.addEventListener('click',event=>langRecord(event.currentTarget,box,send));
  box.querySelector('.lang-own-remove')?.addEventListener('click',async()=>{
    try{langData=await api(`/api/projects/${encodeURIComponent(id)}/languages/${item.code}/own-voice/remove`,'POST',{});drawLangs(id);}catch(error){langNote(box,error.message,true);}
  });
}

// «Голоси для перекладу» in the channel's settings: one example a language for every episode of the channel.
async function bindChannelVoices(channel){
  const section=document.getElementById('channel-voices');if(!section)return;
  const base=`/api/channels/${encodeURIComponent(channel.id)}/voices`;
  const draw=data=>{
    if(!section.isConnected)return;
    section.querySelectorAll('audio').forEach(audio=>audio.pause());
    const have=new Set(data.voices.map(item=>item.code));
    section.innerHTML=`<h3>Голоси для перекладу</h3><p>Приклад голосу для кожної мови, 20–60 секунд: ваш запис цією мовою або запис носія мови. Вкладка «Мови» кожного випуску озвучує переклад саме цим голосом і вимовою. У випуску можна закинути інший.</p>
      <div class="channel-voices-list">${data.voices.map(item=>`<div class="channel-voice" data-code="${item.code}"><span class="channel-voice-name">${langFlag(item.code)} ${esc(item.name)}</span><div class="lang-player"></div><button type="button" class="project-action delete channel-voice-remove" title="Прибрати приклад" aria-label="Прибрати приклад ${esc(item.name)}">×</button></div>`).join('') || '<p class="lang-off">Ще немає жодного прикладу.</p>'}</div>
      <div class="channel-voice-add"><select aria-label="Мова прикладу"><option value="">Мова прикладу…</option>${data.languages.filter(item=>!have.has(item.code)).map(item=>`<option value="${item.code}">${langFlags[item.code] || ''} ${esc(item.name)} · ${esc(item.label)}</option>`).join('')}</select>
        <button type="button" class="secondary lang-own-record" disabled>${micIcon}Записати себе</button><label class="secondary lang-own-file is-off">Закинути запис<input type="file" accept="audio/*,video/*" hidden disabled></label></div>`;
    for(const row of section.querySelectorAll('.channel-voice')){
      const item=data.voices.find(entry=>entry.code===row.dataset.code);
      const player=voicePlayer(null,`${base}/${item.code}/file?v=${item.stamp}`);if(player)row.querySelector('.lang-player').replaceWith(player);
      row.querySelector('.channel-voice-remove').addEventListener('click',async()=>{try{draw(await api(`${base}/${item.code}/remove`,'POST',{}));}catch(error){langNote(section,error.message,true);}});
    }
    const pick=section.querySelector('.channel-voice-add select'),record=section.querySelector('.channel-voice-add .lang-own-record'),fileLabel=section.querySelector('.channel-voice-add .lang-own-file'),file=fileLabel.querySelector('input');
    pick.addEventListener('change',()=>{const off=!pick.value;record.disabled=off;file.disabled=off;fileLabel.classList.toggle('is-off',off);});
    const send=async(blob,name)=>{try{draw(await langSendExample(`${base}/${pick.value}`,blob,name,'',section));}catch(error){langNote(section,error.message,true);}};
    record.addEventListener('click',()=>langRecord(record,section,send));
    file.addEventListener('change',()=>{const chosen=file.files[0];if(chosen&&pick.value)send(chosen,chosen.name);});
  };
  try{draw(await api(base));}catch(error){section.innerHTML=`<h3>Голоси для перекладу</h3><p>${esc(error.message)}</p>`;}
}

// The episode's own voice on top, to compare with (user, 2 November 2026: «має бути ще один блок оригінал… аудіо
// оригінала, длительність, послухати можна»).
// «Оригінал (англійська)»: the original's name with its language, as on its card
function langOriginalName(){const original=langData?.languages.find(item=>item.code===langData.source?.language);return `Оригінал${original?` (${esc(original.label)})`:''}`;}
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
  const hasSample=(item.files.samples || []).includes(item.voice_key);
  // a voicing shows only while what made it still holds: the voice, engine, likeness, example and text
  const readyVoice=item.files.voice&&item.voice_current!==false;
  const fit=voice.synced?[`фрази у свій час, як в оригіналі`,voice.fastest>1.02?`найшвидша прискорена в ${String(voice.fastest).replace('.',',')} раза`:'',voice.latest>0.3?`найбільше запізнення ${String(voice.latest).replace('.',',')} с`:''].filter(Boolean).join(' · '):voice.speed?`прискорено в ${String(voice.speed).replace('.',',')} раза, щоб влізти в ролик`:voice.padded?`наприкінці ${String(voice.padded).replace('.',',')} с тиші до довжини ролика`:'';
  card.innerHTML=`
    <section class="lang-step"><h3><em>1</em>Текст</h3>
      ${item.text?`<label class="lang-title"><span>Заголовок</span><input type="text" maxlength="200" value="${esc(item.title)}"></label>
        <label class="lang-text"><span>Текст озвучки <small class="lang-text-hint">${item.chars.toLocaleString('uk-UA')} символів · правки зберігаються самі</small>${item.lines?`<small class="lang-text-lines">Кожен рядок звучить у свій час, як фраза оригіналу (${item.lines} рядків): правте слова, але не об’єднуйте й не розбивайте рядки</small>`:''}</span><textarea rows="9" spellcheck="false">${esc(text)}</textarea></label>`
      :`<div class="lang-actions"><p>Студія перекладе текст і заголовок ролика: кілька центів, зазвичай до хвилини.${langData.openrouter===true?'':' <span class="lang-warn">Потрібен ключ OpenRouter у налаштуваннях студії.</span>'}</p><button type="button" class="primary lang-translate">Перекласти</button></div>`}
    <div class="lang-job" role="status" aria-live="polite" hidden></div></section>
    <section class="lang-step${item.text?'':' is-off'}"><h3><em>2</em>Озвучка вашим голосом</h3>
      ${item.text?`<div class="lang-voice-bar">${spec.engines?`<label class="lang-chip-select" title="Рушій Fish Audio"><span>Рушій</span><select data-field="engine">${spec.engines.map(engine=>`<option value="${engine.id}"${engine.id===spec.engine?' selected':''}>${esc(engine.name)} · ${esc(engine.note)}</option>`).join('')}</select></label>
          <label class="lang-chip-select" title="Наскільки точно триматися прикладу голосу"><span>Схожість</span><select data-field="style">${(spec.styles || []).map(style=>`<option value="${style.id}"${style.id===spec.style?' selected':''}>${esc(style.name)}</option>`).join('')}</select></label>`:''}
          ${spec.configured===true?'':`<span class="lang-warn">Додайте ключ ${esc(spec.name)}: налаштування студії → «Ключі сервісів»</span>`}</div>
        ${langOwnBlock(item)}
        <div class="lang-sample-row"><div class="lang-sample">${hasSample?`<span class="lang-sample-by" title="Чим зроблено цей зразок">Зразок<small>${esc([spec.engines?.find(engine=>engine.id===spec.engine)?.name,spec.styles?.find(style=>style.id===spec.style)?.name].filter(Boolean).join(' · ') || spec.name)}</small></span><div class="lang-player" data-kind="sample-${esc(item.voice_key)}"></div><button type="button" class="lang-icon lang-sample-run" title="Новий зразок" aria-label="Новий зразок">${langIcons.redo}</button>`
            :`<button type="button" class="secondary lang-sample-run"${langHasVoice(item)?'':' data-blocked="1" disabled title="Спершу додайте приклад голосу цією мовою"'}>${langIcons.play}Послухати зразок</button>`}</div>
          <label class="lang-chip-select lang-sample-size" title="Скільки речень озвучити в зразку"><span>Речень</span><select>${[3,5,10,20].map(n=>`<option value="${n}"${n===langSampleSize()?' selected':''}>${n}</option>`).join('')}</select></label>
          <button type="button" class="primary lang-voice-run" title="${item.chars.toLocaleString('uk-UA')} символів"${langHasVoice(item)?'':' data-blocked="1" disabled'}>${readyVoice?'Озвучити заново':'Озвучити весь ролик'} · <b class="lang-voice-cost">${langCost(spec,price)}</b></button></div>
        ${readyVoice?`<div class="lang-voice"><div class="lang-voice-head"><b>Готова озвучка</b><small>${voice.made_by?`${esc(voice.made_by)} · `:''}${voice.duration?clock(voice.duration):''}${voice.source_duration?` · ролик ${clock(voice.source_duration)}`:''}${fit?` · ${fit}`:''}${voice.longer?` · довша на ${String(voice.longer).replace('.',',')} с`:''}</small>
          <a class="lang-icon lang-download" href="${langUrl(id,item.code,'voice',voice.made_at)}&download=${encodeURIComponent(`Озвучка ${item.name}.mp3`)}" download="Озвучка ${esc(item.name)}.mp3" title="Завантажити MP3${item.folder?' · копія лежить у папці випуску':''}" aria-label="Завантажити MP3">${langDownloadIcon}</a></div>
          <div class="lang-player" data-kind="voice"></div></div>`:''}`
      :'<p class="lang-off">Спершу перекладіть текст.</p>'}
    <div class="lang-job" role="status" aria-live="polite" hidden></div></section>
    <section class="lang-step"><h3><em>3</em>Прев’ю</h3>
      ${langData.thumbnail?`<div class="lang-thumbs"><figure class="lang-thumb"><img src="/api/projects/${encodeURIComponent(id)}/cover?v=${Date.now()}" alt="Прев’ю до перекладу" loading="lazy">
          <div class="project-actions lang-thumb-actions"><a class="project-action" href="/api/projects/${encodeURIComponent(id)}/languages/original/thumbnail?download=${encodeURIComponent('Прев’ю оригінал.png')}" download="Прев’ю оригінал.png" title="Завантажити прев’ю" aria-label="Завантажити прев’ю оригіналу">${langDownloadIcon}</a></div><figcaption>${langOriginalName()}</figcaption></figure>
        <figure class="lang-thumb">${item.files.thumbnail?`<div class="lang-thumb-run has-picture"><img src="${langUrl(id,item.code,'thumbnail')}" alt="Прев’ю після перекладу" loading="lazy"><span class="lang-thumb-wand">${typeof thumbnailIcon==='string'?thumbnailIcon:''}<small>Перекласти ще раз</small></span></div>
          <div class="project-actions lang-thumb-actions"><button type="button" class="project-action thumbnail lang-thumb-redo" title="Перекласти ще раз" aria-label="Перекласти прев’ю ще раз">${typeof thumbnailIcon==='string'?thumbnailIcon:''}</button><a class="project-action" href="${langUrl(id,item.code,'thumbnail')}&download=${encodeURIComponent(`Прев’ю ${item.name}.png`)}" download="Прев’ю ${esc(item.name)}.png" title="Завантажити прев’ю" aria-label="Завантажити прев’ю ${esc(item.name)}">${langDownloadIcon}</a></div>`
          :`<button type="button" class="lang-thumb-run" aria-label="Перекласти прев’ю"><span class="lang-thumb-wand">${typeof thumbnailIcon==='string'?thumbnailIcon:''}<small>Натисніть, щоб перекласти</small></span></button>`}<figcaption>${langFlag(item.code)} ${esc(item.name)}</figcaption>
          <div class="lang-thumb-ask" hidden><label><span>Побажання <em>необов’язково</em></span><input type="text" maxlength="1500" placeholder="Наприклад: напис коротший і жовтий, слово DAY не перекладати" value="${esc(langDrafts[`${id}:${item.code}:wishes`] || '')}"></label>
            <div class="lang-thumb-ask-actions"><button type="button" class="secondary lang-thumb-ask-cancel">Скасувати</button><button type="button" class="primary lang-thumb-ask-go">Перекласти</button></div></div></figure></div>`
      :'<p class="lang-off">У випуску ще немає прев’ю. Створіть його на вкладці «Прев’ю».</p>'}
    <div class="lang-job" role="status" aria-live="polite" hidden></div></section>`;
  for(const box of card.querySelectorAll('.lang-player')){
    const kind=box.dataset.kind;
    const url=kind==='channel'?`/api/channels/${encodeURIComponent(langData.channel_id)}/voices/${item.code}/file?v=${item.channel_voice.stamp}`
      :langUrl(id,item.code,kind,kind==='voice'?voice.made_at:kind==='own'?item.own_voice.stamp:undefined);
    const player=voicePlayer(id,url);
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
      // the voicing was of the old words: it leaves the card, and the button voices anew
      const made=card.querySelector('.lang-voice');if(made){made.querySelectorAll('audio').forEach(audio=>audio.pause());made.remove();}
      const voiceRun=card.querySelector('.lang-voice-run');if(voiceRun&&voiceRun.firstChild?.nodeType===3)voiceRun.firstChild.textContent='Озвучити весь ролик · ';
      
      const fresh=langData.items.find(entry=>entry.code===item.code);
      if(fresh){const cost=card.querySelector('.lang-voice-cost');if(cost)cost.textContent=langCost(spec,fresh.prices?.[spec.id]);}
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
  card.querySelector('.lang-translate')?.addEventListener('click',()=>langStart(id,'translate',item.code));
  card.querySelector('.lang-sample-size select')?.addEventListener('change',event=>{try{localStorage.setItem('langSampleSentences',event.target.value);}catch{}});
  card.querySelector('.lang-sample-run')?.addEventListener('click',async()=>{if(!(await flush()))return;langStart(id,'sample',item.code,{sentences:langSampleSize()});});
  card.querySelector('.lang-voice-run')?.addEventListener('click',async()=>{
    if(!(await flush()))return;
    const fresh=langData.items.find(entry=>entry.code===item.code) || item,cost=fresh.prices&&spec.id in fresh.prices?fresh.prices[spec.id]:price,chars=fresh.chars ?? item.chars;
    modal(`Озвучити ${item.name}?`,`<p>${esc(spec.name)} озвучить весь текст вашим голосом: ${chars.toLocaleString('uk-UA')} символів, ${spec.free?`<b>безкоштовно</b> (рушій ${esc(spec.engines.find(engine=>engine.id===spec.engine)?.name || '')})`:cost===null?`за ціною ${esc(spec.name)} (дивіться на fish.audio). Гроші спишуться з вашого рахунку ${esc(spec.name)}`:`орієнтовно <b>${langMoney(cost)}</b>. Гроші спишуться з вашого рахунку ${esc(spec.name)}`}.</p>
      <p>Студія склеїть частини, вирівняє гучність і піджене довжину під ролик. Зазвичай це кілька хвилин.</p>`,
      [{label:'Скасувати',run:closeModal},{label:`Озвучити · ${langCost(spec,cost)}`,primary:true,run:()=>{closeModal();langStart(id,'voice',item.code);}}]);
  });
  // the wand opens the wishes under the translated picture; «Перекласти» there starts Codex (user, 2 November 2026:
  // «побажання мають проявлятися тоді, коли нажимаєте… перекласти»)
  const ask=card.querySelector('.lang-thumb-ask'),wishes=ask?.querySelector('input');
  wishes?.addEventListener('input',()=>{langDrafts[`${id}:${item.code}:wishes`]=wishes.value;});
  wishes?.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();ask.querySelector('.lang-thumb-ask-go').click();}});
  card.querySelectorAll('button.lang-thumb-run, .lang-thumb-redo').forEach(button=>button.addEventListener('click',()=>{if(!ask)return;ask.hidden=false;wishes.focus();}));
  ask?.querySelector('.lang-thumb-ask-cancel').addEventListener('click',()=>{ask.hidden=true;});
  ask?.querySelector('.lang-thumb-ask-go').addEventListener('click',()=>{ask.hidden=true;langStart(id,'thumbnail',item.code,{wishes:wishes.value || ''});});
  langOwnWire(id,card,item);
  return card;
}

// Messages of this tab stand where the author pressed, not in the studio's banner at the top (user, 2 November 2026:
// «сповіщення… мають бути там, де я нажимаю кнопку»): a short line at the end of that step, or under «Нова мова».
const langStepOf={translate:0,sample:1,voice:1,thumbnail:2};
function langPlace(code,kind){
  const card=document.querySelector(`#project-langs .lang-card[data-code="${code}"]`);
  return card?.querySelectorAll('.lang-step')[langStepOf[kind] ?? 0] || document.querySelector('#project-langs .lang-pills');
}
function langNote(where,message,error=false){
  const holder=where?.closest?.('.lang-step, .lang-pills, .lang-card') || where;
  if(!holder){status(message,error);return;}
  holder.querySelector(':scope > .lang-note')?.remove();
  const note=document.createElement('p');note.className='lang-note'+(error?' is-error':'');note.setAttribute('role',error?'alert':'status');note.textContent=message;
  const job=holder.querySelector(':scope > .lang-job');if(job)job.before(note);else holder.append(note);
  if(!error)setTimeout(()=>note.remove(),8000);
}

// the slots whose cancel the author pressed: only they read «Скасовуємо…» (the button used to be disabled with every other
// button of the card while a job ran, and the next poll took that for a cancel asked; user, 2 November 2026)
const langAsked=new Set();
async function langCancel(id,slot,button){
  langAsked.add(slot);
  if(button){button.disabled=true;button.textContent='Скасовуємо…';}
  try{await api(`/api/projects/${encodeURIComponent(id)}/languages/cancel`,'POST',{slot});}catch(error){langNote(button,error.message,true);}
}

async function langStart(id,kind,code,extra={}){
  try{
    const {job}=await api(`/api/projects/${encodeURIComponent(id)}/languages/${code}/${kind}`,'POST',{provider:langData.provider,...extra});
    langPlace(code,kind)?.querySelector(':scope > .lang-note')?.remove();
    langData.jobs=[...langJobs().filter(other=>other.slot!==job.slot),job];langData.job=job;
    showLangJob();pollLangs(id);
  }catch(error){langNote(langPlace(code,kind),error.message,true);}
}

// Jobs run side by side (user, 2 November 2026: «перекладалось текст, я нажав перекласти прев'ю, і воно зупиняє
// переклад?»): each language has two lanes, its text and voice, and its thumbnail; other languages run at once too.
const langGroupOf=kind=>kind==='thumbnail'?'thumbnail':'voice';
function langJobs(){return langData?.jobs || (langData?.job?[langData.job]:[]);}
function langRunning(code,group){return langJobs().some(job=>job.status==='running'&&(!code||job.code===code)&&(!group||langGroupOf(job.kind)===group));}

function showLangJob(){
  // a job's line sits in the step it works on, inside the language's own card (user, 2 November 2026: «не треба
  // розкидати блоки… все в один блок»): the text for a translation, the voice for a sample or the whole, the thumbnail
  const jobs=langJobs();
  // the capsule of a language at work shows it, whichever card is open
  document.querySelectorAll('#project-langs .lang-pill').forEach(pill=>pill.classList.toggle('is-working',langRunning(pill.dataset.code)));
  for(const card of document.querySelectorAll('#project-langs .lang-card[data-code]')){
    const code=card.dataset.code,steps=[...card.querySelectorAll('.lang-step')];
    // a running lane locks only its own steps: the text and voice, or the thumbnail
    card.querySelectorAll('button:not(.voice-player-play):not(.voice-player-mute)').forEach(button=>{
      if(button.classList.contains('lang-cancel'))return;
      const index=steps.findIndex(step=>step.contains(button));
      const locked=index<0?langRunning(code):langRunning(code,index===2?'thumbnail':'voice');
      button.disabled=locked || button.dataset.blocked==='1';});
    steps.forEach((step,index)=>{
      const box=step.querySelector(':scope > .lang-job');if(!box)return;
      const own=jobs.filter(job=>job.code===code&&langStepOf[job.kind]===index);
      const job=own.find(item=>item.status==='running') || own.sort((a,b)=>(b.finished_at||0)-(a.finished_at||0))[0];
      const busy=job?.status==='running';
      // a finished job shows itself in the card (the text, the player, the picture): only a failure or a cancel says so
      const recent=job&&['failed','cancelled'].includes(job.status)&&job.finished_at&&Date.now()/1000-job.finished_at<120;
      box.hidden=!job || (!busy && !recent);
      box.dataset.status=job?.status || '';
      step.classList.toggle('is-working',busy);
      const slot=job?.slot || (job?`${job.code}|${langGroupOf(job.kind)}`:'');
      if(!busy)langAsked.delete(slot);
      if(box.hidden){box.innerHTML='';return;}
      // the poll redraws this line every 2 s: a cancel already asked for stays shown
      const stopping=langAsked.has(slot) || job.stage==='Скасовуємо…';
      box.innerHTML=busy?`${typeof exportSpinner==='string'?exportSpinner:''}<span>${esc(job.stage || '')}</span><progress max="100" value="${job.progress || 0}"></progress><button type="button" class="secondary lang-cancel"${stopping?' disabled':''}>${stopping?'Скасовуємо…':'Скасувати'}</button>`
        :job.status==='cancelled'?`<span>Скасовано, нічого не збережено.</span>`
        :`<span>Не вдалося: ${esc(job.error || '')}</span>`;
      const cancel=box.querySelector('.lang-cancel');
      cancel?.addEventListener('click',()=>langCancel(state.project.id,slot,cancel));
    });
  }
  // the «after» window of the language being redrawn says so in place of its wand
  for(const tile of document.querySelectorAll('#project-langs .lang-thumb-run')){
    const drawing=langRunning(tile.closest('.lang-card')?.dataset.code,'thumbnail');
    tile.classList.toggle('is-drawing',drawing);
    const label=tile.querySelector('.lang-thumb-wand small');
    if(label){label.dataset.idle??=label.textContent;label.textContent=drawing?'Codex перекладає, 1–3 хвилини…':label.dataset.idle;}
  }
}

async function pollLangs(id){
  if(langPolling)return;langPolling=true;
  try{
    while(langBusy() && state.project?.id===id){
      await new Promise(resolve=>setTimeout(resolve,2000));
      try{const before=langJobs().filter(job=>job.status==='running').map(job=>job.slot);
        langData=await api(`/api/projects/${encodeURIComponent(id)}/languages`);
        // a lane that has just finished brings its result into the card
        const finished=before.some(slot=>!langJobs().some(job=>job.slot===slot&&job.status==='running'));
        if(finished && state.view==='langs' && state.project?.id===id)drawLangs(id);else showLangJob();
      }catch{}
    }
  }finally{langPolling=false;}
}

$('view-langs')?.addEventListener('click',()=>setProjectView('langs'));

// «Озвучка» in the montage can play a translated voice instead of the original, to see how the film goes with it
// (user, 2 November 2026: «дай змогу міняти озвучку, щоб глянути, як вийде»). Preview only: the export keeps the
// original. The choice holds per episode in this browser.
function dubChoice(){
  if(!state.project)return null;
  let code=null;try{code=localStorage.getItem(`dub:${state.project.id}`);}catch{}
  return code || null;
}
let dubStamps={};
function isVoiceClip(clip){
  if(clip?.kind!=='audio')return false;
  const voice=typeof voiceAssetId==='function'?voiceAssetId(state.plan,state.project):null;
  return clip.asset_id===voice || Object.keys(state.project?.audio_gain || {}).includes(clip.asset_id);
}
function dubbedVoiceUrl(clip){
  const code=dubChoice();
  if(!code || !isVoiceClip(clip))return null;
  return `/api/projects/${encodeURIComponent(state.project.id)}/languages/${code}/file/voice?v=${dubStamps[code] || 0}`;
}
function addLayerDubControl(heading,layer){
  if(!(layer?.clips || []).some(isVoiceClip))return;
  const code=dubChoice(),button=document.createElement('button');
  button.type='button';button.className='layer-sound layer-dub'+(code?' is-dubbed':'');button.draggable=false;
  button.title=code?`Перегляд з озвучкою ${code.toUpperCase()} (лише перегляд, експорт з оригіналом)`:'Послухати ролик з перекладеною озвучкою';
  button.setAttribute('aria-label','Мова озвучки для перегляду');
  button.innerHTML=code?`<span class="layer-dub-flag">${langFlags[code] || code}</span>`:'<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3"/></svg>';
  button.addEventListener('click',async event=>{
    event.stopPropagation();
    document.querySelector('.layer-dub-menu')?.remove();
    let data;try{data=await api(`/api/projects/${encodeURIComponent(state.project.id)}/languages`);}catch(error){status(error.message,true);return;}
    const ready=data.items.filter(item=>item.files?.voice&&item.voice_current!==false);
    for(const item of ready)dubStamps[item.code]=Math.round(item.voice?.made_at || 0);
    const menu=document.createElement('div');menu.className='layer-dub-menu lang-menu';menu.setAttribute('role','menu');
    menu.innerHTML=`<button type="button" data-code=""${!code?' class="active"':''}>🎙<span>Оригінал</span></button>${ready.map(item=>`<button type="button" data-code="${item.code}"${item.code===code?' class="active"':''}>${langFlag(item.code)}<span>${esc(item.name)}</span><small>${esc(item.label)}</small></button>`).join('') || '<p class="layer-dub-empty">Готової озвучки іншими мовами ще немає. Її робить вкладка «Мови».</p>'}`;
    const rect=button.getBoundingClientRect();Object.assign(menu.style,{position:'fixed',left:`${rect.left}px`,top:`${rect.bottom+6}px`,zIndex:60});
    document.body.append(menu);
    const close=()=>{menu.remove();document.removeEventListener('pointerdown',outside,true);};
    const outside=e=>{if(!menu.contains(e.target)&&e.target!==button)close();};
    document.addEventListener('pointerdown',outside,true);
    menu.addEventListener('click',e=>{
      const choice=e.target.closest('button[data-code]');if(!choice)return;close();
      try{if(choice.dataset.code)localStorage.setItem(`dub:${state.project.id}`,choice.dataset.code);else localStorage.removeItem(`dub:${state.project.id}`);}catch{}
      const playing=state.playing;if(typeof stopPlayback==='function'&&playing)stopPlayback();
      buildAudioNodes();renderProject();
      status(choice.dataset.code?'Перегляд з перекладеною озвучкою. Експорт лишається з оригіналом.':'Перегляд з оригінальною озвучкою.');
    });
  });
  heading.append(button);
}
