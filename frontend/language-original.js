// The source column is read from the project, independently of paid translations.
let langOriginalDialog=null;

function langSourceDetails(data){
  const source=data.source||{},language=data.languages?.find(item=>item.code===source.language);
  return {...source,name:language?.name||'Мова оригіналу',code:source.language||'',
    filename:source.filename||'Оригінальне аудіо'};
}

function langSourceAudioUrl(id){return `/api/projects/${encodeURIComponent(id)}/languages/original`;}

function langCloseOriginal(){langOriginalDialog?.close();}

function langSourceDialog(id,title,body){
  if(state.project?.id!==id)return null;
  langCloseOriginal();
  const dialog=document.createElement('dialog');dialog.className='lang-script-dialog lang-original-dialog';dialog.dataset.project=id;
  dialog.setAttribute('aria-labelledby','lang-original-dialog-title');
  dialog.innerHTML=`<div class="lang-script-dialog-head"><div><h2 id="lang-original-dialog-title">${title}</h2></div><button type="button" class="lang-script-close" aria-label="Закрити оригінал">×</button></div><div class="lang-script-dialog-body">${body}</div>`;
  dialog.querySelector('.lang-script-close').onclick=()=>dialog.close();
  dialog.addEventListener('click',event=>{if(event.target===dialog)dialog.close();});
  dialog.addEventListener('close',()=>{dialog.querySelectorAll('audio').forEach(audio=>audio.pause());if(langOriginalDialog===dialog)langOriginalDialog=null;dialog.remove();},{once:true});
  langOriginalDialog=dialog;document.body.append(dialog);dialog.showModal();return dialog;
}

async function langOpenSourceScript(id){
  const source=langSourceDetails(langData);
  const dialog=langSourceDialog(id,`${langFlag(source.code)} Оригінал · ${esc(source.name)}`,'<p class="lang-source-loading" role="status">Завантаження сценарію…</p>');
  if(!dialog)return;
  try{
    // This existing read-only endpoint resolves the same episode title and script
    // used for the original cover, including projects without a frame plan.
    const data=await api(`/api/projects/${encodeURIComponent(id)}/thumbnail`);
    if(langOriginalDialog!==dialog||state.project?.id!==id)return;
    dialog.querySelector('.lang-script-dialog-body').innerHTML=`<div class="lang-script-fields"><label class="lang-title"><span>Заголовок</span><input type="text" readonly value="${esc(data.title||source.title||'')}"></label><label class="lang-text"><span>Текст оригіналу <small>${(source.display_chars??langLetters(data.script||'')).toLocaleString('uk-UA')} літер</small></span><textarea rows="14" readonly spellcheck="false">${esc(data.script||'')}</textarea></label></div>`;
  }catch(error){if(langOriginalDialog===dialog)dialog.querySelector('.lang-source-loading').textContent=error.message;}
}

function langOpenSourceAudio(id){
  const source=langSourceDetails(langData);if(!source.voice)return;
  const dialog=langSourceDialog(id,`${langFlag(source.code)} Озвучка оригіналу`,
    `<p class="lang-source-filename">${esc(source.filename)}</p><div class="lang-source-full-player"></div>`);
  if(!dialog)return;
  const player=voicePlayer(id,langSourceAudioUrl(id),{duration:source.duration});
  if(player)dialog.querySelector('.lang-source-full-player').replaceWith(player);
}

function langSourceAudioCard(id,source,narrator=false){
  const card=document.createElement('div');card.className=narrator?'lang-voice-summary lang-source-narrator':'lang-voice-tile lang-source-narration';
  const heading=narrator?'Голос диктора':'Озвучка оригіналу';
  card.innerHTML=`<button type="button" class="${narrator?'lang-voice-open':'lang-voice-tile-open'}" aria-label="${heading}: ${esc(source.name)}"${source.voice?'':' disabled'}>${narrator?`<strong>${micIcon}<span>${heading}</span></strong><span>Оригінальний голос</span>`:`<span class="lang-voice-tile-heading">${langWaveIcon}<span>${heading}</span></span><span class="lang-voice-tile-state">${source.voice?langScriptCheck:''}<strong>${source.voice?'Аудіо прикріплено':'Аудіо ще не додано'}</strong></span>`}</button>`;
  card.querySelector('button').onclick=()=>langOpenSourceAudio(id);
  if(source.voice){
    const holder=document.createElement('div');holder.className='lang-summary-player lang-own has-voice';
    const player=voicePlayer(id,langSourceAudioUrl(id),{filename:source.filename,duration:source.duration,playLabel:`Відтворити оригінал: ${source.name}`});
    if(player){holder.append(player);card.append(holder);}
  }else if(narrator){const note=document.createElement('span');note.className='lang-summary-source';note.textContent='Аудіо ще не додано';card.append(note);}
  return card;
}

function langOpenSourceThumbnail(id){
  const source=langSourceDetails(langData);
  if(!langData.thumbnail){setProjectView('thumb');return;}
  const base=`/api/projects/${encodeURIComponent(id)}`;
  const dialog=langSourceDialog(id,`${langFlag(source.code)} Прев’ю оригіналу`,
    `<figure class="lang-thumb lang-source-cover"><img class="thumb-current" data-project-id="${esc(id)}" src="${base}/cover?v=${Date.now()}" alt="Поточна обкладинка ролика"><div class="project-actions lang-thumb-actions"><a class="project-action" href="${base}/languages/original/thumbnail?download=${encodeURIComponent('Прев’ю оригінал.png')}" download="Прев’ю оригінал.png" aria-label="Завантажити прев’ю оригіналу">${langDownloadIcon}</a></div></figure><button type="button" class="secondary lang-source-gallery">Усі прев’ю</button>`);
  if(dialog)dialog.querySelector('.lang-source-gallery').onclick=()=>{dialog.close();setProjectView('thumb');};
}

function langOriginalColumn(id,data){
  const source=langSourceDetails(data),column=document.createElement('div');column.className='lang-language-column lang-original-column';
  column.innerHTML=`<h3 class="lang-language-heading">${langFlag(source.code)}${esc(source.name)}</h3><button type="button" class="lang-script-file ready" aria-label="Відкрити оригінал: ${esc(source.name)}"><span class="lang-script-file-head">${langMarkIcons.text}<strong>Оригінал</strong><span class="lang-script-fold" aria-hidden="true"></span></span><span class="lang-script-file-title">${esc(source.title||'Сценарій ролика')}</span><span class="lang-script-file-status">${langScriptCheck}</span></button>`;
  column.querySelector('.lang-script-file-title').insertAdjacentHTML('afterend',langScriptCharacters(source));
  column.querySelector('.lang-script-file').onclick=()=>langOpenSourceScript(id);
  column.append(langSourceAudioCard(id,source,true),langSourceAudioCard(id,source));
  const tile=document.createElement('div');tile.className='lang-thumbnail-tile';tile.classList.toggle('has-picture',!!data.thumbnail);
  tile.innerHTML=`<strong>${langFlag(source.code)}Прев’ю</strong><div class="lang-thumbnail-preview"><button type="button" aria-label="Прев’ю оригіналу">${data.thumbnail?`<img class="thumb-current" data-project-id="${esc(id)}" src="/api/projects/${encodeURIComponent(id)}/cover?v=${Date.now()}" alt="Поточна обкладинка ролика" loading="lazy">`:`<span>${thumbnailIcon}<small>Створити прев’ю</small></span>`}</button>${data.thumbnail?`<div class="lang-thumbnail-actions"><a class="project-action" href="/api/projects/${encodeURIComponent(id)}/languages/original/thumbnail?download=${encodeURIComponent('Прев’ю оригінал.png')}" download="Прев’ю оригінал.png" aria-label="Завантажити прев’ю оригіналу" title="Завантажити">${langDownloadIcon}</a><button type="button" class="project-action lang-thumbnail-redo" aria-label="Згенерувати нове прев’ю оригіналу" title="Згенерувати ще раз">${thumbnailIcon}</button></div>`:''}</div>`;
  tile.querySelector('button').onclick=()=>langOpenSourceThumbnail(id);
  tile.querySelector('.lang-thumbnail-redo')?.addEventListener('click',()=>openThumbnail(state.project));column.append(tile);return column;
}
