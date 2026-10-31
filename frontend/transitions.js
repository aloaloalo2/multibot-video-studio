const transitionNames={cut:'Склейка',crossfade:'Розчинення',slide_left:'Зсув ліворуч',slide_right:'Зсув праворуч',slide_up:'Зсув угору',slide_down:'Зсув униз',zoom_in:'М’яке наближення',zoom_out:'М’яке віддалення'};
let joinCacheToken='',joinCache=new Map();
let transitionPointerDrag=null,transitionSuppressClick=false;
function transitionDropTarget(x,y){
  const scroller=document.querySelector('.timeline-scroll'),bounds=scroller.getBoundingClientRect(),label=Number.parseFloat(getComputedStyle(scroller).getPropertyValue('--timeline-label-width'))||190;
  if(x<bounds.left+label||x>bounds.right||y<bounds.top||y>bounds.bottom)return null;
  let closest=null,distance=15;
  for(const marker of document.querySelectorAll('.transition-join')){const r=marker.getBoundingClientRect(),dx=Math.abs(x-(r.left+r.width/2));if(y>=r.top-4&&y<=r.bottom+4&&dx<distance){closest=marker;distance=dx;}}
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
  try{return await action('set_join_transition',{from_ref:marker.dataset.fromRef,to_ref:marker.dataset.toRef,type,duration:previous?.duration ?? (graphicTransitionPresets[type] ? .5 : .35),move_from:origin||undefined},'Перехід додано на стик.');}
  catch(error){if(following){state.selectedTransition=selected;renderInspector();}throw error;}
}
document.addEventListener('pointermove',event=>{
  const drag=transitionPointerDrag;if(!drag||event.pointerId!==drag.pointerId)return;
  if(!drag.moved&&Math.hypot(event.clientX-drag.x,event.clientY-drag.y)<5)return;
  if(!drag.moved){drag.moved=true;document.body.classList.add('dragging-transition');const ghost=document.createElement('div');ghost.className='transition-drag-ghost';ghost.textContent=transitionNames[drag.type];document.body.append(ghost);drag.ghost=ghost;}
  event.preventDefault();drag.ghost.style.left=event.clientX+14+'px';drag.ghost.style.top=event.clientY-30+'px';
  const marker=transitionDropTarget(event.clientX,event.clientY);for(const node of document.querySelectorAll('.join-drop'))node.classList.remove('join-drop');if(marker)marker.classList.add('join-drop');
});
document.addEventListener('pointerup',event=>{
  const drag=transitionPointerDrag;if(!drag||event.pointerId!==drag.pointerId)return;const marker=drag.moved?transitionDropTarget(event.clientX,event.clientY):null;transitionPointerDrag=null;if(drag.source.hasPointerCapture(event.pointerId))drag.source.releasePointerCapture(event.pointerId);drag.ghost?.remove();document.body.classList.remove('dragging-transition');for(const node of document.querySelectorAll('.join-drop'))node.classList.remove('join-drop');
  if(!drag.moved)return;event.preventDefault();transitionSuppressClick=true;setTimeout(()=>{transitionSuppressClick=false;},0);
  if(marker)applyTransitionAtMarker(marker,drag.type,drag.origin).catch(()=>{});else status('Перехід не застосовано. Перетягніть його на підсвічений стик двох сусідніх кадрів.',true);
});
document.addEventListener('pointercancel',()=>{transitionPointerDrag?.ghost?.remove();transitionPointerDrag=null;document.body.classList.remove('dragging-transition');for(const node of document.querySelectorAll('.join-drop'))node.classList.remove('join-drop');});
document.addEventListener('click',event=>{if(transitionSuppressClick){transitionSuppressClick=false;event.preventDefault();event.stopPropagation();}},true);
function transitionEndpoint(ref){if(ref?.startsWith('group:')){const group=sceneGroups().find(g=>g.id===ref.slice(6));return group?groupMembers(group):[];}if(ref?.startsWith('clip:'))return universalClips().filter(c=>c.id===ref.slice(5));return [];}
function transitionInfo(clip){
  const token=state.project?.id+':'+state.project?.revision;
  if(joinCacheToken!==token){joinCacheToken=token;joinCache=new Map();for(const join of state.project?.join_transitions || []){for(const c of transitionEndpoint(join.to_ref))joinCache.set(c.id,{...(joinCache.get(c.id)||{}),incoming:join});for(const c of transitionEndpoint(join.from_ref))if(Math.abs(Number(c.start)+Number(c.duration)-join.seam)<.05)joinCache.set(c.id,{...(joinCache.get(c.id)||{}),outgoing:join});}}
  return joinCache.get(clip.id) || {};
}
function visualFrameTime(time){const fps=Number(state.project?.fps||25);return Math.floor(Number(time)*fps+.5+1e-8)/fps;}
// A transition on whole video frames, as the export draws it (engine/render.py timeline_plan): 0.35 s at 25 fps
// lasts 9 frames there, and the preview used to run it 0.01 s faster.
function joinFrames(join){const fps=Number(state.project?.fps||25),seam=visualFrameTime(join.seam);return {seam,duration:Math.max(1/fps,visualFrameTime(Number(join.seam)+Number(join.duration))-seam)};}
function clipRenderStart(clip){return visualFrameTime(clip.start);}
function clipRenderEnd(clip){return visualFrameTime(Number(clip.start)+Number(clip.duration)+(transitionInfo(clip).outgoing?.duration || 0));}
function transitionValues(clip,local,values){
  const info=transitionInfo(clip),time=Number(clip.start)+local;
  // past its end an outgoing clip still moving keeps the speed of its last keyframe segment, one that stopped holds,
  // as the export (backend/joins.py transport)
  if(info.outgoing && local>Number(clip.duration))for(const prop of ['x','y','scale','opacity']){const points=keyframePoints(clip,prop,Number(clip[prop] ?? (prop==='x'||prop==='y'?.5:1)));if(!points.length)continue;const last=points.at(-1),before=points.at(-2) || last,span=last.time-before.time,moving=span>1e-9&&last.time>=Number(clip.duration)-.05;values[prop]=last.value+(moving?(last.value-before.value)/span:0)*(local-last.time);}
  for(const [direction,join] of [['in',info.incoming],['out',info.outgoing]]){if(!join || (direction==='in' && clip.kind==='text' && clip.text_role==='full_frame'))continue;const span=joinFrames(join),p=easedProgress((time-span.seam)/span.duration,'ease_in_out'),incoming=direction==='in',progress=incoming?1-p:p,type=join.type;
    if(graphicTransitionPresets[type]){
      const config=graphicTransitionPresets[type];
      if(config.kind==='cinematic'){
        values.opacity*=incoming?p:1-p;
      }else values.opacity*=incoming?(p>=.5?1:0):(p<.5?1:0);
      continue;
    }
    if(type==='crossfade')values.opacity*=incoming?p:1-p;
    if(type.startsWith('slide_')){if(type==='slide_left')values.x+=incoming?progress:-progress;if(type==='slide_right')values.x+=incoming?-progress:progress;if(type==='slide_up')values.y+=incoming?progress:-progress;if(type==='slide_down')values.y+=incoming?-progress:progress;}
    if(type.startsWith('zoom_')){const s=type==='zoom_in'?(incoming?.88+.12*p:1+.12*p):(incoming?1.12-.12*p:1-.12*p);values.x=.5+(values.x-.5)*s;values.y=.5+(values.y-.5)*s;values.scale*=s;values.opacity*=incoming?p:1-p;}
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
  const midpoint=()=>{const standard=graphicTransitionPresets[type.value] ? .5 : .35;return standard<limit?standard:(.05+limit)/2;};
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
function transitionJoinMarker(lane,left,right,seam,visualWidth=12){
  const active=(state.project.join_transitions || []).find(j=>j.from_ref===left&&j.to_ref===right),marker=document.createElement('button');marker.type='button';marker.className='transition-join'+(active?' has-transition':'')+(state.selectedTransition?.fromRef===left&&state.selectedTransition?.toRef===right?' selected-transition':'');marker.style.left=((seam-timelineOrigin())/timelineSpan()*100)+'%';marker.textContent=active?'◆':'+';marker.title=active?(transitionNames[active.type] || active.type)+' · натисніть для налаштувань':'Перетягніть сюди перехід';marker.setAttribute('aria-label','Стик '+clock(seam));marker.dataset.fromRef=left;marker.dataset.toRef=right;
  marker.style.width=visualWidth+'px';if(visualWidth<6){marker.classList.add('transition-compact');marker.textContent='';}
  if(active)marker.addEventListener('click',event=>{event.stopPropagation();selectTransition(active);});
  if(active)marker.addEventListener('pointerdown',event=>beginTransitionDrag(event,active.type,active.id));
  if(active)marker.addEventListener('contextmenu',event=>{event.preventDefault();event.stopPropagation();closeStackMenu();const menu=document.createElement('div');menu.className='stack-context-menu';const remove=document.createElement('button');remove.type='button';setTrashButton(remove,'Прибрати перехід');remove.addEventListener('click',()=>{closeStackMenu();action('set_join_transition',{from_ref:left,to_ref:right,type:'cut',duration:0},'Перехід прибрано.').catch(()=>{});});menu.append(remove);document.body.append(menu);menu.style.left=Math.min(event.clientX,window.innerWidth-menu.offsetWidth-8)+'px';menu.style.top=Math.min(event.clientY,window.innerHeight-menu.offsetHeight-8)+'px';});
  if(active){marker.draggable=true;marker.addEventListener('dragstart',event=>{event.dataTransfer.setData('application/x-videostudio-transition',active.type);event.dataTransfer.setData('application/x-videostudio-transition-origin',active.id);document.body.classList.add('dragging-transition');});marker.addEventListener('dragend',()=>document.body.classList.remove('dragging-transition'));}
  marker.addEventListener('dragover',event=>{if(event.dataTransfer.types.includes('application/x-videostudio-transition')){event.preventDefault();marker.classList.add('join-drop');}});marker.addEventListener('dragleave',()=>marker.classList.remove('join-drop'));
  marker.addEventListener('drop',event=>{const type=event.dataTransfer.getData('application/x-videostudio-transition');if(!type)return;event.preventDefault();event.stopPropagation();marker.classList.remove('join-drop');document.body.classList.remove('dragging-transition');applyTransitionAtMarker(marker,type,event.dataTransfer.getData('application/x-videostudio-transition-origin') || undefined).catch(()=>{});});lane.append(marker);
}
let transitionLibraryFilter='all';
const transitionFavorites=new Set((()=>{try{const saved=JSON.parse(localStorage.getItem('studio.transitionFavorites')||'[]');return Array.isArray(saved)?saved:[];}catch{return [];}})());
function initTransitionLibrary(){
  const library=$('transition-library');library.replaceChildren();
  const filters=document.createElement('div');filters.className='transition-filters';
  for(const [filter,label] of [['all','Усі'],['cinematic','Кіно'],['favorites','★ Обрані']]){const button=document.createElement('button');button.type='button';button.textContent=label;button.classList.toggle('active',transitionLibraryFilter===filter);button.setAttribute('aria-pressed',String(transitionLibraryFilter===filter));button.addEventListener('click',()=>{transitionLibraryFilter=filter;initTransitionLibrary();});filters.append(button);}library.append(filters);
  for(const [type,name] of Object.entries(transitionNames)){
    if(type==='cut')continue;
    if(transitionLibraryFilter==='favorites'&&!transitionFavorites.has(type))continue;
    if(transitionLibraryFilter==='cinematic'&&graphicTransitionPresets[type]?.kind!=='cinematic')continue;
    const row=document.createElement('div');row.className='transition-item';const button=document.createElement('button');button.type='button';button.className='transition-chip transition-graphic transition-'+type;button.draggable=true;button.dataset.transition=type;button.setAttribute('aria-label',name);
    button.addEventListener('pointerdown',event=>beginTransitionDrag(event,type));
    const canvas=document.createElement('canvas');canvas.width=160;canvas.height=90;button.append(canvas);const label=document.createElement('span');label.textContent=name;button.append(label);paintTransitionPreview(canvas,type,.3);let frame;
    const stop=()=>{cancelAnimationFrame(frame);paintTransitionPreview(canvas,type,.3);};
    button.addEventListener('mouseenter',()=>{const began=performance.now();cancelAnimationFrame(frame);const tick=now=>{if(!button.isConnected)return;paintTransitionPreview(canvas,type,((now-began)/1350)%1);frame=requestAnimationFrame(tick);};frame=requestAnimationFrame(tick);});button.addEventListener('mouseleave',stop);
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
