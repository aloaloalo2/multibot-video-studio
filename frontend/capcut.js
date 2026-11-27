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
// a long CapCut transition sits 30% shorter on the seam (joins.capcut_duration, user 25 November 2026)
function capcutDefaultDuration(type){const own=Number(capcutCatalog.transitions[type]?.default_duration)||1;return own>1.2?Math.round(own*70)/100:own;}

/* ------------------------------------------------------------------ the seam's transition in the preview */
const capcutPreviews=new Map();   // key -> {state:'loading'|'ready'|'failed', url, video}
// The key follows the two frames at the seam, not the project's revision: an edit anywhere else used to send every CapCut
// seam back into the queue, and until it was drawn again it played as a plain dissolve (user, 26 November 2026: «перехід
// синій, але… там стандартний перехід. Просто прозорість»)
function capcutSides(join){
  const p=state.project;if(!p)return '';
  const clips=new Map((p.tracks||[]).flatMap(t=>t.clips||[]).map(c=>[c.id,c]));
  return [join.from_ref,join.to_ref].map(ref=>{const id=String(ref||'').split(':').pop();const group=(p.scene_groups||[]).find(g=>g.id===id);
    return (group?.clip_ids||[]).map(i=>clips.get(i)).filter(Boolean).map(c=>[c.id,c.start,c.duration,c.trim_start,c.asset_id,c.x,c.y,c.scale,c.opacity,JSON.stringify(c.keyframes||[])].join(',')).join(';');}).join('|');
}
function capcutJoinKey(join){return [state.project?.id,join.id,join.type,Number(join.seam).toFixed(3),Number(join.duration).toFixed(3),capcutSides(join)].join(':');}
function requestCapcutPreview(join){
  const key=capcutJoinKey(join);if(capcutPreviews.has(key))return capcutPreviews.get(key);
  const entry={state:'loading'};capcutPreviews.set(key,entry);capcutWaiting.set(key,{join,entry,projectId:state.project.id});
  setTimeout(pumpCapcutPreviews,0);   // after the whole render asked: the pick sees every seam
  return entry;
}
// The server draws one preview at a time (a new one takes seconds), so the seam the playhead reaches next goes first:
// in join order a seam two seconds ahead waited behind others and played as a plain dissolve («46 47 нет перехода»).
const capcutWaiting=new Map();let capcutPumping=false;
function nextCapcutPreview(){
  let best=null,score=Infinity;const time=state.playhead;
  for(const [key,{join}] of capcutWaiting){const ahead=Number(join.seam)+Number(join.duration||0)-time,value=ahead>=0?ahead:1e6-ahead;if(value<score){score=value;best=key;}}
  return best;
}
// The episode opens first: drawing a transition takes the processor for seconds (a Razgon side is rendered too), and
// started with the page it held back the voice, the music and the pictures of an episode being opened (user, 25 November
// 2026: «заходжу в проект… нажимаю play, і… ні звука нема, ні відео»). Previews wait until the page has loaded its
// media and the author has had a moment, then one at a time.
let capcutQuietUntil=0,capcutQuietProject=null;
function capcutQuiet(){
  if(state.project?.id!==capcutQuietProject){capcutQuietProject=state.project?.id;capcutQuietUntil=performance.now()+6000;}
  return performance.now()<capcutQuietUntil;
}
async function pumpCapcutPreviews(){
  if(capcutPumping)return;
  if(capcutQuiet()){setTimeout(pumpCapcutPreviews,Math.max(200,capcutQuietUntil-performance.now()));return;}
  capcutPumping=true;
  try{
    while(capcutWaiting.size){
      const current=new Set((state.project?.join_transitions||[]).filter(j=>isCapcutTransition(j.type)).map(capcutJoinKey));
      for(const key of [...capcutWaiting.keys()])if(!current.has(key)){capcutWaiting.delete(key);capcutPreviews.delete(key);}   // an older revision or project
      const key=nextCapcutPreview();if(key==null)break;
      const {join,entry,projectId}=capcutWaiting.get(key);capcutWaiting.delete(key);
      try{
        const response=await fetch(`/api/projects/${projectId}/capcut-preview`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({join_id:join.id})});
        const data=await response.json();if(!response.ok)throw new Error(data.error||'Прев’ю переходу не вийшло');
        if(data.live){entry.state='live';capcutDrawn.add(join.id);markCapcutPending();continue;}   // a Razgon code frame: the live picture with a plain blend, the export draws CapCut
        Object.assign(entry,{state:'ready',url:data.url});capcutDrawn.add(join.id);markCapcutPending();
        if(state.project?.id===projectId&&!state.playing)renderPreview();
      }catch(error){entry.state='failed';entry.error=error.message;}
    }
  }finally{capcutPumping=false;}
}
// A drawn seam's small film is loaded only while the playhead is near it and let go once it is far: a film scrubbed
// through kept every seam's video decoded (a hundred on Andromeda), and Chrome stops players past about 75.
const CAPCUT_LOAD_AHEAD=25,CAPCUT_LOAD_BEHIND=5,CAPCUT_DROP_AHEAD=40,CAPCUT_DROP_BEHIND=15;
function capcutVideo(entry){
  if(!entry.video){const video=document.createElement('video');video.muted=true;video.playsInline=true;video.preload='auto';video.className='capcut-transition-video';video.src=entry.url;entry.video=video;}
  return entry.video;
}
function dropCapcutVideo(entry){const video=entry.video;if(!video)return;entry.video=null;video.pause();video.remove();video.removeAttribute('src');video.load();}
// the project's CapCut seams with their preview keys, once per version; previews of an older version are let go
let capcutPrunedFor=null;
function capcutSeams(){
  const seams=memoForProject('capcutSeams',()=>(state.project?.join_transitions||[]).filter(j=>isCapcutTransition(j.type)).map(join=>({join,key:capcutJoinKey(join),span:joinFrames(join)})));
  if(capcutPrunedFor!==state.project){
    capcutPrunedFor=state.project;const keep=new Set(seams.map(seam=>seam.key));
    for(const [key,entry] of capcutPreviews)if(!keep.has(key)&&!capcutWaiting.has(key)){dropCapcutVideo(entry);capcutPreviews.delete(key);}
  }
  return seams;
}
function renderCapcutTransitionOverlay(composition,time){
  const seams=capcutSeams(),chosen=state.selectedTransition;let current=null;
  for(const seam of seams){
    const {join,key,span}=seam,ahead=join.seam-time,picked=chosen?.fromRef===join.from_ref&&chosen?.toRef===join.to_ref;
    // previews of the seams near the playhead (25 s ahead) are drawn ahead, the nearest first
    if((ahead<CAPCUT_LOAD_AHEAD&&ahead>-CAPCUT_LOAD_BEHIND)||picked){const entry=requestCapcutPreview(join);if(entry.state==='ready')capcutVideo(entry);}
    else if(ahead>CAPCUT_DROP_AHEAD||ahead<-CAPCUT_DROP_BEHIND){const entry=capcutPreviews.get(key);if(entry)dropCapcutVideo(entry);}
    if(!current&&time>=span.seam&&time<span.seam+span.duration)current=seam;
  }
  let holder=composition.querySelector('.capcut-transition-overlay');
  const entry=current&&capcutPreviews.get(current.key);
  if(!current||entry?.state!=='ready'){if(holder){holder.hidden=true;holder.firstChild?.pause?.();}return;}
  if(!holder){holder=document.createElement('div');holder.className='capcut-transition-overlay';composition.append(holder);}
  const video=capcutVideo(entry);
  if(holder.firstChild!==video){holder.replaceChildren(video);}
  // over the montage's pictures, under the channel's plate
  const brandIds=previewBrandIds();let base=0,brand=Infinity;
  for(const node of composition.querySelectorAll('.composition-clip')){const z=Number(node.style.zIndex)||0;if(brandIds.has(node.dataset.clipId))brand=Math.min(brand,z-1);else base=Math.max(base,z);}
  holder.style.zIndex=String(Math.min(base+1,brand));holder.hidden=false;
  const span=current.span,target=Math.max(0,Math.min(span.duration,time-span.seam));
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
  const video=wrapper._loop!==undefined?wrapper._loop:wrapper.querySelector('video.capcut-loop');if(!video)return;
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
  const saved=channel.settings?.transitions||{},allowed=new Set(Array.isArray(saved.allowed)?saved.allowed:CAPCUT_DEFAULT_POOL);
  const section=document.createElement('details');section.className='channel-settings-group settings-transitions regular-only';
  section.innerHTML=`<summary>${typeof channelSettingsIcon==='function'?channelSettingsIcon('look'):''}<span><strong>Переходи</strong><small class="settings-choice-summary"></small></span><svg class="channel-settings-chevron" viewBox="0 0 20 20" aria-hidden="true"><path d="m7 4 6 6-6 6"/></svg></summary>
  <div class="channel-settings-group-body"><div class="settings-section settings-transitions-body">
    <p class="settings-transitions-note"></p>
  </div></div>`;
  const body=section.querySelector('.settings-transitions-body'),note=section.querySelector('.settings-transitions-note');
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
    const count=section.querySelectorAll('[data-transition-type]:checked').length;
    for(const box of section.querySelectorAll('.settings-transition-group'))box.querySelector('.settings-transition-count').textContent=`${box.querySelectorAll('input:checked').length} з ${box.querySelectorAll('input').length}`;
    const off=!count;
    section.querySelector('.settings-choice-summary').textContent=off?'Вимкнено: між кадрами завжди склейка':`Вибрано ${count} з ${total}`;
    note.textContent=off?'Студія не ставитиме переходів: кадри змінюються склейкою.':'Де ставити перехід, студія вирішує сама: з вибраних переходів.';
  }
  section.addEventListener('change',update);update();
  return section;
}
function channelTransitionValues(){
  if(!document.querySelector('[data-transition-type]'))return null;
  return {allowed:[...document.querySelectorAll('[data-transition-type]:checked')].map(i=>i.dataset.transitionType)};
}


/* ------------------------------------------------------------------ which CapCut transitions are drawn yet */
// A CapCut transition's marker on the timeline is white until its picture is drawn, then blue (user, 25 November 2026:
// «переходи, які сині… зроби їх білі, якщо вони не показуються ще такими, як вони мають бути»). The server says which
// are drawn (its background pass draws them all); a dissolve, a slide or a cinematic one is drawn live and is blue at once.
let capcutDrawn=new Set(),capcutReadyTimer=0,capcutReadyFor=null,capcutReadyBusy=null;
function capcutPending(join){return !!join&&isCapcutTransition(join.type)&&!capcutDrawn.has(join.id);}
function markCapcutPending(){
  const joins=state.project?.join_transitions||[];
  for(const marker of document.querySelectorAll('.transition-join.has-transition')){
    const join=joins.find(j=>j.from_ref===marker.dataset.fromRef&&j.to_ref===marker.dataset.toRef);
    marker.classList.toggle('transition-pending',capcutPending(join));
  }
}
async function refreshCapcutReady(){
  const id=state.project?.id;if(!id||capcutReadyBusy===id)return;   // one request at a time: it schedules the next
  clearTimeout(capcutReadyTimer);capcutReadyTimer=0;capcutReadyBusy=id;
  try{
    const data=await api(`/api/projects/${encodeURIComponent(id)}/capcut-ready`);
    if(state.project?.id!==id)return;
    capcutDrawn=new Set(data.ready||[]);capcutReadyFor=id;markCapcutPending();
    // seams the server has drawn already play at once, with no request of their own (user, 26 November 2026: «щоб
    // моментально я міг їх просто подивитися»): the server hands out a film only while both frames are as drawn
    let filled=false;
    for(const join of state.project.join_transitions||[]){
      const url=data.urls?.[join.id];if(!url||!isCapcutTransition(join.type))continue;
      const key=capcutJoinKey(join),known=capcutPreviews.get(key);
      if(known?.state==='ready')continue;
      if(known)capcutWaiting.delete(key);
      capcutPreviews.set(key,{state:'ready',url});filled=true;
    }
    if(filled&&!state.playing)renderPreview();
  }catch{}finally{capcutReadyBusy=null;}
  // no timer left means none runs: the next redraw with new seams (the frame agent adds them while the editor is open)
  // starts the polling again; a stale id kept it «running» and new transitions never played until a reload (user,
  // 27 November 2026: «чому синє… але нема переходу»)
  capcutReadyTimer=state.project?.id===id&&(state.project.join_transitions||[]).some(capcutPending)?setTimeout(refreshCapcutReady,4000):0;
}
