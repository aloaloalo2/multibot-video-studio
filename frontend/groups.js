/* Frame groups compact the timeline while preserving editable native clips. */
function sceneGroups(){return state.project?.scene_groups || [];}
// Rows are never moved by hand (user, 25 November 2026: «щоб я не міг переміщати ніякі слої»; the capture-phase
// dragstart guard at the end of this file): a heading keeps only what names its row.
function enableStackReorder(heading,ref){heading.draggable=false;heading.dataset.stackRef=ref;}
function enableLayerReorder(heading,layer){heading.draggable=false;heading.dataset.layerId=layer.id;}
let groupedRenderIndex=null;
// A grouped timeline asks for each group's members and bounds many times per draw; both are fixed for one project version.
function groupMembers(group){
  const cache=memoForProject('groupMembers',()=>new WeakMap());
  if(!cache.has(group))cache.set(group,findGroupMembers(group));
  return cache.get(group).slice();
}
function findGroupMembers(group){
  const ids=new Set(group.clip_ids);
  if(!groupedRenderIndex)return universalClips().filter(c=>ids.has(c.id));
  const matches=[];
  for(const id of ids)for(const item of groupedRenderIndex.get(id) || [])matches.push(item);
  return matches.sort((a,b)=>a.order-b.order).map(item=>item.clip);
}
function groupById(id){return memoForProject('groupById',()=>new Map(sceneGroups().map(group=>[group.id,group]))).get(id);}
function closeStackMenu(){document.querySelector('.stack-context-menu')?.remove();}
function stackOpen(entry){clearTransitionSelection();if(entry.ref==='scenes'){state.selectedStack='scenes';state.selected=null;state.selectedGroup=null;renderInspector();return;}if(entry.clip){state.selectedGroup=null;selectUniversalClip(entry.clip.id,false);return;}const group=entry.groups.find(g=>{const b=groupBounds(g);return state.playhead>=b.start&&state.playhead<b.end;}) || entry.groups[0];if(group)expandFrameGroup(group);}
function addStackTools(heading,entry){
  const title=document.createElement('span');title.className='stack-title';title.textContent=entry.title;heading.replaceChildren(title);if(entry.layer){addLayerEyeControl(heading,entry.layer);addLayerSoundControl(heading,entry.layer);if(typeof addLayerDubControl==='function')addLayerDubControl(heading,entry.layer);}
  else if(entry.groups?.length){const ids=new Set(entry.groups.flatMap(group=>group.clip_ids || []));addLayerEyeControl(heading,layers().filter(layer=>(layer.clips || []).some(clip=>ids.has(clip.id))),entry.title);}
  const button=document.createElement('button');button.type='button';button.className='stack-menu-button';button.textContent='⋮';button.setAttribute('aria-label','Дії доріжки '+entry.title);
  const open=event=>{event.preventDefault();event.stopPropagation();closeStackMenu();const menu=document.createElement('div');menu.className='stack-context-menu';menu.setAttribute('role','menu');
    const items=[['Відкрити властивості',()=>stackOpen(entry)]];
    if(entry.clip)items.push(['Перейменувати',()=>modal('Назва доріжки',`<label>Назва<input id="stack-new-name" value="${esc(entry.title)}" maxlength="120"></label>`,[{label:'Зберегти',primary:true,run:async()=>{try{await action('batch',{actions:[{type:'update_layer',payload:{layer_id:entry.layer.id,name:$('stack-new-name').value}},{type:'update_clip',payload:{clip_id:entry.clip.id,patch:{title:$('stack-new-name').value}}}]},'Назву збережено.');closeModal();}catch(error){status(error.message,true);}}}])]);
    else if(entry.groups.length===1)items.push(['Перейменувати',()=>{selectFrameGroup(entry.groups[0]);$('frame-title')?.select();}]);
    if(entry.clip)items.push(['Прибрати доріжку',()=>modal('Прибрати доріжку',`<p>Прибрати «${esc(entry.title)}»? Дію можна скасувати.</p>`,[{label:'Прибрати',primary:true,run:async()=>{try{await action('delete_clip',{clip_id:entry.clip.id},'Доріжку прибрано.');closeModal();}catch(error){status(error.message,true);}}}])]);
    for(const [name,run] of items){const item=document.createElement('button');item.type='button';if(name.startsWith('Прибрати'))setTrashButton(item,name);else item.textContent=name;item.setAttribute('role','menuitem');item.addEventListener('click',()=>{closeStackMenu();run();});menu.append(item);}
    document.body.append(menu);const rect=heading.getBoundingClientRect();menu.style.left=Math.min(window.innerWidth-menu.offsetWidth-8,event.type==='contextmenu'?event.clientX:rect.right-20)+'px';menu.style.top=Math.min(window.innerHeight-menu.offsetHeight-8,rect.bottom)+'px';
  };
  button.addEventListener('click',open);heading.addEventListener('contextmenu',open);heading.addEventListener('dblclick',event=>{if(event.target.closest('button,input,select,a'))return;stackOpen(entry);});heading.addEventListener('click',event=>{if(event.target.closest('.stack-menu-button,.layer-sound'))return;if(entry.ref==='scenes'){selectTimelineIds(entry.groups.flatMap(group=>group.clip_ids),event.metaKey||event.ctrlKey||event.shiftKey);return;}if(entry.clip){state.activeLayer=entry.layer.id;selectTimelineIds([entry.clip.id],event.metaKey||event.ctrlKey||event.shiftKey);}else{const group=entry.groups.find(g=>{const b=groupBounds(g);return state.playhead>=b.start&&state.playhead<b.end;}) || entry.groups[0];selectFrameGroup(group);}});heading.append(button);
}
document.addEventListener('pointerdown',event=>{if(!event.target.closest('.stack-context-menu,.stack-menu-button'))closeStackMenu();},true);
document.addEventListener('keydown',event=>{if(event.key==='Escape')closeStackMenu();});
function groupBounds(group){
  const cache=memoForProject('groupBounds',()=>new WeakMap());
  if(!cache.has(group)){const clips=groupMembers(group);cache.set(group,{start:Math.min(...clips.map(c=>Number(c.start))),end:Math.max(...clips.map(c=>Number(c.start)+Number(c.duration)))});}
  return {...cache.get(group)};
}

function renderGroupingControls(){
  renderCompositionTabs();prepareTimelineMenu();
  if(state.expandedGroup&&!sceneGroups().some(g=>g.id===state.expandedGroup))state.expandedGroup=null;
  if(state.selectedGroup&&!sceneGroups().some(g=>g.id===state.selectedGroup))state.selectedGroup=null;
  const toolbar=document.querySelector('.timeline-toolbar');
  let box=$('timeline-group-controls');
  if(!box){box=document.createElement('div');box.id='timeline-group-controls';box.className='timeline-group-controls';toolbar.insertBefore(box,toolbar.querySelector('.timeline-spacer'));}
  box.replaceChildren();
  const repairFrames=selectedRepairFrames();
  if(repairFrames.length){
    const repair=document.createElement('button');repair.type='button';repair.id='repair-selected-frames';repair.className='secondary';
    repair.textContent='Внести правки';repair.title=repairFrames.length===1?`Правки до кадру ${repairFrames[0]}`:`Правки до ${repairFrames.length} кадрів`;
    repair.addEventListener('click',()=>openFrameRepair(repairFrames));box.append(repair);
  }
  const remove=document.createElement('button');remove.type='button';setTrashButton(remove,'Видалити виділене',true);remove.disabled=state.busy || !(state.selected || state.selectedGroup || state.multiSelection?.length);remove.addEventListener('click',deleteTimelineSelection);
  if(state.selected || state.selectedGroup || state.multiSelection?.length)box.append(remove);

  if(!state.expandedGroup && (state.multiSelection?.length || 0)>=2 && state.multiSelection.length<=200 && !sceneGroups().some(group=>group.clip_ids.some(id=>state.multiSelection.includes(id)))){const group=document.createElement('button');group.type='button';group.id='group-selection';group.textContent='Згрупувати ('+state.multiSelection.length+')';group.addEventListener('click',()=>createSelectedGroup());box.append(group);}
}

function toggleClipSelection(id){
  state.selectedTransition=null;
  const selected=new Set(state.multiSelection || []);
  if(state.selected)selected.add(state.selected);
  selected.has(id)?selected.delete(id):selected.add(id);state.multiSelection=[...selected];state.selected=null;state.selectedGroup=null;
  if(!refreshTimelineSelection())renderTimeline();status(`Вибрано елементів: ${selected.size}. Натисніть «Згрупувати».`);
}

function createSelectedGroup(){
  const clipIds=[...(state.multiSelection || [])];if(clipIds.length<2)return;
  modal('Згрупувати кадр','<label>Назва кадру<input id="new-frame-name" value="Новий кадр" maxlength="120"></label>',[{label:'Згрупувати',primary:true,run:async()=>{try{await action('group_clips',{clip_ids:clipIds,title:$('new-frame-name').value,default_background:true},'Кадр згруповано.');state.multiSelection=[];state.compactTimeline=true;closeModal();renderTimeline();}catch(error){status(error.message,true);}}}]);
}

function selectFrameGroup(group){clearTransitionSelection();state.selectedStack=null;state.selected=null;state.selectedGroup=group.id;state.multiSelection=[];refreshTimelineSelection();renderInspector();renderPreview();}
// A selection changes only the marks of the blocks already drawn, never the timeline itself: a click used to draw
// all 650 blocks again with their waveforms (about 290 ms on Andromeda, 25 November 2026). Answers false when there is
// no drawn timeline to mark, so the caller may draw it.
function refreshTimelineSelection(){
  const tracks=document.querySelectorAll('#timeline-tracks .track-row');
  renderGroupingControls();
  if(!tracks.length)return false;
  const chosen=new Set(state.multiSelection || []);
  for(const node of document.querySelectorAll('#timeline-tracks [data-clip-id]')){
    const id=node.dataset.clipId;node.classList.toggle('selected',state.selected===id);node.classList.toggle('multi-selected',chosen.has(id));
  }
  for(const node of document.querySelectorAll('#timeline-tracks [data-group-id]')){
    const id=node.dataset.groupId,group=groupById(id);
    node.classList.toggle('selected',state.selectedGroup===id || !!(chosen.size&&group?.clip_ids.length&&group.clip_ids.every(clip=>chosen.has(clip))));
  }
  for(const lane of document.querySelectorAll('#timeline-tracks .track-lane[data-layer-id]'))lane.closest('.track-row')?.classList.toggle('active-layer',state.activeLayer===lane.dataset.layerId);
  return true;
}
function expandFrameGroup(group){
  state.selectedTransition=null;
  if(!state.expandedGroup)state.groupPreviousZoom=state.zoom;
  state.compositionTabs=state.compositionTabs || [];if(!state.compositionTabs.includes(group.id))state.compositionTabs.push(group.id);
  stopPlayback();state.expandedGroup=group.id;state.selectedGroup=group.id;state.selected=null;state.compactTimeline=true;
  const bounds=groupBounds(group);state.playhead=bounds.start;state.zoom=1;renderTimeline();
  document.querySelector('.timeline-scroll').scrollLeft=0;document.querySelector('.timeline-scroll').scrollTop=0;
  renderInspector();renderPreview();
}

function frameBlock(clip){return clip.kind==='animation'&&clip.content_type==='shape'&&!clip.asset_id&&/^Razgon · кадр/.test(clip.title || '');}
// a frame block whose scene the agent has drawn (director.js framesDrawn): a made frame, grey like any other made frame;
// only the export renders it
function draftFrameClip(clip){return frameBlock(clip)&&!!(typeof framesDrawn==='function'&&framesDrawn()?.has(Number(/кадр (\d+)/.exec(clip.title)?.[1])));}
function emptyFrameClip(clip){return frameBlock(clip)&&!draftFrameClip(clip);}

function plannedTimelineFrames(){return directMontage()?[]:(state.plan?.frames || []).filter(frame=>Number.isFinite(Number(frame.start))&&Number(frame.end)>Number(frame.start));}
function missingPlannedFrames(frames,bounds){
  return frames.filter(frame=>!bounds.some(b=>b.start<=Number(frame.start)+.04&&b.end>=Number(frame.end)-.04));
}
function appendPlannedFrames(lane,groups){
  const missing=missingPlannedFrames(plannedTimelineFrames(),groups.filter(group=>groupMembers(group).length).map(groupBounds));
  for(const frame of missing){
    const block=document.createElement('button');block.type='button';block.className='planned-frame-guide';
    block.dataset.plannedFrame=frame.number;block.textContent=frame.number;
    block.style.left=((Number(frame.start)-timelineOrigin())/timelineSpan()*100)+'%';
    block.style.width=((Number(frame.end)-Number(frame.start))/timelineSpan()*100)+'%';
    block.setAttribute('aria-label',`Кадр ${frame.number} · заплановано`);
    block.title=`Кадр ${frame.number} · ${clock(frame.start)} - ${clock(frame.end)} · ${planFormatNames[frame.format]||frame.format}\n${frame.visual?.idea||frame.idea||''}`;
    lane.append(block);
  }
}

function groupLane(title,groups,ref){
  const row=document.createElement('div');row.className='track-row universal-row grouped-row';
  const label=document.createElement('div');label.className='layer-heading group-heading';label.textContent=title;
  if(ref&&groups.length)enableStackReorder(label,ref);
  if(ref&&groups.length)addStackTools(label,{ref,groups,title});
  const lane=document.createElement('div');lane.className='track-lane universal-lane frame-group-lane';lane.style.width=timelineWidth()+'px';
  if(ref==='scenes')appendPlannedFrames(lane,groups);
  const occupied=[],chosen=new Set(state.multiSelection || []);
  for(const group of groups){
    const bounds=groupBounds(group),members=groupMembers(group);if(!members.length)continue;
    let slot=ref==='scenes'?0:occupied.findIndex(end=>end<=bounds.start+.001);if(slot<0)slot=occupied.length;occupied[slot]=bounds.end;
    const button=document.createElement('button');button.type='button';button.draggable=false;button.className='frame-group-clip';button.dataset.groupId=group.id;
    button.classList.add(members.some(c=>c.kind==='animation'&&c.content_type==='image')?'group-animation':'group-text');
    // an animated film's frame that is still only the director's code block, not a drawn picture yet, reads as empty
    if(members.every(emptyFrameClip))button.classList.add('group-empty');
    // a Razgon frame drawn as code is grey like every made frame, one already rendered into video green (user, 31 October
    // 2026: «створені кодом кадри сірі, відрендерені вже відео можуть бути зелені»); a frame not drawn yet stays dark
    // green only while that video is really there: a render whose file went with a deleted episode folder leaves the
    // frame as code, grey (user, 2 November 2026: «чому кадри зелені, якщо це просто код»)
    else if(members.some(c=>['video','image'].includes(c.kind)&&/^Razgon · кадр/.test(c.title || '')&&!state.assetsLoading&&(state.assets || []).some(asset=>asset.id===c.asset_id)))button.classList.add('group-made');
    Object.assign(button.style,{left:(bounds.start/timelineSpan()*100)+'%',width:((bounds.end-bounds.start)/timelineSpan()*100)+'%',top:(2+slot*29)+'px'});
    // a frame of the host's HeyGen video shows its still again and again across the block, as a film strip (user,
    // 25 November 2026: «замість сірого… стоп-кадр його… по пару раз один за одним… щоб я знав, що це відео фрагмент»),
    // always the block's full height and centred, so a narrow block shows the middle of the still («на всю по висоті…
    // відцентровано»)
    // the channel logo's row shows the logo the same way (user, 25 November 2026: «Логотип так само»)
    const hostVideo=members.find(c=>c.kind==='video'&&isHostVideo(c,group));
    if(hostVideo){button.classList.add('group-host-video');   // the stills 35% more transparent (user, 25 November 2026)
      button.style.setProperty('--strip',`url("/api/projects/${encodeURIComponent(state.project.id)}/assets/${encodeURIComponent(hostVideo.asset_id)}/thumbnail")`);}
    // the logo layer is a frame-sized picture with the logo in a corner: the strip shows the channel's own logo file,
    // spaced evenly along the row
    // (the plate of the channel's settings, 65% more transparent: user, 25 November 2026)
    else if(group.role==='overlay'&&members.some(isChannelLogo)&&state.project?.channel_id){button.classList.add('group-plate-strip');
      button.style.setProperty('--plate',`url("/api/channels/${encodeURIComponent(state.project.channel_id)}/logo")`);}
    const number=group.title.match(/\d+/)?.[0],shownTitle=groupDisplayTitle(group);button.textContent=(bounds.end-bounds.start)/timelineSpan()*timelineWidth()<22||group.role==='overlay'?'':number || shownTitle;button.title=`${shownTitle} · ${clock(bounds.start)} - ${clock(bounds.end)} · ${members.length} елементів. Подвійний клік відкриває кадр.`;
    button.setAttribute('aria-label',`${group.title}, ${members.length} елементів`);if(group.id===state.selectedGroup || group.clip_ids.every(id=>chosen.has(id)))button.classList.add('selected');
    lane.append(button);
  }
  lane.style.height=(Math.max(1,occupied.length)*29+2)+'px';
  if(ref==='scenes'){const sorted=[...groups].sort((a,b)=>groupBounds(a).start-groupBounds(b).start);for(let i=1;i<sorted.length;i++){const previous=groupBounds(sorted[i-1]),next=groupBounds(sorted[i]);if(Math.abs(previous.end-next.start)<=1/Number(state.project.fps || 25)+.001){const nearby=Math.min(previous.end-previous.start,next.end-next.start)*timelineWidth()/timelineSpan();const width=Math.max(2,Math.min(12,nearby*.9));transitionJoinMarker(lane,'group:'+sorted[i-1].id,'group:'+sorted[i].id,previous.end,width);}}}
  row.append(label,lane);return row;
}

function renderGroupedTimeline(){
  const previousIndex=groupedRenderIndex;
  groupedRenderIndex=new Map();
  universalClips().forEach((clip,order)=>{const entries=groupedRenderIndex.get(clip.id) || [];entries.push({clip,order});groupedRenderIndex.set(clip.id,entries);});
  try{return renderGroupedTimelineWithIndex();}finally{groupedRenderIndex=previousIndex;}
}

function compactSoundRows(entries){
  const rows=[],families=new Map();
  for(const entry of entries){
    const clip=entry.clip,title=clip?.title||'';
    const family=clip?.kind==='audio'&&entry.layer.clips.every(c=>c.kind==='audio')
      ? /^(?:Звук ролика · )?(?:музика|музыка|music)(?:\s|$)/iu.test(title)?'music'
        : /^Звук (?:ролика|переходу|друку|олівця|появи) · /u.test(title)?'sfx':null : null;   // every effect, transition, typing and pencil sounds too, is SFX (user, 21 and 25 November 2026: «звук друку… то ж є спеціальна SFX дорожка»)
    if(!family){rows.push(entry);continue;}
    let row=families.get(family);
    if(!row){row={title:family==='music'?'Музика':'SFX',soundFamily:family,soundItems:[],z:entry.z};families.set(family,row);rows.push(row);}
    row.soundItems.push(entry);row.z=Math.max(row.z,entry.z);
  }
  for(const row of families.values())row.soundItems.sort((a,b)=>Number(a.clip.start)-Number(b.clip.start));
  return rows;
}

// the clips the grouped timeline drew, by id, for the one click listener of all of them (below)
let groupedClipTargets=new Map();
function appendGroupedMediaClip(lane,{clip,layer}){
  const button=document.createElement('button');button.type='button';button.className='track-clip universal-clip grouped-media kind-'+clip.kind+(emptyFrameClip(clip)?' empty-frame':draftFrameClip(clip)?' draft-frame':'');button.dataset.clipId=clip.id;groupedClipTargets.set(clip.id,{clip,layer});if(state.selected===clip.id)button.classList.add('selected');if(state.multiSelection?.includes(clip.id))button.classList.add('multi-selected');button.textContent=clip.kind==='audio'?'':clipLabel(clip);   /* a sound shows only its waveform; its name stays in the tooltip (user, 25 November 2026: «на SFX… прибери взагалі назви… залиш там лише волни») */button.title=clipLabel(clip);button.setAttribute('aria-label',clipLabel(clip));Object.assign(button.style,{left:((Number(clip.start)-timelineOrigin())/timelineSpan()*100)+'%',width:(Number(clip.duration)/timelineSpan()*100)+'%'});if(clip.kind==='audio')drawAudioWaveform(button,clip);if(layer.muted)button.style.opacity='.45';lane.append(button);
}

function soundLane(entry){
  const row=document.createElement('div');row.className='track-row universal-row soundtrack-row';
  const label=document.createElement('div');label.className='layer-heading group-heading';
  const title=document.createElement('button');title.type='button';title.className='layer-name';title.textContent=entry.title;title.title=`${entry.soundItems.length} звукових фрагментів`;
  title.addEventListener('click',event=>selectTimelineIds(entry.soundItems.map(item=>item.clip.id),event.metaKey||event.ctrlKey||event.shiftKey));label.append(title);
  const lane=document.createElement('div');lane.className='track-lane universal-lane';lane.style.width=timelineWidth()+'px';
  for(const item of entry.soundItems)appendGroupedMediaClip(lane,item);
  row.append(label,lane);addLayerSoundControl(label,[...new Set(entry.soundItems.map(item=>item.layer))],entry.title);return row;
}

function renderGroupedTimelineWithIndex(){
  groupedClipTargets=new Map();
  const ruler=$('time-ruler'),tracks=$('timeline-tracks');ruler.replaceChildren();tracks.replaceChildren();ruler.className='time-ruler universal-ruler';
  const label=document.createElement('div');label.className='track-label';ruler.append(label);
  const marks=document.createElement('div');marks.className='time-ruler-marks';marks.style.width=timelineWidth()+'px';
  renderTimelineRulerMarks(marks,timelineSpan(),timelineWidth());ruler.append(marks);
  const scenes=sceneGroups().filter(g=>g.role!=='overlay').sort((a,b)=>groupBounds(a).start-groupBounds(b).start);
  const index=new Map();layers().forEach((layer,i)=>{for(const c of layer.clips || [])index.set(c.id,i);});
  let rows=[];
  if(scenes.length||plannedTimelineFrames().length)rows.push({title:'Кадри · '+Math.max(scenes.length,plannedTimelineFrames().length),groups:scenes,ref:'scenes',z:scenes.length?Math.max(...scenes.flatMap(g=>g.clip_ids.map(id=>index.get(id) ?? -1))):-1});
  for(const group of sceneGroups().filter(g=>g.role==='overlay'))rows.push({title:groupDisplayTitle(group),groups:[group],ref:'group:'+group.id,z:Math.max(...group.clip_ids.map(id=>index.get(id) ?? -1))});
  const grouped=new Set(sceneGroups().flatMap(g=>g.clip_ids));
  for(const layer of layers())for(const clip of layer.clips || [])if(!grouped.has(clip.id))rows.push({title:clipLabel(clip),clip,layer,ref:'layer:'+layer.id,z:index.get(clip.id)});
  // the higher the row, the higher its layer in the picture; sound rows go under all of them (universal.js timelineRowOrder)
  rows=compactSoundRows(rows);
  const sound=entry=>entry.soundItems?(entry.soundFamily==='music'?2:3):!entry.groups&&entry.clip.kind==='audio'?1:0;
  rows.sort((a,b)=>sound(a)-sound(b) || b.z-a.z);
  for(const entry of rows){
    if(entry.groups){tracks.append(groupLane(entry.title,entry.groups,entry.ref));continue;}
    if(entry.soundItems){tracks.append(soundLane(entry));continue;}
    const row=document.createElement('div');row.className='track-row universal-row';const label=document.createElement('div');label.className='layer-heading group-heading';label.textContent=entry.title;enableStackReorder(label,entry.ref);addStackTools(label,entry);
    const lane=document.createElement('div');lane.className='track-lane universal-lane';lane.style.width=timelineWidth()+'px';
    appendGroupedMediaClip(lane,entry);row.append(label,lane);tracks.append(row);
  }
}

function prepareTimelineMenu(){
  if($('timeline-add-menu'))return;
  const toolbar=document.querySelector('.timeline-toolbar');
  const menu=document.createElement('details');menu.id='timeline-add-menu';menu.className='timeline-add-menu';menu.style.display='none';
  const summary=document.createElement('summary');summary.textContent='＋ Додати';summary.setAttribute('aria-label','Додати елемент на таймлайн');menu.append(summary);
  const content=document.createElement('div');content.className='timeline-add-options';
  for(const id of ['add-layer','add-scene','add-text','add-animation','add-transition']){const button=$(id);if(button){content.append(button);button.addEventListener('click',()=>{menu.open=false;});}}
  const gradient=document.createElement('button');gradient.type='button';gradient.textContent='Градієнт 4 точки';gradient.addEventListener('click',()=>{menu.open=false;openGradientClip().catch(error=>status(error.message,true));});content.append(gradient);
  menu.append(content);toolbar.insertBefore(menu,toolbar.querySelector('.timeline-spacer'));
}

function renderCompositionTabs(){
  if(state.compositionProject!==state.project?.id){state.compositionProject=state.project?.id;state.compositionTabs=[];state.expandedGroup=null;state.selectedGroup=null;}
  let bar=$('composition-tabs');if(!bar){bar=document.createElement('div');bar.id='composition-tabs';bar.className='composition-tabs';bar.setAttribute('role','tablist');bar.setAttribute('aria-label','Композиції таймлайна');document.querySelector('.timeline-toolbar h2').after(bar);}
  bar.replaceChildren();
  const main=document.createElement('button');main.type='button';main.className='composition-tab'+(!state.expandedGroup?' active':'');main.textContent='Увесь ролик';main.setAttribute('role','tab');main.setAttribute('aria-selected',String(!state.expandedGroup));main.addEventListener('click',()=>{stopPlayback();state.expandedGroup=null;state.selected=null;state.selectedGroup=null;state.zoom=state.groupPreviousZoom || 1;renderTimeline();renderInspector();renderPreview();});const mainWrap=document.createElement('div');mainWrap.className='composition-tab-wrap composition-main-tab';mainWrap.append(main);bar.append(mainWrap);
  // the author writes any change to the film and Claude makes it (user, 15 November 2026)
  if(state.project?.production_request?.id&&!state.expandedGroup){const ask=document.createElement('button');ask.type='button';ask.className='claude-ask-button';ask.title='Попросити Claude змінити ролик';ask.setAttribute('aria-label','Попросити Claude змінити ролик');ask.innerHTML=typeof projectCostIcons==='object'?projectCostIcons.claude_code:'✦';ask.addEventListener('click',()=>{const numbers=selectedRepairFrames();openFrameRepair(numbers,{film:!numbers.length});});bar.append(ask);}
  state.compositionTabs=(state.compositionTabs || []).filter(id=>sceneGroups().some(g=>g.id===id));
  for(const id of state.compositionTabs){const group=sceneGroups().find(g=>g.id===id);const wrapper=document.createElement('div');wrapper.className='composition-tab-wrap';const button=document.createElement('button');button.type='button';button.className='composition-tab'+(state.expandedGroup===id?' active':'');button.textContent=group.title;button.setAttribute('role','tab');button.setAttribute('aria-selected',String(state.expandedGroup===id));button.addEventListener('click',()=>expandFrameGroup(group));const close=document.createElement('button');close.type='button';close.className='composition-close';close.textContent='×';close.setAttribute('aria-label','Закрити вкладку '+group.title);close.addEventListener('click',()=>{state.compositionTabs=state.compositionTabs.filter(x=>x!==id);if(state.expandedGroup===id){stopPlayback();state.expandedGroup=null;state.selected=null;state.selectedGroup=null;state.zoom=state.groupPreviousZoom || 1;}renderTimeline();renderInspector();renderPreview();});wrapper.append(button,close);bar.append(wrapper);}
}

function renderGroupInspector(){
  const group=sceneGroups().find(g=>g.id===state.selectedGroup);if(!group)return;
  const box=$('universal-inspector');$('inspector-fields').hidden=true;$('inspector-empty').hidden=true;box.hidden=false;
  const bounds=groupBounds(group),members=groupMembers(group);
  box.innerHTML=`<div class="universal-properties"><strong>${esc(group.title)}</strong><small>${clock(bounds.start)} - ${clock(bounds.end)} · ${members.length} елементів</small><button id="open-frame-layers" type="button">Відкрити елементи кадру</button><section><h3>Елементи кадру</h3><div id="frame-member-list" class="frame-member-list"></div></section><section><label>Назва<input id="frame-title" value="${esc(group.title)}"></label><button id="save-frame-title" type="button">Зберегти назву</button></section><button id="ungroup-frame" class="secondary" type="button">Розгрупувати кадр</button><button id="delete-frame" class="danger trash-button" type="button">${trashIcon}<span>Прибрати кадр</span></button></div>`;
  $('open-frame-layers').addEventListener('click',()=>expandFrameGroup(group));
  if(members.some(c=>c.visual_effect)){const remove=document.createElement('button');remove.type='button';setTrashButton(remove,'Прибрати ефекти кадру');remove.addEventListener('click',()=>action('batch',{actions:members.filter(c=>c.visual_effect).map(c=>({type:'update_clip',payload:{clip_id:c.id,patch:{visual_effect:null}}}))},'Ефекти кадру прибрано.').catch(()=>{}));box.querySelector('.universal-properties').append(remove);}
  for(const clip of members){const button=document.createElement('button');button.type='button';button.className='frame-member';button.textContent=clipLabel(clip);button.addEventListener('click',()=>{expandFrameGroup(group);state.selectedGroup=null;selectUniversalClip(clip.id);});$('frame-member-list').append(button);}
  $('save-frame-title').addEventListener('click',()=>action('update_group',{group_id:group.id,title:$('frame-title').value},'Назву кадру збережено.').catch(()=>{}));
  $('ungroup-frame').addEventListener('click',async()=>{try{await action('ungroup_clips',{group_id:group.id},'Кадр розгруповано.');state.selectedGroup=null;state.expandedGroup=null;renderTimeline();renderInspector();}catch(error){status(error.message,true);}});
  $('delete-frame').addEventListener('click',()=>modal('Прибрати кадр',`<p>Прибрати «${esc(group.title)}» та його ${members.length} елементів? Дію можна скасувати.</p>`,[{label:'Прибрати',primary:true,run:async()=>{try{await action('delete_group',{group_id:group.id},'Кадр прибрано.');state.selectedGroup=null;state.expandedGroup=null;closeModal();renderTimeline();renderInspector();}catch(error){status(error.message,true);}}}]));
}

// a clip of the grouped timeline, chosen without drawing the timeline again (universal.js selectUniversalClip draws it)
function selectTimelineClip(id){
  const target=groupedClipTargets.get(id);if(!target)return;
  clearTransitionSelection();state.selectedStack=null;state.selected=id;state.activeLayer=target.layer.id;state.replaceMode=false;
  if(!refreshTimelineSelection())renderTimeline();
  renderInspector();renderPreview();status(`Вибрано кліп «${clipLabel(target.clip)}».`);
}
// One listener for every frame block, planned frame and clip of the grouped timeline: 460 blocks of Andromeda carried
// their own, made again on every redraw.
(()=>{
  const tracks=document.getElementById('timeline-tracks');if(!tracks)return;
  tracks.addEventListener('click',event=>{
    const add=event.metaKey||event.ctrlKey||event.shiftKey;
    const block=event.target.closest('.frame-group-clip');
    if(block){event.stopPropagation();const group=groupById(block.dataset.groupId);if(!group)return;if(add)selectTimelineIds(group.clip_ids,true);else selectFrameGroup(group);return;}
    const planned=event.target.closest('.planned-frame-guide');
    if(planned){event.stopPropagation();status(`Кадр ${planned.dataset.plannedFrame} заплановано. Готовий матеріал з’явиться тут після створення.`);return;}
    const media=event.target.closest('.grouped-media'),target=media&&groupedClipTargets.get(media.dataset.clipId);
    if(!target)return;
    state.activeLayer=target.layer.id;
    if(add){selectTimelineIds([target.clip.id],true);return;}
    state.multiSelection=[];state.selectedGroup=null;selectTimelineClip(target.clip.id);
  });
  tracks.addEventListener('dblclick',event=>{const block=event.target.closest('.frame-group-clip'),group=block&&groupById(block.dataset.groupId);if(group)expandFrameGroup(group);});
})();

function selectTimelineIds(ids,append=false){
  const previousGroup=sceneGroups().find(group=>group.id===state.selectedGroup);
  clearTransitionSelection();state.selectedGroup=null;state.selectedStack=null;
  const chosen=new Set(append?[...(state.multiSelection || []),...(state.selected?[state.selected]:[]),...(previousGroup?.clip_ids || [])]:[]);
  for(const id of ids)chosen.add(id);
  state.selected=null;state.multiSelection=[...chosen];
  if(typeof refreshTimelineSelection!=='function'||!refreshTimelineSelection())renderTimeline();
  renderInspector();
}

function selectedRepairFrames(){
  if(!state.project?.production_request)return [];
  const selected=new Set([...(state.multiSelection || []),...(state.selected?[state.selected]:[])]);
  const clips=new Map(universalClips().map(clip=>[clip.id,clip]));
  const valid=new Set((state.plan?.frames || []).map(frame=>Number(frame.number)));
  const numbers=[];
  for(const group of sceneGroups()){
    if(group.role==='overlay'||!(group.id===state.selectedGroup||group.clip_ids.some(id=>selected.has(id))))continue;
    const source=group.clip_ids.map(id=>clips.get(id)?.title || '').find(title=>/^Razgon · кадр \d+/.test(title));
    const n=Number(source?.match(/кадр (\d+)/)?.[1] || group.title.match(/^Кадр\s+(\d+)$/)?.[1]);
    if(valid.has(n))numbers.push(n);
  }
  return [...new Set(numbers)].sort((a,b)=>a-b);
}

function openFrameRepair(numbers=selectedRepairFrames(),{film=false}={}){
  if(!numbers.length&&!film)return;
  const pid=state.project.id,clientId=crypto.randomUUID();
  modal(film?'Що змінити в ролику?':numbers.length===1?`Правки до кадру ${numbers[0]}`:'Правки до вибраних кадрів',
    `<div class="frame-repair-dialog"><div class="frame-repair-numbers">${film?'<span>Увесь ролик</span>':numbers.map(n=>`<span>Кадр ${n}</span>`).join('')}</div><label for="frame-repair-notes">Що змінити?</label><textarea id="frame-repair-notes" rows="5" maxlength="4000" placeholder="${film?'Напишіть, що змінити чи виправити: кадри, текст, переходи, звук, монтаж…':'Опишіть, що виправити у вибраних кадрах…'}"></textarea><p>${film?'Claude сам знайде, чого стосується правка, і змінить лише це.':'Режисер отримає вибрані кадри та готові матеріали проєкту.'}</p><p class="frame-repair-error" role="status"></p></div>`,
    [{label:'Додати в чергу',primary:true,run:async()=>{
      const field=$('frame-repair-notes'),error=document.querySelector('.frame-repair-error');
      if(state.project?.id!==pid)return;
      const notes=field.value.trim();if(!notes){error.textContent='Опишіть потрібні зміни.';field.focus();return;}
      const button=$('modal-actions').querySelector('button');button.disabled=true;button.textContent='Надсилаємо…';
      try{
        await api(`/api/projects/${encodeURIComponent(pid)}/production-edits`,'POST',{notes,frame_numbers:numbers,client_id:clientId});
        if(state.project?.id!==pid)return;
        delete frameEditQueueReads[pid];clearTimeout(frameEditQueueTimers[pid]);
        closeModal();renderGroupingControls();renderMontageMake();status('Правки збережено в черзі. Режисер виконає їх по черзі.');
      }catch(e){if(state.project?.id!==pid)return;error.textContent=e.message;button.disabled=false;button.textContent='Додати в чергу';}
    }}]);
}

const frameEditQueueReads={},frameEditQueueTimers={};
function refreshFrameEdits(make,pid){
  const slot=make.querySelector('.frame-edit-queue');if(!slot)return;
  const cached=frameEditQueueReads[pid];
  const draw=data=>{
    slot.replaceChildren();
    for(const job of data.jobs.filter(j=>['queued','starting','running','failed'].includes(j.status)).slice(-5)){
      const row=document.createElement('div');row.className='frame-edit-queue-row';row.dataset.status=job.status;
      if(['starting','running'].includes(job.status)){const spinner=document.createElement('span');spinner.className='export-spinner frame-edit-queue-spinner';spinner.setAttribute('aria-hidden','true');row.append(spinner);}
      const label=document.createElement('span');label.className='frame-edit-queue-label';
      const paused=job.status==='failed'&&/призупинено|на ваше прохання/i.test(job.error || '');
      const frames=!job.frame_numbers.length?'увесь ролик':job.frame_numbers.length>3?`${job.frame_numbers.length} кадрів`:`${job.frame_numbers.length===1?'кадр':'кадри'} ${job.frame_numbers.join(', ')}`;
      label.textContent=`${job.status==='queued'?'У черзі':paused?'Призупинено':job.status==='failed'?'Не виконано':'В роботі'} · ${frames}`;
      label.title=job.frame_numbers.length?`Кадри: ${job.frame_numbers.join(', ')}`:'Увесь ролик';
      const note=document.createElement('span');note.className='frame-edit-queue-note';note.textContent=job.error || job.notes;note.title=note.textContent;
      row.append(label,note);
      if(job.status==='queued'){
        const cancel=document.createElement('button');cancel.type='button';cancel.textContent='×';cancel.setAttribute('aria-label',`Прибрати правки до кадрів ${job.frame_numbers.join(', ')}`);
        cancel.addEventListener('click',async()=>{cancel.disabled=true;try{const data=await api(`/api/projects/${pid}/production-edits/${job.id}/cancel`,'POST',{});if(state.project?.id!==pid)return;frameEditQueueReads[pid]={data,at:Date.now()};draw(data);}catch(e){cancel.disabled=false;status(e.message,true);}});row.append(cancel);
      }
      slot.append(row);
    }
  };
  if(cached?.data)draw(cached.data);
  if(cached?.pending||Date.now()-(cached?.at || 0)<2000)return;
  frameEditQueueReads[pid]={...cached,pending:true};
  api(`/api/projects/${pid}/production-edits`).then(data=>{
    frameEditQueueReads[pid]={data,at:Date.now()};
    if(state.project?.id!==pid||!slot.isConnected)return;
    draw(data);clearTimeout(frameEditQueueTimers[pid]);
    if(data.jobs.some(j=>['queued','starting','running'].includes(j.status))){
      frameEditQueueTimers[pid]=setTimeout(()=>{if(state.project?.id===pid){refreshFrameEdits(make,pid);pollProduction(pid);}},3000);
    }
  }).catch(()=>{frameEditQueueReads[pid]={...cached,at:Date.now()};});
}
function selectEntireTimeline(){selectTimelineIds(universalClips().filter(clip=>!state.expandedGroup || sceneGroups().find(g=>g.id===state.expandedGroup)?.clip_ids.includes(clip.id)).map(clip=>clip.id));}
async function deleteTimelineSelection(){
  if(state.busy)return;
  try{
    if(state.selectedGroup)await action('delete_group',{group_id:state.selectedGroup},'Кадр видалено. Дію можна скасувати.');
    else{
      const ids=[...new Set([...(state.multiSelection || []),...(state.selected?[state.selected]:[])])].filter(id=>universalClips().some(c=>c.id===id));
      if(!ids.length)return;
      await action('batch',{actions:ids.map(id=>({type:'delete_clip',payload:{clip_id:id}}))},'Виділені кліпи видалено. Дію можна скасувати.');
    }
    state.selected=null;state.selectedGroup=null;state.multiSelection=[];renderProject();
  }catch(error){status(error.message,true);}
}
let timelineKeyboardActive=false;
document.addEventListener('pointerdown',event=>{timelineKeyboardActive=!!event.target.closest('#editor-timeline');});
document.addEventListener('keydown',event=>{
  if(state.view!=='editor' || !timelineKeyboardActive || event.isComposing || event.target.closest('input,textarea,select,[contenteditable="true"]') || !$('modal-backdrop').hidden)return;
  if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='a'){event.preventDefault();selectEntireTimeline();}
  else if(event.key==='Delete'||event.key==='Backspace'){event.preventDefault();deleteTimelineSelection();}
});

let timelineMarquee=null,timelineIgnoreClickUntil=0;
document.addEventListener('click',event=>{
  if(!event.target.closest('#timeline-content'))return;
  if(performance.now()<timelineIgnoreClickUntil){event.preventDefault();event.stopImmediatePropagation();return;}
  if(state.view!=='editor' || event.target.closest('button,.layer-heading,.time-ruler,.track-clip,.frame-group-clip,#timeline-playhead'))return;
  event.preventDefault();event.stopImmediatePropagation();
  const lane=event.target.closest('.track-lane');
  if(lane)state.playhead=layerTime(event,lane);
  state.activeLayer=null;selectTimelineIds([]);renderPreview();
},true);
document.addEventListener('pointerdown',event=>{
  timelineIgnoreClickUntil=0;
  // a selection box may start anywhere on the lanes, on a frame or the plate too (user, 25 November 2026: «нажимаю… на
  // плашку і тягну… виділення»): a press without a drag stays that block's click
  const onBlock=event.target.closest('.track-clip,.frame-group-clip');
  if(event.button!==0 || state.view!=='editor' || state.busy || !event.target.closest('#timeline-content') || event.target.closest('.layer-heading,.time-ruler,#timeline-playhead,.transition-join') || (!onBlock&&event.target.closest('button')))return;
  const viewport=document.querySelector('.timeline-scroll').getBoundingClientRect();
  const labelWidth=parseFloat(getComputedStyle(document.querySelector('.timeline-scroll')).getPropertyValue('--timeline-label-width')) || 142;
  if(event.clientX<viewport.left+labelWidth)return;
  if(!onBlock)event.preventDefault();
  const box=document.createElement('div');box.className='timeline-selection-box';document.body.append(box);
  const base=event.metaKey||event.ctrlKey||event.shiftKey?[...(state.multiSelection || []),...(state.selected?[state.selected]:[]),...(sceneGroups().find(g=>g.id===state.selectedGroup)?.clip_ids || [])]:[];
  timelineMarquee={x:event.clientX,y:event.clientY,box,base,moved:false,ids:base,pointer:event.pointerId};
});
document.addEventListener('pointermove',event=>{
  const drag=timelineMarquee;if(!drag || event.pointerId!==drag.pointer)return;
  if(!drag.moved && Math.hypot(event.clientX-drag.x,event.clientY-drag.y)<4)return;
  event.preventDefault();drag.moved=true;
  const left=Math.min(drag.x,event.clientX),top=Math.min(drag.y,event.clientY),right=Math.max(drag.x,event.clientX),bottom=Math.max(drag.y,event.clientY);
  Object.assign(drag.box.style,{left:left+'px',top:top+'px',width:(right-left)+'px',height:(bottom-top)+'px'});
  // the blocks are measured once for a box (again only after a scroll): measuring 650 of them on every move of the
  // pointer laid the page out each time
  const scroller=document.querySelector('.timeline-scroll'),key=scroller.scrollLeft+','+scroller.scrollTop;
  if(drag.key!==key){
    drag.key=key;drag.viewport=scroller.getBoundingClientRect();
    drag.blocks=[...document.querySelectorAll('#timeline-tracks [data-clip-id],#timeline-tracks [data-group-id]')].map(node=>({node,rect:node.getBoundingClientRect(),
      members:node.dataset.groupId?groupById(node.dataset.groupId)?.clip_ids || []:[node.dataset.clipId]}));
  }
  const viewport=drag.viewport,ids=new Set(drag.base);
  for(const {node,rect,members} of drag.blocks){
    // a block counts when the box covers most of it, half its width or more (user, 25 November 2026: «все, що попало
    // повністю… або… сильно частково»): the long plate under a box over a few frames stays out
    const shownLeft=Math.max(rect.left,viewport.left),shownRight=Math.min(rect.right,viewport.right);
    const across=Math.max(0,Math.min(shownRight,right)-Math.max(shownLeft,left)),width=Math.max(1,shownRight-shownLeft);
    const hit=across>=width*.5 && rect.bottom>Math.max(top,viewport.top) && rect.top<Math.min(bottom,viewport.bottom);
    if(hit)for(const id of members)ids.add(id);
    node.classList.toggle(node.dataset.groupId?'selected':'multi-selected',hit || members.every(id=>ids.has(id)));
  }
  drag.ids=[...ids];
});
function finishTimelineMarquee(event){
  const drag=timelineMarquee;if(!drag || event.pointerId!==drag.pointer)return;
  timelineMarquee=null;drag.box.remove();
  if(drag.moved){timelineIgnoreClickUntil=performance.now()+300;selectTimelineIds(event.type==='pointercancel'?drag.base:drag.ids);}
}
document.addEventListener('pointerup',finishTimelineMarquee);
document.addEventListener('pointercancel',finishTimelineMarquee);
// the host's video in a frame: an asset HeyGen made, or a video in a frame the plan gives the host
function isHostVideo(clip,group){
  const asset=(state.assets||state.project?.assets||[]).find(item=>item.id===clip.asset_id);
  if(asset?.source==='heygen')return true;
  const number=Number(group.title.match(/\d+/)?.[0]);
  return !!number&&(state.plan?.frames||[]).some(frame=>frame.number===number&&frame.format==='host');
}
function isChannelLogo(clip){
  const asset=(state.assets||state.project?.assets||[]).find(item=>item.id===clip.asset_id);
  return clip.kind==='image'&&(asset?.source==='channel-logo'||/^Логотип/.test(clip.title||''));
}
// the channel's logo layer reads simply «Плашка» on the timeline (user, 25 November 2026)
function groupDisplayTitle(group){
  return group.role==='overlay'&&groupMembers(group).some(isChannelLogo)?'Плашка':group.title;
}
// Nothing on the timeline is moved by hand (user, 25 November 2026: «щоб я не міг переміщати ніякі слої… максимум… виділяти»):
// clips, frames and rows are selected, never dragged. A transition dragged in from its library still lands on a seam.
document.addEventListener('dragstart',event=>{
  if(event.target.closest?.('#editor-timeline')&&!event.target.closest('.transition-chip')){event.preventDefault();event.stopImmediatePropagation();}
},true);
