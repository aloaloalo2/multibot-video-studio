function channelSoundMarkup(){
  // three rows with a switch each and nothing to read (user, 26 November 2026: «просто хай будуть перемикачі… мінімалістичніше…
  // без оцих пояснювань»); a row opens to its list
  const sw=(id,label,extra='')=>`<label class="logo-switch sound-switch"><input id="${id}" type="checkbox" role="switch" aria-label="${label}"${extra}><span aria-hidden="true"></span></label>`;
  return `<section class="settings-section settings-sound"><h3 hidden>Музика й ефекти</h3>
    <div hidden><input id="sound-generate" type="checkbox"><span class="channel-sound-generate"></span><small id="sound-music-note"></small>
      <div class="channel-music-styles" id="music-styles"><div class="channel-sound-categories"></div></div>
      <input id="sound-effects" type="checkbox"><input id="sound-library" type="checkbox"><small id="sound-effect-count"></small><small id="sound-library-count"></small></div>
    <div class="sound-row">
      <details class="channel-sound-group channel-sound-music-library"><summary><span>Музика</span><small id="music-library-count"></small></summary>
        <div id="music-library" class="channel-music-library"></div>
      </details>${sw('sound-music','Музика')}
    </div>
    <div class="sound-row">
      <details class="channel-sound-group channel-sound-sfx"><summary><span>SFX</span><small id="sound-sfx-count"></small></summary>
        <div id="sound-categories" class="channel-sound-categories"></div>
        <div id="animation-sfx-library" class="channel-sound-categories"></div>
      </details>${sw('sound-sfx','SFX')}
    </div>
    <div class="sound-row regular-only">
      <details class="channel-sound-group"><summary><span>Звуки переходів</span><small id="sound-transition-count"></small></summary>
        <div id="transition-categories" class="channel-sound-categories"></div>
      </details>${sw('sound-transitions','Звуки переходів',' disabled')}
    </div>
  </section>`;
}
// The sound catalogue is the same for every channel and only changes with a studio update: one read per page,
// shared by every opening of the settings (107 KB and about 0.5 s each time before, 25 November 2026)
let channelSoundCatalogRead=null;
function channelSoundCatalog(){
  channelSoundCatalogRead ||= api('/api/sound-effects').catch(error=>{channelSoundCatalogRead=null;throw error;});
  return channelSoundCatalogRead;
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
  // one switch (user, 26 November 2026: «або ми генеруємо музику, або ні»): on is a score generated for each film, its sound,
  // mood, key and tempo picked by the studio for that film and never the channel's last ones (soundtrack.music_pick)
  music.checked=(saved?.music?.enabled??true)&&(saved?.music?.generate??true);generate.checked=music.checked;
  music.addEventListener('change',()=>{generate.checked=music.checked;});
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
  const stop=()=>{root.pauseMusicTrack?.();if(sample){sample.pause();sample.remove();sample=null;}root.querySelectorAll('.sound-preview').forEach(b=>{b.classList.remove('playing');b.setAttribute('aria-pressed','false');});};
  function update(){
    generate.checked=music.checked;root.querySelector('.channel-sound-generate').hidden=true;
    root.querySelector('.channel-sound-generate').classList.toggle('muted',!music.checked);
    root.querySelector('#sound-music-note').textContent=music.checked?'Своя музика для кожного ролика.':'Без фонової музики.';
    const ticked=[...root.querySelectorAll('#music-library input:checked')].map(input=>input.value);
    root.soundValue.music={enabled:music.checked,generate:music.checked,...(root.musicLibraryReady?{tracks:ticked}:saved?.music?.tracks?{tracks:[...saved.music.tracks]}:{})};
    if(root.musicLibraryReady)root.querySelector('#music-library-count').textContent=music.checked?`${ticked.length} з ${root.querySelectorAll('#music-library input').length}`:'';
    root.querySelector('#music-library').classList.toggle('sound-off',!music.checked);
    styles.hidden=true;
    for(const group of groups){
      const inputs=[...group.list.querySelectorAll('input')],selected=inputs.filter(i=>i.checked);
      inputs.forEach(input=>input.disabled=!group.toggle.checked||(group.key==='library'&&!root.librarySoundsReady));
      group.list.hidden=!group.toggle.checked;
      group.count.textContent=group.toggle.checked&&inputs.length?`${selected.length} з ${inputs.length}`:'';
      root.soundValue[group.key].enabled=group.toggle.checked;
      if(group.key==='effects')root.soundValue.effects.version=2;   // today's SFX list: an unticked new sound stays unticked
      if(inputs.length)root.soundValue[group.key][group.field]=[...selected.map(i=>i.value),...(group.unavailableChoices||[])];
    }
    const sfxInputs=[...root.querySelectorAll('#sound-categories input,#animation-sfx-library input')];
    root.querySelector('#sound-sfx-count').textContent=root.querySelector('#sound-sfx').checked&&sfxInputs.length?`${sfxInputs.filter(i=>i.checked).length} з ${sfxInputs.length}`:'';
  }
  // one SFX switch for the synthesized sounds and the files (user, 21 November 2026: «ефекти акцентів це те саме, що SFX
  // для анімації… розділяти не потрібно»)
  const sfxToggle=root.querySelector('#sound-sfx'),effectsToggle=root.querySelector('#sound-effects'),libraryToggle=root.querySelector('#sound-library');
  sfxToggle.checked=effectsToggle.checked||libraryToggle.checked;
  sfxToggle.addEventListener('change',()=>{effectsToggle.checked=sfxToggle.checked;if(!libraryToggle.disabled)libraryToggle.checked=sfxToggle.checked;update();});
  for(const control of [music,generate,...groups.map(g=>g.toggle)])control.addEventListener('change',update);
  update();
  channelSoundCatalog().then(data=>{
    if(!root.isConnected)return;
    root.transitionSoundsReady=Array.isArray(data.transitions);
    root.musicStylesReady=false;   // no list of sounds to choose from: the studio picks one for each film
    // «Стиль музики»: the channel's generated score, heard before choosing (user, 17 November 2026)
    const choose=value=>{musicChoice=value;music.checked=value!=='none';generate.checked=value!=='none'&&value!=='own';if(value!=='none'&&value!=='own')musicStyle=value;update();};
    const rows=[];   // the list of sounds is gone (26 November 2026): one switch, the studio picks the sound per film
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
    styles.hidden=true;
    // «Музична бібліотека»: the studio's tracks from the YouTube Audio Library, ticked for the channel (26 November 2026)
    const PLAY='<svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path d="m7 4 9 6-9 6Z"/></svg>',PAUSE='<svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path d="M6 4h3v12H6zM11 4h3v12h-3z"/></svg>';
    const clock=seconds=>{const s=Math.max(0,Math.round(Number(seconds)||0));return `${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`;};
    let track=null;   // {id, audio, play, time, seconds}
    const paint=(item,playing)=>{item.play.innerHTML=playing?PAUSE:PLAY;item.play.classList.toggle('playing',playing);item.play.setAttribute('aria-pressed',String(playing));
      item.time.textContent=playing||item.audio.currentTime>0?`${clock(item.audio.currentTime)} / ${clock(item.seconds)}`:clock(item.seconds);
      if(!item.seeking)item.seek.value=String(item.audio.currentTime||0);};
    const dropTrack=()=>{if(!track)return;track.audio.pause();track.audio.removeAttribute('src');track.audio.load();track.play.innerHTML=PLAY;track.play.classList.remove('playing');track.play.setAttribute('aria-pressed','false');track.time.textContent=clock(track.seconds);track.audio.remove();track.seek.remove();track.play.parentElement.classList.remove('active');track=null;};
    async function toggleTrack(row,play,time){
      if(track?.id===row.id){if(track.audio.paused){stop();try{await track.audio.play();}catch{status('Не вдалося прослухати трек.',true);}}else track.audio.pause();return;}
      dropTrack();stop();
      const audio=new Audio(row.preview_url);audio.volume=.5;audio.preload='auto';audio.hidden=true;play.parentElement.append(audio);   // in the dialog, so closing it pauses the track
      // a seek bar under the playing track, to hear its middle or end (user, 26 November 2026: «додай перемотку… музика довга»)
      const seek=document.createElement('input');seek.type='range';seek.className='music-seek';seek.min='0';seek.max=String(row.seconds||0);seek.step='0.1';seek.value='0';seek.setAttribute('aria-label',`Перемотати: ${row.title}`);
      play.parentElement.append(seek);play.parentElement.classList.add('active');   // the chosen track stays lit, playing or paused
      const item={id:row.id,audio,play,time,seek,seconds:row.seconds,seeking:false};track=item;
      audio.addEventListener('loadedmetadata',()=>{if(Number.isFinite(audio.duration))seek.max=String(audio.duration);});
      seek.addEventListener('input',()=>{item.seeking=true;time.textContent=`${clock(seek.value)} / ${clock(item.seconds)}`;});
      seek.addEventListener('change',()=>{audio.currentTime=Number(seek.value);item.seeking=false;paint(item,!audio.paused);});
      audio.addEventListener('play',()=>paint(item,true));audio.addEventListener('pause',()=>paint(item,false));
      audio.addEventListener('timeupdate',()=>{if(!audio.paused)paint(item,true);});
      audio.addEventListener('ended',()=>{audio.currentTime=0;paint(item,false);});
      try{await audio.play();}catch{if(track===item){dropTrack();status('Не вдалося прослухати трек.',true);}}
    }
    root.stopMusicTrack=dropTrack;
    root.pauseMusicTrack=()=>{if(track&&!track.audio.paused)track.audio.pause();};
    const musicList=root.querySelector('#music-library');
    if(Array.isArray(data.music_library)){
      root.musicLibraryReady=true;
      const chosen=new Set(saved?.music?.tracks||[]);let heading=null;
      for(const row of data.music_library){
        if(row.category!==heading){heading=row.category;const head=document.createElement('div');head.className='channel-sound-source';head.textContent=heading[0].toUpperCase()+heading.slice(1);musicList.append(head);}
        // one list, a track a row; the button plays and pauses and keeps the place (user, 26 November 2026: «як один
        // блок, і щоб плей-пауза… працювали»)
        const item=document.createElement('div');item.className='music-track';
        const label=document.createElement('label');label.className='check';
        const input=document.createElement('input');input.type='checkbox';input.value=row.id;input.checked=chosen.has(row.id);
        const name=document.createElement('span');name.className='music-track-name';name.textContent=row.title;
        const artist=document.createElement('small');artist.textContent=row.artist;
        const time=document.createElement('small');time.className='music-track-time';time.textContent=clock(row.seconds);
        label.append(input,name,artist);input.addEventListener('change',update);
        const play=document.createElement('button');play.type='button';play.className='sound-preview';play.setAttribute('aria-label',`Прослухати: ${row.title}`);play.setAttribute('aria-pressed','false');play.innerHTML=PLAY;
        play.addEventListener('click',()=>toggleTrack(row,play,time));
        item.append(label,time,play);musicList.append(item);
      }
      if(!data.music_library.length)musicList.textContent='Бібліотека музики ще порожня.';
    }
    root.librarySoundsReady=data.library_selection===true&&Array.isArray(data.library);
    for(const group of groups){
      const rows=data[group.key==='effects'?'categories':group.key];
      if(!Array.isArray(rows)){group.list.textContent='Доступно після оновлення студії.';continue;}
      group.toggle.disabled=group.key==='library'&&!root.librarySoundsReady;
      if(group.key==='library'){
        const present=new Set(rows.map(row=>row.mixkit_id));
        group.unavailableChoices=(saved?.library?.ids||[]).filter(id=>!present.has(id));
      }
      let lastSource=null;
      for(const row of rows){
        // CapCut's trending sounds get their own heading under the studio's own SFX (25 November 2026)
        if((group.key==='library'||group.key==='transitions')&&row.source_group&&row.source_group!==lastSource){
          if(lastSource!==null||row.source_group.startsWith('capcut')){const head=document.createElement('div');head.className='channel-sound-source';head.textContent=({capcut:'CapCut · У тренді','capcut-pencil':'CapCut · Олівець і крейда'})[row.source_group]||'Добірка студії';group.list.append(head);}
          lastSource=row.source_group;
        }
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
          const audio=document.createElement('audio');audio.src=row.preview_url;audio.volume=.6;sample=audio;   // every SFX is levelled to one loudness, so one player volume
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
