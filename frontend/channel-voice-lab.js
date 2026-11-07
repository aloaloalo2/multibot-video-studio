// Original voice trial. Upload is local; a paid request starts only from Listen.
// Compare the parameters that actually reach the selected service.
function voiceLabSampleKey(s){
  const fields=['provider','language','text',...(s.provider==='fishaudio'?['fish_engine','temperature','top_p']:['model','delivery','stability','similarity_boost'])];
  return JSON.stringify(fields.map(k=>[k,s[k]]));
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
  if(channel.id!=='b012a0e49c3b1c18')return;
  const box=document.createElement('section');box.className='settings-section channel-voice-lab';
  box.innerHTML='<h3>Голос <small>Тест</small></h3><p role="status">Завантажуємо налаштування…</p>';
  document.querySelector('.logo-section').after(box);
  const base=`/api/channels/${channel.id}/voice-lab`;
  let data,signature='',timer;
  const current=()=>box.isConnected;
  const settingsKey=value=>JSON.stringify(Object.entries(value).sort(([a],[b])=>a.localeCompare(b)));
  const read=()=>({provider:box.querySelector('[name=provider]').value,fish_engine:box.querySelector('[name=fish_engine]').value,
    temperature:Number(box.querySelector('[name=temperature]').value)/100,top_p:Number(box.querySelector('[name=top_p]').value)/100,language:box.querySelector('[name=language]').value,model:box.querySelector('[name=model]').value,
    delivery:box.querySelector('[name=delivery]').value,stability:Number(box.querySelector('[name=stability]').value)/100,
    similarity_boost:Number(box.querySelector('[name=similarity_boost]').value)/100,text:box.querySelector('textarea').value.trim()});
  const clearSample=()=>voiceLabClearSample(box.querySelector('.voice-lab-result'));
  const playSample=()=>{const selected=box.querySelector('.voice-lab-result audio');if(!selected)return;document.querySelectorAll('.voice-player audio').forEach(other=>{if(other!==selected)other.pause();});selected.play().catch(()=>{});};
  const message=(text,error=false)=>{const el=box.querySelector('.voice-lab-status');if(el){el.textContent=text;el.classList.toggle('error',error);}};
  const estimate=()=>{
    const settings=read(),fish=settings.provider==='fishaudio',rate=settings.model==='eleven_v4_turbo'?.26:.5;
    const same=settingsKey(settings)===signature;
    const {cached}=voiceLabSampleState(settings,data);
    const count=[...settings.text].length+(settings.delivery==='neutral'?0:settings.delivery==='calm'?22:28);
    const fishRate=data.fish_models.find(m=>m.id===settings.fish_engine)?.rate||0;
    const usd=new TextEncoder().encode(settings.text).length*fishRate;
    const price=fish?(usd?`≈ $${usd.toFixed(4)}`:'безкоштовно'):`≈ ${Math.ceil(count*rate).toLocaleString('uk-UA')} кредитів`;
    box.querySelectorAll('[data-provider]').forEach(el=>{el.hidden=el.dataset.provider!==settings.provider;});
    box.querySelector('.voice-lab-listen').innerHTML=`${playIcon}<span>${data.job?.status==='running'?'Створюємо зразок…':cached?'Відтворити зразок · безкоштовно':`Створити зразок · ${price}`}</span>`;
    box.querySelector('.voice-lab-listen').disabled=!data.reference||data.job?.status==='running';
    box.querySelector('.voice-lab-save').disabled=same;
    box.querySelectorAll('input[type=range]').forEach(input=>{input.nextElementSibling.textContent=input.value+'%';});
  };
  const sample=()=>{
    const output=box.querySelector('.voice-lab-result');clearSample();
    const {matches}=voiceLabSampleState(read(),data);
    if(data.job?.status==='done'&&matches){
      const player=voicePlayer(null,`${base}/sample?key=${data.job.fingerprint}`,{filename:'Зразок голосу.mp3',playLabel:'Відтворити зразок голосу'});
      output.append(player);
      const used=data.job.settings||data.settings;
      const caption=document.createElement('small');caption.textContent=used.provider==='elevenlabs'?`Стабільність ${Math.round(used.stability*100)}% · Схожість ${Math.round(used.similarity_boost*100)}%`:`Виразність ${Math.round(used.temperature*100)}% · Варіативність ${Math.round(used.top_p*100)}%`;output.append(caption);
      message(data.job.cached?'Зразок із кешу. Повторної оплати немає.':'Зразок готовий. Можна прослухати та змінити налаштування.');
    }else if(data.job?.status==='failed')message(data.job.error||'Не вдалося створити зразок',true);
    else if(data.job?.status==='running'){
      const state=box.querySelector('.voice-lab-status');state.innerHTML=`${exportSpinner}<span>${data.job.stage==='reference'?'Розпізнаємо приклад для Fish Audio':data.job.stage==='clone'?'Готуємо клон голосу':'Озвучуємо зразок'}…</span>`;
    }else if(!matches&&data.job?.status==='done')message('Налаштування змінено. Створіть новий зразок, щоб почути результат.');
    estimate();
  };
  const poll=async()=>{
    if(!current())return;
    try{const wasRunning=data.job?.status==='running';data=await api(base);if(!current())return;sample();if(data.job?.status==='running')timer=setTimeout(poll,1600);else if(wasRunning&&data.job?.status==='done')playSample();}
    catch(error){message(error.message,true);}
  };
  const draw=()=>{
    if(!current())return;
    const s=data.settings;
    box.innerHTML=`<h3>Голос <small>Тест</small></h3><p>Власний голос зі звичайною розмовною подачею. Налаштуйте й послухайте до 4 речень.</p>
      <div class="voice-lab-reference"><span class="voice-lab-reference-player"></span><label class="secondary voice-lab-upload">${data.reference?'Замінити запис':'Додати аудіо або відео'}<input type="file" accept="audio/*,video/*" hidden></label>${data.reference?`<button type="button" class="voice-lab-remove" aria-label="Прибрати приклад голосу">${trashIcon}</button>`:''}</div>
      <div class="settings-three-column"><label>Сервіс<select name="provider"><option value="elevenlabs" ${s.provider==='elevenlabs'?'selected':''}>ElevenLabs</option><option value="fishaudio" ${s.provider==='fishaudio'?'selected':''}>Fish Audio</option></select></label><label>Мова голосу<select name="language">${data.languages.map(l=>`<option value="${l.code}" ${l.code===s.language?'selected':''}>${esc(l.name)}</option>`).join('')}</select></label>
      <label data-provider="elevenlabs">Модель<select name="model">${data.models.map(m=>`<option value="${m.id}" ${m.id===s.model?'selected':''}>${esc(m.name)}</option>`).join('')}</select></label>
      <label data-provider="fishaudio">Модель<select name="fish_engine">${data.fish_models.map(m=>`<option value="${m.id}" ${m.id===s.fish_engine?'selected':''}>${esc(m.name)}</option>`).join('')}</select></label>
      <label data-provider="elevenlabs">Подача<select name="delivery">${[['conversational','Розмовна'],['neutral','Як у записі'],['calm','Спокійна']].map(([k,v])=>`<option value="${k}" ${k===s.delivery?'selected':''}>${v}</option>`).join('')}</select></label></div>
      <div class="voice-lab-sliders" data-provider="elevenlabs">${[['stability','Стабільність'],['similarity_boost','Схожість із записом']].map(([k,v])=>`<label>${v}<span><input name="${k}" type="range" min="0" max="100" step="5" value="${Math.round(s[k]*100)}"><output>${Math.round(s[k]*100)}%</output></span></label>`).join('')}</div>
      <div class="voice-lab-sliders" data-provider="fishaudio">${[['temperature','Виразність'],['top_p','Варіативність']].map(([k,v])=>`<label>${v}<span><input name="${k}" type="range" min="0" max="100" step="5" value="${Math.round(s[k]*100)}"><output>${Math.round(s[k]*100)}%</output></span></label>`).join('')}</div>
      <label class="voice-lab-text">Текст зразка · до 4 речень<textarea rows="3" maxlength="2000">${esc(s.text)}</textarea></label>
      <div class="voice-lab-actions"><button type="button" class="secondary voice-lab-listen"></button><button type="button" class="secondary voice-lab-save">Зберегти голос</button></div>
      <div class="voice-lab-status" role="status" aria-live="polite"></div><div class="voice-lab-result"></div>`;
    if(data.reference)box.querySelector('.voice-lab-reference-player').replaceChildren(voicePlayer(null,`${base}/reference?v=${data.reference.stamp}`,{filename:data.reference.filename,playLabel:'Відтворити приклад голосу'}));
    else box.querySelector('.voice-lab-reference-player').textContent='Приклад для клонування';
    signature=settingsKey(read());
    box.saveVoiceSettings=async()=>{data=await api(base,'POST',{settings:read()});return data;};
    box.querySelectorAll('select,input[type=range],textarea').forEach(input=>input.addEventListener('input',()=>{clearSample();message('Налаштування змінено. Створіть зразок із цими параметрами.');estimate();}));
    box.querySelector('.voice-lab-save').addEventListener('click',async()=>{try{data=await api(base,'POST',{settings:read()});draw();message('Налаштування голосу збережено.');}catch(error){message(error.message,true);}});
    box.querySelector('.voice-lab-remove')?.addEventListener('click',async()=>{try{data=await api(base+'/reference/remove','POST',{});draw();}catch(error){message(error.message,true);}});
    box.querySelector('input[type=file]').addEventListener('change',async event=>{
      const file=event.target.files[0];if(!file)return;
      const label=event.target.closest('label');label.classList.add('is-off');message('Завантажуємо запис і готуємо MP3…');
      try{
        await api(base,'POST',{settings:read()});
        const response=await fetch(base+'/reference',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-File-Name':encodeURIComponent(file.name)},body:file});
        const result=await response.json();if(!response.ok)throw new Error(result.error||'Не вдалося завантажити запис');
        data=result;draw();message('Запис збережено. Можна створити зразок у вибраному сервісі.');
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
