// Saved channel voice. Upload is local; synthesis starts only from the sample button.
// Compare the parameters that actually reach the selected service.
function voiceLabSampleKey(s){
  if(s.provider==='heygen')return JSON.stringify(['provider','language','text','heygen_model','heygen_voice_id','speed',...((s.heygen_expressiveness??.5)!==.5?['heygen_expressiveness']:[])].map(k=>[k,s[k]]));
  const fields=['provider','language','text','noise_cleanup',...(s.provider==='fishaudio'?['fish_engine','temperature','top_p','chunk_length','speed']:['model','delivery','stability','similarity_boost','direction','speed'])];
  return JSON.stringify(fields.map(k=>[k,k==='speed'?(s[k]??1):s[k]]));
}
function voiceLabClearSample(output){
  output.querySelectorAll('audio').forEach(audio=>{audio.pause();audio.removeAttribute('src');audio.load();});
  output.replaceChildren();
}
function voiceLabSampleState(selected,data){
  const same=voiceLabSampleKey(selected)===voiceLabSampleKey(data.settings);
  return {cached:same&&!!data.cached_sample,matches:same&&!!data.sample_matches_settings};
}
async function bindChannelVoiceLab(channel){
  const box=document.createElement('section');box.className='settings-section channel-voice-lab';
  box.innerHTML='<h3>Голос</h3><p role="status">Завантажуємо налаштування…</p>';
  document.querySelector('.logo-section').after(box);
  const base=`/api/channels/${channel.id}/voice-lab`;
  let data,signature='',timer;
  const current=()=>box.isConnected;
  const settingsKey=value=>JSON.stringify(Object.entries(value).sort(([a],[b])=>a.localeCompare(b)));
  const read=()=>({heygen_expressiveness:Number(box.querySelector('[name=heygen_expressiveness]').value)/100,heygen_model:box.querySelector('[name=heygen_model]').value,heygen_voice_id:box.querySelector('[name=heygen_voice_id]').value.trim(),provider:box.querySelector('[name=provider]').value,fish_engine:box.querySelector('[name=fish_engine]').value,
    speed:Number(box.querySelector('[name=speed]').value)/100,noise_cleanup:data.settings.noise_cleanup,chunk_length:data.settings.chunk_length,direction:box.querySelector('[name=direction]').value.trim(),temperature:Number(box.querySelector('[name=temperature]').value)/100,top_p:Number(box.querySelector('[name=top_p]').value)/100,language:box.querySelector('[name=language]').value,model:box.querySelector('[name=model]').value,
    delivery:box.querySelector('[name=delivery]').value,stability:Number(box.querySelector('[name=stability]').value)/100,
    similarity_boost:Number(box.querySelector('[name=similarity_boost]').value)/100,text:box.querySelector('textarea').value.trim()});
  const clearSample=()=>voiceLabClearSample(box.querySelector('.voice-lab-result'));
  const playSample=()=>{const selected=box.querySelector('.voice-lab-result audio');if(!selected)return;document.querySelectorAll('.voice-player audio').forEach(other=>{if(other!==selected)other.pause();});selected.play().catch(()=>{});};
  const message=(text,error=false)=>{const el=box.querySelector('.voice-lab-status');if(el){el.textContent=text;el.classList.toggle('error',error);}};
  const estimate=()=>{
    const settings=read(),fish=settings.provider==='fishaudio',rate=settings.model==='eleven_v4_turbo'?.26:.5;
    const same=settingsKey(settings)===signature;
    const {cached}=voiceLabSampleState(settings,data);
    const count=[...settings.text].length+(settings.direction?[...settings.direction].length+3:settings.delivery==='neutral'?0:settings.delivery==='calm'?22:28);
    const fishRate=data.fish_models.find(m=>m.id===settings.fish_engine)?.rate||0;
    const sameOriginal=voiceLabSampleKey({...settings,speed:1})===voiceLabSampleKey({...data.settings,speed:1});
    const usd=data.cached_fish_original&&sameOriginal?0:new TextEncoder().encode(settings.text).length*fishRate;
    const freeOriginal=data.cached_original&&voiceLabSampleKey({...settings,speed:1})===voiceLabSampleKey({...data.settings,speed:1});
    const heygen=settings.provider==='heygen',heygenCost=[...settings.text].length*(data.heygen_models?.find(m=>m.id===settings.heygen_model)?.rate||0);
    const price=freeOriginal?'безкоштовно':heygen?(heygenCost?`≈ $${heygenCost.toFixed(4)}`:'безкоштовно'):fish?(usd?`≈ $${usd.toFixed(4)}`:'безкоштовно'):`≈ ${Math.ceil(count*rate).toLocaleString('uk-UA')} кредитів`;
    box.querySelectorAll('[data-provider]').forEach(el=>{el.hidden=el.dataset.provider!==settings.provider;});
    box.querySelector('.voice-lab-listen').innerHTML=`${playIcon}<span>${data.job?.status==='running'?'Створюємо зразок…':cached?'Відтворити зразок · безкоштовно':`Створити зразок · ${price}`}</span>`;
    box.querySelector('.voice-lab-listen').disabled=!(heygen?settings.heygen_voice_id:data.reference)||data.job?.status==='running';
    box.querySelector('.voice-lab-save').disabled=same;
    box.querySelector('.voice-lab-identity-state').textContent=settings.heygen_voice_id?'Голос вибрано':'';
    box.querySelector('.heygen-create-voice').disabled=!data.reference;
    box.querySelectorAll('input[type=range]').forEach(input=>{input.nextElementSibling.textContent=input.value+'%';});
  };
  const preparedPlayer=()=>{
    const output=box.querySelector('.voice-lab-prepared'),key=data.prepared_reference?.key;
    if(read().noise_cleanup&&key&&output.dataset.key!==key){voiceLabClearSample(output);output.dataset.key=key;output.append(voicePlayer(null,`${base}/prepared?key=${key}`,{filename:'Очищений приклад.mp3',playLabel:'Відтворити очищений приклад'}));}
  };
  const sample=()=>{
    preparedPlayer();
    const output=box.querySelector('.voice-lab-result');clearSample();
    const {matches}=voiceLabSampleState(read(),data);
    if(data.job?.status==='done'&&matches){
      const player=voicePlayer(null,`${base}/sample?key=${data.job.fingerprint}`,{filename:'Зразок голосу.mp3',playLabel:'Відтворити зразок голосу'});
      output.append(player);
      const used=data.job.settings||data.settings;
      const caption=document.createElement('small');caption.textContent=used.provider==='heygen'?`Виразність ${Math.round((used.heygen_expressiveness??.5)*100)}%`:used.provider==='elevenlabs'?`Стабільність ${Math.round(used.stability*100)}% · Схожість ${Math.round(used.similarity_boost*100)}%`:`Виразність ${Math.round(used.temperature*100)}% · Варіативність ${Math.round(used.top_p*100)}%`;output.append(caption);
      message(data.job.cached?'Зразок із кешу. Повторної оплати немає.':'Зразок готовий. Можна прослухати та змінити налаштування.');
    }else if(data.job?.status==='failed')message(data.job.error||'Не вдалося створити зразок',true);
    else if(data.job?.status==='running'){
      const state=box.querySelector('.voice-lab-status');state.innerHTML=`${exportSpinner}<span>${data.job.stage==='cleanup'?'Очищуємо шум на комп’ютері':data.job.stage==='reference'?'Розпізнаємо приклад для Fish Audio':data.job.stage==='clone'?'Підключаємо голос':'Озвучуємо зразок'}…</span>`;
    }else if(!matches&&data.job?.status==='done')message('Налаштування змінено. Створіть новий зразок, щоб почути результат.');
    estimate();
  };
  const poll=async()=>{
    if(!current())return;
    try{const wasRunning=data.job?.status==='running';data=await api(base);if(!current())return;sample();if(data.job?.status==='running')timer=setTimeout(poll,1600);else if(wasRunning&&data.job?.status==='done')playSample();}
    catch(error){message(error.message,true);}
  };
  const audition=async draft=>{
    const dialog=document.createElement('dialog');dialog.className='voice-reference-dialog';
    dialog.innerHTML=`<h3>Підготувати запис</h3><p>${esc(draft.filename)}</p><div class="reference-preview-player"></div><label class="reference-clean-choice"><input type="checkbox">Очистити шум</label><p class="reference-preview-status">Прослухайте запис. За бажанням увімкніть очищення.</p><div class="reference-preview-actions"><button type="button" class="secondary reference-preview-cancel">Скасувати</button><button type="button" class="secondary reference-preview-accept">Використовувати аудіо</button></div>`;
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
    dialog.querySelector('.reference-preview-cancel').addEventListener('click',()=>dialog.close());
    dialog.addEventListener('close',()=>{voiceLabClearSample(output);dialog.remove();if(!accepted){message('Новий запис не прикріплено.');api(base+'/reference/discard','POST',{draft_id:draft.id}).catch(()=>{});}});
    accept.addEventListener('click',async()=>{
      accept.disabled=true;
      try{data=await api(base+'/reference/accept','POST',{draft_id:draft.id,cleaned:choice.checked});accepted=true;dialog.close();draw();message('Вибрану версію прикріплено. Саме вона використовуватиметься для голосу.');}
      catch(error){note.textContent=error.message;accept.disabled=false;}
    });
  };
  const draw=()=>{
    if(!current())return;
    const s=data.settings;
    box.innerHTML=`<h3>Голос</h3><p class="voice-lab-intro">Налаштуйте голос і прослухайте зразок.</p>
      <div class="settings-three-column voice-lab-service"><label>Сервіс<select name="provider"><option value="elevenlabs" ${s.provider==='elevenlabs'?'selected':''}>ElevenLabs</option><option value="fishaudio" ${s.provider==='fishaudio'?'selected':''}>Fish Audio</option><option value="heygen" ${s.provider==='heygen'?'selected':''}>HeyGen</option></select></label><label>Мова голосу<select name="language">${data.languages.map(l=>`<option value="${l.code}" ${l.code===s.language?'selected':''}>${esc(l.name)}</option>`).join('')}</select></label>
      <label data-provider="elevenlabs">Модель<select name="model">${data.models.map(m=>`<option value="${m.id}" ${m.id===s.model?'selected':''}>${esc(m.name)}</option>`).join('')}</select></label>
      <label data-provider="heygen">Модель<select name="heygen_model">${(data.heygen_models||[]).map(m=>`<option value="${m.id}" ${m.id===s.heygen_model?'selected':''}>${esc(m.name.replace(/^HeyGen /,''))}</option>`).join('')}</select></label><label data-provider="fishaudio">Модель<select name="fish_engine">${data.fish_models.map(m=>`<option value="${m.id}" ${m.id===s.fish_engine?'selected':''}>${esc(m.name)}</option>`).join('')}</select></label>
      <label data-provider="elevenlabs">Подача<select name="delivery">${[['conversational','Розмовна'],['neutral','Як у записі'],['calm','Спокійна']].map(([k,v])=>`<option value="${k}" ${k===s.delivery?'selected':''}>${v}</option>`).join('')}</select></label></div>

      <div class="voice-lab-source"><h4>Приклад голосу</h4><div class="voice-lab-reference"><span class="voice-lab-reference-player"></span><label class="secondary voice-lab-upload" ${data.reference?'hidden':''}>Додати аудіо або відео<input type="file" accept="audio/*,video/*" hidden></label>${data.reference?`<button type="button" class="voice-lab-remove" aria-label="Прибрати приклад голосу">${trashIcon}</button>`:''}</div>
      <small class="voice-lab-preparation-status" ${data.reference?.cleanup_applied?'':'hidden'}>Вибрано очищену версію</small><div class="voice-lab-prepared"></div></div>
      <div class="voice-lab-identity" data-provider="heygen"><div class="voice-lab-identity-heading"><h4>Голос HeyGen</h4><span class="voice-lab-identity-state"></span></div><div class="voice-lab-identity-actions"><button type="button" class="secondary heygen-load-voices">Вибрати голос</button><button type="button" class="secondary heygen-create-voice">Створити із запису</button></div><select class="heygen-voice-list" aria-label="Голос HeyGen" hidden></select><details class="voice-lab-advanced"><summary>Ввести ID вручну</summary><label>ID голосу<input name="heygen_voice_id" value="${esc(s.heygen_voice_id||'')}" placeholder="ID голосу з вашого акаунта" autocomplete="off" spellcheck="false"></label></details></div>
      <div class="voice-lab-tuning">
      <div class="voice-lab-sliders"><label>Швидкість · у студії<span><input name="speed" type="range" min="90" max="110" step="1" value="${Math.max(90,Math.min(110,Math.round((s.speed??1)*100)))}"><output>${Math.max(90,Math.min(110,Math.round((s.speed??1)*100)))}%</output></span></label></div><div class="voice-lab-sliders" data-provider="elevenlabs">${[['stability','Стабільність'],['similarity_boost','Схожість із записом']].map(([k,v])=>`<label>${v}<span><input name="${k}" type="range" min="0" max="100" step="5" value="${Math.round(s[k]*100)}"><output>${Math.round(s[k]*100)}%</output></span></label>`).join('')}</div>
      <div class="voice-lab-sliders" data-provider="heygen"><label>Виразність<span><input name="heygen_expressiveness" type="range" min="0" max="100" step="5" value="${Math.round((s.heygen_expressiveness??.5)*100)}"><output>${Math.round((s.heygen_expressiveness??.5)*100)}%</output></span><small>Від стриманої до виразнішої подачі. Для нового зразка instant-голосу.</small></label></div>
      <div class="voice-lab-sliders" data-provider="fishaudio">${[['temperature','Виразність'],['top_p','Варіативність']].map(([k,v])=>`<label>${v}<span><input name="${k}" type="range" min="0" max="100" step="5" value="${Math.round(s[k]*100)}"><output>${Math.round(s[k]*100)}%</output></span></label>`).join('')}</div>
      </div><label class="voice-lab-direction" data-provider="elevenlabs">Побажання до подачі<input name="direction" type="text" maxlength="160" value="${esc(s.direction)}" placeholder="Спокійно, тепло, без дикторської подачі"><small>Необов’язково. Якщо заповнено, застосовується замість вибраної подачі.</small></label>
      <label class="voice-lab-text">Текст зразка<textarea rows="3" maxlength="2000">${esc(s.text)}</textarea></label>
      <div class="voice-lab-actions"><button type="button" class="secondary voice-lab-listen"></button><button type="button" class="secondary voice-lab-save">Зберегти голос</button></div>
      <div class="voice-lab-status" role="status" aria-live="polite"></div><div class="voice-lab-result"></div>`;
    if(data.reference)box.querySelector('.voice-lab-reference-player').replaceChildren(voicePlayer(null,`${base}/reference?v=${data.reference.stamp}`,{filename:data.reference.filename,playLabel:'Відтворити приклад голосу'}));
    else box.querySelector('.voice-lab-reference-player').textContent='Приклад для клонування';

    box.querySelector('.heygen-load-voices').onclick=async()=>{try{const result=await api(base+'/heygen-voices');const select=box.querySelector('.heygen-voice-list');select.innerHTML='<option value="">Оберіть голос</option>'+result.voices.map(v=>`<option value="${esc(v.voice_id)}">${esc(v.name||v.voice_id)} · ${esc(v.mode||'')}</option>`).join('');select.hidden=false;select.onchange=()=>{box.querySelector('[name=heygen_voice_id]').value=select.value;clearSample();estimate();};}catch(error){message(error.message,true);}};
    box.querySelector('.heygen-create-voice').onclick=async(event)=>{const button=event.currentTarget;button.disabled=true;message('Готуємо запис і створюємо instant-голос HeyGen…');try{data=await api(base+'/heygen-clone','POST',{settings:read()});draw();message('Голос створено й вибрано. HeyGen може готувати його кілька секунд, після цього можна прослухати зразок.');}catch(error){message(error.message,true);button.disabled=false;}};
    signature=settingsKey(read());
    box.saveVoiceSettings=async()=>{data=await api(base,'POST',{settings:read()});return data;};
    box.querySelectorAll('select,input:not([type=file]),textarea').forEach(input=>input.addEventListener('input',()=>{clearSample();message('Налаштування змінено. Створіть зразок із цими параметрами.');estimate();}));
    box.querySelector('.voice-lab-save').addEventListener('click',async()=>{try{data=await api(base,'POST',{settings:read()});draw();message('Налаштування голосу збережено.');}catch(error){message(error.message,true);}});
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
      const button=box.querySelector('.voice-lab-listen');button.disabled=true;
      try{
        data=await api(base+'/sample','POST',{settings:read(),client_id:crypto.randomUUID()});
        signature=settingsKey(data.settings);sample();
        if(data.job?.status==='running')timer=setTimeout(poll,1000);
        else playSample();
      }catch(error){message(error.message,true);estimate();}
    });
    sample();
    if(data.job?.status==='running')timer=setTimeout(poll,1500);
  };
  try{data=await api(base);draw();}catch(error){box.innerHTML=`<h3>Голос</h3><p>${esc(error.message)}</p>`;}
}
