function channelSoundMarkup(){
  return `<section class="settings-section settings-sound"><h3 hidden>Музика й ефекти</h3>
    <div class="channel-sound-music">
      <label class="check"><input id="sound-music" type="checkbox">Використовувати музику</label>
      <label class="check channel-sound-generate"><input id="sound-generate" type="checkbox">Створювати фонову музику</label>
      <small id="sound-music-note"></small>
    </div>
    <details class="channel-sound-group"><summary><span>Ефекти акцентів</span><small id="sound-effect-count"></small></summary>
      <label class="check"><input id="sound-effects" type="checkbox">Використовувати для акцентів</label>
      <div id="sound-categories" class="channel-sound-categories"></div>
      <p class="channel-sound-note">Поява елементів, числа, підписи та інші акценти всередині кадру.</p>
    </details>
    <details class="channel-sound-group regular-only"><summary><span>Звуки переходів</span><small id="sound-transition-count"></small></summary>
      <label class="check"><input id="sound-transitions" type="checkbox" disabled>Використовувати на стиках</label>
      <div id="transition-categories" class="channel-sound-categories"></div>
      <p class="channel-sound-note">Режисер обирає доречні переходи й чергує позначені звуки. М’які склейки переважно залишаються тихими.</p>
    </details>
    <details class="channel-sound-group"><summary><span>SFX для анімацій</span><small>Добірка Mixkit</small></summary>
      <p class="channel-sound-note">Ці звуки використовуються в нових анімаціях і показуються окремими кліпами на доріжці SFX. Дозволені для YouTube з монетизацією.</p>
      <div id="animation-sfx-library" class="channel-sound-categories"></div>
    </details>
  </section>`;
}
function bindChannelSound(saved){
  const root=document.querySelector('.settings-sound');
  const music=root.querySelector('#sound-music'),generate=root.querySelector('#sound-generate');
  music.checked=saved?.music?.enabled??true;generate.checked=saved?.music?.generate??true;
  const groups=[
    {key:'effects',field:'categories',toggle:root.querySelector('#sound-effects'),list:root.querySelector('#sound-categories'),count:root.querySelector('#sound-effect-count'),defaultOn:true},
    {key:'transitions',field:'styles',toggle:root.querySelector('#sound-transitions'),list:root.querySelector('#transition-categories'),count:root.querySelector('#sound-transition-count'),defaultOn:false}
  ];
  root.soundValue={music:{enabled:music.checked,generate:generate.checked}};
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
    root.soundValue.music={enabled:music.checked,generate:generate.checked};
    for(const group of groups){
      const inputs=[...group.list.querySelectorAll('input')],selected=inputs.filter(i=>i.checked);
      inputs.forEach(input=>input.disabled=!group.toggle.checked);
      group.list.hidden=!group.toggle.checked;
      group.count.textContent=!group.toggle.checked?'Вимкнено':inputs.length?`${selected.length} звуків`:'';
      root.soundValue[group.key].enabled=group.toggle.checked;
      if(inputs.length)root.soundValue[group.key][group.field]=selected.map(i=>i.value);
    }
  }
  for(const control of [music,generate,...groups.map(g=>g.toggle)])control.addEventListener('change',update);
  update();
  api('/api/sound-effects').then(data=>{
    if(!root.isConnected)return;
    root.transitionSoundsReady=Array.isArray(data.transitions);
    const library=root.querySelector('#animation-sfx-library');
    for(const row of data.library||[]){
      const item=document.createElement('div');item.className='channel-sound-category';
      const label=document.createElement('span');label.textContent=row.label;
      const play=document.createElement('button');play.type='button';play.className='sound-preview';
      play.textContent='▶';play.setAttribute('aria-label','Прослухати '+row.label);play.setAttribute('aria-pressed','false');
      play.addEventListener('click',async()=>{
        const active=play.classList.contains('playing');stop();if(active)return;
        const audio=document.createElement('audio');audio.src=row.preview_url;audio.volume=.3;sample=audio;
        audio.addEventListener('ended',stop,{once:true});audio.addEventListener('error',stop,{once:true});
        play.classList.add('playing');play.setAttribute('aria-pressed','true');
        try{await audio.play();}catch(error){stop();status('Не вдалося прослухати звук.',true);}
      });item.append(label,play);library.append(item);
    }
    if(!data.library?.length)library.textContent='Добірка SFX ще не імпортована.';
    for(const group of groups){
      const rows=data[group.key==='effects'?'categories':'transitions'];
      if(!Array.isArray(rows)){group.list.textContent='Доступно після оновлення студії.';continue;}
      group.toggle.disabled=false;
      for(const row of rows){
        const item=document.createElement('div');item.className='channel-sound-category';
        const label=document.createElement('label');label.className='check';
        const input=document.createElement('input');input.type='checkbox';input.value=row.id;
        const choices=saved?.[group.key]?.[group.field];input.checked=!choices||choices.includes(row.id);
        label.append(input,document.createTextNode(row.label));input.addEventListener('change',update);
        const play=document.createElement('button');play.type='button';play.className='sound-preview';play.setAttribute('aria-label',`Прослухати: ${row.label}`);play.setAttribute('aria-pressed','false');play.innerHTML='<svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path d="m7 4 9 6-9 6Z"/></svg>';
        play.addEventListener('click',async()=>{
          const wasPlaying=play.classList.contains('playing');stop();if(wasPlaying)return;
          const audio=document.createElement('audio');audio.src=row.preview_url;audio.volume=.65;sample=audio;
          audio.hidden=true;item.append(audio);audio.onended=()=>{stop();audio.remove();};
          play.classList.add('playing');play.setAttribute('aria-pressed','true');
          try{await audio.play();}catch(error){stop();audio.remove();status('Не вдалося прослухати звук.',true);}
        });item.append(label,play);group.list.append(item);
      }
    }update();
  }).catch(()=>{if(root.isConnected)groups.forEach(g=>g.list.textContent='Категорії звуку стануть доступні після оновлення студії.');});
}
function channelSoundValues(){
  const root=document.querySelector('.settings-sound'),value={...root.soundValue};
  if(!root.transitionSoundsReady)delete value.transitions;
  return value;
}
