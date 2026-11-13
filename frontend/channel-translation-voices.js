/* Each language owns its narration choices and its explicit sample request. */
async function bindChannelVoices(channel){
  const section=$('channel-voices'),generation=state.modalGeneration;if(!section)return;
  const live=()=>section.isConnected&&state.modalGeneration===generation&&$('channel-voices')===section;
  const base=`/api/channels/${encodeURIComponent(channel.id)}/voices`,rows=new Map();let disposed=false,ownsRecording=false;
  section.translationVoiceDispose?.();
  section.translationVoiceDispose=()=>{disposed=true;for(const row of rows.values())clearTimeout(row.timer);if(ownsRecording&&langRecorder?.state==='recording')langRecorder.stop();};
  if(!section.translationVoiceCleanupBound){const previous=$('modal-body').channelSettingsCleanup;section.translationVoiceCleanupBound=true;$('modal-body').channelSettingsCleanup=()=>{previous?.();section.translationVoiceDispose?.();};}
  const current=()=>!disposed&&live();
  let data;
  try{data=await api(base);}catch(error){if(current())section.innerHTML=`<p role="status">${esc(error.message)}</p>`;return;}
  if(!current())return;
  if(!data.voice_controls)return bindLegacyChannelVoices(channel,data);
  section.innerHTML=`<p class="channel-translation-note">Голос і модель для кожної мови. Застосовуються до випусків, де цю мову ще не озвучено.</p><div class="channel-translation-list"></div><div class="channel-voice-add"><select aria-label="Мова прикладу"><option value="">Додати мову…</option>${data.languages.filter(item=>!data.voices.some(voice=>voice.code===item.code)).map(item=>`<option value="${item.code}">${langFlags[item.code]||''} ${esc(item.name)}</option>`).join('')}</select><button type="button" class="secondary lang-own-record" disabled>${micIcon}Записати себе</button><label class="secondary lang-own-file is-off">${langIcons.upload}Додати запис<input type="file" accept="audio/*,video/*" hidden disabled></label></div>`;
  const options=data.narration_options;
  function cost(quote,provider){
    if(quote?.amount===0)return 'безкоштовно';
    if(quote?.amount==null)return 'за тарифом '+(options.providers.find(item=>item.id===provider)?.name||'сервісу');
    return quote.unit==='credits'?`≈ ${Math.ceil(quote.amount).toLocaleString('uk-UA')} кредитів`:langMoney(quote.amount);
  }
  function paintControls(row){
    const provider=row.settings.provider,models=options[provider],engine=row.settings[langModelField(provider)];
    row.provider.value=provider;
    row.voiceId.closest('label').hidden=provider!=='heygen';
    row.voiceId.value=row.settings.heygen_voice_id || '';
    row.voiceId.placeholder=engine==='starfish'?'ID голосу Starfish':'Автоматично з прикладу';
    row.engine.innerHTML=models.map(model=>`<option value="${model.id}">${esc(model.name)}</option>`).join('');row.engine.value=engine;
    row.style.value=row.settings.fish_style;row.style.closest('label').hidden=provider!=='fishaudio';
  }
  function paintSample(row,result){
    if(!current())return;
    row.result=result;const working=row.sending||result.working||result.job?.status==='running';
    if(!working && result.job?.status==='failed' && result.job.client_id===row.attempt)row.attempt=null;
    for(const field of [row.provider,row.engine,row.style,row.voiceId,row.text,row.remove])field.disabled=!!working;
    row.button.disabled=!!working||!result.available;row.button.hidden=!!result.sample;
    row.button.innerHTML=working?'<span class="export-spinner"></span><span>Створюємо зразок…</span>':`${langIcons.play}<span>Створити зразок · ${esc(cost(result.estimate,row.settings.provider))}</span>`;
    row.status.textContent=result.job?.status==='failed'?result.job.error||'Не вдалося створити зразок.':!result.available?(row.settings.provider==='heygen'&&row.settings.heygen_model==='starfish'?'Введіть ID голосу Starfish.':'Додайте голос для вибраного сервісу.'):'';
    if(result.sample){
      if(row.output.dataset.key!==result.sample.key){
        row.output.querySelectorAll('audio').forEach(audio=>audio.pause());row.output.replaceChildren();
        const model=(options[row.settings.provider]||[]).find(item=>item.id===row.settings[langModelField(row.settings.provider)]);
        const player=voicePlayer(null,result.sample.url,{filename:`Зразок · ${model?.name||''}`,playLabel:'Послухати зразок голосу'});
        if(player)row.output.append(player);row.output.dataset.key=result.sample.key;
        if(row.autoplay){row.autoplay=false;row.output.querySelector('audio')?.play().catch(()=>{});}
      }
    }else{row.output.querySelectorAll('audio').forEach(audio=>audio.pause());row.output.replaceChildren();delete row.output.dataset.key;}
    clearTimeout(row.timer);if(working)row.timer=setTimeout(()=>load(row),1200);
  }
  async function load(row){
    if(!current())return;const version=++row.version;
    const query=new URLSearchParams({settings:JSON.stringify(row.settings)});if(row.text.value.trim())query.set('text',row.text.value.trim());
    try{
      const result=await api(`${base}/${row.item.code}/sample?${query}`);
      if(!current()||version!==row.version)return;
      if(!row.text.value)row.text.value=result.text;paintSample(row,result);
    }catch(error){if(current()&&version===row.version){row.status.textContent=error.message;clearTimeout(row.timer);row.timer=setTimeout(()=>load(row),3000);}}
  }
  function changed(row){
    row.version++;row.attempt=null;row.autoplay=false;clearTimeout(row.timer);
    row.output.querySelectorAll('audio').forEach(audio=>audio.pause());row.output.replaceChildren();delete row.output.dataset.key;
    row.button.hidden=false;row.button.disabled=true;row.button.innerHTML=`${langIcons.play}<span>Створити зразок</span>`;row.status.textContent='';
    row.timer=setTimeout(()=>load(row),200);
  }
  function addRow(item){
    const card=document.createElement('article');card.className='channel-translation-voice';card.dataset.code=item.code;
    card.innerHTML=`<div class="channel-translation-heading"><strong>${langFlag(item.code)} ${esc(item.name)}</strong><button type="button" class="project-action delete channel-voice-remove" title="Прибрати голос" aria-label="Прибрати голос ${esc(item.name)}">${langIcons.trash}</button></div>${item.remote_only?'<p class="channel-translation-note">Голос збережений у сервісі</p>':'<details class="channel-translation-reference"><summary>Приклад голосу</summary><div class="lang-player"></div></details>'}<div class="channel-translation-models"><label>Сервіс<select data-setting="provider" aria-label="Сервіс ${esc(item.name)}">${options.providers.map(provider=>`<option value="${provider.id}">${esc(provider.name)}</option>`).join('')}</select></label><label>Модель<select data-setting="engine" aria-label="Модель ${esc(item.name)}"></select></label><label>Подача<select data-setting="style" aria-label="Подача ${esc(item.name)}">${options.styles.map(style=>`<option value="${style.id}">${esc(style.name)}</option>`).join('')}</select></label><label hidden>ID голосу HeyGen<input type="text" data-setting="voice-id" maxlength="128" autocomplete="off"></label></div><div class="channel-translation-audition"><details><summary>Текст зразка</summary><textarea rows="3" maxlength="1000" aria-label="Текст зразка ${esc(item.name)}"></textarea></details><button type="button" class="secondary channel-translation-sample" disabled>${langIcons.play}<span>Створити зразок</span></button><div class="channel-translation-result"></div><p class="channel-translation-status" role="status"></p></div>`;
    section.querySelector('.channel-translation-list').append(card);
    if(!item.remote_only){const player=voicePlayer(null,`${base}/${item.code}/file?v=${item.stamp}`,{filename:'Приклад голосу',playLabel:'Послухати приклад голосу'});if(player)card.querySelector('.lang-player').replaceWith(player);}
    const row={item,card,settings:JSON.parse(JSON.stringify(item.settings)),version:0,timer:null,sending:false,attempt:null,autoplay:false,
      provider:card.querySelector('[data-setting="provider"]'),engine:card.querySelector('[data-setting="engine"]'),style:card.querySelector('[data-setting="style"]'),voiceId:card.querySelector('[data-setting="voice-id"]'),text:card.querySelector('textarea'),button:card.querySelector('.channel-translation-sample'),output:card.querySelector('.channel-translation-result'),status:card.querySelector('.channel-translation-status'),remove:card.querySelector('.channel-voice-remove')};
    rows.set(item.code,row);paintControls(row);
    row.provider.onchange=()=>{row.settings.provider=row.provider.value;paintControls(row);changed(row);};
    row.engine.onchange=()=>{row.settings[langModelField(row.settings.provider)]=row.engine.value;if(row.settings.provider==='fishaudio'){row.settings.fish_style=row.settings.fish_styles[row.engine.value]||options.fishaudio.find(model=>model.id===row.engine.value).default_style;}paintControls(row);changed(row);};
    row.style.onchange=()=>{row.settings.fish_style=row.style.value;row.settings.fish_styles[row.settings.fish_engine]=row.style.value;changed(row);};
    row.voiceId.oninput=()=>{row.settings.heygen_voice_id=row.voiceId.value.trim();changed(row);};
    row.text.oninput=()=>changed(row);
    row.button.onclick=async()=>{
      if(!current()||row.sending||row.result?.working||!row.result?.available)return;
      row.sending=true;row.attempt ||= crypto.randomUUID();row.autoplay=true;const version=row.version;
      paintSample(row,{...row.result,sample:null});
      try{
        const result=await api(`${base}/${item.code}/sample`,'POST',{settings:row.settings,text:row.text.value.trim(),client_id:row.attempt});
        if(current()&&version===row.version){row.sending=false;paintSample(row,result);}
      }catch(error){if(current()&&version===row.version){row.status.textContent=error.message;row.autoplay=false;row.sending=false;row.button.disabled=false;row.timer=setTimeout(()=>load(row),1500);}}
      finally{row.sending=false;}
    };
    row.remove.onclick=async()=>{if(row.remove.disabled)return;row.remove.disabled=true;try{await api(`${base}/${item.code}/remove`,'POST',{});if(current()){clearTimeout(row.timer);card.querySelectorAll('audio').forEach(audio=>audio.pause());rows.delete(item.code);card.remove();const option=document.createElement('option');option.value=item.code;option.textContent=(langFlags[item.code]||'')+' '+item.name;section.querySelector('.channel-voice-add select').append(option);}}catch(error){if(current()){row.status.textContent=error.message;row.remove.disabled=false;}}};
    load(row);
  }
  for(const item of data.voices)addRow(item);
  section.voiceSettingsSnapshot=()=>Object.fromEntries([...rows].map(([code,row])=>[code,JSON.parse(JSON.stringify(row.settings))]));
  section.saveVoiceSettings=async settings=>{if(Object.keys(settings||{}).length)await api(base+'/settings','POST',{languages:settings});};
  const picker=section.querySelector('.channel-voice-add select'),record=section.querySelector('.lang-own-record'),label=section.querySelector('.lang-own-file'),file=label.querySelector('input');
  picker.onchange=()=>{record.disabled=file.disabled=!picker.value;label.classList.toggle('is-off',!picker.value);};
  const send=async(blob,name)=>{if(!current()||!picker.value)return;try{const result=await langSendExample(`${base}/${picker.value}`,blob,name,'',section.querySelector('.channel-voice-add'));if(current()){for(const item of result.voices)if(!rows.has(item.code))addRow(item);for(const option of [...picker.options])if(rows.has(option.value))option.remove();picker.value='';picker.onchange();}}catch(error){if(current())langNote(section,error.message,true);}};
  record.onclick=()=>{ownsRecording=true;return langRecord(record,section,send);};
  file.onchange=()=>{if(file.files[0])send(file.files[0],file.files[0].name);};
}
