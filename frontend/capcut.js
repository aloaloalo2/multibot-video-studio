/* CapCut transitions and effects in the editor (user, 14 November 2026: «Усе додати»).
   The export draws them with engine/capcut_fx.py; the preview shows the same drawing: a seam's transition as a small
   video the server renders on demand (POST /api/projects/<id>/capcut-preview), an overlay effect as a looping VP9 with
   alpha, an effect that changes the picture with a backdrop filter over what lies below. */
const capcutCatalog={transitions:{},effects:{}};
const capcutReady=fetch('/capcut-catalog.json').then(response=>{if(!response.ok)throw new Error('Не вдалося завантажити переходи CapCut');return response.json();}).then(data=>{
  Object.assign(capcutCatalog.transitions,data.transitions);Object.assign(capcutCatalog.effects,data.effects);
  for(const [id,entry] of Object.entries(data.transitions))transitionNames[id]=entry.name;
  if(typeof initTransitionLibrary==='function')initTransitionLibrary();
  if(state.project){renderTimeline();if(state.selectedTransition)renderInspector();}
  return data;
}).catch(error=>status(error.message,true));
function capcutDefaultDuration(type){return Number(capcutCatalog.transitions[type]?.default_duration)||1;}

/* ------------------------------------------------------------------ the seam's transition in the preview */
const capcutPreviews=new Map();   // key -> {state:'loading'|'ready'|'failed', url, video}
let capcutQueue=Promise.resolve();
function capcutJoinKey(join){return [state.project?.id,join.id,join.type,Number(join.seam).toFixed(3),Number(join.duration).toFixed(3),state.project?.revision].join(':');}
function requestCapcutPreview(join){
  const key=capcutJoinKey(join);if(capcutPreviews.has(key))return capcutPreviews.get(key);
  const entry={state:'loading'};capcutPreviews.set(key,entry);const projectId=state.project.id;
  capcutQueue=capcutQueue.then(async()=>{
    if(state.project?.id!==projectId){capcutPreviews.delete(key);return;}
    try{
      const response=await fetch(`/api/projects/${projectId}/capcut-preview`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({join_id:join.id})});
      const data=await response.json();if(!response.ok)throw new Error(data.error||'Прев’ю переходу не вийшло');
      const video=document.createElement('video');video.muted=true;video.playsInline=true;video.preload='auto';video.className='capcut-transition-video';video.src=data.url;
      Object.assign(entry,{state:'ready',url:data.url,video});
      if(state.project?.id===projectId&&!state.playing)renderPreview();
    }catch(error){entry.state='failed';entry.error=error.message;}
  });
  return entry;
}
function renderCapcutTransitionOverlay(composition,time){
  const joins=(state.project?.join_transitions||[]).filter(j=>isCapcutTransition(j.type));
  // previews of the seams near the playhead are drawn ahead, one at a time
  for(const join of joins)if(Math.abs(join.seam-time)<20||(state.selectedTransition?.fromRef===join.from_ref&&state.selectedTransition?.toRef===join.to_ref))requestCapcutPreview(join);
  const join=joins.find(j=>{const span=joinFrames(j);return time>=span.seam&&time<span.seam+span.duration;});
  let holder=composition.querySelector('.capcut-transition-overlay');
  const entry=join&&capcutPreviews.get(capcutJoinKey(join));
  if(!join||entry?.state!=='ready'){if(holder){holder.hidden=true;holder.querySelector('video')?.pause();}return;}
  if(!holder){holder=document.createElement('div');holder.className='capcut-transition-overlay';composition.append(holder);}
  if(holder.firstChild!==entry.video){holder.replaceChildren(entry.video);}
  const brandIds=new Set(sceneGroups().filter(g=>g.role==='overlay').flatMap(g=>g.clip_ids));
  const base=Array.from(composition.querySelectorAll('.composition-clip')).filter(e=>!brandIds.has(e.dataset.clipId)).map(e=>Number(e.style.zIndex)||0);
  const brand=Array.from(composition.querySelectorAll('.composition-clip')).filter(e=>brandIds.has(e.dataset.clipId)).map(e=>Number(e.style.zIndex)||0);
  holder.style.zIndex=String(Math.min(Math.max(0,...base)+1,brand.length?Math.min(...brand)-1:Infinity));holder.hidden=false;
  const span=joinFrames(join),video=entry.video,target=Math.max(0,Math.min(span.duration,time-span.seam));
  if(state.playing){if(video.paused)video.play().catch(()=>{});if(Math.abs(video.currentTime-target)>.12)video.currentTime=target;}
  else{if(!video.paused)video.pause();if(Math.abs(video.currentTime-target)>.02)video.currentTime=target;}
}

/* ------------------------------------------------------------------ effect clips in the preview */
// what a picture-changing effect does in the browser: a backdrop filter acts on everything under its row, as the export
const capcutContentLook={capcut_e07:'blur(1.5px) brightness(1.05)',capcut_e08:'brightness(1.08) contrast(1.05)',capcut_e12:'grayscale(1) sepia(1) hue-rotate(65deg) saturate(2.6) brightness(.85) contrast(1.15)'};
function capcutEffectElement(clip){
  const name=clip.capcut_effect,entry=capcutCatalog.effects[name],element=document.createElement('div');element.className='capcut-effect';
  if(entry?.mode==='content'||!entry){element.style.backdropFilter=element.style.webkitBackdropFilter=capcutContentLook[name]||'none';if(name==='capcut_e12')element.classList.add('capcut-crt');return element;}
  const video=document.createElement('video');video.className='capcut-loop';video.muted=true;video.loop=true;video.playsInline=true;video.preload='auto';
  video.src=`/api/capcut/effects/${name}/preview.webm`;element.append(video);return element;
}
function syncCapcutEffect(wrapper,clip,local){
  const video=wrapper.querySelector('video.capcut-loop');if(!video)return;
  if(state.playing){if(video.paused)video.play().catch(()=>{});}
  else{if(!video.paused)video.pause();if(Number.isFinite(video.duration)&&video.duration>0){const target=local%video.duration;if(Math.abs(video.currentTime-target)>.05)video.currentTime=target;}}
}

/* ------------------------------------------------------------------ the effect library */
async function applyCapcutEffect(name,{groupId,clipId,film}={}){
  const entry=capcutCatalog.effects[name];if(!entry)return;
  let payload={effect:name};
  if(!film){
    let group=groupId?sceneGroups().find(g=>g.id===groupId&&g.role!=='overlay'):null;
    if(!group&&clipId)group=sceneGroups().find(g=>g.role!=='overlay'&&(g.clip_ids||[]).includes(clipId));
    if(group)payload.group_id=group.id;
    else if(clipId){const clip=universalClips().find(c=>c.id===clipId);if(!clip){status('Виберіть кадр для ефекту.',true);return;}payload.start=Number(clip.start);payload.end=Number(clip.start)+Number(clip.duration);}
    else{status('Виберіть кадр або натисніть «На весь ролик».',true);return;}
  }
  await action('add_capcut_effect',payload,`Ефект «${entry.name}» додано${film?' на весь ролик':''}.`);
}
function appendCapcutEffects(){
  const library=$('effect-library');if(!library||library.querySelector('.capcut-effects'))return;
  const box=document.createElement('div');box.className='capcut-effects';
  for(const [group,label] of [['noise','Шуми CapCut'],['trend','Тренди CapCut']]){
    const title=document.createElement('p');title.className='effect-hint capcut-group-title';title.textContent=label;box.append(title);
    for(const [name,entry] of Object.entries(capcutCatalog.effects).filter(([,e])=>e.group===group)){
      const row=document.createElement('div');row.className='capcut-effect-row';
      const button=document.createElement('button');button.type='button';button.className='effect-chip capcut-effect-chip';button.title='Перетягніть на кадр або натисніть, щоб накласти на вибраний кадр';
      const img=document.createElement('img');img.src='/'+entry.thumb;img.alt='';img.loading='lazy';
      const caption=document.createElement('span');caption.textContent=entry.name;button.append(img,caption);
      button.addEventListener('pointerdown',event=>{if(event.button!==0)return;event.preventDefault();event.currentTarget.setPointerCapture(event.pointerId);capcutEffectDrag={name,pointerId:event.pointerId,x:event.clientX,y:event.clientY,moved:false};});
      button.addEventListener('click',()=>{if(capcutEffectSuppress)return;applyCapcutEffect(name,{groupId:state.selectedGroup,clipId:state.selected}).catch(()=>{});});
      const film=document.createElement('button');film.type='button';film.className='capcut-film';film.textContent='На весь ролик';film.title='Окремий рядок над усім відео, під плашкою каналу: ефект діє на все, що нижче';
      film.addEventListener('click',()=>applyCapcutEffect(name,{film:true}).catch(()=>{}));
      row.append(button,film);box.append(row);
    }
  }
  library.append(box);
}
let capcutEffectDrag=null,capcutEffectSuppress=false;
document.addEventListener('pointermove',event=>{const drag=capcutEffectDrag;if(!drag||event.pointerId!==drag.pointerId)return;if(!drag.moved&&Math.hypot(event.clientX-drag.x,event.clientY-drag.y)<5)return;if(!drag.moved){drag.moved=true;drag.ghost=document.createElement('div');drag.ghost.className='transition-drag-ghost';drag.ghost.textContent=capcutCatalog.effects[drag.name].name;document.body.append(drag.ghost);}drag.ghost.style.left=event.clientX+14+'px';drag.ghost.style.top=event.clientY-30+'px';document.querySelectorAll('.effect-drop').forEach(e=>e.classList.remove('effect-drop'));effectDropTarget(event.clientX,event.clientY)?.classList.add('effect-drop');});
document.addEventListener('pointerup',event=>{const drag=capcutEffectDrag;if(!drag||event.pointerId!==drag.pointerId)return;capcutEffectDrag=null;drag.ghost?.remove();document.querySelectorAll('.effect-drop').forEach(e=>e.classList.remove('effect-drop'));if(!drag.moved)return;capcutEffectSuppress=true;setTimeout(()=>{capcutEffectSuppress=false;},0);const target=effectDropTarget(event.clientX,event.clientY);if(target)applyCapcutEffect(drag.name,{groupId:target.dataset.groupId,clipId:target.dataset.clipId}).catch(()=>{});else status('Перетягніть ефект на кадр у таймлайні.',true);});
if(typeof initEffectLibrary==='function'){const plainEffectLibrary=initEffectLibrary;initEffectLibrary=function(){plainEffectLibrary();capcutReady.then(appendCapcutEffects);};}

/* ------------------------------------------------------------------ the channel's «Переходи» */
// The set the montage used before the channel chose anything: a new channel starts with it switched on.
const CAPCUT_DEFAULT_POOL=['crossfade','slide_left','slide_right','zoom_in','zoom_out','cin_pearl_mist','cin_blue_moon','cin_arctic_mist'];
function capcutPreviewVideo(type){
  const entry=capcutCatalog.transitions[type],video=document.createElement('video');
  video.muted=true;video.loop=true;video.playsInline=true;video.preload='none';video.poster='/'+entry.thumb;video.src='/'+entry.thumb.replace(/\.jpg$/,'.mp4');
  return video;
}
function transitionPreviewCard(type){
  // a live look at the transition: CapCut ones play their small film, the studio's own are drawn as in the library
  const frame=document.createElement('span');frame.className='transition-card-preview';let stop=()=>{},play=()=>{};
  if(capcutCatalog.transitions[type]){
    const video=capcutPreviewVideo(type);frame.append(video);
    play=()=>{video.play().catch(()=>{});};stop=()=>{video.pause();video.currentTime=0;video.load();};
  }else{
    const canvas=document.createElement('canvas');canvas.width=256;canvas.height=144;frame.append(canvas);paintTransitionPreview(canvas,type,.5);let raf;
    play=()=>{const began=performance.now();cancelAnimationFrame(raf);const tick=now=>{if(!canvas.isConnected)return;paintTransitionPreview(canvas,type,((now-began)/1500)%1);raf=requestAnimationFrame(tick);};raf=requestAnimationFrame(tick);};
    stop=()=>{cancelAnimationFrame(raf);paintTransitionPreview(canvas,type,.5);};
  }
  return {frame,play,stop};
}
function channelTransitionSection(channel){
  const saved=channel.settings?.transitions||{},allowed=new Set(Array.isArray(saved.allowed)?saved.allowed:CAPCUT_DEFAULT_POOL),share=Math.round(100*(saved.share??.7));
  const section=document.createElement('details');section.className='channel-settings-group settings-transitions';
  section.innerHTML=`<summary>${typeof channelSettingsIcon==='function'?channelSettingsIcon('look'):''}<span><strong>Переходи</strong><small class="settings-choice-summary"></small></span><svg class="channel-settings-chevron" viewBox="0 0 20 20" aria-hidden="true"><path d="m7 4 6 6-6 6"/></svg></summary>
  <div class="channel-settings-group-body"><div class="settings-section settings-transitions-body">
    <label class="settings-transitions-share"><span>Як часто ставити перехід</span><span class="settings-transitions-range"><input id="settings-transition-share" type="range" min="0" max="100" step="5" value="${share}" aria-label="Частка стиків з переходом, відсотків"><output></output></span></label>
    <p class="settings-transitions-note"></p>
  </div></div>`;
  const body=section.querySelector('.settings-transitions-body'),range=section.querySelector('#settings-transition-share'),out=section.querySelector('output'),note=section.querySelector('.settings-transitions-note');
  const groups=[['Ефектні','Трендові переходи з рухом, спалахами й 3D',Object.keys(capcutCatalog.transitions)],['Спокійні','Розчинення, зсуви, м’які наближення й кольорові шторки',Object.keys(transitionNames).filter(t=>t!=='cut'&&!isCapcutTransition(t))]];
  const total=groups.reduce((sum,group)=>sum+group[2].length,0);
  for(const [label,hint,types] of groups){
    const box=document.createElement('div');box.className='settings-transition-group';
    box.innerHTML=`<div class="settings-transition-head"><span><strong>${label}</strong><small>${hint}</small></span><span class="settings-transition-count"></span><button type="button" class="settings-transition-all">Вибрати всі</button><button type="button" class="settings-transition-none">Зняти всі</button></div>`;
    const grid=document.createElement('div');grid.className='settings-transition-grid';
    for(const type of types){
      const card=document.createElement('label');card.className='settings-transition-card';
      const input=document.createElement('input');input.type='checkbox';input.dataset.transitionType=type;input.checked=allowed.has(type);
      const {frame,play,stop}=transitionPreviewCard(type);
      const mark=document.createElement('span');mark.className='transition-card-mark';mark.setAttribute('aria-hidden','true');mark.innerHTML='<svg viewBox="0 0 20 20"><path d="m4 10 4 4 8-8"/></svg>';
      const name=document.createElement('span');name.className='transition-card-name';name.textContent=transitionNames[type]||type;
      frame.append(mark);card.append(input,frame,name);card.title=(transitionNames[type]||type)+(capcutCatalog.transitions[type]?' · '+String(capcutCatalog.transitions[type].default_duration).replace('.',',')+' с':'');
      card.addEventListener('mouseenter',play);card.addEventListener('mouseleave',stop);input.addEventListener('focus',play);input.addEventListener('blur',stop);
      grid.append(card);
    }
    const setAll=value=>{grid.querySelectorAll('input').forEach(input=>{if(input.checked!==value){input.checked=value;input.dispatchEvent(new Event('change',{bubbles:true}));}});update();};
    box.querySelector('.settings-transition-all').addEventListener('click',()=>setAll(true));
    box.querySelector('.settings-transition-none').addEventListener('click',()=>setAll(false));
    box.append(grid);body.append(box);
  }
  function update(){
    const count=section.querySelectorAll('[data-transition-type]:checked').length,percent=Number(range.value);
    out.textContent=percent+'%';
    for(const box of section.querySelectorAll('.settings-transition-group'))box.querySelector('.settings-transition-count').textContent=`${box.querySelectorAll('input:checked').length} з ${box.querySelectorAll('input').length}`;
    const off=!count||!percent;
    section.querySelector('.settings-choice-summary').textContent=off?'Вимкнено: між кадрами завжди склейка':`Вибрано ${count} з ${total} · на ${percent}% стиків`;
    note.textContent=off?'Студія не ставитиме переходів: кадри змінюються склейкою.':`Приблизно на ${percent} зі 100 стиків між кадрами студія поставить один із вибраних переходів, щоразу навмання. На решті стиків і перед текстовим кадром буде звичайна склейка.`;
  }
  section.addEventListener('change',update);range.addEventListener('input',update);update();
  return section;
}
function channelTransitionValues(){
  const range=$('settings-transition-share');if(!range)return null;
  return {allowed:[...document.querySelectorAll('[data-transition-type]:checked')].map(i=>i.dataset.transitionType),share:Number(range.value)/100};
}
