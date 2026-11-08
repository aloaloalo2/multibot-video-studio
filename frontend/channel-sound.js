function channelSoundMarkup(){
  return `<section class="settings-section settings-sound"><h3 hidden>Музика й ефекти</h3>
    <div class="channel-sound-music">
      <label class="check"><input id="sound-music" type="checkbox">Використовувати музику</label>
      <label class="check channel-sound-generate"><input id="sound-generate" type="checkbox">Створювати фонову музику</label>
      <small id="sound-music-note"></small>
    </div>
    <div class="channel-sound-effects-head"><label class="check"><input id="sound-effects" type="checkbox">Звукові ефекти</label><span id="sound-effect-count"></span></div>
    <div id="sound-categories" class="channel-sound-categories"></div>
    <p class="channel-sound-note">Короткі звуки на переходах і появі елементів. Позначені варіанти чергуються протягом ролика.</p>
  </section>`;
}
function bindChannelSound(saved){
  const root=document.querySelector('.settings-sound');
  const music=root.querySelector('#sound-music'),generate=root.querySelector('#sound-generate'),effects=root.querySelector('#sound-effects'),list=root.querySelector('#sound-categories');
  music.checked=saved?.music?.enabled??true;generate.checked=saved?.music?.generate??true;effects.checked=saved?.effects?.enabled??true;
  root.soundValue={music:{enabled:music.checked,generate:generate.checked},effects:{enabled:effects.checked,...(saved?.effects?.categories?{categories:[...saved.effects.categories]}:{})}};
  let sample=null;
  const stop=()=>{if(sample){sample.pause();sample.remove();sample=null;}root.querySelectorAll('.sound-preview').forEach(b=>{b.classList.remove('playing');b.setAttribute('aria-pressed','false');});};
  function update(){
    generate.disabled=!music.checked;
    root.querySelector('.channel-sound-generate').classList.toggle('muted',!music.checked);
    root.querySelector('#sound-music-note').textContent=!music.checked?'Ролик без фонової музики.':generate.checked?'Студія може створити музичний супровід.':'Використовуватиметься лише вже додана музика.';
    list.querySelectorAll('input').forEach(input=>input.disabled=!effects.checked);
    list.classList.toggle('muted',!effects.checked);
    const inputs=[...list.querySelectorAll('input')],count=inputs.filter(i=>i.checked).length;
    root.querySelector('#sound-effect-count').textContent=inputs.length?`${effects.checked?count:0} / ${inputs.length}`:'';
    root.soundValue.music={enabled:music.checked,generate:generate.checked};
    root.soundValue.effects.enabled=effects.checked;
    if(inputs.length)root.soundValue.effects.categories=inputs.filter(i=>i.checked).map(i=>i.value);
    if(!effects.checked)stop();
  }
  for(const control of [music,generate,effects])control.addEventListener('change',update);
  update();
  api('/api/sound-effects').then(data=>{
    if(!root.isConnected)return;
    for(const row of data.categories){
      const item=document.createElement('div');item.className='channel-sound-category';
      const label=document.createElement('label');label.className='check';
      const input=document.createElement('input');input.type='checkbox';input.value=row.id;input.checked=!saved?.effects?.categories||saved.effects.categories.includes(row.id);
      label.append(input,document.createTextNode(row.label));input.addEventListener('change',update);
      const play=document.createElement('button');play.type='button';play.className='sound-preview';play.setAttribute('aria-label',`Прослухати: ${row.label}`);play.setAttribute('aria-pressed','false');play.innerHTML='<svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path d="m7 4 9 6-9 6Z"/></svg>';
      play.addEventListener('click',async()=>{
        const wasPlaying=play.classList.contains('playing');stop();if(wasPlaying)return;
        const audio=document.createElement('audio');audio.src=row.preview_url;audio.volume=.65;sample=audio;
        // Mounted media are paused by the settings navigation and modal cleanup.
        audio.hidden=true;item.append(audio);audio.onended=()=>{stop();audio.remove();};
        play.classList.add('playing');play.setAttribute('aria-pressed','true');
        try{await audio.play();}catch(error){stop();audio.remove();status('Не вдалося прослухати звук.',true);}
      });item.append(label,play);list.append(item);
    }update();
  }).catch(()=>{if(root.isConnected)list.textContent='Категорії звуку стануть доступні після оновлення студії.';});
}
function channelSoundValues(){return document.querySelector('.settings-sound').soundValue;}
