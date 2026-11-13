const langSamplePreview=new Set();
// languages.js — the «Мови» tab after «Прев’ю» (backend/languages.py): the episode's voice in other languages with the
// author's own cloned voice, and the thumbnail with its words translated. The video itself is not changed (user,
// 2 November 2026: «відео ролик перекладати я поки не хочу, лише аудіо і превью»). Each language goes in three steps:
// the text (translated by MiniMax, editable), the voice (a cheap sample first, then the whole with its price shown
// before) and the thumbnail (before and after).
const langDrafts={};
let langData=null,langPolling=null;
let langBalance=null,langBalanceLoading=false,langBalanceTimer=null;
const langUploads=new Map();

const langDownloadIcon='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11m0 0-4.5-4.5M12 15l4.5-4.5M5 19h14"/></svg>';
function langCost(spec,value){return spec?.free||value===0?'безкоштовно':value==null?`за тарифом ${spec?.name || 'сервісу'}`:spec?.unit==='credits'?`≈ ${Math.ceil(value).toLocaleString('uk-UA')} кредитів`:langMoney(value || 0);}
function langMoney(value){return value>=0.01?`≈ $${value.toFixed(2).replace('.',',')}`:'менше $0,01';}
function langUrl(id,code,kind,stamp){return `/api/projects/${encodeURIComponent(id)}/languages/${code}/file/${kind}?v=${stamp || Date.now()}`;}

function renderLangView(){
  const tab=$('view-langs'),section=$('project-langs');if(!tab||!section)return;
  const project=state.project,open=!!project&&state.view==='langs';
  tab.hidden=!project;tab.classList.toggle('active',open);tab.setAttribute('aria-pressed',String(open));
  if(typeof updateLanguageCostBadge==='function')updateLanguageCostBadge(project?.id);
  section.hidden=!open;
  if(!open){langCloseOriginal();langVoiceDialog?.dialog.close();langResultDialog?.dialog.close();langThumbnailDialog?.dialog.close();if(section.childElementCount){section.querySelectorAll('.lang-alignment').forEach(block=>block.dispose?.());section.querySelectorAll('audio').forEach(audio=>audio.pause());section.replaceChildren();}delete section.dataset.project;return;}
  if(section.dataset.project!==project.id){section.dataset.project=project.id;section.innerHTML=`<div class="lang-view"><div class="lang-head"><h1>${langTranslateIcon}Мови</h1><p class="lang-lead">Завантаження…</p></div></div>`;loadLangs(project.id);}
}

async function loadLangs(id){
  let data;
  try{data=await api(`/api/projects/${encodeURIComponent(id)}/languages`);}
  catch(error){if(state.project?.id===id&&state.view==='langs'){const lead=document.querySelector('#project-langs .lang-lead');if(lead)lead.textContent=error.message;}return;}
  if(state.project?.id!==id || state.view!=='langs')return;
  langData=data;
  drawLangs(id);
  if(langBusy())pollLangs(id);
}

function langBalanceMarkup(){
  const known=Number.isFinite(langBalance?.remaining_credits),stale=langBalance?.state==='stale';
  return `<div><small>Баланс ElevenLabs</small><strong>${known?`${langBalance.remaining_credits.toLocaleString('uk-UA')} кредитів`:langBalanceLoading?'Перевіряємо…':'Недоступний'}</strong>${stale?'<small>Останній відомий баланс</small>':''}</div>`;
}
function langPaintBalance(){
  document.querySelectorAll('#project-langs .lang-balance,.lang-result-dialog .lang-balance,.lang-confirm-balance').forEach(box=>{
    box.innerHTML=langBalanceMarkup();
    box.setAttribute('aria-busy',String(langBalanceLoading));
  });
}

async function langRefreshBalance(force=false){
  clearTimeout(langBalanceTimer);
  if(state.view!=='langs'||!langData?.items.some(item=>langSpec(item).id==='elevenlabs')||langBalanceLoading)return;
  langBalanceLoading=true;langPaintBalance();
  try{langBalance=await api('/api/elevenlabs/balance'+(force?'?refresh=1':''));}
  catch(error){langBalance={...langBalance,state:langBalance?.remaining_credits!=null?'stale':'unavailable',error:error.message};}
  finally{langBalanceLoading=false;langPaintBalance();if(state.view==='langs'&&langData?.items.some(item=>langSpec(item).id==='elevenlabs'))langBalanceTimer=setTimeout(()=>langRefreshBalance(),30000);}
}

function langBusy(){return langJobs().some(job=>job.status==='running');}

// A flag for each language, shown in its capsule and in the «+» menu.
const langFlags={en:'🇬🇧',uk:'🇺🇦',ru:'🇷🇺',de:'🇩🇪',es:'🇪🇸',fr:'🇫🇷',pt:'🇵🇹',it:'🇮🇹',pl:'🇵🇱',tr:'🇹🇷',nl:'🇳🇱',hi:'🇮🇳',ar:'🇸🇦',ja:'🇯🇵',ko:'🇰🇷',zh:'🇨🇳',id:'🇮🇩',cs:'🇨🇿',ro:'🇷🇴',kk:'🇰🇿'};
// The original script file uses the same muted document icon.
const langMarkIcons={text:'<svg viewBox="0 0 24 24"><path d="M14 3H6v18h12V7zM14 3v5h4M9 12h6m-6 4h6"/></svg>'};
function langFlag(code){return `<span class="lang-flag" aria-hidden="true">${langFlags[code] || '🌐'}</span>`;}
// the language open below the capsules, per episode, remembered in the browser
function langChosen(id){
  let code=null;try{code=localStorage.getItem(`langTab:${id}`);}catch{}
  const codes=(langData?.items || []).map(item=>item.code);
  return codes.includes(code)?code:codes[0] || null;
}
// Each language has its own script, narrator, narration and thumbnail cards.
function drawLangs(id){
  const section=$('project-langs');if(!section||section.dataset.project!==id)return;
  if(langOriginalDialog?.dataset.project!==id)langCloseOriginal();
  langCloseSampleMenu();
  section.querySelectorAll('.lang-alignment').forEach(block=>block.dispose?.());
  section.querySelectorAll('audio').forEach(audio=>audio.pause());
  const data=langData;
  const chosen=langChosen(id);
  section.innerHTML=`<div class="lang-view">
    <div class="lang-head"><h1>${langTranslateIcon}Мови<button type="button" class="lang-add-language" aria-label="Додати мову перекладу" title="Додати мову">+</button></h1>
      <p class="lang-lead">Озвучка ролика іншими мовами вашим голосом і прев’ю з перекладеним текстом.</p></div>
    <div class="lang-cards"></div>
  </div>`;
  // listeners go on the page's own root, drawn anew each time, so they never pile up on the section
  const view=section.querySelector('.lang-view'),cards=section.querySelector('.lang-cards');
  const addLanguage=section.querySelector('.lang-add-language');addLanguage.hidden=!langScriptAvailable(data).length;addLanguage.onclick=()=>langOpenScriptPicker(id);
  const item=data.items.find(entry=>entry.code===chosen);
  if(item)cards.append(langCard(id,item,langSpec(item)));
  else {cards.innerHTML='<section class="lang-script-step lang-step"><div class="lang-script-library"></div></section>';langScriptLibrary(id,cards.querySelector('.lang-script-library'),data);}
  if(data.items.some(item=>langSpec(item).id==='elevenlabs')){langPaintBalance();langRefreshBalance();}
  view.addEventListener('change',event=>langChangeVoiceSetting(id,event));
  langRefreshVoiceDialog();
  langRefreshVoiceResultDialog();
  langRefreshThumbnailDialog();
  showLangJob();
  langLoadVoiceScores(id);
}

// The voice of a language always comes from an example in that language (user, 2 November 2026: «переклад будемо брати
// завжди від прикладу ролика на мові… або запис, або закинути приклад носія»): the channel's example serves every
// episode («в настройках каналу»), an episode's own wins («якщо ні, то можна закинути свій»). No example, no voicing.
const langIcons={play:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l11-6.5z"/></svg>',redo:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/></svg>',upload:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16V4m0 0-4.5 4.5M12 4l4.5 4.5M5 20h14"/></svg>',trash:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M10 4h4m-8 3 1 13h10l1-13"/></svg>',back:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 14 4 9l5-5M4 9h11a5 5 0 0 1 0 10h-3"/></svg>'};
const micIcon='<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>';
const langWaveIcon='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 10v4m4-8v12m5-16v20m5-16v12m4-8v4"/></svg>';
function langRemoteVoice(item){
  return (item.provider==='heygen' && item.narration?.heygen_voice_id) || item.remote_voice_ids?.[item.provider];
}
function langHasVoice(item){
  if(langRemoteVoice(item))return true;
  if(item.provider==='heygen' && langSpec(item).engine==='starfish')return false;
  if(Object.values(item.remote_voice_ids || {}).some(Boolean))return false;
  return !!(item.own_voice || item.channel_voice || langData?.source?.voice);
}
function langHeardWarn(example){return example?.heard===false?'<p class="lang-warn">Не вдалося розпізнати слова в прикладі. Для точнішого голосу запишіть або завантажте чіткіший запис без фонового шуму.</p>':'';}
function langOwnBlock(item){
  const own=item.own_voice,shared=item.channel_voice,fromOriginal=!!langData?.source?.voice;
  // an example in hand is a small line (user, 2 November 2026: «не виділяй її так… просто маленький приклад, основа
  // акценту на створенні аудіо»; «кнопки… просто значки»): its label, a compact player and icons
  const model=item.fish_model?'<i class="lang-model-mark" title="Збережена модель голосу у Fish: звучить чистіше, ніж швидкий клон">✓ модель</i>':'';
  const add=(again)=>`<button type="button" class="lang-icon lang-own-record" title="${again?'Записати заново':'Записати себе'}" aria-label="${again?'Записати заново':'Записати себе'}">${micIcon}</button><label class="lang-icon lang-own-file" role="button" tabindex="0" title="Завантажити приклад голосу" aria-label="Завантажити приклад голосу">${langIcons.upload}<input type="file" accept="audio/*,video/*" hidden></label>`;
  if(langRemoteVoice(item))return `<div class="lang-own has-voice"><span class="lang-own-label">Голос збережений у сервісі</span><details class="voice-lab-advanced"><summary>ID голосу</summary><code>${esc(langRemoteVoice(item))}</code></details></div>`;
  if(own)return `<div class="lang-own has-voice"><span class="lang-own-label">Голос диктора${model?`<small>${model}</small>`:''}</span><div class="lang-player" data-kind="own"></div>
    <div class="lang-own-actions"><button type="button" class="lang-icon lang-own-remove" title="Прибрати приклад" aria-label="Прибрати приклад">${langIcons.trash}</button></div>${langHeardWarn(own)}</div>`;
  if(shared)return `<div class="lang-own has-voice"><span class="lang-own-label">Голос диктора<small>з налаштувань каналу ${model}</small></span><div class="lang-player" data-kind="channel"></div>
    <div class="lang-own-actions"><button type="button" class="lang-icon lang-own-remove" title="Прибрати приклад" aria-label="Прибрати приклад">${langIcons.trash}</button></div>${langHeardWarn(shared)}</div>`;
  return `<div class="lang-own source-voice"><span class="lang-own-label">Голос диктора</span><div class="lang-own-actions">${add(false)}</div><small class="lang-source-note">${fromOriginal?'Зараз голос береться з оригінального аудіо ролика.':'Додайте приклад голосу для озвучки.'}</small></div>`;
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
function langPaintUpload(url){
  const upload=langUploads.get(url);
  document.querySelectorAll('[data-upload-url]').forEach(box=>{
    if(box.dataset.uploadUrl!==url)return;
    box.querySelector('.lang-reference-progress')?.remove();
    box.classList.toggle('is-uploading',!!upload);box.setAttribute('aria-busy',String(!!upload));
    if(!upload)return;
    box.querySelectorAll('audio').forEach(audio=>audio.pause());
    const line=document.createElement('div');line.className='lang-reference-progress';line.setAttribute('role','status');line.setAttribute('aria-live','polite');
    line.innerHTML=`<span class="lang-upload-spinner" aria-hidden="true"></span><div><b>${upload.processing?'Готуємо MP3 та розпізнаємо голос…':`Завантажуємо · ${upload.percent}%`}</b><small title="${esc(upload.name)}">${esc(upload.name)}</small>${upload.processing?'':`<progress max="100" value="${upload.percent}" aria-label="Завантаження прикладу голосу"></progress>`}</div>`;
    box.append(line);
  });
}
async function langSendExample(url,blob,name,said,holder){
  if(langUploads.has(url))throw new Error('Цей приклад уже завантажується.');
  holder.dataset.uploadUrl=url;
  const upload={name,percent:0,processing:false};langUploads.set(url,upload);langPaintUpload(url);showLangJob();
  try{return await new Promise((resolve,reject)=>{
    const xhr=new XMLHttpRequest();xhr.open('POST',url);xhr.timeout=1800000;
    xhr.setRequestHeader('Content-Type','application/octet-stream');xhr.setRequestHeader('X-File-Name',encodeURIComponent(name));xhr.setRequestHeader('X-Said-Text',encodeURIComponent(said || ''));
    xhr.upload.onprogress=event=>{if(event.lengthComputable)upload.percent=Math.round(event.loaded/event.total*100);langPaintUpload(url);};
    xhr.upload.onload=()=>{upload.processing=true;langPaintUpload(url);};
    xhr.onload=()=>{let data;try{data=JSON.parse(xhr.responseText);}catch{reject(new Error('Студія повернула некоректну відповідь.'));return;}if(xhr.status>=200&&xhr.status<300)resolve(data);else reject(new Error(data.error || 'Не вдалося зберегти запис'));};
    xhr.onerror=()=>reject(new Error('Завантаження перервано. Перевірте з’єднання зі студією.'));
    xhr.ontimeout=()=>reject(new Error('Обробка запису не завершилась вчасно. Перевірте стан студії.'));
    xhr.onabort=()=>reject(new Error('Завантаження скасовано.'));
    xhr.send(blob);
  });}finally{langUploads.delete(url);langPaintUpload(url);showLangJob();}
}
function langOwnWire(id,card,item){
  const box=card.querySelector('.lang-own');if(!box)return;
  const url=`/api/projects/${encodeURIComponent(id)}/languages/${item.code}/own-voice`;
  box.dataset.uploadUrl=url;langPaintUpload(url);
  const send=async(blob,name)=>{
    try{const data=await langSendExample(url,blob,name,item.passage,box);if(state.project?.id===id&&state.view==='langs'){langData=data;drawLangs(id);}}
    catch(error){const current=[...document.querySelectorAll('[data-upload-url]')].find(element=>element.dataset.uploadUrl===url);if(current)langNote(current,error.message,true);}
  };
  box.querySelectorAll('.lang-own-file input').forEach(file=>file.addEventListener('change',()=>{const chosen=file.files[0];if(chosen)send(chosen,chosen.name);}));
  box.querySelector('.lang-own-file')?.addEventListener('keydown',event=>{
    if(event.key==='Enter'||event.key===' '){event.preventDefault();event.currentTarget.querySelector('input').click();}
  });
  box.querySelector('.lang-own-record')?.addEventListener('click',event=>langRecord(event.currentTarget,box,send));
  box.querySelector('.lang-own-remove')?.addEventListener('click',async()=>{
    try{const data=await api(`/api/projects/${encodeURIComponent(id)}/languages/${item.code}/own-voice/remove`,'POST',{});if(state.project?.id===id&&state.view==='langs'){langData=data;drawLangs(id);}}catch(error){langNote(box,error.message,true);}
  });
}

// «Голоси для перекладу» in the channel's settings: one example a language for every episode of the channel.
function channelVoiceDefaults(settings){
  if(!settings)return '';
  return `<div class="channel-voice-defaults"><span class="channel-voice-defaults-label">Збережені налаштування ✓</span><div class="channel-voice-defaults-values"><span>Сервіс <strong>${esc(settings.provider_name)}</strong></span><span>Модель <strong>${esc(settings.engine_name)}</strong></span>${settings.style_name?`<span>Подача <strong>${esc(settings.style_name)}</strong></span>`:''}</div></div>`;
}
async function bindLegacyChannelVoices(channel,initial=null){
  const section=document.getElementById('channel-voices');if(!section)return;
  const base=`/api/channels/${encodeURIComponent(channel.id)}/voices`;
  const draw=data=>{
    if(!section.isConnected)return;
    section.querySelectorAll('audio').forEach(audio=>audio.pause());
    const have=new Set(data.voices.map(item=>item.code));
    section.innerHTML=`<h3>Голоси для перекладу</h3><p>Голоси застосовуються до випусків, де цю мову ще не озвучено.</p>
      ${channelVoiceDefaults(data.narration_defaults)}
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
    const send=async(blob,name)=>{try{draw(await langSendExample(`${base}/${pick.value}`,blob,name,'',section.querySelector('.channel-voice-add')));}catch(error){langNote(section,error.message,true);}};
    record.addEventListener('click',()=>langRecord(record,section,send));
    file.addEventListener('change',()=>{const chosen=file.files[0];if(chosen&&pick.value)send(chosen,chosen.name);});
  };
  try{draw(initial||await api(base));}catch(error){section.innerHTML=`<h3>Голоси для перекладу</h3><p>${esc(error.message)}</p>`;}
}

// The episode's own voice on top, to compare with (user, 2 November 2026: «має бути ще один блок оригінал… аудіо
// оригінала, длительність, послухати можна»).
// «Оригінал (англійська)»: the original's name with its language, as on its card
function langOriginalName(){const original=langData?.languages.find(item=>item.code===langData.source?.language);return `Оригінал${original?` (${esc(original.label)})`:''}`;}
function langThumbnailFlag(item){
  const country=item.flag_country,checked=!!country&&langData.thumbnail_options?.add_flag===true;
  const title=country?`Помітно адаптувати візуал під країну (${country.name}): одяг, прапор, вивіска чи деталі оточення. Вибір зберігається для каналу.`:'Для цієї мови немає однозначного прапора країни';
  return `<label class="lang-thumb-flag${country?'':' is-unavailable'}" title="${esc(title)}"><input type="checkbox" class="lang-thumb-add-flag"${checked?' checked':''}${country?'':' disabled'}><span>Адаптувати під країну${country?` ${esc(country.flag)}`:''}</span></label>`;
}

function langQualityNotice(report,voice=false){
  if(!report || report.state==='ok')return '';
  const issues=report.issues || [];
  const language=code=>langData?.languages?.find(item=>item.code===code)?.name||code||'не визначено';
  const rows=issues.map(entry=>`<li><strong>Фраза ${entry.index+1}${entry.detected?` · ${esc(language(entry.detected))}`:''}</strong>${voice&&Number.isFinite(entry.start)?` <button type="button" class="secondary lang-review-play" data-start="${entry.start}" data-end="${entry.end || entry.start+5}">▶ ${clock(entry.start)}</button>`:''}<p class="lang-quality-phrase">${esc(entry.text||'Текст фрази недоступний. Оновіть сторінку для повторної перевірки.')}</p></li>`).join('');
  return `<div class="lang-quality-alert" role="alert"><strong>${report.state==='unavailable'?'Перевірка мови недоступна':voice?'В озвучці є фрагменти іншою мовою':'У перекладі є фрагменти іншою мовою'}</strong><p>${voice?'Збережені записи залишено для виправлення. Завантаження та збереження цього аудіо заблоковано.':'Озвучення заблоковано до виправлення тексту.'}</p>${issues.length?`<details${issues.length===1?' open':''}><summary>Перевірити ${issues.length} фраз</summary><ul>${rows}</ul></details>`:''}</div>`;
}

function langApplyQuality(card,item){
  const unsafe=item.language_check && item.language_check.state!=='ok';
  const box=card.querySelector('.lang-text-quality');if(box)box.innerHTML=langQualityNotice(item.language_check);
  for(const button of card.querySelectorAll('.lang-sample-run,.lang-voice-run')){
    button.dataset.blocked=unsafe||!langHasVoice(item)?'1':'0';
    button.disabled=button.dataset.blocked==='1'||langRunning(item.code,'voice');
    if(unsafe)button.title='Спершу виправте мову перекладу';else button.removeAttribute('title');
  }
}

function langCacheNote(item,spec){
  const estimate=item.voice_estimates?.[spec.id];
  return estimate?.reused?`Із кешу: ${estimate.reused} із ${estimate.total} фраз. До озвучення: ${estimate.generate}.`:'';
}
function langVoiceAction(item,spec){
  return item.voice_estimates?.[spec.id]?.generate===0?'Зібрати озвучку':item.files?.voice?'Оновити озвучку':'Згенерувати озвучку';
}
function langVoiceStatus(item,spec){
  if(!item.files?.voice||item.voice_current===false||item.voice?.provider!==spec.id)return '';
  if([item.language_check,item.voice_language_check].some(report=>report&&report.state!=='ok'))return '';
  const duration=langVoiceDurationIssue(item);if(duration)return duration.label;
  return item.saved_mix?.state==='saved'?'Озвучку збережено ✓':'Озвучка готова ✓';
}

function langVoiceDurationIssue(item){
  if(item.duration_check&&item.duration_check.state!=='unknown')return ['too_long','too_short'].includes(item.duration_check.state)?item.duration_check:null;
  const actual=item.voice?.duration,source=item.voice?.source_duration||langData?.source?.duration;
  if(!Number.isFinite(actual)||!Number.isFinite(source)||actual<=0||source<=0||Math.abs(actual-source)<=.1)return null;
  return {state:actual>source?'too_long':'too_short',label:actual>source?'Тривалість перевищена':'Тривалість закоротка',difference_seconds:actual-source};
}

function langLetters(text){
  return Array.from(text||'').filter(char=>/\p{L}/u.test(char)&&!/[ʼʻ]/u.test(char)).length;
}

function langTranslationInfo(item){
  if(!Number.isFinite(item.translate_cost))return '';
  return `Переклад · $${item.translate_cost.toFixed(3)}`;
}

function langNumberComparison(item){
  const value=item.translation_length?.number_comparison;
  if(!value?.available || !Number.isFinite(value.difference_percent))return '';
  const number=n=>n.toLocaleString('uk-UA',{maximumFractionDigits:2});
  const percent=(value.difference_percent>0?'+':'')+number(value.difference_percent);
  const limit=item.translation_length?.script_comparison?.tolerance_percent;
  return `Лише літери, з урахуванням чисел: ${percent}% · оригінал ${number(value.source_chars)} · переклад ${number(value.translated_chars)} літер${limit?` · межа ±${limit}%`:''}`;
}

function langModelField(provider){
  return {elevenlabs:'eleven_engine',fishaudio:'fish_engine',heygen:'heygen_model'}[provider];
}
function langSpec(item){
  const choices=item?.narration || {},provider=item?.provider || langData.provider;
  const base=langData.providers.find(entry=>entry.id===provider) || langData.providers[0];
  const engine=choices[langModelField(provider)] || base.engine;
  const style=choices.fish_styles?.[engine] || choices.fish_style || base.style;
  return {...base,engine,style,free:provider!=='elevenlabs'&&(base.engines||[]).some(entry=>entry.id===engine&&entry.per_char===0)};
}

let langVoiceDialog=null;
function langVoiceSummary(id,item){
  const card=document.createElement('div');card.className='lang-voice-summary';card.dataset.code=item.code;
  const spec=langSpec(item),engine=spec.engines?.find(entry=>entry.id===spec.engine);
  const kind=item.own_voice?'own':item.channel_voice?'channel':null;
  card.innerHTML=`<button type="button" class="lang-voice-open" aria-label="Налаштування голосу: ${esc(item.name)}" title="Змінити голос і налаштування">
    <strong>${micIcon}<span>Голос диктора</span></strong><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 4 5 5M4 20l5-1L20 8a2 2 0 0 0-5-5L4 14z"/></svg>
    <span>${esc(spec.name)}<small>${esc(engine?.name||spec.engine)}${spec.styles?' · '+esc(spec.styles.find(style=>style.id===spec.style)?.name||''):''}</small></span></button>
    ${kind?`<div class="lang-summary-player lang-own has-voice"><div class="lang-player" data-kind="${kind}"></div></div>`:`<span class="lang-summary-source">${langRemoteVoice(item)?'Голос збережений у сервісі':langData.source?.voice?'Голос з оригіналу':'Додайте аудіо'}</span>`}`;
  card.querySelector('.lang-voice-open').onclick=()=>langOpenVoiceSettings(id,item.code);
  langWirePlayers(id,card,item);
  return card;
}

function langRefreshVoiceDialog(){
  if(!langVoiceDialog)return;
  const {id,code,dialog}=langVoiceDialog;
  const item=langData?.items.find(entry=>entry.code===code);
  if(state.project?.id!==id||!item){dialog.close();return;}
  dialog.querySelectorAll('audio').forEach(audio=>audio.pause());
  dialog.querySelector('.lang-voice-dialog-body').replaceChildren(langVoiceSetup(id,item));
}

function langOpenVoiceSettings(id,code){
  if(state.project?.id!==id)return;
  const item=langData?.items.find(entry=>entry.code===code);if(!item)return;
  langVoiceDialog?.dialog.close();
  const dialog=document.createElement('dialog');dialog.className='lang-voice-dialog';
  dialog.setAttribute('aria-labelledby','lang-voice-dialog-title');
  dialog.innerHTML=`<div class="lang-script-dialog-head"><h2 id="lang-voice-dialog-title">${langFlag(code)} ${esc(item.name)}</h2><button type="button" class="lang-script-close" aria-label="Закрити налаштування голосу">×</button></div><div class="lang-voice-dialog-body"></div>`;
  langVoiceDialog={id,code,dialog};langRefreshVoiceDialog();
  dialog.querySelector('.lang-script-close').onclick=()=>dialog.close();
  dialog.addEventListener('click',event=>{if(event.target===dialog)dialog.close();});
  dialog.addEventListener('change',event=>langChangeVoiceSetting(id,event));
  dialog.addEventListener('close',()=>{
    dialog.querySelectorAll('audio').forEach(audio=>audio.pause());langCloseSampleMenu();
    if(langVoiceDialog?.dialog===dialog)langVoiceDialog=null;
    dialog.remove();
  },{once:true});
  document.body.append(dialog);dialog.showModal();showLangJob();
}

async function langChangeVoiceSetting(id,event){
    const select=event.target.closest('.lang-chip-select select[data-field], .lang-engine select[data-field], .lang-chip-select input[data-field]');if(!select)return;
    const field=select.dataset.field || 'engine';
    const code=select.closest('.lang-voice-setup')?.dataset.code;
    const entry=langData.items.find(item=>item.code===code);if(!entry)return;
    const controls=select.closest('.lang-voice-setup');controls.dataset.saving='1';showLangJob();
    try{
      const data=await api(`/api/projects/${encodeURIComponent(id)}/languages/provider`,'POST',
        {code,provider:langSpec(entry).id,[field]:select.value.trim()});
      if(state.project?.id===id){langData=data;drawLangs(id);}
    }catch(error){langNote(controls,error.message,true);}
    finally{delete controls.dataset.saving;showLangJob();}
}

function langVoiceSetup(id,item){
  const card=document.createElement('div');card.className='lang-voice-setup';card.dataset.code=item.code;
  const spec=langSpec(item),hasSample=(item.files.samples || []).includes(item.voice_key);
  const readyVoice=item.files.voice&&item.voice_current!==false;
  const savedDefaults=langData.defaults?.by_language?.[item.code] ?? langData.defaults?.saved;
  card.innerHTML=`<div class="lang-voice-panel lang-reference-panel">${langOwnBlock(item)}</div>
        <div class="lang-voice-panel lang-voice-bar"><span class="lang-panel-title">Налаштування озвучення</span><label class="lang-chip-select" title="Сервіс озвучення"><span>Сервіс</span><select data-field="provider">${langData.providers.map(service=>`<option value="${service.id}"${service.id===spec.id?' selected':''}>${esc(service.name)}</option>`).join('')}</select></label>
          ${spec.engines?`<label class="lang-chip-select" title="Модель ${esc(spec.name)}"><span>Рушій</span><select data-field="engine">${spec.engines.map(engine=>`<option value="${engine.id}"${engine.id===spec.engine?' selected':''}>${esc(engine.name)}${spec.id!=='elevenlabs'&&engine.note?' · '+esc(engine.note):''}</option>`).join('')}</select></label>`:''}
          ${spec.id==='heygen'?`<label class="lang-chip-select"><span>ID голосу</span><input data-field="voice_id" maxlength="128" aria-label="ID голосу HeyGen" value="${esc(item.narration?.heygen_voice_id || '')}" placeholder="${esc(item.remote_voice_ids?.heygen || (spec.engine==='starfish'?'ID голосу Starfish':'Автоматично з прикладу'))}"></label>`:''}
          ${spec.styles?`<label class="lang-chip-select" title="Варіативність подачі голосу. Кожен рушій зберігає свій вибір."><span>Подача</span><select data-field="style">${spec.styles.map(style=>`<option value="${style.id}"${style.id===spec.style?' selected':''}>${esc(style.name)}</option>`).join('')}</select></label>`:''}
          ${item.text&&(!readyVoice||langSamplePreview.has(`${id}:${item.code}`))?`<div class="lang-inline-sample">
            <button type="button" class="lang-sample-run lang-sample-round" title="${hasSample?'Відтворити готовий зразок безкоштовно':'Зразок: оберіть кількість речень'}" aria-label="Послухати зразок"${hasSample?'':' aria-haspopup="menu" aria-expanded="false"'}${langHasVoice(item)?'':' data-blocked="1" disabled'}>${playIcon}</button>
            <span class="lang-inline-sample-label">Зразок<small class="lang-sample-time"${hasSample?'':' hidden'}>${hasSample?`${clock(0)} / ${clock(item.sample?.duration || 0)}`:''}</small></span>
            <button type="button" class="lang-sample-choose" title="Інша кількість речень" aria-label="Обрати інший зразок" aria-haspopup="menu" aria-expanded="false"${hasSample?'':' hidden'}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></button>
            ${hasSample?`<audio class="lang-sample-audio" preload="metadata" src="${langUrl(id,item.code,'sample-'+item.voice_key,item.sample?.made_at)}"></audio>`:''}
          </div>`:''}
          ${spec.configured===true?'':`<span class="lang-warn">Додайте ключ ${esc(spec.name)}: налаштування студії → «Ключі сервісів»</span>`}
          ${spec.id==='elevenlabs'&&spec.configured===true&&spec.connection_error?`<span class="lang-warn">${esc(spec.connection_error)}. Список моделей поки з документації.</span>`:''}

          </div>
    ${savedDefaults?'':`<button type="button" class="secondary lang-defaults" title="Зберегти цей голос і налаштування для нових випусків каналу"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 3h12l4 4v14H3V3zM7 3v6h10V3M7 21v-8h10v8"/></svg>Зберегти налаштування</button>`}
    <div class="lang-setup-job" role="status" aria-live="polite" hidden></div>`;
  langWirePlayers(id,card,item);
  langWireSample(id,card,item,spec);
  langOwnWire(id,card,item);
  langApplyQuality(card,item);
  return card;
}

function langWirePlayers(id,card,item){
  const voice=item.voice || {};
  for(const box of card.querySelectorAll('.lang-player')){
    const kind=box.dataset.kind;
    const url=kind==='channel'?`/api/channels/${encodeURIComponent(langData.channel_id)}/voices/${item.code}/file?v=${item.channel_voice.stamp}`
      :langUrl(id,item.code,kind,kind==='voice'?voice.made_at:kind==='own'?item.own_voice.stamp:undefined);
    const example=kind==='own'?item.own_voice:kind==='channel'?item.channel_voice:null;
    const player=voicePlayer(id,url,example?{filename:example.filename || 'own-voice.mp3',duration:example.duration}:{});
    if(kind==='voice'&&player){const audio=player.querySelector('audio');if(audio){audio.dataset.alignmentProject=id;audio.dataset.alignmentCode=item.code;}}
    if(player)box.replaceWith(player);
  }
}

function langWireSample(id,card,item,spec){
  const flush=()=>langFlushScript(id,item.code);
  let sampleAudio=card.querySelector('.lang-sample-audio'),samplePlay=card.querySelector('.lang-sample-run');
  const sampleChoose=card.querySelector('.lang-sample-choose');
  let playSample=sampleAudio?langBindSamplePlayback(sampleAudio,samplePlay,card.querySelector('.lang-sample-time'),item.sample?.duration || 0):null;
  const chooseSample=async button=>{
    if(!(await flush()))return;
    langOpenSampleMenu(button,item,spec,async count=>{if(!(await flush()))return;try{localStorage.setItem('langSampleSentences',String(count));}catch{}sampleAudio?.pause();langStart(id,'sample',item.code,{sentences:count});},playSample?async()=>{if(sampleAudio?.paused)await playSample();}:null);
  };
  samplePlay?.addEventListener('click',async()=>{
    langCloseSampleMenu();
    if(sampleAudio&&!sampleAudio.paused){sampleAudio.pause();return;}
    if(!(await flush()))return;
    if(playSample)await playSample();else await chooseSample(samplePlay);
  });
  sampleChoose?.addEventListener('click',()=>chooseSample(sampleChoose));
  card.querySelector('.lang-defaults')?.addEventListener('click',event=>langSaveDefaults(id,item.code,event.currentTarget));
}

const langMagicVoiceIcon='<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="3" width="6" height="11" rx="3"/><path d="M3 11a7 7 0 0 0 14 0M10 18v3M7 21h6M19 2v6m-3-3h6M20 15v4m-2-2h4"/></svg>';
let langResultDialog=null;
const langVoiceScores=new Map();
const langVoiceScoreKey=(id,item)=>`${id}:${item.code}:${item.voice?.made_at||''}:${item.voice_current!==false}`;

async function langLoadVoiceScores(id){
  const snapshot=langData;
  await Promise.allSettled(snapshot.items.filter(item=>item.files?.voice&&item.voice_current!==false).map(async item=>{
    const data=await langAlignmentLoad(id,item,snapshot);
    if(state.project?.id!==id||langData!==snapshot)return;
    langVoiceScores.set(langVoiceScoreKey(id,item),data.status==='ready'?data.synchronization:null);
    langPaintVoiceTiles();
  }));
}

function langVoiceTileState(item){
  const spec=langSpec(item),jobs=langJobs().filter(job=>job.code===item.code&&['voice','refit','save-audio'].includes(job.kind));
  const job=jobs.find(entry=>entry.status==='running')||jobs.sort((a,b)=>(b.started_at||b.finished_at||0)-(a.started_at||a.finished_at||0))[0];
  if(job?.status==='running')return {kind:'working',label:job.kind==='voice'?'Створюємо озвучку':job.kind==='refit'?'Вирівнюємо озвучку':'Зберігаємо озвучку',detail:`${Math.round(job.progress||0)}%`,progress:job.progress||0,job};
  if(!item.text||item.translation_resumable)return {kind:'blocked',blocked:true,label:'Спершу завершіть переклад',detail:''};
  const duration=item.files?.voice&&item.voice_current!==false&&langVoiceDurationIssue(item);
  if(duration)return {kind:'attention',durationIssue:true,label:duration.label,detail:`${Math.abs(duration.difference_seconds).toLocaleString('uk-UA',{maximumFractionDigits:1})} с ${duration.state==='too_long'?'довша':'коротша'} за оригінал`};
  if(job?.status==='failed')return {kind:'attention',label:'Перевірити озвучку',detail:'',job};
  const status=langVoiceStatus(item,spec);
  if(status){
    const review=item.voice?.timing_status==='review'||item.voice?.alignment?.within_limit===false;
    return {kind:'ready',review,label:review?'Перевірити синхронізацію':status.replace(' ✓',''),detail:item.voice?.duration?clock(item.voice.duration):'Переглянути'};
  }
  return {kind:'action',label:langVoiceAction(item,spec),detail:langCost(spec,item.prices?.[spec.id]),blocked:langRunning(item.code,'voice')||!langHasVoice(item)||!item.text||!!(item.language_check&&item.language_check.state!=='ok')};
}

function langVoiceTile(id,item){
  const card=document.createElement('div');card.className='lang-voice-tile';card.dataset.code=item.code;
  card.innerHTML='<button type="button" class="lang-voice-tile-open"></button>';
  card.querySelector('button').onclick=()=>{
    const current=langData?.items.find(entry=>entry.code===item.code);if(!current)return;
    const status=langVoiceTileState(current);
    if(status.blocked)return;
    if(status.kind==='action')langConfirmVoice(id,item.code);else langOpenVoiceResult(id,item.code);
  };
  return card;
}

function langPaintVoiceTiles(){
  document.querySelectorAll('#project-langs .lang-voice-tile').forEach(card=>{
    const item=langData?.items.find(entry=>entry.code===card.dataset.code);if(!item)return;
    const status=langVoiceTileState(item),button=card.querySelector('button');
    card.dataset.status=status.kind;card.classList.toggle('duration-issue',!!status.durationIssue);button.disabled=status.kind==='blocked'||(status.kind==='action'&&status.blocked);
    const icon=status.kind==='working'?exportSpinner:status.kind==='attention'||status.review?'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 10 18H2zM12 8v6m0 3v1"/></svg>':status.kind==='ready'?'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6"/></svg>':langMagicVoiceIcon;
    const score=status.kind==='ready'?langVoiceScores.get(langVoiceScoreKey(state.project?.id,item)):null;
    button.innerHTML=`<span class="lang-voice-tile-heading">${langWaveIcon}<span>Озвучка перекладу</span></span>${status.kind==='ready'||status.durationIssue?'':`<span class="lang-voice-tile-icon">${icon}</span>`}<span class="lang-voice-tile-state">${status.kind==='ready'||status.durationIssue?icon:''}<strong>${esc(status.label)}</strong></span>${score?`<span class="lang-voice-tile-score" title="Оцінка збігу таймінгів фраз із оригіналом">${score.percent.toLocaleString('uk-UA',{maximumFractionDigits:1})}% <small>синхронності</small></span>`:''}${status.detail&&status.kind!=='ready'?`<small>${esc(status.detail)}</small>`:''}${status.kind==='working'?`<progress max="100" value="${status.progress}"></progress>`:''}`;
    const existing=card.querySelector('.lang-summary-player');
    if((status.kind==='ready'||status.durationIssue)&&!existing){
      const box=document.createElement('div');box.className='lang-summary-player lang-own has-voice';
      const player=voicePlayer(state.project.id,langUrl(state.project.id,item.code,'voice',item.voice?.made_at),{filename:`${item.name}.mp3`,duration:item.voice?.duration,playLabel:`Відтворити озвучку: ${item.name}`});
      if(player){const audio=player.querySelector('audio');audio.dataset.alignmentProject=state.project.id;audio.dataset.alignmentCode=item.code;box.append(player);card.append(box);}
    }else if(status.kind!=='ready'&&!status.durationIssue&&existing){existing.querySelectorAll('audio').forEach(audio=>audio.pause());existing.remove();}
    button.setAttribute('aria-label',`${status.label}: ${item.name}`);button.title=status.job?.error||status.job?.stage||status.label;
  });
  document.querySelectorAll('.lang-alignment-generate').forEach(button=>{
    const item=langData?.items.find(entry=>entry.code===button.dataset.code);if(!item)return;
    const status=langVoiceTileState(item);button.disabled=status.kind==='working'||!item.text||!langHasVoice(item)||!!(item.language_check&&item.language_check.state!=='ok');
    button.textContent=status.kind==='working'?`${status.label} · ${status.detail}`:item.text?langVoiceAction(item,langSpec(item)):'Спершу перекладіть текст';
  });
}

function langRefreshVoiceResultDialog(){
  if(!langResultDialog)return;
  const {id,code,dialog}=langResultDialog,item=langData?.items.find(entry=>entry.code===code);
  if(state.project?.id!==id||!item){dialog.close();return;}
  dialog.querySelectorAll('.lang-alignment').forEach(block=>block.dispose?.());
  dialog.querySelectorAll('audio').forEach(audio=>audio.pause());
  dialog.querySelector('.lang-result-dialog-body').replaceChildren(langVoiceResult(id,item),langAlignment(id,item));langPaintBalance();
}

function langOpenVoiceResult(id,code){
  if(state.project?.id!==id)return;
  const item=langData?.items.find(entry=>entry.code===code);if(!item)return;
  langVoiceDialog?.dialog.close();langResultDialog?.dialog.close();
  const dialog=document.createElement('dialog');dialog.className='lang-result-dialog';
  dialog.setAttribute('aria-labelledby','lang-result-title');
  dialog.innerHTML=`<div class="lang-script-dialog-head"><h2 id="lang-result-title">${langFlag(code)} Озвучка · ${esc(item.name)}</h2><button type="button" class="lang-script-close" aria-label="Закрити озвучку">×</button></div><div class="lang-result-dialog-body"></div>`;
  langResultDialog={id,code,dialog};langRefreshVoiceResultDialog();
  dialog.querySelector('.lang-script-close').onclick=()=>dialog.close();
  dialog.addEventListener('click',event=>{if(event.target===dialog)dialog.close();});
  dialog.addEventListener('close',()=>{dialog.querySelectorAll('.lang-alignment').forEach(block=>block.dispose?.());dialog.querySelectorAll('audio').forEach(audio=>audio.pause());if(langResultDialog?.dialog===dialog)langResultDialog=null;dialog.remove();},{once:true});
  document.body.append(dialog);dialog.showModal();langPaintBalance();showLangJob();
}

function langVoiceResult(id,item){
  const spec=langSpec(item),card=document.createElement('article');
  card.className='lang-card lang-voice-result';card.dataset.code=item.code;card.dataset.project=id;
  const price=item.prices[spec.id],voice=item.voice || {};
  // a voicing shows only while what made it still holds: the voice, engine, likeness, example and text
  const readyVoice=item.files.voice&&item.voice_current!==false;
  const unsafeVoice=item.files.voice&&item.voice_matches_text!==false&&item.voice_language_check&&item.voice_language_check.state!=='ok';
  const durationIssue=langVoiceDurationIssue(item);
  const mix=durationIssue?{state:'unavailable',error:durationIssue.label+'. Файл випуску не збережено.'}:item.saved_mix || {state:'missing'};
  const mixText=mix.state==='saved'?'✓ Озвучку з музикою й ефектами збережено в папці випуску':mix.state==='outdated'?'Монтаж або озвучка змінилися. Оновіть збережений файл.':mix.state==='unavailable'?mix.error:'Голос готовий. Залишилося зберегти файл із музикою й ефектами.';
  const alignmentNeeded=!!durationIssue||voice.timing_status==='review'||voice.alignment?.within_limit===false;
  const fit=voice.synced?[voice.centered?`паузи розподілено навколо фраз`:`фрази у свій час, як в оригіналі`,voice.fastest>1.02?`найшвидша прискорена в ${String(voice.fastest).replace('.',',')} раза`:'',voice.latest>0.3?`${voice.centered?'зміщення для підгонки':'найбільше запізнення'} ${String(voice.latest).replace('.',',')} с`:'',voice.slowest<.99?`темп до ${Math.round(voice.slowest*100)}%`:'',voice.long_gaps?.length?`паузи понад 1,5 с: ${voice.long_gaps.length}, потребують перевірки`:'',voice.timing_issues?.length?`перевірте таймінги ${voice.timing_issues.length} фраз`:''].filter(Boolean).join(' · '):voice.speed?`прискорено в ${String(voice.speed).replace('.',',')} раза, щоб влізти в ролик`:voice.padded?`наприкінці ${String(voice.padded).replace('.',',')} с тиші до довжини ролика`:'';
  card.innerHTML=`
    <section class="lang-step" data-lang-step="1">
        ${item.text?`<div class="lang-sample-row">
          ${spec.id==='elevenlabs'?'<div class="lang-balance" role="status" aria-live="polite"></div>':''}
          <div class="lang-voice-actions"><span class="lang-voice-saved" role="status"${langVoiceStatus(item,spec)?'':' hidden'}>${langVoiceStatus(item,spec)}</span><button type="button" class="${readyVoice?'secondary':'primary'} lang-voice-run"${langVoiceStatus(item,spec)?' hidden':''} title="${item.chars.toLocaleString('uk-UA')} літер"${langHasVoice(item)?'':' data-blocked="1" disabled'}>${langVoiceAction(item,spec)} · <b class="lang-voice-cost">${langCost(spec,price)}</b></button><small class="lang-cache-note"${langVoiceStatus(item,spec)?' hidden':''}>${langCacheNote(item,spec)}</small></div></div>
        ${readyVoice?`<div class="lang-voice${durationIssue?' is-duration-mismatch':''}"><div class="lang-voice-head"><b${alignmentNeeded?' class="lang-warn"':''}>${durationIssue?`<svg class="lang-duration-warning" viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 10 18H2zM12 8v6m0 3v1"/></svg>${durationIssue.label}`:alignmentNeeded?'Готова озвучка · перевірте синхронізацію':'Готова озвучка'}</b><small>${voice.made_by?`${esc(voice.made_by)} · `:''}${voice.duration?clock(voice.duration):''}${voice.source_duration?` · ролик ${clock(voice.source_duration)}`:''}${fit?` · ${fit}`:''}${voice.longer?` · довша на ${String(voice.longer).replace('.',',')} с`:''}</small>
          <div class="lang-voice-delivery"><a class="lang-icon lang-download" href="${langUrl(id,item.code,'voice',voice.made_at)}&download=${encodeURIComponent(`Озвучка ${item.name}.mp3`)}" download="Озвучка ${esc(item.name)}.mp3" title="Завантажити лише голос" aria-label="Завантажити MP3">${langDownloadIcon}</a>${mix.state==='saved'||durationIssue?'':`<button type="button" class="secondary lang-save-audio"${mix.state==='unavailable'?' data-blocked="1" disabled':''} title="Зберегти озвучку цією мовою разом із музикою й ефектами монтажу без витрат кредитів">${mix.state==='outdated'?'Оновити файл':'Зберегти файл'}</button>`}</div></div>
          <div class="lang-player" data-kind="voice"></div><p class="lang-mix-status${mix.state==='saved'?' is-saved':''}" role="status">${esc(mixText)}${mix.state==='saved'?`<small>${esc(mix.filename)}</small>`:''}</p></div>`:''}`
      :'<p class="lang-off">Спершу перекладіть текст.</p>'}
    ${unsafeVoice?`<div class="lang-voice is-unsafe">${langQualityNotice(item.voice_language_check,true)}<div class="lang-player" data-kind="voice"></div></div>`:''}
    <div class="lang-job" role="status" aria-live="polite" hidden></div></section>
`;
  langApplyQuality(card,item);langWirePlayers(id,card,item);
  card.querySelector('.lang-save-audio')?.addEventListener('click',async()=>{if(await langFlushScript(id,item.code))langStart(id,'save-audio',item.code);});
  card.querySelector('.lang-voice-run')?.addEventListener('click',()=>langConfirmVoice(id,item.code));
  return card;
}

async function langConfirmVoice(id,code){
    if(state.project?.id!==id||!(await langFlushScript(id,code)))return;
    const fresh=langData.items.find(entry=>entry.code===code);
    if(!fresh||langRunning(code,'voice')||!langHasVoice(fresh))return;
    if(!fresh.text||fresh.translation_resumable||(fresh.language_check&&fresh.language_check.state!=='ok'))return;
    const spec=langSpec(fresh),cost=fresh.prices?.[spec.id],chars=fresh.chars;
    langResultDialog?.dialog.close();
    const estimate=fresh.voice_estimates?.[spec.id],cached=estimate?.reused || 0,generate=estimate?.generate;
    const action=langVoiceAction(fresh,spec);
    modal(`${action} ${fresh.name}?`,`${spec.id==='elevenlabs'?`<div class="lang-balance lang-confirm-balance" role="status" aria-live="polite">${langBalanceMarkup()}</div>`:''}<p>${cached?`${cached} із ${estimate.total} фраз уже є в кеші. `:''}${generate===0?'Усі фрази буде зібрано локально без платних запитів.':`${esc(spec.name)} озвучить ${generate!=null?generate+' нових або змінених фраз':chars.toLocaleString('uk-UA')+' літер'}: <b>${esc(langCost(spec,cost))}</b>. Автоматичних платних повторів немає.`}</p>
      <p>Студія використає збережений текст і вирівняє озвучку паузами та зміною темпу до ${Number(fresh.tempo_percent||langData.tempo_percent||15).toLocaleString('uk-UA')}% в обидва боки. Змінений темп буде позначено для прослуховування.</p><p>Якщо тривалість відповідає ролику, озвучку автоматично зведемо з музикою й ефектами монтажу та збережемо в папці випуску.</p>`,
      [{label:`${action} · ${langCost(spec,cost)}`,primary:true,run:()=>{closeModal();langStart(id,'voice',code);}}]);
    if(spec.id==='elevenlabs')langRefreshBalance(true);
}

function langCard(id,item,spec){
  const card=document.createElement('article');card.className='lang-card lang-workspace';card.dataset.code=item.code;
  card.innerHTML='<section class="lang-step lang-script-step" data-lang-step="0"><div class="lang-script-library"></div></section>';
  langScriptLibrary(id,card.querySelector('.lang-script-library'),langData);
  return card;
}

function langThumbnailResult(id,item){
  const card=document.createElement('article');card.className='lang-card lang-thumbnail-result';card.dataset.code=item.code;
  card.innerHTML=`
    <section class="lang-step" data-lang-step="2">
      ${langData.thumbnail?`<div class="lang-thumbs"><figure class="lang-thumb"><img src="/api/projects/${encodeURIComponent(id)}/cover?v=${Date.now()}" alt="Прев’ю до перекладу" loading="lazy">
          <div class="project-actions lang-thumb-actions"><a class="project-action" href="/api/projects/${encodeURIComponent(id)}/languages/original/thumbnail?download=${encodeURIComponent('Прев’ю оригінал.png')}" download="Прев’ю оригінал.png" title="Завантажити прев’ю" aria-label="Завантажити прев’ю оригіналу">${langDownloadIcon}</a></div><figcaption>${langOriginalName()}</figcaption></figure>
        <figure class="lang-thumb">${item.files.thumbnail?`<div class="lang-thumb-run has-picture" role="button" tabindex="0" aria-label="Згенерувати нове прев’ю"><img src="${langUrl(id,item.code,'thumbnail')}" alt="Прев’ю після перекладу" loading="lazy"><span class="lang-thumb-wand">${typeof thumbnailIcon==='string'?thumbnailIcon:''}<small>Згенерувати ще одне</small></span></div>
          <div class="project-actions lang-thumb-actions"><button type="button" class="project-action thumbnail lang-thumb-redo" title="Згенерувати ще одне" aria-label="Згенерувати прев’ю ще раз">${typeof thumbnailIcon==='string'?thumbnailIcon:''}</button><a class="project-action" href="${langUrl(id,item.code,'thumbnail')}&download=${encodeURIComponent(`Прев’ю ${item.name}.png`)}" download="Прев’ю ${esc(item.name)}.png" title="Завантажити прев’ю" aria-label="Завантажити прев’ю ${esc(item.name)}">${langDownloadIcon}</a></div>`
          :`<button type="button" class="lang-thumb-run" aria-label="Згенерувати прев’ю"><span class="lang-thumb-wand">${typeof thumbnailIcon==='string'?thumbnailIcon:''}<small>Натисніть, щоб згенерувати</small></span></button>`}<figcaption>${langFlag(item.code)} ${esc(item.name)}</figcaption>
          <div class="lang-thumb-ask" hidden><label><span>Побажання <em>необов’язково</em></span><input type="text" maxlength="1500" placeholder="Наприклад: напис коротший і жовтий, слово DAY не перекладати" value="${esc(langDrafts[`${id}:${item.code}:wishes`] || '')}"></label>
            ${langThumbnailFlag(item)}
            ${langData.thumbnail_options?.hero_reference?'<label class="thumb-hero-choice"><input class="lang-thumb-use-hero" type="checkbox" checked>Головний герой</label>':''}
            <div class="lang-thumb-ask-actions"><button type="button" class="secondary lang-thumb-ask-cancel">Скасувати</button><button type="button" class="primary lang-thumb-ask-go">Згенерувати</button></div></div></figure></div>`
      :'<p class="lang-off">У випуску ще немає прев’ю. Створіть його на вкладці «Прев’ю».</p>'}
    <div class="lang-job" role="status" aria-live="polite" hidden></div></section>`;
  // the wand opens the wishes under the translated picture; «Перекласти» there starts Codex (user, 2 November 2026:
  // «побажання мають проявлятися тоді, коли нажимаєте… перекласти»)
  const ask=card.querySelector('.lang-thumb-ask'),wishes=ask?.querySelector('input[type="text"]'),flag=ask?.querySelector('.lang-thumb-add-flag');
  flag?.addEventListener('change',async()=>{
    const previous=langData.thumbnail_options || {add_flag:false},wanted=flag.checked;
    flag.disabled=true;langData.thumbnail_options={add_flag:wanted};
    try{const saved=await api(`/api/projects/${encodeURIComponent(id)}/languages/thumbnail-options`,'POST',{add_flag:wanted});if(state.project?.id===id)langData.thumbnail_options=saved;}
    catch(error){if(state.project?.id===id)langData.thumbnail_options=previous;flag.checked=previous.add_flag===true;langNote(ask,error.message,true);}
    finally{flag.disabled=!item.flag_country;}
  });
  wishes?.addEventListener('input',()=>{langDrafts[`${id}:${item.code}:wishes`]=wishes.value;});
  wishes?.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();ask.querySelector('.lang-thumb-ask-go').click();}});
  card.querySelectorAll('.lang-thumb-run, .lang-thumb-redo').forEach(button=>{
    const open=()=>{if(!ask||langRunning(item.code,'thumbnail'))return;ask.hidden=false;wishes.focus();};
    button.addEventListener('click',open);
    if(button.tagName!=='BUTTON')button.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();open();}});
  });
  ask?.querySelector('.lang-thumb-ask-cancel').addEventListener('click',()=>{ask.hidden=true;});
  ask?.querySelector('.lang-thumb-ask-go').addEventListener('click',()=>{const hero=ask.querySelector('.lang-thumb-use-hero');ask.hidden=true;langStart(id,'thumbnail',item.code,{wishes:wishes.value || '',add_flag:!!item.flag_country&&flag.checked,...(hero?{use_hero:hero.checked}:{})});});
  return card;
}

let langThumbnailDialog=null;
const langThumbnailPending=new Set();
function langThumbnailTile(id,item){
  const tile=document.createElement('div');tile.className='lang-thumbnail-tile';tile.dataset.code=item.code;
  const ready=!!item.files?.thumbnail;
  tile.innerHTML=`<strong>${langFlag(item.code)}Прев’ю</strong><div class="lang-thumbnail-preview"><button type="button" class="lang-thumbnail-image" aria-label="Прев’ю: ${esc(item.name)}">${ready?`<img src="${langUrl(id,item.code,'thumbnail')}" alt="Прев’ю ${esc(item.name)}" loading="lazy">`:''}<span class="lang-thumbnail-status"${ready?' hidden':''}>${typeof thumbnailIcon==='string'?thumbnailIcon:''}<small>Згенерувати</small></span></button>${ready?`<div class="lang-thumbnail-actions"><a class="project-action" href="${langUrl(id,item.code,'thumbnail')}&download=${encodeURIComponent(`Прев’ю ${item.name}.png`)}" download="Прев’ю ${esc(item.name)}.png" aria-label="Завантажити прев’ю: ${esc(item.name)}" title="Завантажити">${langDownloadIcon}</a><button type="button" class="project-action lang-thumbnail-redo" aria-label="Згенерувати прев’ю ще раз: ${esc(item.name)}" title="Згенерувати ще раз">${typeof thumbnailIcon==='string'?thumbnailIcon:''}</button></div>`:''}</div>`;
  tile.classList.toggle('has-picture',!!item.files?.thumbnail);
  tile.querySelector('.lang-thumbnail-image').onclick=()=>langOpenThumbnail(id,item.code);
  tile.querySelector('.lang-thumbnail-redo')?.addEventListener('click',()=>langOpenThumbnail(id,item.code,true));return tile;
}
function langRefreshThumbnailDialog(){
  if(!langThumbnailDialog)return;
  const {id,code,dialog}=langThumbnailDialog,item=langData?.items.find(entry=>entry.code===code);
  if(state.project?.id!==id||!item){dialog.close();return;}
  dialog.querySelector('.lang-thumbnail-dialog-body').replaceChildren(langThumbnailResult(id,item));
}
function langOpenThumbnail(id,code,showWishes=false){
  if(state.project?.id!==id)return;
  const item=langData?.items.find(entry=>entry.code===code);if(!item)return;
  langThumbnailDialog?.dialog.close();
  const dialog=document.createElement('dialog');dialog.className='lang-thumbnail-dialog';dialog.setAttribute('aria-labelledby','lang-thumbnail-title');
  dialog.innerHTML=`<div class="lang-script-dialog-head"><h2 id="lang-thumbnail-title">${langFlag(code)} Прев’ю · ${esc(item.name)}</h2><button type="button" class="lang-script-close" aria-label="Закрити прев’ю">×</button></div><div class="lang-thumbnail-dialog-body"></div>`;
  langThumbnailDialog={id,code,dialog};langRefreshThumbnailDialog();
  const ask=dialog.querySelector('.lang-thumb-ask');if(ask&&(!item.files?.thumbnail||showWishes))ask.hidden=false;
  dialog.querySelector('.lang-script-close').onclick=()=>dialog.close();
  dialog.addEventListener('click',event=>{if(event.target===dialog)dialog.close();});
  dialog.addEventListener('close',()=>{if(langThumbnailDialog?.dialog===dialog)langThumbnailDialog=null;dialog.remove();},{once:true});
  document.body.append(dialog);dialog.showModal();showLangJob();
}

function langRemoveLanguage(id,code){
  const item=langData?.items.find(entry=>entry.code===code);if(!item||langRunning(code))return;
  modal(`Прибрати ${item.name}?`,`<p>Переклад і озвучка цієї мови зникнуть зі студії.${item.folder?' Файли в папці випуску залишаться.':''}</p>`,
    [{label:'Прибрати мову',danger:true,run:async()=>{closeModal();
      try{const data=await api(`/api/projects/${encodeURIComponent(id)}/languages/${code}/remove`,'POST',{});if(state.project?.id!==id)return;langData=data;delete langDrafts[`${id}:${code}`];drawLangs(id);}
      catch(error){langNote(document.querySelector('.lang-script-library'),error.message,true);}}}]);
}

// Messages of this tab stand where the author pressed, not in the studio's banner at the top (user, 2 November 2026:
// «сповіщення… мають бути там, де я нажимаю кнопку»): a short line at the end of that step, or under «Нова мова».
const langStepOf={translate:0,sample:1,voice:1,'save-audio':1,refit:1,thumbnail:2};
function langPlace(code,kind){
  if(kind==='sample')return document.querySelector(`.lang-voice-setup[data-code="${code}"]`) || document.querySelector(`#project-langs .lang-voice-summary[data-code="${code}"]`);
  if(['voice','refit','save-audio'].includes(kind))return document.querySelector(`.lang-result-dialog .lang-card[data-code="${code}"] .lang-step`)||document.querySelector(`#project-langs .lang-voice-tile[data-code="${code}"]`);
  if(kind==='thumbnail')return document.querySelector(`.lang-thumbnail-dialog .lang-card[data-code="${code}"] .lang-step`)||document.querySelector(`#project-langs .lang-thumbnail-tile[data-code="${code}"]`);
  const card=document.querySelector(`#project-langs .lang-card[data-code="${code}"]`);
  return card?.querySelector(`[data-lang-step="${langStepOf[kind] ?? 0}"]`) || document.querySelector('#project-langs .lang-script-library');
}
function langNote(where,message,error=false){
  const holder=where?.closest?.('.lang-voice-setup, .lang-voice-summary, .lang-voice-tile, .lang-thumbnail-tile, .lang-step, .lang-card') || where;
  if(!holder){status(message,error);return;}
  holder.querySelector(':scope > .lang-note')?.remove();
  const note=document.createElement('p');note.className='lang-note'+(error?' is-error':'');note.setAttribute('role',error?'alert':'status');note.textContent=message;
  const job=holder.querySelector(':scope > .lang-job');if(job)job.before(note);else holder.append(note);
  if(!error)setTimeout(()=>note.remove(),8000);
}

// the slots whose cancel the author pressed: only they read «Скасовуємо…» (the button used to be disabled with every other
// button of the card while a job ran, and the next poll took that for a cancel asked; user, 2 November 2026)
const langAsked=new Set();
function langCancelKey(id,job){return `${id}:${job.slot}:${job.started_at||0}`;}
function langStopping(job,id=state.project?.id){return !!job&&(job.cancel_requested||langAsked.has(langCancelKey(id,job)));}
function langCancelButton(job){const stopping=langStopping(job);return `<button type="button" class="secondary lang-cancel" data-slot="${esc(job.slot)}"${stopping?' disabled':''}>${stopping?'Скасовуємо…':'Скасувати'}</button>`;}
async function langCancel(id,slot,button){
  const job=langJobs().find(entry=>entry.slot===slot),key=langCancelKey(id,job||{slot});
  if(langAsked.has(key))return;
  langAsked.add(key);
  if(button){button.disabled=true;button.textContent='Скасовуємо…';}
  try{
    const data=await api(`/api/projects/${encodeURIComponent(id)}/languages/cancel`,'POST',{slot});
    if(state.project?.id!==id)return;
    if(data.jobs){langData.jobs=data.jobs;langData.job=data.job;}
    showLangJob();
  }catch(error){langAsked.delete(key);if(button){button.disabled=false;button.textContent='Скасувати';}if(state.project?.id===id)langNote(button,error.message,true);}
}

async function langStart(id,kind,code,extra={}){
  if(state.project?.id!==id)return;
  const thumbnailKey=`${id}:${code}`;
  if(kind==='thumbnail'){langThumbnailPending.add(thumbnailKey);langThumbnailDialog?.dialog.close();showLangJob();}
  try{
    const payload=(kind==='sample'||kind==='voice')?{...extra,expected_provider:langSpec(langData.items.find(item=>item.code===code)).id}:extra;
    const {job}=await api(`/api/projects/${encodeURIComponent(id)}/languages/${code}/${kind}`,'POST',payload);
    if(state.project?.id!==id)return;
    if(kind==='voice'){langSamplePreview.delete(`${id}:${code}`);const sample=document.querySelector(`#project-langs .lang-voice-setup[data-code="${code}"] .lang-inline-sample`);sample?.querySelectorAll('audio').forEach(audio=>audio.pause());}
    if(kind==='sample')langSamplePreview.add(`${id}:${code}`);
    langPlace(code,kind)?.querySelector(':scope > .lang-note')?.remove();
    langData.jobs=[...langJobs().filter(other=>other.slot!==job.slot),job];langData.job=job;
    showLangJob();pollLangs(id);return true;
  }catch(error){if(state.project?.id===id){if(kind==='translate'&&langScriptDialog?.project===id&&langScriptDialog.code===code)langScriptDialog.error(error.message);else langNote(langPlace(code,kind),error.message,true);}return false;}
  finally{if(kind==='thumbnail'){langThumbnailPending.delete(thumbnailKey);if(state.project?.id===id)showLangJob();}}
}

// Jobs run side by side (user, 2 November 2026: «перекладалось текст, я нажав перекласти прев'ю, і воно зупиняє
// переклад?»): each language has two lanes, its text and voice, and its thumbnail; other languages run at once too.
const langGroupOf=kind=>kind==='thumbnail'?'thumbnail':'voice';
function langJobs(){return langData?.jobs || (langData?.job?[langData.job]:[]);}
function langRunning(code,group){return langJobs().some(job=>job.status==='running'&&(!code||job.code===code)&&(!group||langGroupOf(job.kind)===group));}

function langPaintVoiceSetups(){
  document.querySelectorAll('#project-langs .lang-voice-setup,.lang-voice-dialog .lang-voice-setup').forEach(box=>{
    const code=box.dataset.code,id=state.project?.id;
    const uploading=langUploads.has(`/api/projects/${encodeURIComponent(id)}/languages/${code}/own-voice`);
    const locked=langRunning(code,'voice')||uploading||box.dataset.saving==='1';
    box.querySelectorAll('button,select,input').forEach(control=>{
      if(control.matches('.voice-player-play,.voice-player-mute,.lang-cancel,.lang-setup-review'))return;
      control.disabled=control.matches('.lang-defaults')?uploading||box.dataset.saving==='1'||control.dataset.saving==='1':locked||control.dataset.blocked==='1';
    });
    box.querySelector('.lang-own-file')?.classList.toggle('is-off',locked);
    const jobs=langJobs().filter(job=>job.code===code&&['voice','sample','refit'].includes(job.kind));
    const job=jobs.find(entry=>entry.status==='running')||jobs.sort((a,b)=>(b.started_at||0)-(a.started_at||0))[0];
    const full=job?.status==='running'&&job.kind!=='sample';
    const sample=box.querySelector('.lang-inline-sample');if(sample){sample.hidden=full;if(full)sample.querySelector('audio')?.pause();}
    const progress=box.querySelector('.lang-setup-job');
    progress.hidden=!job||!['running','failed'].includes(job.status);
    if(progress.hidden){progress.replaceChildren();return;}
    if(job.status==='running'){
      const stopping=langStopping(job);
      progress.innerHTML=`<span>${esc(job.stage||'Починаємо…')}</span><progress max="100" value="${job.progress||0}"></progress><button type="button" class="lang-icon lang-cancel" title="Скасувати" aria-label="Скасувати"${stopping?' disabled':''}>×</button>`;
      progress.querySelector('button').onclick=event=>langCancel(id,job.slot,event.currentTarget);
    }else{
      progress.innerHTML='<button type="button" class="lang-setup-review">Перевірити озвучку</button>';
      const review=progress.querySelector('button');review.title=job.error||'';
      review.onclick=()=>langOpenVoiceResult(id,code);
    }
  });
}

function showLangJob(){
  langPaintScriptJobs();
  langPaintVoiceSetups();
  langPaintVoiceTiles();
  // a job's line sits in the step it works on, inside the language's own card (user, 2 November 2026: «не треба
  // розкидати блоки… все в один блок»): the text for a translation, the voice for a sample or the whole, the thumbnail
  const jobs=langJobs();
  // the capsule of a language at work shows it, whichever card is open
  for(const card of document.querySelectorAll('#project-langs .lang-card[data-code],.lang-result-dialog .lang-card[data-code],.lang-thumbnail-dialog .lang-card[data-code]')){
    const code=card.dataset.code,steps=[...card.querySelectorAll('.lang-step')];
    const uploading=langUploads.has(`/api/projects/${encodeURIComponent(state.project?.id)}/languages/${code}/own-voice`);
    const fullVoiceRunning=jobs.some(job=>job.code===code&&['voice','refit'].includes(job.kind)&&job.status==='running');
    const savingAudio=fullVoiceRunning||jobs.some(job=>job.code===code&&job.kind==='save-audio'&&job.status==='running');
    card.querySelectorAll('.lang-voice-delivery,.lang-mix-status').forEach(element=>element.hidden=savingAudio);
    const synthesis=card.querySelector('.lang-voice-actions');if(synthesis)synthesis.hidden=fullVoiceRunning;
    // a running lane locks only its own steps: the text and voice, or the thumbnail
    card.querySelectorAll('button:not(.voice-player-play):not(.voice-player-mute)').forEach(button=>{
      if(button.classList.contains('lang-cancel')||button.closest('.lang-script-library'))return;
      if(button.classList.contains('lang-defaults')){button.disabled=button.dataset.saving==='1'||uploading;return;}
      const index=Number(button.closest('[data-lang-step]')?.dataset.langStep ?? -1);
      const locked=index<0?langRunning(code):langRunning(code,index===2?'thumbnail':'voice');
      button.disabled=locked || (uploading&&index===1) || button.dataset.blocked==='1';});
    steps.forEach(step=>{
      const index=Number(step.dataset.langStep);
      const box=step.querySelector(':scope > .lang-job');if(!box)return;
      const own=jobs.filter(job=>job.code===code&&langStepOf[job.kind]===index);
      const job=own.find(item=>item.status==='running') || own.sort((a,b)=>(b.finished_at||0)-(a.finished_at||0))[0];
      const busy=job?.status==='running';
      // a finished job shows itself in the card (the text, the player, the picture): only a failure or a cancel says so
      const recent=job&&(job.status==='failed'||job.status==='cancelled'&&job.finished_at&&Date.now()/1000-job.finished_at<120);
      box.hidden=!job || (!busy && !recent);
      box.dataset.status=job?.status || '';
      step.classList.toggle('is-working',busy);
      const slot=job?.slot || (job?`${job.code}|${langGroupOf(job.kind)}`:'');
      if(!busy&&job)langAsked.delete(langCancelKey(state.project?.id,job));
      if(box.hidden){box.innerHTML='';return;}
      // the poll redraws this line every 2 s: a cancel already asked for stays shown
      const stopping=langStopping(job);
      box.innerHTML=busy?`${typeof exportSpinner==='string'?exportSpinner:''}<span>${esc(job.stage || '')}</span><progress max="100" value="${job.progress || 0}"></progress><button type="button" class="secondary lang-cancel"${stopping?' disabled':''}>${stopping?'Скасовуємо…':'Скасувати'}</button>`
        :job.status==='cancelled'?`<span>${job.voice_ready?'Озвучка готова. Збереження файлу з музикою й ефектами скасовано.':job.kind==='translate'?'Переклад призупинено. Готові частини збережено для продовження.':'Скасовано. Готові записи фраз збережено.'}</span>`
        :`<span>Не вдалося: ${esc(job.error || '')}</span>`;
      const cancel=box.querySelector('.lang-cancel');
      cancel?.addEventListener('click',()=>langCancel(state.project.id,slot,cancel));
    });
  }
  // the «after» window of the language being redrawn says so in place of its wand
  for(const tile of document.querySelectorAll('.lang-thumbnail-dialog .lang-thumb-run')){
    const drawing=langRunning(tile.closest('.lang-card')?.dataset.code,'thumbnail');
    tile.classList.toggle('is-drawing',drawing);
    tile.setAttribute('aria-disabled',String(drawing));
    const label=tile.querySelector('.lang-thumb-wand small');
    if(label){label.dataset.idle??=label.textContent;label.textContent=drawing?'Codex генерує, 1-3 хвилини…':label.dataset.idle;}
  }
  document.querySelectorAll('#project-langs .lang-thumbnail-tile[data-code]').forEach(tile=>{
    const busy=langThumbnailPending.has(`${state.project?.id}:${tile.dataset.code}`)||langRunning(tile.dataset.code,'thumbnail');tile.classList.toggle('is-working',busy);tile.setAttribute('aria-busy',String(busy));tile.querySelector('.lang-thumbnail-image').disabled=busy;
    const status=tile.querySelector('.lang-thumbnail-status');status.hidden=tile.classList.contains('has-picture')&&!busy;
    status.innerHTML=busy?'<i class="export-spinner" aria-hidden="true"></i><small>Створюємо прев’ю…</small>':`${typeof thumbnailIcon==='string'?thumbnailIcon:''}<small>Згенерувати</small>`;
    const redo=tile.querySelector('.lang-thumbnail-redo');if(redo)redo.disabled=busy;
  });
  document.querySelectorAll('.lang-language-remove').forEach(button=>button.disabled=langRunning(button.dataset.code));
}

async function pollLangs(id){
  if(langPolling===id)return;langPolling=id;
  try{
    while(langBusy() && state.project?.id===id && langPolling===id){
      await new Promise(resolve=>setTimeout(resolve,2000));
      if(state.project?.id!==id || langPolling!==id)break;
      try{const before=langJobs().filter(job=>job.status==='running').map(job=>job.slot);
        const data=await api(`/api/projects/${encodeURIComponent(id)}/languages`);
        if(state.project?.id!==id || langPolling!==id)break;
        langData=data;
        // a lane that has just finished brings its result into the card
        const finished=before.some(slot=>!langJobs().some(job=>job.slot===slot&&job.status==='running'));
        if(finished&&state.view==='thumb'&&typeof renderThumbView==='function'){
          const view=document.getElementById('project-thumb');if(view)delete view.dataset.project;renderThumbView();
        }
        if(finished && state.view==='langs' && state.project?.id===id){drawLangs(id);langRefreshBalance(true);}else showLangJob();
      }catch{}
    }
  }finally{if(langPolling===id)langPolling=null;}
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
const dubOptionsCache=new Map(),dubOptionsPending=new Map();
async function loadDubOptions(id){
  const cached=dubOptionsCache.get(id);
  if(cached&&Date.now()-cached.at<15000)return cached.data;
  if(dubOptionsPending.has(id))return dubOptionsPending.get(id);
  const request=api(`/api/projects/${encodeURIComponent(id)}/languages/voices`).then(data=>{
    dubOptionsCache.set(id,{at:Date.now(),data});return data;
  }).finally(()=>dubOptionsPending.delete(id));
  dubOptionsPending.set(id,request);return request;
}
function isVoiceClip(clip){
  if(clip?.kind!=='audio')return false;
  const asset=(state.project?.assets || []).find(item=>item.id===clip.asset_id);
  if(/music_sfx|музика|музыка|\bmusic\b|\bsfx\b/i.test(`${clip.title || ''} ${asset?.name || ''}`))return false;
  const voice=typeof voiceAssetId==='function'?voiceAssetId(state.plan,state.project):null;
  if(clip.asset_id===voice || Object.keys(state.project?.audio_gain || {}).includes(clip.asset_id))return true;
  // Restored episodes can retain the full narration under a different imported asset id.
  const duration=Number(state.project?.duration || 0);
  return /^(Озвучка|Voiceover|Narration)$/i.test((clip.title || '').trim()) && duration>0 && Number(clip.start || 0)<0.5 && Number(clip.duration || 0)>=duration*.9;
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
    const projectId=state.project.id;
    const menu=document.createElement('div');menu.className='layer-dub-menu lang-menu';menu.setAttribute('role','menu');
    const original=`<button type="button" data-code=""${!code?' class="active"':''}>🎙<span>Оригінал</span></button>`;
    menu.innerHTML=original+'<p class="layer-dub-empty" role="status">Завантаження озвучок…</p>';
    const rect=button.getBoundingClientRect();Object.assign(menu.style,{position:'fixed',left:`${rect.left}px`,top:`${rect.bottom+6}px`,zIndex:60});
    document.body.append(menu);
    const placeMenu=()=>{const height=menu.getBoundingClientRect().height,width=menu.getBoundingClientRect().width;
      menu.style.left=`${Math.max(8,Math.min(rect.left,window.innerWidth-width-8))}px`;
      menu.style.top=`${rect.bottom+6+height<=window.innerHeight-8?rect.bottom+6:Math.max(8,rect.top-height-6)}px`;};
    placeMenu();
    const close=()=>{menu.remove();document.removeEventListener('pointerdown',outside,true);};
    const outside=e=>{if(!menu.contains(e.target)&&e.target!==button)close();};
    document.addEventListener('pointerdown',outside,true);
    menu.addEventListener('click',e=>{
      const choice=e.target.closest('button[data-code]');if(!choice)return;close();
      if(state.project?.id!==projectId)return;
      try{if(choice.dataset.code)localStorage.setItem(`dub:${state.project.id}`,choice.dataset.code);else localStorage.removeItem(`dub:${state.project.id}`);}catch{}
      const playing=state.playing;if(typeof stopPlayback==='function'&&playing)stopPlayback();
      buildAudioNodes();renderProject();
      status(choice.dataset.code?'Перегляд з перекладеною озвучкою. Експорт лишається з оригіналом.':'Перегляд з оригінальною озвучкою.');
    });
    try{
      const data=await loadDubOptions(projectId);
      if(!menu.isConnected||state.project?.id!==projectId)return;
      for(const item of data.items)dubStamps[item.code]=Math.round(item.made_at || 0);
      menu.innerHTML=original+(data.items.map(item=>`<button type="button" data-code="${item.code}"${item.code===code?' class="active"':''}>${langFlag(item.code)}<span>${esc(item.name)}</span><small>${esc(item.label)}</small></button>`).join('') || '<p class="layer-dub-empty">Готової озвучки іншими мовами ще немає. Її робить вкладка «Мови».</p>');
      placeMenu();
    }catch(error){if(menu.isConnected){menu.innerHTML=original+`<p class="layer-dub-empty">${esc(error.message)}</p>`;placeMenu();}}
  });
  heading.append(button);
}


async function langSaveDefaults(id,code,button){
  button.dataset.saving='1';button.disabled=true;button.setAttribute('aria-busy','true');
  try{
    const defaults=await api(`/api/projects/${encodeURIComponent(id)}/languages/defaults`,'POST',{code});
    if(state.project?.id===id&&state.view==='langs'){langData.defaults=defaults;drawLangs(id);}
  }catch(error){langNote(button,error.message,true);}
  finally{delete button.dataset.saving;button.removeAttribute('aria-busy');showLangJob();}
}

function langBindSamplePlayback(audio,button,label,duration=0){
  let waiting=false;
  const paint=()=>{
    if(audio.dataset?.stale==='1')return;
    const playing=!audio.paused&&!audio.ended;
    button.innerHTML=playing?pauseIcon:playIcon;
    button.setAttribute('aria-label',playing?'Призупинити зразок':'Послухати зразок');
    button.setAttribute('aria-pressed',String(playing));
    button.setAttribute('aria-busy',String(waiting));
    button.title=playing?'Призупинити зразок':'Відтворити готовий зразок безкоштовно';
    label.hidden=false;
    label.textContent=audio.error?'Помилка відтворення':waiting?'Завантажуємо…':`${clock(audio.currentTime)} / ${clock(Number.isFinite(audio.duration)?audio.duration:duration)}`;
  };
  for(const name of ['loadedmetadata','timeupdate','play'])audio.addEventListener(name,paint);
  for(const name of ['playing','pause','ended','error'])audio.addEventListener(name,()=>{waiting=false;paint();});
  audio.addEventListener('waiting',()=>{waiting=true;paint();});
  paint();
  return async()=>{
    if(!audio.paused){audio.pause();return;}
    if(audio.ended)audio.currentTime=0;
    document.querySelectorAll('.voice-player audio,.lang-sample-audio').forEach(other=>{if(other!==audio)other.pause();});
    if(typeof stopPlayback==='function')stopPlayback();
    waiting=true;paint();
    try{await audio.play();}
    catch(error){if(error.name!=='AbortError')langNote(button,'Не вдалося відтворити зразок: '+error.message,true);}
    finally{waiting=false;paint();}
  };
}

function langCloseSampleMenu(){document.querySelector('.lang-sample-menu')?.remove();document.querySelectorAll('.lang-inline-sample [aria-expanded="true"]').forEach(button=>button.setAttribute('aria-expanded','false'));}
function langOpenSampleMenu(button,item,spec,choose,playExisting=null){
  const opened=button.getAttribute('aria-expanded')==='true';langCloseSampleMenu();if(opened)return;
  const menu=document.createElement('div');menu.className='lang-sample-menu';menu.setAttribute('role','menu');menu.setAttribute('aria-label','Кількість речень для зразка');
  button.setAttribute('aria-haspopup','menu');button.setAttribute('aria-expanded','true');
  if(playExisting){
    const ready=document.createElement('button');ready.type='button';ready.setAttribute('role','menuitem');
    ready.innerHTML=`<span class="lang-sample-choice">${langIcons.play}<span>Відтворити готовий зразок</span></span><small>безкоштовно</small>`;
    ready.addEventListener('click',()=>{langCloseSampleMenu();button.focus();playExisting();});menu.append(ready);
  }
  for(const count of [3,5,10,20]){
    const option=document.createElement('button');option.type='button';option.setAttribute('role','menuitem');
    const price=langCost(spec,item.sample_prices?.[spec.id]?.[String(count)]);
    const actual=item.sample_options?.[spec.id]?.[String(count)]?.sentences || count;
    option.innerHTML=`<span class="lang-sample-choice">${langIcons.play}<span>${count}${actual>count?'+':''} ${count===3?'речення':'речень'}</span></span><small>${esc(price)}</small>`;
    if(actual>count)option.title=`Збережена фраза прозвучить повністю: у зразку ${actual} речень.`;
    option.addEventListener('click',()=>{langCloseSampleMenu();button.focus();choose(count);});menu.append(option);
  }
  menu.addEventListener('keydown',event=>{if(!['ArrowDown','ArrowUp'].includes(event.key))return;event.preventDefault();const options=[...menu.querySelectorAll('button')],index=options.indexOf(document.activeElement);options[(index+(event.key==='ArrowDown'?1:options.length-1))%options.length].focus();});
  (button.closest('dialog') || document.body).append(menu);const rect=button.getBoundingClientRect();
  menu.style.left=Math.max(8,Math.min(rect.left,window.innerWidth-menu.offsetWidth-8))+'px';
  menu.style.top=(rect.bottom+menu.offsetHeight+6<window.innerHeight?rect.bottom+6:Math.max(8,rect.top-menu.offsetHeight-6))+'px';
  menu.querySelector('button').focus();
}
document.addEventListener('pointerdown',event=>{if(!event.target.closest('.lang-sample-menu,.lang-inline-sample'))langCloseSampleMenu();},true);
document.addEventListener('keydown',event=>{if(event.key==='Escape'){const button=document.querySelector('.lang-inline-sample [aria-expanded="true"]');langCloseSampleMenu();button?.focus();}});
