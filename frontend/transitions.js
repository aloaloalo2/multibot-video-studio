// CapCut transitions (capcut.js, engine/capcut_fx.py) are drawn by the server; the seam cuts until that video is ready
function isCapcutTransition(type){return typeof type==='string'&&type.startsWith('capcut_t');}
const transitionNames={cut:'Склейка',crossfade:'Розчинення',slide_left:'Зсув ліворуч',slide_right:'Зсув праворуч',slide_up:'Зсув угору',slide_down:'Зсув униз',zoom_in:'М’яке наближення',zoom_out:'М’яке віддалення'};
let joinCacheToken='',joinCache=new Map();
let transitionPointerDrag=null,transitionSuppressClick=false;
// The seams' places are measured once for a drag (again only after a scroll): measuring all 106 markers on every
// pointer move laid the page out again each time.
function transitionDropTarget(x,y,drag=null){
  const scroller=document.querySelector('.timeline-scroll'),key=scroller.scrollLeft+','+scroller.scrollTop;
  let seen=drag?.seams;
  if(!seen||seen.key!==key||!seen.markers.every(item=>item.marker.isConnected)){
    seen={key,bounds:scroller.getBoundingClientRect(),label:Number.parseFloat(getComputedStyle(scroller).getPropertyValue('--timeline-label-width'))||190,
      markers:[...document.querySelectorAll('.transition-join')].map(marker=>({marker,r:marker.getBoundingClientRect()}))};
    if(drag)drag.seams=seen;
  }
  const bounds=seen.bounds;
  if(x<bounds.left+seen.label||x>bounds.right||y<bounds.top||y>bounds.bottom)return null;
  let closest=null,distance=15;
  for(const {marker,r} of seen.markers){const dx=Math.abs(x-(r.left+r.width/2));if(y>=r.top-4&&y<=r.bottom+4&&dx<distance){closest=marker;distance=dx;}}
  return closest;
}
function beginTransitionDrag(event,type,origin){
  if(event.button!==0)return;event.preventDefault();event.stopPropagation();event.currentTarget.setPointerCapture(event.pointerId);
  transitionPointerDrag={pointerId:event.pointerId,type,origin,x:event.clientX,y:event.clientY,moved:false,source:event.currentTarget};
}
async function applyTransitionAtMarker(marker,type,origin){
  const previous=(state.project.join_transitions || []).find(join=>join.id===origin);
  const selected=state.selectedTransition,following=previous && selected?.fromRef===previous.from_ref && selected?.toRef===previous.to_ref;
  if(following)state.selectedTransition={fromRef:marker.dataset.fromRef,toRef:marker.dataset.toRef};
  try{return await action('set_join_transition',{from_ref:marker.dataset.fromRef,to_ref:marker.dataset.toRef,type,duration:previous?.duration ?? (isCapcutTransition(type) ? capcutDefaultDuration(type) : graphicTransitionPresets[type] ? .5 : type==='crossfade' ? .3 : .35),move_from:origin||undefined},'Перехід додано на стик.');}
  catch(error){if(following){state.selectedTransition=selected;renderInspector();}throw error;}
}
document.addEventListener('pointermove',event=>{
  const drag=transitionPointerDrag;if(!drag||event.pointerId!==drag.pointerId)return;
  if(!drag.moved&&Math.hypot(event.clientX-drag.x,event.clientY-drag.y)<5)return;
  if(!drag.moved){drag.moved=true;document.body.classList.add('dragging-transition');const ghost=document.createElement('div');ghost.className='transition-drag-ghost';ghost.textContent=transitionNames[drag.type];document.body.append(ghost);drag.ghost=ghost;}
  event.preventDefault();drag.ghost.style.left=event.clientX+14+'px';drag.ghost.style.top=event.clientY-30+'px';
  const marker=transitionDropTarget(event.clientX,event.clientY,drag);if(marker!==drag.hover){drag.hover?.classList.remove('join-drop');marker?.classList.add('join-drop');drag.hover=marker;}
});
document.addEventListener('pointerup',event=>{
  const drag=transitionPointerDrag;if(!drag||event.pointerId!==drag.pointerId)return;const marker=drag.moved?transitionDropTarget(event.clientX,event.clientY,drag):null;transitionPointerDrag=null;if(drag.source.hasPointerCapture(event.pointerId))drag.source.releasePointerCapture(event.pointerId);drag.ghost?.remove();document.body.classList.remove('dragging-transition');for(const node of document.querySelectorAll('.join-drop'))node.classList.remove('join-drop');
  if(!drag.moved)return;event.preventDefault();transitionSuppressClick=true;setTimeout(()=>{transitionSuppressClick=false;},0);
  if(marker)applyTransitionAtMarker(marker,drag.type,drag.origin).catch(()=>{});else status('Перехід не застосовано. Перетягніть його на підсвічений стик двох сусідніх кадрів.',true);
});
document.addEventListener('pointercancel',()=>{transitionPointerDrag?.ghost?.remove();transitionPointerDrag=null;document.body.classList.remove('dragging-transition');for(const node of document.querySelectorAll('.join-drop'))node.classList.remove('join-drop');});
document.addEventListener('click',event=>{if(transitionSuppressClick){transitionSuppressClick=false;event.preventDefault();event.stopPropagation();}},true);
function transitionEndpoint(ref){if(ref?.startsWith('group:')){const group=sceneGroups().find(g=>g.id===ref.slice(6));return group?groupMembers(group):[];}if(ref?.startsWith('clip:'))return universalClips().filter(c=>c.id===ref.slice(5));return [];}
function transitionInfo(clip){
  const token=state.project?.id+':'+state.project?.revision;
  // a dissolve fades only the side on top, the side under it stays whole, as the export (backend/joins.py transport;
  // user, 21 November 2026: «переходи… в чорноту, а потім різко появляється наступний кадр»)
  if(joinCacheToken!==token){joinCacheToken=token;joinCache=new Map();const level=new Map();(typeof layers==='function'?layers():[]).forEach((layer,i)=>(layer.clips||[]).forEach(c=>level.set(c.id,/^Razgon · кадр/.test(c.title||'')?-1:i)));   // the live Razgon player lies under the whole montage, so a seam with a Razgon frame fades the other side (22 November 2026: «між 5 і 6 нема переходу»)
    for(const join of state.project?.join_transitions || []){
      const ins=transitionEndpoint(join.to_ref),outs=transitionEndpoint(join.from_ref),lv=list=>list.map(c=>level.get(c.id)).filter(v=>v!==undefined);
      // only the clips on screen in the transition decide which side lies on top, as the export (joins.transport): a
      // lead-in gone seconds before the seam made Astéroïde 86→87 a plain cut (27 November 2026)
      const a=lv(outs.filter(c=>Math.abs(Number(c.start)+Number(c.duration)-join.seam)<=.05)),b=lv(ins.filter(c=>Number(c.start)<Number(join.seam)+Number(join.duration))),outUnder=!!(a.length&&b.length&&Math.max(...a)<Math.max(...b)),inUnder=!!(a.length&&b.length&&Math.max(...b)<Math.max(...a));   // a fading group lies at its top layer's place (transitionGroup)
      for(const c of ins)joinCache.set(c.id,{...(joinCache.get(c.id)||{}),incoming:{...join,under:inUnder}});
      for(const c of outs)if(Math.abs(Number(c.start)+Number(c.duration)-join.seam)<.05)joinCache.set(c.id,{...(joinCache.get(c.id)||{}),outgoing:{...join,under:outUnder}});}}
  return joinCache.get(clip.id) || {};
}
function visualFrameTime(time){const fps=Number(state.project?.fps||25);return Math.floor(Number(time)*fps+.5+1e-8)/fps;}
// A transition on whole video frames, as the export draws it (engine/render.py timeline_plan): 0.35 s at 25 fps
// lasts 9 frames there, and the preview used to run it 0.01 s faster.
// A transition out of a video with no frames after its edge ends on the seam (anchor «end», backend/joins.py
// ends_at_seam): the video plays its own last moments under it and the next frame comes in early, no held last picture.
// how long before its seam a transition starts (backend/joins.py lead_seconds): its hit lands on the seam
function joinAhead(join){return Number.isFinite(Number(join.lead))?Number(join.lead):(join.anchor==='end'?Number(join.duration):0);}
function joinStart(join){return Number(join.seam)-joinAhead(join);}
function joinFrames(join){const fps=Number(state.project?.fps||25),start=joinStart(join),seam=visualFrameTime(start);return {seam,duration:Math.max(1/fps,visualFrameTime(start+Number(join.duration))-seam)};}
function joinLead(clip){const join=transitionInfo(clip).incoming;return join&&Math.abs(Number(clip.start)-Number(join.seam))<.05?joinAhead(join):0;}
function clipRenderStart(clip){return visualFrameTime(Number(clip.start)-joinLead(clip));}
function clipRenderEnd(clip){const out=transitionInfo(clip).outgoing;return visualFrameTime(Number(clip.start)+Number(clip.duration)+(out?Math.max(0,(Number(out.duration)||0)-joinAhead(out)):0));}
// A frame group fades in or out as one picture, as the export (engine/render.py group_sides; user, 22 November 2026:
// «перехід використовує групи, а не кожен слой»): fading each layer alone shows the group's lower layers through it.
function transitionFades(type){const config=graphicTransitionPresets[type];return type==='crossfade'||type.startsWith('zoom_')||!!(config&&config.kind==='cinematic');}
function groupedJoinSides(clip){const info=transitionInfo(clip);return [['in',info.incoming],['out',info.outgoing]].filter(([direction,join])=>join&&join.id&&!join.under&&transitionFades(join.type)&&!(direction==='in'&&clip.kind==='text'&&clip.text_role==='full_frame'));}
function transitionGroup(clip,time){
  let key='',alpha=1;
  for(const [direction,join] of groupedJoinSides(clip)){const span=joinFrames(join);if(time<span.seam||time>=span.seam+span.duration)continue;const p=easedProgress((time-span.seam)/span.duration,'ease_in_out');key+=(key?'|':'')+join.id+':'+direction;alpha*=direction==='in'?p:1-p;}
  return key?{key,alpha}:null;
}
function transitionValues(clip,local,values,grouped=false){
  const info=transitionInfo(clip),time=Number(clip.start)+local,groupSides=grouped?new Set(groupedJoinSides(clip).map(([direction])=>direction)):new Set();
  // past its end an outgoing clip still moving keeps the speed of its last keyframe segment, one that stopped holds,
  // as the export (backend/joins.py transport)
  // an incoming clip that comes in early runs its starting motion on backwards, as the export (joins.lead)
  const lead=joinLead(clip);
  if(lead&&local<0)for(const prop of ['x','y','scale','opacity']){const points=keyframePoints(clip,prop,Number(clip[prop] ?? (prop==='x'||prop==='y'?.5:1)));if(!points.length)continue;const head=points[0].time>1e-9?{time:0,value:Number(clip[prop] ?? (prop==='x'||prop==='y'?.5:1))}:points[0],after=points[0].time>1e-9?points[0]:(points[1]||head),span=after.time-head.time;let first=head.value-(span>1e-9?(after.value-head.value)/span*lead:0);if(prop==='opacity')first=Math.max(0,Math.min(1,first));else if(prop==='scale')first=Math.max(.05,first);values[prop]=first+(head.value-first)*easedProgress((local+lead)/lead,clip.easing);}
  if(info.outgoing && local>Number(clip.duration))for(const prop of ['x','y','scale','opacity']){const points=keyframePoints(clip,prop,Number(clip[prop] ?? (prop==='x'||prop==='y'?.5:1)));if(!points.length)continue;const last=points.at(-1),before=points.at(-2) || last,span=last.time-before.time,moving=span>1e-9&&last.time>=Number(clip.duration)-.05;values[prop]=last.value+(moving?(last.value-before.value)/span:0)*(local-last.time);}
  for(const [direction,join] of [['in',info.incoming],['out',info.outgoing]]){if(!join || (direction==='in' && clip.kind==='text' && clip.text_role==='full_frame'))continue;const span=joinFrames(join),p=easedProgress((time-span.seam)/span.duration,'ease_in_out'),incoming=direction==='in',progress=incoming?1-p:p,type=join.type;
    if(graphicTransitionPresets[type]){
      const config=graphicTransitionPresets[type];
      if(config.kind==='cinematic'){
        if(!join.under&&!groupSides.has(direction))values.opacity*=incoming?p:1-p;
      }else values.opacity*=incoming?(p>=.5?1:0):(p<.5?1:0);
      continue;
    }
    // a CapCut transition plays its drawn video over the seam (capcut.js); until it is ready (and beside a Razgon frame,
    // which only the export draws) the preview cuts on the seam: a stand-in dissolve made a CapCut seam look like a plain
    // fade (user, 26 November 2026: «прозорість по дефолту прибери… я путаюсь, це дійсно перехід чи ні»)
    if(type.startsWith('capcut_t')){if(incoming?time<Number(join.seam):time>=Number(join.seam))values.opacity=0;continue;}
    if(type==='crossfade'&&!join.under&&!groupSides.has(direction))values.opacity*=incoming?p:1-p;
    if(type.startsWith('slide_')){if(type==='slide_left')values.x+=incoming?progress:-progress;if(type==='slide_right')values.x+=incoming?-progress:progress;if(type==='slide_up')values.y+=incoming?progress:-progress;if(type==='slide_down')values.y+=incoming?-progress:progress;}
    if(type.startsWith('zoom_')){const s=type==='zoom_in'?(incoming?.88+.12*p:1+.12*p):(incoming?1.12-.12*p:1-.12*p);values.x=.5+(values.x-.5)*s;values.y=.5+(values.y-.5)*s;values.scale*=s;if(!join.under&&!groupSides.has(direction))values.opacity*=incoming?p:1-p;}
  }
  return values;
}
function transitionDurationLimit(join){
  const span=ref=>{const clips=transitionEndpoint(ref);return clips.length?Math.max(...clips.map(clip=>Number(clip.start)+Number(clip.duration)))-Math.min(...clips.map(clip=>Number(clip.start))):0;};
  return Math.max(.05,Math.min(2,span(join.from_ref),span(join.to_ref)));
}
function clearTransitionSelection(){state.selectedTransition=null;document.querySelectorAll('.transition-join.selected-transition').forEach(marker=>marker.classList.remove('selected-transition'));}
function selectTransition(join){
  stopPlayback();state.selectedTransition={fromRef:join.from_ref,toRef:join.to_ref};
  state.selected=null;state.selectedGroup=null;state.selectedStack=null;state.multiSelection=[];state.playhead=join.seam;
  renderTimeline();renderInspector();renderPreview();
}
function renderTransitionInspector(join){
  const box=$('universal-inspector'),limit=transitionDurationLimit(join);
  $('inspector-fields').hidden=true;$('inspector-empty').hidden=true;box.hidden=false;
  const options=Object.entries(transitionNames).filter(([type])=>type!=='cut').map(([type,name])=>`<option value="${esc(type)}" ${type===join.type?'selected':''}>${esc(name)}</option>`).join('');
  box.innerHTML=`<div class="universal-properties transition-properties"><strong>Перехід</strong><small>Стик ${clock(join.seam)}</small><section><label>Вид переходу<select id="transition-property-type">${options}</select></label><label>Тривалість, с<input id="transition-property-duration" type="number" min="0.05" max="${limit}" step="0.001" value="${join.duration}"></label><label><span class="transition-speed-title">Швидкість <output id="transition-property-speed-value"></output></span><input id="transition-property-speed" type="range" min="0" max="100" step="1" aria-label="Тривалість переходу"></label><div class="transition-speed-ends"><span>Швидше</span><span>Повільніше</span></div><p id="transition-property-autosave" aria-live="polite">Збережено</p></section><button id="transition-property-remove" class="danger full trash-button" type="button">${trashIcon}<span>Прибрати перехід</span></button></div>`;
  const type=$('transition-property-type'),duration=$('transition-property-duration'),speed=$('transition-property-speed'),speedValue=$('transition-property-speed-value'),saveState=$('transition-property-autosave');
  const midpoint=()=>{const standard=isCapcutTransition(type.value) ? capcutDefaultDuration(type.value) : graphicTransitionPresets[type.value] ? .5 : type.value==='crossfade' ? .3 : .35;return standard<limit?standard:(.05+limit)/2;};
  const update=(moveThumb=true)=>{const value=Number(duration.value);speed.disabled=limit<=.05;if(!Number.isFinite(value)||value<=0){speedValue.textContent='';return;}speedValue.textContent=new Intl.NumberFormat('uk-UA',{minimumFractionDigits:2,maximumFractionDigits:3}).format(value)+' с';speed.setAttribute('aria-valuetext',speedValue.textContent);if(moveThumb){const clamped=Math.max(.05,Math.min(limit,value)),mid=midpoint();const position=clamped<=mid?50*(clamped-.05)/(mid-.05):50+50*(clamped-mid)/(limit-mid);speed.value=Number.isFinite(position)?Math.max(0,Math.min(100,Math.round(position))):50;}};
  const projectId=state.project.id;let pending=null,saving=false,removing=false,inFlightKey=null,savedKey=`${join.type}:${Number(join.duration).toFixed(3)}`,durationTimer;
  const key=entry=>`${entry.type}:${Number(entry.duration).toFixed(3)}`;
  const flush=async()=>{
    if(saving)return;saving=true;
    try{while(pending){
      if(state.project?.id!==projectId){pending=null;break;}
      if(state.busy){await new Promise(resolve=>setTimeout(resolve,60));continue;}
      const next=pending;pending=null;inFlightKey=key(next);
      try{await action('set_join_transition',next,'Налаштування переходу збережено.',{preserveInspector:true});savedKey=inFlightKey;}
      catch(error){if(!pending && box.contains(duration)){const saved=(state.project?.join_transitions || []).find(item=>item.from_ref===join.from_ref&&item.to_ref===join.to_ref);if(saved){duration.value=saved.duration;type.value=saved.type;update();}saveState.textContent='Не вдалося зберегти';}continue;}
      finally{inFlightKey=null;}
      if(!pending && box.contains(duration))saveState.textContent='Збережено';
    }}finally{saving=false;}
  };
  const commit=()=>{if(removing)return;const value=Number(duration.value);if(!duration.value || !Number.isFinite(value) || value<.05 || value>limit){status(`Тривалість має бути від 0,05 до ${String(limit).replace('.',',')} с.`,true);saveState.textContent='Не збережено';return;}const next={from_ref:join.from_ref,to_ref:join.to_ref,type:type.value,duration:value},nextKey=key(next);if((pending && key(pending)===nextKey)||(!pending&&saving&&inFlightKey===nextKey))return;if(!pending&&!saving&&savedKey===nextKey){saveState.textContent='Збережено';return;}pending=next;saveState.textContent='Зберігається…';void flush();};
  duration.addEventListener('input',()=>{update();saveState.textContent='Зберігається…';clearTimeout(durationTimer);durationTimer=setTimeout(commit,350);});
  const finishDuration=()=>{clearTimeout(durationTimer);commit();};
  duration.addEventListener('change',finishDuration);duration.addEventListener('blur',finishDuration);
  duration.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();finishDuration();duration.blur();}});
  type.addEventListener('change',()=>{update();commit();});
  speed.addEventListener('input',()=>{const position=Number(speed.value),mid=midpoint();const value=position<=50?.05+(mid-.05)*position/50:mid+(limit-mid)*(position-50)/50;duration.value=Math.max(.05,Math.min(limit,Math.round(value*100)/100)).toFixed(2);update(false);saveState.textContent='Зберігається…';});
  speed.addEventListener('change',commit);
  $('transition-property-remove').addEventListener('click',async()=>{removing=true;pending=null;clearTimeout(durationTimer);try{while(state.busy && state.project?.id===projectId)await new Promise(resolve=>setTimeout(resolve,60));if(state.project?.id===projectId)await action('set_join_transition',{from_ref:join.from_ref,to_ref:join.to_ref,type:'cut',duration:0},'Перехід прибрано.');}catch(error){removing=false;status(error.message,true);}});
  update();
}
// the transition saved on a seam, by its two sides (one map a project version: every marker asked the whole list)
function joinAt(left,right){
  const joins=memoForProject('joinsBySeam',()=>{const map=new Map();for(const join of state.project.join_transitions || []){const key=join.from_ref+'\n'+join.to_ref;if(!map.has(key))map.set(key,join);}return map;});
  return joins.get(left+'\n'+right);
}
function transitionJoinMarker(lane,left,right,seam,visualWidth=12){
  const active=joinAt(left,right),marker=document.createElement('button');marker.type='button';marker.className='transition-join'+(active?' has-transition':'')+(active&&typeof capcutPending==='function'&&capcutPending(active)?' transition-pending':'')+(state.selectedTransition?.fromRef===left&&state.selectedTransition?.toRef===right?' selected-transition':'');marker.style.left=((seam-timelineOrigin())/timelineSpan()*100)+'%';marker.textContent='';marker.title=active?(transitionNames[active.type] || active.type)+' · натисніть для налаштувань':'Перетягніть сюди перехід';marker.setAttribute('aria-label','Стик '+clock(seam));marker.dataset.fromRef=left;marker.dataset.toRef=right;
  marker.style.width=Math.max(10,visualWidth)+'px';if(visualWidth<6)marker.classList.add('transition-compact');
  lane.append(marker);
}
// A seam's clicks, its menu and drops from the library are handled once for the whole timeline: a film of 106 seams
// carried five listeners on each marker, made again on every redraw.
// A transition on the timeline stays on its seam: nothing there is moved by hand (user, 25 November 2026).
function markerJoin(event){const marker=event.target.closest?.('.transition-join');return marker?{marker,join:joinAt(marker.dataset.fromRef,marker.dataset.toRef)}:{};}
(()=>{
  const tracks=document.getElementById('timeline-tracks');if(!tracks)return;
  const dragged=event=>event.dataTransfer?.types.includes('application/x-videostudio-transition');
  tracks.addEventListener('click',event=>{const {marker,join}=markerJoin(event);if(!marker)return;event.stopPropagation();if(join)selectTransition(join);});
  tracks.addEventListener('contextmenu',event=>{
    const {join}=markerJoin(event);if(!join)return;
    event.preventDefault();event.stopPropagation();closeStackMenu();
    const menu=document.createElement('div');menu.className='stack-context-menu';const remove=document.createElement('button');remove.type='button';setTrashButton(remove,'Прибрати перехід');
    remove.addEventListener('click',()=>{closeStackMenu();action('set_join_transition',{from_ref:join.from_ref,to_ref:join.to_ref,type:'cut',duration:0},'Перехід прибрано.').catch(()=>{});});
    menu.append(remove);document.body.append(menu);menu.style.left=Math.min(event.clientX,window.innerWidth-menu.offsetWidth-8)+'px';menu.style.top=Math.min(event.clientY,window.innerHeight-menu.offsetHeight-8)+'px';
  });
  tracks.addEventListener('dragover',event=>{const {marker}=markerJoin(event);if(marker&&dragged(event)){event.preventDefault();marker.classList.add('join-drop');}});
  tracks.addEventListener('dragleave',event=>{const {marker}=markerJoin(event);if(marker&&!marker.contains(event.relatedTarget))marker.classList.remove('join-drop');});
  tracks.addEventListener('drop',event=>{
    const {marker}=markerJoin(event);if(!marker)return;const type=event.dataTransfer.getData('application/x-videostudio-transition');if(!type)return;
    event.preventDefault();event.stopPropagation();marker.classList.remove('join-drop');document.body.classList.remove('dragging-transition');
    applyTransitionAtMarker(marker,type,event.dataTransfer.getData('application/x-videostudio-transition-origin') || undefined).catch(()=>{});
  });
})();
let transitionLibraryFilter='all';
const transitionFavorites=new Set((()=>{try{const saved=JSON.parse(localStorage.getItem('studio.transitionFavorites')||'[]');return Array.isArray(saved)?saved:[];}catch{return [];}})());
function initTransitionLibrary(){
  const library=$('transition-library');library.replaceChildren();
  const filters=document.createElement('div');filters.className='transition-filters';
  for(const [filter,label] of [['all','Усі'],['cinematic','Кіно'],['capcut','CapCut'],['favorites','★ Обрані']]){const button=document.createElement('button');button.type='button';button.textContent=label;button.classList.toggle('active',transitionLibraryFilter===filter);button.setAttribute('aria-pressed',String(transitionLibraryFilter===filter));button.addEventListener('click',()=>{transitionLibraryFilter=filter;initTransitionLibrary();});filters.append(button);}library.append(filters);
  for(const [type,name] of Object.entries(transitionNames)){
    if(type==='cut')continue;
    if(transitionLibraryFilter==='favorites'&&!transitionFavorites.has(type))continue;
    if(transitionLibraryFilter==='cinematic'&&graphicTransitionPresets[type]?.kind!=='cinematic')continue;
    if(transitionLibraryFilter==='capcut'&&!isCapcutTransition(type))continue;
    const row=document.createElement('div');row.className='transition-item';const button=document.createElement('button');button.type='button';button.className='transition-chip transition-graphic transition-'+type;button.draggable=true;button.dataset.transition=type;button.setAttribute('aria-label',name);
    button.addEventListener('pointerdown',event=>beginTransitionDrag(event,type));
    const capcut=isCapcutTransition(type)&&capcutCatalog.transitions[type];
    const canvas=capcut?capcutPreviewVideo(type):document.createElement('canvas');if(capcut){canvas.className='capcut-thumb';button.addEventListener('mouseenter',()=>canvas.play().catch(()=>{}));button.addEventListener('mouseleave',()=>{canvas.pause();canvas.currentTime=0;canvas.load();});}else{canvas.width=160;canvas.height=90;}button.append(canvas);const label=document.createElement('span');label.textContent=name;button.append(label);if(!capcut)paintTransitionPreview(canvas,type,.3);let frame;
    const stop=()=>{cancelAnimationFrame(frame);if(!capcut)paintTransitionPreview(canvas,type,.3);};
    if(!capcut)button.addEventListener('mouseenter',()=>{const began=performance.now();cancelAnimationFrame(frame);const tick=now=>{if(!button.isConnected)return;paintTransitionPreview(canvas,type,((now-began)/1350)%1);frame=requestAnimationFrame(tick);};frame=requestAnimationFrame(tick);});button.addEventListener('mouseleave',stop);
    button.addEventListener('dragstart',event=>{stop();event.dataTransfer.effectAllowed='copyMove';event.dataTransfer.setData('application/x-videostudio-transition',type);event.dataTransfer.setData('text/plain',name);document.body.classList.add('dragging-transition');});
    button.addEventListener('dragend',()=>document.body.classList.remove('dragging-transition'));button.addEventListener('click',()=>status('Перетягніть перехід на стик двох сусідніх кадрів.'));
    const star=document.createElement('button');star.type='button';star.className='transition-favorite';const favorite=transitionFavorites.has(type);star.textContent=favorite?'★':'☆';star.setAttribute('aria-pressed',String(favorite));star.setAttribute('aria-label',(favorite?'Прибрати з обраних: ':'Додати в обрані: ')+name);star.title=favorite?'Прибрати з обраних':'Додати в обрані';star.addEventListener('click',()=>{if(transitionFavorites.has(type))transitionFavorites.delete(type);else transitionFavorites.add(type);try{localStorage.setItem('studio.transitionFavorites',JSON.stringify([...transitionFavorites]));}catch{status('Не вдалося зберегти обрані переходи.',true);}initTransitionLibrary();});row.append(button,star);library.append(row);
  }
  if(transitionLibraryFilter==='favorites'&&!library.querySelector('.transition-item')){const empty=document.createElement('p');empty.className='transition-empty';empty.textContent='Натисніть ☆ біля переходу, щоб додати його сюди';library.append(empty);}
}
initTransitionLibrary();
graphicTransitionReady.then(data=>{Object.assign(transitionNames,Object.fromEntries(Object.entries(data).map(([id,preset])=>[id,preset.name])));initTransitionLibrary();if(state.project){renderTimeline();if(state.selectedTransition)renderInspector();}}).catch(error=>status(error.message,true));
document.querySelector('.timeline-scroll').addEventListener('dragover',event=>{if(event.dataTransfer.types.includes('application/x-videostudio-transition'))event.preventDefault();});
document.querySelector('.timeline-scroll').addEventListener('drop',event=>{if(!event.dataTransfer.getData('application/x-videostudio-transition'))return;event.preventDefault();document.body.classList.remove('dragging-transition');status('Перехід не застосовано. Перетягніть його на підсвічений стик двох сусідніх кадрів.',true);});
