// Saved channel voice. Upload is local; synthesis starts only from the sample button.
const VOICE_TEMPO_MIN=87,VOICE_TEMPO_MAX=105;
function voiceTempoPercent(value){return Math.max(VOICE_TEMPO_MIN,Math.min(VOICE_TEMPO_MAX,Math.round(Number(value)||100)));}
function voiceTempoRange(id,value,name=''){
  return `<span class="tempo-scale"><input id="${esc(id)}" ${name?`name="${esc(name)}"`:''} type="range" min="${VOICE_TEMPO_MIN}" max="${VOICE_TEMPO_MAX}" step="1" value="${voiceTempoPercent(value)}" aria-label="Швидкість озвучки"><span class="tempo-ticks" aria-hidden="true">${Array.from({length:VOICE_TEMPO_MAX-VOICE_TEMPO_MIN+1},(_,i)=>`<i${i+VOICE_TEMPO_MIN===100?' class="tempo-normal"':''}></i>`).join('')}</span><span class="tempo-labels" aria-hidden="true"><span>87%</span><span>105%</span></span></span>`;
}
// Compare the parameters that actually reach the selected service.
function voiceLabSampleKey(s){
  if(s.provider==='heygen')return JSON.stringify(['provider','language','text','heygen_model','heygen_voice_id',...(s.heygen_model==='starfish'?['heygen_starfish_speed','heygen_starfish_ssml','heygen_starfish_locale']:(s.heygen_expressiveness??.5)!==.5?['heygen_expressiveness']:[])].map(k=>[k,s[k]]));
  const fields=['provider','language','text',...(voiceLabVoiceId(s)?[]:['noise_cleanup']),...(s.provider==='fishaudio'?['fish_engine','temperature','top_p','chunk_length','fish_voice_id']:['model','delivery','stability','similarity_boost','direction','eleven_voice_id'])];
  return JSON.stringify(fields.map(k=>[k,k==='speed'?(s[k]??1):s[k]]));
}
function voiceLabVoiceId(s){return s?.[s.provider==='heygen'?'heygen_voice_id':s.provider==='fishaudio'?'fish_voice_id':'eleven_voice_id']||'';}
function voiceLabAvailable(settings,reference){
  return !!voiceLabVoiceId(settings)||(settings?.provider!=='heygen'&&!!reference);
}
function voiceLabHeygenCost(s,models){
  const spec=models?.find(m=>m.id===s.heygen_model),text=s.heygen_model==='starfish'&&s.heygen_starfish_ssml?s.text.replace(/<[^>]*>/g,''):s.text;
  return [...text].length*(spec?.rate||0)/(s.heygen_model==='starfish'?(s.heygen_starfish_speed??1):1);
}
function voiceLabClearSample(output){
  output.querySelectorAll('audio').forEach(audio=>{audio.pause();audio.removeAttribute('src');audio.load();});
  output.replaceChildren();
}
function voiceLabSampleState(selected,data){
  const same=voiceLabSampleKey(selected)===voiceLabSampleKey(data.settings);
  const matches=same&&!!(data.sample_matches_settings||data.local_preview);
  return {cached:same&&!!(data.cached_sample||data.local_preview),matches,
    ready:matches&&data.job?.status!=='running'&&!!(data.job?.status==='done'||data.local_preview)};
}
async function bindChannelVoiceLab(channel){
  const box=document.createElement('section');box.className='settings-section channel-voice-lab';
  box.innerHTML='<h3>Голос</h3><p role="status">Завантажуємо налаштування…</p>';
  const slot=document.getElementById('channel-voice-settings');
  if(slot)slot.append(box);else document.querySelector('.logo-section').after(box);
  const base=`/api/channels/${channel.id}/voice-lab`;
  let data,timer,localPreview,noisePreview,sampleStarting=false;
  const cleanup=new MutationObserver(()=>{if(!box.isConnected||$('modal-backdrop').hidden){localPreview?.dispose();noisePreview?.dispose();clearTimeout(timer);cleanup.disconnect();}});
  cleanup.observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['hidden']});
  const current=()=>box.isConnected&&!$('modal-backdrop').hidden;
  const read=()=>({heygen_starfish_speed:Number(box.querySelector('[name=heygen_starfish_speed]').value)/100,heygen_starfish_ssml:box.querySelector('[name=heygen_starfish_ssml]').value==='ssml',heygen_starfish_locale:box.querySelector('[name=heygen_starfish_locale]').value.trim(),heygen_expressiveness:Number(box.querySelector('[name=heygen_expressiveness]').value)/100,heygen_model:box.querySelector('[name=heygen_model]').value,heygen_voice_id:box.querySelector('[name=heygen_voice_id]').value.trim(),provider:box.querySelector('[name=provider]').value,fish_engine:box.querySelector('[name=fish_engine]').value,
    fish_voice_id:box.querySelector('[name=fish_voice_id]').value.trim(),eleven_voice_id:box.querySelector('[name=eleven_voice_id]').value.trim(),speed:Number(box.querySelector('[name=speed]').value)/100,reverb:readVoiceReverb(box),room_noise:readVoiceNoise(box),noise_cleanup:data.settings.noise_cleanup,chunk_length:data.settings.chunk_length,direction:box.querySelector('[name=direction]').value.trim(),temperature:Number(box.querySelector('[name=temperature]').value)/100,top_p:Number(box.querySelector('[name=top_p]').value)/100,language:box.querySelector('[name=language]').value,model:box.querySelector('[name=model]').value,
    delivery:box.querySelector('[name=delivery]').value,stability:Number(box.querySelector('[name=stability]').value)/100,
    similarity_boost:Number(box.querySelector('[name=similarity_boost]').value)/100,text:box.querySelector('textarea').value.trim()});
  const clearSample=()=>voiceLabClearSample(box.querySelector('.voice-lab-result'));
  const playSample=()=>{const selected=box.querySelector('.voice-lab-result audio');if(!selected)return;document.querySelectorAll('.voice-player audio').forEach(other=>{if(other!==selected)other.pause();});selected.play().catch(()=>{});};
  const message=(text,error=false)=>{const el=box.querySelector('.voice-lab-status');if(el){el.textContent=text;el.classList.toggle('error',error);}};
  const localSample=(allow=voiceLabSampleKey(read())===voiceLabSampleKey(data.settings))=>{
    const slot=box.querySelector('.voice-local-preview'),local=box.querySelector('.voice-local-settings');if(!slot||!local)return;
    const source=allow?data.local_preview:null;
    local.querySelectorAll('[name=speed],[data-reverb],[data-noise]').forEach(control=>control.disabled=!source);
    if(slot.dataset.source===(source||''))return;
    localPreview?.dispose();slot.replaceChildren();slot.dataset.source=source||'';
    if(source){
      const player=voicePlayer(null,source,{playLabel:'Прослухати налаштування голосу'});slot.append(player);
      const audio=player.querySelector('audio'),error=error=>message(error.message,true);
      const effects=attachVoiceEffects(audio,()=>readVoiceReverb(box),data.local_preview_tempo?()=>1:()=>read().speed,error,()=>readVoiceNoise(box),data.local_effects_version??2);
      const tempo=data.local_preview_tempo?attachVoiceTempo(audio,source,()=>read().speed,error):null;
      localPreview={update(){effects.update();tempo?.update();},dispose(){tempo?.dispose();effects.dispose();}};
    }else slot.innerHTML='<small>Спочатку створіть зразок голосу.</small>';
  };
  const estimate=()=>{
    const settings=read(),fish=settings.provider==='fishaudio',rate=settings.model==='eleven_v4_turbo'?.26:.5;
    localSample();
    const {cached,ready}=voiceLabSampleState(settings,data);
    const count=[...settings.text].length+(settings.direction?[...settings.direction].length+3:settings.delivery==='neutral'?0:settings.delivery==='calm'?22:28);
    const fishRate=data.fish_models.find(m=>m.id===settings.fish_engine)?.rate||0;
    const sameOriginal=voiceLabSampleKey({...settings,speed:1,reverb:{enabled:false},room_noise:{enabled:false}})===voiceLabSampleKey({...data.settings,speed:1,reverb:{enabled:false},room_noise:{enabled:false}});
    const usd=data.cached_fish_original&&sameOriginal?0:new TextEncoder().encode(settings.text).length*fishRate;
    const freeOriginal=data.cached_original&&voiceLabSampleKey({...settings,speed:1,reverb:{enabled:false},room_noise:{enabled:false}})===voiceLabSampleKey({...data.settings,speed:1,reverb:{enabled:false},room_noise:{enabled:false}});
    const heygen=settings.provider==='heygen',heygenCost=voiceLabHeygenCost(settings,data.heygen_models);
    const price=freeOriginal?'безкоштовно':heygen?(heygenCost?`≈ $${heygenCost.toFixed(4)}`:'безкоштовно'):fish?(usd?`≈ $${usd.toFixed(4)}`:'безкоштовно'):`≈ ${Math.ceil(count*rate).toLocaleString('uk-UA')} кредитів`;
    box.querySelectorAll('[data-provider]').forEach(el=>{el.hidden=el.dataset.provider!==settings.provider;});
    const starfish=heygen&&settings.heygen_model==='starfish';
    box.querySelectorAll('[data-heygen-engine]').forEach(el=>{el.hidden=!heygen||el.dataset.heygenEngine!==(starfish?'starfish':'voice');});
    box.querySelector('.voice-lab-identity').hidden=!heygen;
    box.querySelector('.voice-lab-listen').innerHTML=`${playIcon}<span>${data.job?.status==='running'?'Створюємо зразок…':cached?'Відтворити зразок · безкоштовно':`Створити зразок · ${price}`}</span>`;
    box.querySelector('.voice-lab-listen').disabled=!voiceLabAvailable(settings,data.reference)||data.job?.status==='running'||sampleStarting;
    box.querySelector('.voice-lab-actions').hidden=ready;
    const fishCreate=box.querySelector('.fish-create-voice');
    fishCreate.disabled=!data.reference||!!settings.fish_voice_id;
    fishCreate.closest('.voice-id-actions').hidden=fishCreate.disabled;
    box.querySelectorAll('[data-copy-voice]').forEach(button=>button.disabled=!(box.querySelector(`[name=${button.dataset.copyVoice}]`).value.trim()||data.voice_ids?.[button.dataset.service]));
    box.querySelector('.heygen-create-voice').disabled=!data.reference||starfish;
    box.querySelector('.heygen-create-voice').hidden=starfish;
    box.querySelectorAll('input[type=range][name],[data-reverb=amount],[data-noise=amount]').forEach(input=>{const output=input.closest('label')?.querySelector('output');if(output)output.textContent=input.value+'%';});
  };
  const preparedPlayer=()=>{
    const output=box.querySelector('.voice-lab-prepared'),key=data.prepared_reference?.key;
    if(read().noise_cleanup&&key&&output.dataset.key!==key){voiceLabClearSample(output);output.dataset.key=key;output.append(voicePlayer(null,`${base}/prepared?key=${key}`,{filename:'Очищений приклад.mp3',playLabel:'Відтворити очищений приклад'}));}
  };
  const sample=()=>{
    preparedPlayer();
    localSample();
    const output=box.querySelector('.voice-lab-result');clearSample();
    const {matches,ready}=voiceLabSampleState(read(),data);
    if(ready){
      const player=voicePlayer(null,data.local_preview||`${base}/sample?key=${data.job.fingerprint}`,{filename:'Зразок голосу готовий',playLabel:'Відтворити зразок голосу'});
      output.append(player);
      const used=data.job?.settings||data.settings;
      const caption=document.createElement('small');caption.textContent=used.provider==='heygen'&&used.heygen_model==='starfish'?`Starfish · швидкість ${Math.round((used.heygen_starfish_speed??1)*100)}% · ${used.heygen_starfish_ssml?'SSML':'звичайний текст'}`:used.provider==='heygen'?`Виразність ${Math.round((used.heygen_expressiveness??.5)*100)}%`:used.provider==='elevenlabs'?`Стабільність ${Math.round(used.stability*100)}% · Схожість ${Math.round(used.similarity_boost*100)}%`:`Виразність ${Math.round(used.temperature*100)}% · Варіативність ${Math.round(used.top_p*100)}%`;output.append(caption);
      message('');
    }else if(data.job?.status==='failed')message(data.job.error||'Не вдалося створити зразок',true);
    else if(data.job?.status==='running'){
      const state=box.querySelector('.voice-lab-status');state.innerHTML=`${exportSpinner}<span>${data.job.stage==='cleanup'?'Очищуємо шум на комп’ютері':data.job.stage==='reference'?'Розпізнаємо приклад для Fish Audio':data.job.stage==='clone'?'Підключаємо голос':'Озвучуємо зразок'}…</span>`;
    }else if(!matches&&(data.job?.status==='done'||data.local_preview))message('Налаштування змінено. Створіть зразок із цими параметрами.');
    else message('');
    estimate();
  };
  const poll=async()=>{
    if(!current())return;
    try{const wasRunning=data.job?.status==='running';data=await api(base);if(!current())return;sample();if(data.job?.status==='running')timer=setTimeout(poll,1600);else if(wasRunning&&data.job?.status==='done')playSample();}
    catch(error){if(current()){message(error.message,true);if(data.job?.status==='running'&&error.httpStatus!==404)timer=setTimeout(poll,3000);}}
  };
  const audition=async draft=>{
    const dialog=document.createElement('dialog');dialog.className='voice-reference-dialog';
    dialog.innerHTML=`<div class="reference-preview-head"><h3>Підготувати запис</h3><button type="button" class="lang-script-close reference-preview-close" aria-label="Закрити підготовку запису">×</button></div><p>${esc(draft.filename)}</p><div class="reference-preview-player"></div><label class="reference-clean-choice"><input type="checkbox">Очистити шум</label><p class="reference-preview-status">Прослухайте запис. За бажанням увімкніть очищення.</p><div class="reference-preview-actions"><button type="button" class="secondary reference-preview-accept">Використовувати аудіо</button></div>`;
    document.body.append(dialog);dialog.showModal();
    const output=dialog.querySelector('.reference-preview-player'),choice=dialog.querySelector('input'),accept=dialog.querySelector('.reference-preview-accept'),note=dialog.querySelector('.reference-preview-status');
    let cleanPromise=null,accepted=false;
    const switchPreview=clean=>{
      const before=output.querySelector('audio'),at=before?.currentTime||0,playing=before&&!before.paused;
      voiceLabClearSample(output);
      output.append(voicePlayer(null,`${base}/draft?id=${draft.id}&clean=${clean?1:0}`,{filename:clean?'Очищена версія':'Початковий запис',playLabel:'Прослухати вибрану версію'}));
      const audio=output.querySelector('audio');audio.addEventListener('loadedmetadata',()=>{audio.currentTime=Math.min(at,audio.duration||at);if(playing)audio.play().catch(()=>{});},{once:true});
    };
    switchPreview(false);
    choice.addEventListener('change',async()=>{
      if(!choice.checked){switchPreview(false);accept.disabled=false;note.textContent='Початковий запис. Гучність не підсилюється.';return;}
      accept.disabled=true;note.textContent='Очищуємо шум локально…';
      try{
        cleanPromise ||= api(base+'/reference/preview','POST',{draft_id:draft.id});
        await cleanPromise;if(!dialog.open||!choice.checked)return;
        switchPreview(true);accept.disabled=false;note.textContent='Порівняйте результат. Зніміть галочку, щоб повернути початковий запис.';
      }catch(error){cleanPromise=null;choice.checked=false;accept.disabled=false;note.textContent=error.message;switchPreview(false);}
    });
    dialog.querySelector('.reference-preview-close').addEventListener('click',()=>dialog.close());
    dialog.addEventListener('close',()=>{voiceLabClearSample(output);dialog.remove();if(!accepted){message('Новий запис не прикріплено.');api(base+'/reference/discard','POST',{draft_id:draft.id}).catch(()=>{});}});
    accept.addEventListener('click',async()=>{
      accept.disabled=true;
      try{data=await api(base+'/reference/accept','POST',{draft_id:draft.id,cleaned:choice.checked});accepted=true;dialog.close();draw();message('Вибрану версію прикріплено. Саме вона використовуватиметься для голосу.');}
      catch(error){note.textContent=error.message;accept.disabled=false;}
    });
  };
  const draw=()=>{
    if(!current())return;
    localPreview?.dispose();noisePreview?.dispose();
    const s=data.settings;
    box.innerHTML=`<h3>Голос</h3>
      <div class="settings-three-column voice-lab-service"><label>Сервіс<select name="provider" aria-label="Сервіс"><option value="elevenlabs" ${s.provider==='elevenlabs'?'selected':''}>ElevenLabs</option><option value="fishaudio" ${s.provider==='fishaudio'?'selected':''}>Fish Audio</option><option value="heygen" ${s.provider==='heygen'?'selected':''}>HeyGen</option></select></label><label>Мова голосу<select name="language" aria-label="Мова голосу">${data.languages.map(l=>`<option value="${l.code}" ${l.code===s.language?'selected':''}>${esc(l.name)}</option>`).join('')}</select></label>
      <label data-provider="elevenlabs">Модель<select name="model">${data.models.map(m=>`<option value="${m.id}" ${m.id===s.model?'selected':''}>${esc(m.name)}</option>`).join('')}</select></label>
      <label data-provider="heygen">Модель<select name="heygen_model">${(data.heygen_models||[]).map(m=>`<option value="${m.id}" ${m.id===s.heygen_model?'selected':''}>${esc(m.name.replace(/^HeyGen /,''))}</option>`).join('')}</select></label><label data-provider="fishaudio">Модель<select name="fish_engine">${data.fish_models.map(m=>`<option value="${m.id}" ${m.id===s.fish_engine?'selected':''}>${esc(m.name)}</option>`).join('')}</select></label>
      <label data-provider="elevenlabs">Подача<select name="delivery">${[['conversational','Розмовна'],['neutral','Як у записі'],['calm','Спокійна']].map(([k,v])=>`<option value="${k}" ${k===s.delivery?'selected':''}>${v}</option>`).join('')}</select></label></div>

      <div class="voice-lab-source"><h4>Приклад голосу</h4><div class="voice-lab-reference"><span class="voice-lab-reference-player"></span><label class="secondary voice-lab-upload" ${data.reference||voiceLabVoiceId(s)?'hidden':''}>Додати аудіо або відео<input type="file" accept="audio/*,video/*" hidden></label>${data.reference||voiceLabVoiceId(s)?`<button type="button" class="voice-lab-remove" aria-label="Прибрати голос">${trashIcon}</button>`:''}</div>
      <small class="voice-lab-preparation-status" ${data.reference?.cleanup_applied?'':'hidden'}>Вибрано очищену версію</small><div class="voice-lab-prepared"></div></div>
      <div class="voice-lab-identity" data-provider="heygen"><div class="voice-lab-identity-actions"><button type="button" class="secondary heygen-load-voices">Вибрати голос</button><button type="button" class="secondary heygen-create-voice">Створити із запису</button></div><select class="heygen-voice-list" aria-label="Голос HeyGen" hidden></select></div>
      ${[['heygen','heygen_voice_id','HeyGen'],['fishaudio','fish_voice_id','Fish Audio'],['elevenlabs','eleven_voice_id','ElevenLabs']].map(([provider,field,label])=>`<details class="voice-lab-advanced voice-id-details" data-provider="${provider}"><summary>ID голосу</summary><label for="voice-id-${provider}">ID голосу ${label}</label><div class="voice-id-field"><input id="voice-id-${provider}" name="${field}" value="${esc(s[field]||'')}" placeholder="Вставте ID з цього самого акаунта" autocomplete="off" spellcheck="false"><button type="button" class="voice-id-copy" data-copy-voice="${field}" data-service="${provider}" aria-label="Скопіювати ID голосу ${label}" title="Скопіювати ID"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></svg></button></div>${!s[field]&&data.voice_ids?.[provider]?`<small class="voice-known-id">Збережений ID: <code>${esc(data.voice_ids[provider])}</code></small>`:''}${provider==='fishaudio'?'<div class="voice-id-actions"><button type="button" class="secondary fish-create-voice">Зберегти голос у Fish</button></div>':''}</details>`).join('')}
      <div class="voice-lab-tuning">
      <div class="voice-lab-sliders"><label>Швидкість<span>${voiceTempoRange("voice-lab-speed",(s.speed??1)*100,"speed")}<output>${voiceTempoPercent((s.speed??1)*100)}%</output></span></label></div><div class="voice-lab-sliders" data-provider="elevenlabs">${[['stability','Стабільність'],['similarity_boost','Схожість із записом']].map(([k,v])=>`<label>${v}<span><input name="${k}" type="range" min="0" max="100" step="5" value="${Math.round(s[k]*100)}"><output>${Math.round(s[k]*100)}%</output></span></label>`).join('')}</div>
      <div class="voice-lab-sliders" data-heygen-engine="voice"><label>Виразність<span><input name="heygen_expressiveness" type="range" min="0" max="100" step="5" value="${Math.round((s.heygen_expressiveness??.5)*100)}"><output>${Math.round((s.heygen_expressiveness??.5)*100)}%</output></span><small>Від стриманої до виразнішої подачі. Для нового зразка instant-голосу.</small></label></div>
      <div class="voice-lab-starfish" data-heygen-engine="starfish"><label>Швидкість голосу Starfish<span><input name="heygen_starfish_speed" type="range" min="50" max="200" step="5" value="${Math.round((s.heygen_starfish_speed??1)*100)}"><output></output></span></label><label>Формат тексту<select name="heygen_starfish_ssml"><option value="text" ${!s.heygen_starfish_ssml?'selected':''}>Звичайний текст</option><option value="ssml" ${s.heygen_starfish_ssml?'selected':''}>SSML, паузи та вимова</option></select></label><label>Регіональна вимова<input name="heygen_starfish_locale" maxlength="35" value="${esc(s.heygen_starfish_locale||'')}" placeholder="Автоматично, наприклад uk-UA"></label><small>Приблизно $0,12 за хвилину аудіо. Пауза та темп впливають на ціну. SSML зі службовими тегами: до 5000 символів для повного сценарію</small></div>
      <div class="voice-lab-sliders" data-provider="fishaudio">${[['temperature','Виразність'],['top_p','Варіативність']].map(([k,v])=>`<label>${v}<span><input name="${k}" type="range" min="0" max="100" step="5" value="${Math.round(s[k]*100)}"><output>${Math.round(s[k]*100)}%</output></span></label>`).join('')}</div>
      </div><label class="voice-lab-direction" data-provider="elevenlabs">Побажання до подачі<input name="direction" type="text" maxlength="160" value="${esc(s.direction)}" placeholder="Спокійно, тепло, без дикторської подачі"><small>Необов’язково. Якщо заповнено, застосовується замість вибраної подачі.</small></label>
      <label class="voice-lab-text">Текст зразка<textarea rows="3" maxlength="2000">${esc(s.text)}</textarea></label>
      <div class="voice-lab-actions"><button type="button" class="secondary voice-lab-listen"></button></div>
      <div class="voice-lab-status" role="status" aria-live="polite"></div><div class="voice-lab-result"></div>`;
    // Keep one editor per setting while grouping the shared recording, service and audition.
    const tuning=box.querySelector('.voice-lab-tuning'),speed=tuning.firstElementChild;
    const advanced=document.createElement('details');advanced.className='voice-lab-expression';
    advanced.innerHTML='<summary>Додаткові налаштування голосу</summary><div class="voice-local-settings"></div>';
    box.querySelector('.voice-lab-result').after(advanced);advanced.querySelector('.voice-local-settings').append(speed);
    advanced.querySelector('.voice-local-settings').insertAdjacentHTML('beforeend',voiceReverbControls(s.reverb,s.room_noise)+'<div class="voice-local-preview"></div>');
    noisePreview=bindVoiceNoisePreview(advanced,error=>message(error.message,true),data.local_effects_version??2);
    const delivery=box.querySelector('[name=delivery]').closest('label');tuning.prepend(delivery);
    const step=(number,key,title)=>{
      const section=document.createElement('section');section.className='voice-lab-step';section.dataset.voiceStep=key;
      const id=`voice-step-${channel.id}-${key}`;section.setAttribute('aria-labelledby',id);
      section.innerHTML=`<h4 id="${id}"><span class="voice-lab-step-number" aria-hidden="true">${number}</span>${title}</h4>`;
      return section;
    };
    const referenceStep=step(1,'reference','Приклад голосу'),modelStep=step(2,'model','Сервіс і модель'),sampleStep=step(3,'sample','Текст і зразок');
    const reference=box.querySelector('.voice-lab-source');reference.querySelector('h4').remove();referenceStep.append(reference);
    modelStep.append(box.querySelector('.voice-lab-service'),tuning,box.querySelector('.voice-lab-direction'),box.querySelector('.voice-lab-identity'),...box.querySelectorAll('.voice-id-details'));
    sampleStep.append(box.querySelector('.voice-lab-text'),box.querySelector('.voice-lab-actions'),box.querySelector('.voice-lab-status'),box.querySelector('.voice-lab-result'),advanced);
    box.append(referenceStep,modelStep,sampleStep);
    box.querySelectorAll('.voice-id-details').forEach(details=>{details.open=!!(details.querySelector('input[name]').value.trim()||data.voice_ids?.[details.dataset.provider]);});
    localSample();
    syncVoiceReverb(box);
    if(data.reference)box.querySelector('.voice-lab-reference-player').replaceChildren(voicePlayer(null,`${base}/reference?v=${data.reference.stamp}`,{filename:data.reference.filename,playLabel:'Відтворити приклад голосу'}));
    else box.querySelector('.voice-lab-reference-player').textContent=voiceLabVoiceId(s)?'Голос збережений у сервісі':'Приклад для клонування';

    box.querySelector('.heygen-load-voices').onclick=async()=>{try{const model=read().heygen_model;const result=await api(base+'/heygen-voices?model='+encodeURIComponent(model));if(!current()||read().heygen_model!==model)return;const select=box.querySelector('.heygen-voice-list');select.innerHTML='<option value="">Оберіть голос</option>'+result.voices.map(v=>`<option value="${esc(v.voice_id)}">${esc(v.name||v.voice_id)} · ${esc(v.mode||'')}</option>`).join('');select.hidden=false;select.onchange=()=>{box.querySelector('[name=heygen_voice_id]').value=select.value;sample();};}catch(error){message(error.message,true);}};
    box.querySelector('.heygen-create-voice').onclick=async(event)=>{const button=event.currentTarget;button.disabled=true;message('Готуємо запис і створюємо instant-голос HeyGen…');try{data=await api(base+'/heygen-clone','POST',{settings:read()});draw();message('Голос створено й вибрано. HeyGen може готувати його кілька секунд, після цього можна прослухати зразок.');}catch(error){message(error.message,true);button.disabled=false;}};
    box.querySelector('.fish-create-voice').onclick=async(event)=>{const button=event.currentTarget;button.disabled=true;message('Зберігаємо приватний голос у Fish…');try{data=await api(base+'/fish-clone','POST',{settings:read()});if(!current())return;draw();box.querySelector('[data-provider=fishaudio].voice-id-details').open=true;message('ID голосу збережено. Для наступних озвучок використовуватиметься цей ID.');}catch(error){if(current()){message(error.message,true);estimate();}}};
    box.querySelectorAll('[data-copy-voice]').forEach(button=>button.onclick=async()=>{const input=box.querySelector(`[name=${button.dataset.copyVoice}]`),value=input.value.trim()||data.voice_ids?.[button.dataset.service];if(!value)return;try{await navigator.clipboard.writeText(value);message('ID голосу скопійовано');}catch(error){input.focus();input.select();message('Виділіть ID і скопіюйте його вручну',true);}});
    let previousModel=read().heygen_model;
    box.querySelector('[name=heygen_model]').addEventListener('input',()=>{const model=read().heygen_model;if((previousModel==='starfish')!==(model==='starfish')){box.querySelector('[name=heygen_voice_id]').value='';const list=box.querySelector('.heygen-voice-list');list.replaceChildren();list.hidden=true;}previousModel=model;});
    box.voiceSettingsSnapshot=read;
    box.saveVoiceSettings=async(settings=read())=>{data=await api(base,'POST',{settings});return data;};
    box.querySelectorAll('select[name],input[name]:not([type=file]),textarea,[data-reverb],[data-noise]').forEach(input=>input.addEventListener('input',()=>{
      if(input.closest('.voice-local-settings')){syncVoiceReverb(box);localPreview?.update();message('');}
      else {sample();return;}
      estimate();
    }));
    box.querySelector('.voice-lab-remove')?.addEventListener('click',async()=>{try{data=await api(base+'/reference/remove','POST',{});draw();}catch(error){message(error.message,true);}});
    box.querySelector('input[type=file]').addEventListener('change',async event=>{
      const file=event.target.files[0];if(!file)return;
      const label=event.target.closest('label');label.classList.add('is-off');message('Завантажуємо запис для попереднього прослуховування…');
      try{
        await api(base,'POST',{settings:read()});
        const response=await fetch(base+'/reference',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-File-Name':encodeURIComponent(file.name)},body:file});
        const result=await response.json();if(!response.ok)throw new Error(result.error||'Не вдалося завантажити запис');
        label.classList.remove('is-off');await audition(result.draft);event.target.value='';
      }catch(error){message(error.message,true);label.classList.remove('is-off');}
    });
    box.querySelector('.voice-lab-listen').addEventListener('click',async()=>{
      if(sampleStarting||data.job?.status==='running'||!voiceLabAvailable(read(),data.reference))return;
      if(voiceLabSampleState(read(),data).cached&&box.querySelector('.voice-lab-result audio')){playSample();return;}
      sampleStarting=true;const button=box.querySelector('.voice-lab-listen');button.disabled=true;
      try{
        data=await api(base+'/sample','POST',{settings:read(),client_id:crypto.randomUUID()});
        if(!current())return;
        sample();
        if(data.job?.status==='running')timer=setTimeout(poll,1000);
        else playSample();
      }catch(error){if(current())message(error.message,true);}
      finally{sampleStarting=false;if(current())estimate();}
    });
    sample();
    if(data.job?.status==='running')timer=setTimeout(poll,1500);
  };
  const load=async()=>{
    try{data=await api(base);if(current())draw();}
    catch(error){if(!current())return;box.innerHTML=`<h3>Голос</h3><p role="status">${esc(error.message)}</p><button type="button" class="secondary voice-lab-retry">Повторити завантаження</button>`;
      box.querySelector('.voice-lab-retry').onclick=async event=>{event.currentTarget.disabled=true;await load();};}
  };
  await load();
}
