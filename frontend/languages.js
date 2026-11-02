// languages.js — the «Мови» tab after «Прев’ю» (backend/languages.py): the episode's voice in other languages with the
// author's own cloned voice, and the thumbnail with its words translated. The video itself is not changed (user,
// 2 November 2026: «відео ролик перекладати я поки не хочу, лише аудіо і превью»). Each language goes in three steps:
// the text (translated by DeepSeek, editable), the voice (a cheap sample first, then the whole with its price shown
// before) and the thumbnail (before and after).
const langDrafts={};
let langData=null,langPolling=false;

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
  const data=langData,src=data.source,provider=data.provider,spec=data.providers.find(item=>item.id===provider) || data.providers[0];
  const used=new Set(data.items.map(item=>item.code));
  const missingKey=spec.configured!==true;
  section.innerHTML=`<div class="lang-view">
    <div class="lang-head"><h1>Мови</h1>
      <p class="lang-lead">Озвучка ролика іншими мовами вашим голосом і прев’ю з перекладеним текстом. Відео не змінюється: готову озвучку завантажте на YouTube як додаткову аудіодоріжку.</p></div>
    <div class="lang-settings">
      <div class="lang-source"><b>Оригінал</b><span>${src.chars?`${src.chars.toLocaleString('uk-UA')} символів${src.duration?` · ${clock(src.duration)} озвучки`:''}`:'Тексту озвучки ще немає: спершу додайте й розпізнайте озвучку на вкладці «План ролика»'}</span>
        <small>Орієнтовна ціна озвучки однієї мови: ${data.providers.map(item=>`${esc(item.name)} ${langMoney(src.estimate[item.id] || 0)}`).join(' · ')}. Переклад тексту: кілька центів.</small></div>
      <div class="lang-provider"><b>Голос</b><div class="lang-segment" role="radiogroup" aria-label="Сервіс озвучки">${data.providers.map(item=>`<button type="button" role="radio" data-provider="${item.id}" aria-checked="${item.id===provider}" class="${item.id===provider?'active':''}">${esc(item.name)}${item.configured===true?'':'<i title="Ключ не додано">!</i>'}</button>`).join('')}</div>
        <small>${esc(spec.note)}${missingKey?` <span class="lang-warn">Додайте ключ ${esc(spec.name)}: налаштування студії → «Ключі сервісів».</span>`:''}${data.openrouter===true?'':' <span class="lang-warn">Для перекладу потрібен ключ OpenRouter.</span>'}</small></div>
    </div>
    <div class="lang-job" role="status" aria-live="polite" hidden></div>
    <div class="lang-cards"></div>
    <label class="lang-add"><span>Додати мову</span><select><option value="">Оберіть мову…</option>${data.languages.filter(item=>!used.has(item.code)).map(item=>`<option value="${item.code}">${esc(item.name)} · ${esc(item.label)}</option>`).join('')}</select></label>
  </div>`;
  const cards=section.querySelector('.lang-cards');
  if(!data.items.length)cards.innerHTML='<p class="lang-empty">Ще немає жодної мови. Оберіть мову нижче, і студія перекладе текст ролика.</p>';
  for(const item of data.items)cards.append(langCard(id,item,spec));
  section.querySelector('.lang-add select').addEventListener('change',async event=>{
    const code=event.target.value;if(!code)return;
    try{langData=await api(`/api/projects/${encodeURIComponent(id)}/languages/${code}`,'POST',{});drawLangs(id);
      if(data.openrouter===true)langStart(id,'translate',code);}catch(error){status(error.message,true);}
  });
  section.querySelectorAll('.lang-segment button').forEach(button=>button.addEventListener('click',async()=>{
    if(button.dataset.provider===langData.provider)return;
    try{langData=await api(`/api/projects/${encodeURIComponent(id)}/languages/provider`,'POST',{provider:button.dataset.provider});drawLangs(id);}catch(error){status(error.message,true);}
  }));
  showLangJob();
}

function langCard(id,item,spec){
  const card=document.createElement('article');card.className='lang-card';card.dataset.code=item.code;
  const text=langDrafts[`${id}:${item.code}`] ?? item.text,price=item.prices[spec.id],voice=item.voice || {};
  const sampleBy=item.sample_provider&&item.sample_provider!==spec.id?(langData.providers.find(p=>p.id===item.sample_provider)?.name || ''):'';
  const fit=voice.speed?`прискорено в ${String(voice.speed).replace('.',',')} раза, щоб влізти в ролик`:voice.padded?`наприкінці ${String(voice.padded).replace('.',',')} с тиші до довжини ролика`:'';
  card.innerHTML=`<header><h2>${esc(item.name)}</h2><span>${esc(item.label)}</span><button type="button" class="lang-remove" title="Прибрати мову" aria-label="Прибрати мову ${esc(item.name)}">${typeof trashIcon==='string'?trashIcon:'×'}</button></header>
    <section class="lang-step"><h3><em>1</em>Текст</h3>
      ${item.text?`<label class="lang-title"><span>Заголовок</span><input type="text" maxlength="200" value="${esc(item.title)}"></label>
        <label class="lang-text"><span>Текст озвучки <small>${item.chars.toLocaleString('uk-UA')} символів · можна виправити перед озвучкою</small></span><textarea rows="9" spellcheck="false">${esc(text)}</textarea></label>
        <div class="lang-actions"><button type="button" class="secondary lang-retranslate">Перекласти заново</button><button type="button" class="primary lang-save" disabled>Зберегти правки</button></div>`
      :`<div class="lang-actions"><p>Студія перекладе текст і заголовок ролика: кілька центів, зазвичай до хвилини.</p><button type="button" class="primary lang-translate">Перекласти</button></div>`}
    </section>
    <section class="lang-step${item.text?'':' is-off'}"><h3><em>2</em>Озвучка вашим голосом</h3>
      ${item.text?`<p class="lang-price">Весь текст через ${esc(spec.name)}: <b>${langMoney(price || 0)}</b> <small>(${item.chars.toLocaleString('uk-UA')} символів)</small>. Спершу послухайте зразок, він коштує майже нічого.</p>
        <div class="lang-sample">${item.files.sample?'<div class="lang-player" data-kind="sample"></div>':''}<button type="button" class="secondary lang-sample-run">${item.files.sample?'Інший зразок':'Послухати зразок'}</button>${sampleBy?`<small>зразок озвучено через ${esc(sampleBy)}</small>`:''}</div>
        ${item.files.voice?`<div class="lang-voice"><b>Готова озвучка</b><div class="lang-player" data-kind="voice"></div>
          <small>${voice.duration?clock(voice.duration):''}${voice.source_duration?` · ролик ${clock(voice.source_duration)}`:''}${fit?` · ${fit}`:''}${voice.longer?` · довша за ролик на ${String(voice.longer).replace('.',',')} с`:''}</small>
          ${item.folder?`<small class="lang-folder">Файл у папці випуску: ${esc(item.folder)}</small>`:''}
          <a class="lang-download" href="${langUrl(id,item.code,'voice',voice.made_at)}" download="Озвучка ${esc(item.name)}.mp3">Завантажити MP3</a></div>`:''}
        <div class="lang-actions"><button type="button" class="primary lang-voice-run">${item.files.voice?'Озвучити заново':'Озвучити весь ролик'} · ${langMoney(price || 0)}</button></div>`
      :'<p class="lang-off">Спершу перекладіть текст.</p>'}
    </section>
    <section class="lang-step"><h3><em>3</em>Прев’ю</h3>
      ${langData.thumbnail?`<div class="lang-thumbs"><figure><img src="/api/projects/${encodeURIComponent(id)}/cover?v=${Date.now()}" alt="Прев’ю до перекладу" loading="lazy"><figcaption>До</figcaption></figure>
        <figure>${item.files.thumbnail?`<img src="${langUrl(id,item.code,'thumbnail')}" alt="Прев’ю після перекладу" loading="lazy">`:'<div class="lang-thumb-empty">Ще не перекладено</div>'}<figcaption>Після · ${esc(item.name)}</figcaption></figure></div>
        <div class="lang-actions"><p>Codex перемалює обкладинку, змінивши тільки слова на ній.</p><button type="button" class="secondary lang-thumb-run">${item.files.thumbnail?'Перекласти ще раз':'Перекласти прев’ю'}</button></div>`
      :'<p class="lang-off">У випуску ще немає прев’ю. Створіть його на вкладці «Прев’ю».</p>'}
    </section>`;
  for(const box of card.querySelectorAll('.lang-player')){
    const player=voicePlayer(id,langUrl(id,item.code,box.dataset.kind,box.dataset.kind==='voice'?voice.made_at:undefined));
    if(player)box.replaceWith(player);
  }
  const area=card.querySelector('textarea'),title=card.querySelector('.lang-title input'),save=card.querySelector('.lang-save');
  const dirty=()=>{const changed=area.value!==item.text || title.value!==item.title;save.disabled=!changed;if(area.value!==item.text)langDrafts[`${id}:${item.code}`]=area.value;else delete langDrafts[`${id}:${item.code}`];};
  if(area){area.addEventListener('input',dirty);title.addEventListener('input',dirty);dirty();
    save.addEventListener('click',async()=>{
      try{langData=await api(`/api/projects/${encodeURIComponent(id)}/languages/${item.code}/text`,'POST',{text:area.value,title:title.value});
        delete langDrafts[`${id}:${item.code}`];drawLangs(id);status('Правки збережено. Зразок озвучки треба послухати заново.');}catch(error){status(error.message,true);}
    });}
  card.querySelector('.lang-remove').addEventListener('click',()=>modal(`Прибрати ${item.name}?`,
    `<p>Переклад і озвучка цієї мови зникнуть зі студії.${item.folder?' Файли в папці випуску залишаться.':''}</p>`,
    [{label:'Скасувати',run:closeModal},{label:'Прибрати мову',danger:true,run:async()=>{closeModal();
      try{langData=await api(`/api/projects/${encodeURIComponent(id)}/languages/${item.code}/remove`,'POST',{});delete langDrafts[`${id}:${item.code}`];drawLangs(id);}catch(error){status(error.message,true);}}}]));
  card.querySelector('.lang-translate')?.addEventListener('click',()=>langStart(id,'translate',item.code));
  card.querySelector('.lang-retranslate')?.addEventListener('click',()=>modal(`Перекласти ${item.name} заново?`,
    '<p>Новий переклад замінить поточний текст разом із вашими правками.</p>',
    [{label:'Скасувати',run:closeModal},{label:'Перекласти заново',primary:true,run:()=>{closeModal();delete langDrafts[`${id}:${item.code}`];langStart(id,'translate',item.code);}}]));
  card.querySelector('.lang-sample-run')?.addEventListener('click',()=>{if(!save?.disabled){status('Спершу збережіть правки тексту.',true);return;}langStart(id,'sample',item.code);});
  card.querySelector('.lang-voice-run')?.addEventListener('click',()=>{
    if(!save?.disabled){status('Спершу збережіть правки тексту.',true);return;}
    modal(`Озвучити ${item.name}?`,`<p>${esc(spec.name)} озвучить весь текст вашим голосом: ${item.chars.toLocaleString('uk-UA')} символів, орієнтовно <b>${langMoney(price || 0)}</b>. Гроші спишуться з вашого рахунку ${esc(spec.name)}.</p>
      <p>Студія склеїть частини, вирівняє гучність і піджене довжину під ролик. Зазвичай це кілька хвилин.</p>`,
      [{label:'Скасувати',run:closeModal},{label:`Озвучити · ${langMoney(price || 0)}`,primary:true,run:()=>{closeModal();langStart(id,'voice',item.code);}}]);
  });
  card.querySelector('.lang-thumb-run')?.addEventListener('click',()=>langStart(id,'thumbnail',item.code));
  return card;
}

async function langStart(id,kind,code){
  try{
    const {job}=await api(`/api/projects/${encodeURIComponent(id)}/languages/${code}/${kind}`,'POST',{provider:langData.provider});
    langData.job=job;showLangJob();pollLangs(id);
  }catch(error){status(error.message,true);}
}

function showLangJob(){
  const box=document.querySelector('#project-langs .lang-job'),job=langData?.job;if(!box)return;
  const busy=langBusy();
  document.querySelectorAll('#project-langs .lang-card button:not(.voice-player-play):not(.voice-player-mute), #project-langs .lang-add select').forEach(button=>{
    if(button.classList.contains('lang-save'))return;button.disabled=busy;});
  const name=job?.code?(langData.languages.find(item=>item.code===job.code)?.name || ''):'';
  const recent=job&&job.status!=='running'&&job.finished_at&&Date.now()/1000-job.finished_at<120;
  box.hidden=!job || (!busy && !recent);
  box.dataset.status=job?.status || '';
  if(box.hidden)return;
  box.innerHTML=busy?`${typeof exportSpinner==='string'?exportSpinner:''}<span><b>${esc(name)}: ${esc(job.what || '')}</b> · ${esc(job.stage || '')}</span><progress max="100" value="${job.progress || 0}"></progress>`
    :job.status==='done'?`<span><b>${esc(name)}: ${esc(job.what || '')} готово.</b>${job.cost?` Витрачено ${langMoney(job.cost)}.`:''}</span>`
    :`<span><b>${esc(name)}: ${esc(job.what || '')} не вдалося.</b> ${esc(job.error || '')}</span>`;
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
