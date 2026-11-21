function channelSoundMarkup(){
  return `<section class="settings-section settings-sound"><h3 hidden>Музика й ефекти</h3>
    <div class="channel-sound-music">
      <div hidden><label class="check"><input id="sound-music" type="checkbox">Використовувати музику</label>
      <label class="check channel-sound-generate"><input id="sound-generate" type="checkbox">Створювати фонову музику</label>
      <small id="sound-music-note"></small></div>
      <div class="channel-music-styles" id="music-styles" role="radiogroup" aria-label="Фонова музика"><span class="channel-music-styles-title">Фонова музика</span><small class="channel-music-styles-note">Музика змінюється разом із настроєм розповіді; вибір задає, якими інструментами вона звучить. «М’який фон» і «Глибокий фон» без дзвінких нот.</small><div class="channel-sound-categories"></div></div>
    </div>
    <details class="channel-sound-group channel-sound-sfx"><summary><span>SFX</span><small id="sound-sfx-count"></small></summary>
      <label class="check"><input id="sound-sfx" type="checkbox">Використовувати SFX</label>
      <input id="sound-effects" type="checkbox" hidden><input id="sound-library" type="checkbox" hidden><small id="sound-effect-count" hidden></small><small id="sound-library-count" hidden></small>
      <p class="channel-sound-note">Одна добірка для акцентів і анімацій: звуки моушн-дизайну на появу, обертання, кліки, накручування тексту. Кожен звук звучить цілим, до 4 с, гучність вирівняна.</p>
      <div id="sound-categories" class="channel-sound-categories"></div>
      <div id="animation-sfx-library" class="channel-sound-categories"></div>
    </details>
    <details class="channel-sound-group regular-only"><summary><span>Звуки переходів</span><small id="sound-transition-count"></small></summary>
      <label class="check"><input id="sound-transitions" type="checkbox" disabled>Використовувати на стиках</label>
      <div id="transition-categories" class="channel-sound-categories"></div>
      <p class="channel-sound-note">Режисер обирає доречні переходи й чергує позначені звуки. М’які склейки переважно залишаються тихими.</p>
    </details>
  </section>`;
}
function bindChannelSound(saved){
  const root=document.querySelector('.settings-sound');
  const music=root.querySelector('#sound-music'),generate=root.querySelector('#sound-generate');
  music.checked=saved?.music?.enabled??true;generate.checked=saved?.music?.generate??true;
  const groups=[
    {key:'effects',field:'categories',toggle:root.querySelector('#sound-effects'),list:root.querySelector('#sound-categories'),count:root.querySelector('#sound-effect-count'),defaultOn:true},
    {key:'transitions',field:'styles',toggle:root.querySelector('#sound-transitions'),list:root.querySelector('#transition-categories'),count:root.querySelector('#sound-transition-count'),defaultOn:false},
    {key:'library',field:'ids',toggle:root.querySelector('#sound-library'),list:root.querySelector('#animation-sfx-library'),count:root.querySelector('#sound-library-count'),defaultOn:saved?.effects?.enabled??true}
  ];
  let musicStyle=saved?.music?.style||'whatif';
  // one choice instead of two checkboxes (user, 17 November 2026): «Без музики», a synthesizer, or the channel's own track
  let musicChoice=!music.checked?'none':!generate.checked?'own':musicStyle;
  const styles=root.querySelector('#music-styles');
  root.soundValue={music:{enabled:music.checked,generate:generate.checked,style:musicStyle}};
  for(const group of groups){
    group.toggle.checked=saved?.[group.key]?.enabled??group.defaultOn;
    const choices=saved?.[group.key]?.[group.field];
    root.soundValue[group.key]={enabled:group.toggle.checked,...(choices?{[group.field]:[...choices]}:{})};
  }
  let sample=null;
  const stop=()=>{if(sample){sample.pause();sample.remove();sample=null;}root.querySelectorAll('.sound-preview').forEach(b=>{b.classList.remove('playing');b.setAttribute('aria-pressed','false');});};
  function update(){
    generate.disabled=!music.checked;root.querySelector('.channel-sound-generate').hidden=!music.checked;
    root.querySelector('.channel-sound-generate').classList.toggle('muted',!music.checked);
    root.querySelector('#sound-music-note').textContent=!music.checked?'Ролик без фонової музики.':generate.checked?'Студія може створити музичний супровід.':'Використовуватиметься лише вже додана музика.';
    root.soundValue.music={enabled:music.checked,generate:generate.checked,...(root.musicStylesReady?{style:musicStyle}:{})};
    styles.hidden=!root.musicStylesReady;
    for(const group of groups){
      const inputs=[...group.list.querySelectorAll('input')],selected=inputs.filter(i=>i.checked);
      inputs.forEach(input=>input.disabled=!group.toggle.checked||(group.key==='library'&&!root.librarySoundsReady));
      group.list.hidden=!group.toggle.checked;
      group.count.textContent=!group.toggle.checked?'Вимкнено':inputs.length?`Обрано: ${selected.length}`:'';
      root.soundValue[group.key].enabled=group.toggle.checked;
      if(group.key==='effects')root.soundValue.effects.version=2;   // today's SFX list: an unticked new sound stays unticked
      if(inputs.length)root.soundValue[group.key][group.field]=[...selected.map(i=>i.value),...(group.unavailableChoices||[])];
    }
    const sfxInputs=[...root.querySelectorAll('#sound-categories input,#animation-sfx-library input')];
    root.querySelector('#sound-sfx-count').textContent=!root.querySelector('#sound-sfx').checked?'Вимкнено':sfxInputs.length?`Обрано: ${sfxInputs.filter(i=>i.checked).length}`:'';
  }
  // one SFX switch for the synthesized sounds and the files (user, 21 November 2026: «ефекти акцентів це те саме, що SFX
  // для анімації… розділяти не потрібно»)
  const sfxToggle=root.querySelector('#sound-sfx'),effectsToggle=root.querySelector('#sound-effects'),libraryToggle=root.querySelector('#sound-library');
  sfxToggle.checked=effectsToggle.checked||libraryToggle.checked;
  sfxToggle.addEventListener('change',()=>{effectsToggle.checked=sfxToggle.checked;if(!libraryToggle.disabled)libraryToggle.checked=sfxToggle.checked;update();});
  for(const control of [music,generate,...groups.map(g=>g.toggle)])control.addEventListener('change',update);
  update();
  api('/api/sound-effects').then(data=>{
    if(!root.isConnected)return;
    root.transitionSoundsReady=Array.isArray(data.transitions);
    root.musicStylesReady=Array.isArray(data.music_styles);
    // «Стиль музики»: the channel's generated score, heard before choosing (user, 17 November 2026)
    const choose=value=>{musicChoice=value;music.checked=value!=='none';generate.checked=value!=='none'&&value!=='own';if(value!=='none'&&value!=='own')musicStyle=value;update();};
    const rows=[{id:'none',label:'Без музики'},...(data.music_styles||[]),...(musicChoice==='own'?[{id:'own',label:'Лише своя музика'}]:[])];
    for(const row of rows){
      const item=document.createElement('div');item.className='channel-sound-category';
      const label=document.createElement('label');label.className='check';
      const input=document.createElement('input');input.type='radio';input.name='music-style';input.value=row.id;input.checked=row.id===musicChoice;
      input.addEventListener('change',()=>choose(row.id));
      label.append(input,document.createTextNode(row.label));
      if(!row.preview_url){item.append(label);styles.lastElementChild.append(item);continue;}
      const play=document.createElement('button');play.type='button';play.className='sound-preview';play.setAttribute('aria-label',`Прослухати: ${row.label}`);play.setAttribute('aria-pressed','false');play.innerHTML='<svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path d="m7 4 9 6-9 6Z"/></svg>';
      play.addEventListener('click',async()=>{
        const wasPlaying=play.classList.contains('playing');stop();if(wasPlaying)return;
        const audio=document.createElement('audio');audio.src=row.preview_url;audio.volume=.5;sample=audio;audio.hidden=true;item.append(audio);
        audio.onended=audio.onerror=()=>{if(sample===audio)stop();audio.remove();};
        play.classList.add('playing');play.setAttribute('aria-pressed','true');
        try{await audio.play();}catch(error){if(sample===audio){stop();status('Не вдалося прослухати музику.',true);}audio.remove();}
      });
      item.append(label,play);styles.lastElementChild.append(item);
    }
    if(!root.musicStylesReady){styles.hidden=true;root.querySelector('.channel-sound-music>div').hidden=false;}   // an older studio: the two checkboxes
    root.librarySoundsReady=data.library_selection===true&&Array.isArray(data.library);
    for(const group of groups){
      const rows=data[group.key==='effects'?'categories':group.key];
      if(!Array.isArray(rows)){group.list.textContent='Доступно після оновлення студії.';continue;}
      group.toggle.disabled=group.key==='library'&&!root.librarySoundsReady;
      if(group.key==='library'){
        const present=new Set(rows.map(row=>row.mixkit_id));
        group.unavailableChoices=(saved?.library?.ids||[]).filter(id=>!present.has(id));
      }
      for(const row of rows){
        const item=document.createElement('div');item.className='channel-sound-category';
        const label=document.createElement('label');label.className='check';
        const input=document.createElement('input');input.type='checkbox';input.value=group.key==='library'?row.mixkit_id:row.id;
        const choices=saved?.[group.key]?.[group.field];
        input.checked=!choices||choices.includes(input.value);
        if(group.key==='library'&&!saved?.library&&saved?.effects?.categories)input.checked=saved.effects.categories.includes(row.category);
        label.append(input,document.createTextNode(row.label));input.addEventListener('change',update);
        const play=document.createElement('button');play.type='button';play.className='sound-preview';play.setAttribute('aria-label',`Прослухати: ${row.label}`);play.setAttribute('aria-pressed','false');play.innerHTML='<svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path d="m7 4 9 6-9 6Z"/></svg>';
        play.addEventListener('click',async()=>{
          const wasPlaying=play.classList.contains('playing');stop();if(wasPlaying)return;
          const audio=document.createElement('audio');audio.src=row.preview_url;audio.volume=.6;   // every SFX is levelled to one loudness, so one player volumesample=audio;
          audio.hidden=true;item.append(audio);
          audio.onended=audio.onerror=()=>{if(sample===audio)stop();audio.remove();};
          play.classList.add('playing');play.setAttribute('aria-pressed','true');
          try{await audio.play();}catch(error){if(sample===audio){stop();status('Не вдалося прослухати звук.',true);}audio.remove();}
        });item.append(label,play);group.list.append(item);
      }
      if(group.key==='library'&&!rows.length)group.list.textContent='Добірка SFX ще не імпортована.';
    }update();
    if(!root.librarySoundsReady)groups.find(g=>g.key==='library').count.textContent='Доступно після оновлення';
  }).catch(()=>{if(root.isConnected)groups.forEach(g=>g.list.textContent='Категорії звуку стануть доступні після оновлення студії.');});
}
function channelSoundValues(){
  const root=document.querySelector('.settings-sound'),value={...root.soundValue};
  if(!root.transitionSoundsReady)delete value.transitions;
  if(!root.librarySoundsReady)delete value.library;
  return value;
}
