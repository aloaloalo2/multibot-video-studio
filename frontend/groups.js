/* Frame groups compact the timeline while preserving editable native clips. */
function sceneGroups(){return state.project?.scene_groups || [];}
function enableStackReorder(heading,ref){
  heading.draggable=true;heading.dataset.stackRef=ref;heading.title='Перетягніть доріжку за назву, щоб змінити порядок';
  heading.addEventListener('dragstart',event=>{if(event.target.closest('.stack-menu-button')){event.preventDefault();return;}event.dataTransfer.setData('application/x-videostudio-stack',ref);event.dataTransfer.effectAllowed='move';heading.classList.add('layer-dragging');});
  heading.addEventListener('dragend',()=>{heading.classList.remove('layer-dragging');for(const n of document.querySelectorAll('.layer-drop-above,.layer-drop-below'))n.classList.remove('layer-drop-above','layer-drop-below');});
  heading.addEventListener('dragover',event=>{if(!event.dataTransfer.types.includes('application/x-videostudio-stack'))return;event.preventDefault();const above=event.clientY<heading.getBoundingClientRect().top+heading.getBoundingClientRect().height/2;heading.classList.toggle('layer-drop-above',above);heading.classList.toggle('layer-drop-below',!above);});
  heading.addEventListener('dragleave',event=>{if(!heading.contains(event.relatedTarget))heading.classList.remove('layer-drop-above','layer-drop-below');});
  heading.addEventListener('drop',async event=>{const source=event.dataTransfer.getData('application/x-videostudio-stack');if(!source)return;event.preventDefault();event.stopPropagation();const above=event.clientY<heading.getBoundingClientRect().top+heading.getBoundingClientRect().height/2;heading.classList.remove('layer-drop-above','layer-drop-below');if(source===ref)return;try{await action('reorder_stack',{source,target:ref,above},'Доріжки переставлено.');}catch(error){status(error.message,true);}});
}
function enableLayerReorder(heading,layer){
  heading.draggable=true;heading.dataset.layerId=layer.id;heading.title='Перетягніть, щоб змінити порядок шарів';
  heading.addEventListener('dragstart',event=>{event.dataTransfer.setData('application/x-videostudio-layer',layer.id);event.dataTransfer.effectAllowed='move';heading.classList.add('layer-dragging');});
  heading.addEventListener('dragend',()=>{heading.classList.remove('layer-dragging');for(const el of document.querySelectorAll('.layer-drop-above,.layer-drop-below'))el.classList.remove('layer-drop-above','layer-drop-below');});
  heading.addEventListener('dragover',event=>{if(!event.dataTransfer.types.includes('application/x-videostudio-layer'))return;event.preventDefault();const above=event.clientY<heading.getBoundingClientRect().top+heading.getBoundingClientRect().height/2;heading.classList.toggle('layer-drop-above',above);heading.classList.toggle('layer-drop-below',!above);});
  heading.addEventListener('dragleave',event=>{if(!heading.contains(event.relatedTarget))heading.classList.remove('layer-drop-above','layer-drop-below');});
  heading.addEventListener('drop',async event=>{const id=event.dataTransfer.getData('application/x-videostudio-layer');if(!id)return;event.preventDefault();event.stopPropagation();const above=event.clientY<heading.getBoundingClientRect().top+heading.getBoundingClientRect().height/2;heading.classList.remove('layer-drop-above','layer-drop-below');if(id===layer.id)return;const order=layers().map(l=>l.id).filter(x=>x!==id),target=order.indexOf(layer.id);if(target<0)return;const index=Math.min(order.length,target+(above?1:0));try{await action('move_layer',{layer_id:id,to_index:index},'Порядок шарів збережено.');}catch(error){status(error.message,true);}});
}
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
function closeStackMenu(){document.querySelector('.stack-context-menu')?.remove();}
function stackOpen(entry){clearTransitionSelection();if(entry.ref==='scenes'){state.selectedStack='scenes';state.selected=null;state.selectedGroup=null;renderInspector();return;}if(entry.clip){state.selectedGroup=null;selectUniversalClip(entry.clip.id);return;}const group=entry.groups.find(g=>{const b=groupBounds(g);return state.playhead>=b.start&&state.playhead<b.end;}) || entry.groups[0];if(group)expandFrameGroup(group);}
function addStackTools(heading,entry){
  const title=document.createElement('span');title.className='stack-title';title.textContent=entry.title;heading.replaceChildren(title);if(entry.layer)addLayerSoundControl(heading,entry.layer);
  const button=document.createElement('button');button.type='button';button.className='stack-menu-button';button.textContent='⋮';button.setAttribute('aria-label','Дії доріжки '+entry.title);
  const open=event=>{event.preventDefault();event.stopPropagation();closeStackMenu();const menu=document.createElement('div');menu.className='stack-context-menu';menu.setAttribute('role','menu');
    const items=[['Відкрити властивості',()=>stackOpen(entry)]];
    if(entry.clip)items.push(['Перейменувати',()=>modal('Назва доріжки',`<label>Назва<input id="stack-new-name" value="${esc(entry.title)}" maxlength="120"></label>`,[{label:'Скасувати',run:closeModal},{label:'Зберегти',primary:true,run:async()=>{try{await action('batch',{actions:[{type:'update_layer',payload:{layer_id:entry.layer.id,name:$('stack-new-name').value}},{type:'update_clip',payload:{clip_id:entry.clip.id,patch:{title:$('stack-new-name').value}}}]},'Назву збережено.');closeModal();}catch(error){status(error.message,true);}}}])]);
    else if(entry.groups.length===1)items.push(['Перейменувати',()=>{selectFrameGroup(entry.groups[0]);$('frame-title')?.select();}]);
    if(entry.clip)items.push(['Прибрати доріжку',()=>modal('Прибрати доріжку',`<p>Прибрати «${esc(entry.title)}»? Дію можна скасувати.</p>`,[{label:'Залишити',run:closeModal},{label:'Прибрати',primary:true,run:async()=>{try{await action('delete_clip',{clip_id:entry.clip.id},'Доріжку прибрано.');closeModal();}catch(error){status(error.message,true);}}}])]);
    for(const [name,run] of items){const item=document.createElement('button');item.type='button';if(name.startsWith('Прибрати'))setTrashButton(item,name);else item.textContent=name;item.setAttribute('role','menuitem');item.addEventListener('click',()=>{closeStackMenu();run();});menu.append(item);}
    document.body.append(menu);const rect=heading.getBoundingClientRect();menu.style.left=Math.min(window.innerWidth-menu.offsetWidth-8,event.type==='contextmenu'?event.clientX:rect.right-20)+'px';menu.style.top=Math.min(window.innerHeight-menu.offsetHeight-8,rect.bottom)+'px';
  };
  button.addEventListener('click',open);heading.addEventListener('contextmenu',open);heading.addEventListener('dblclick',()=>stackOpen(entry));heading.addEventListener('click',event=>{if(event.target.closest('.stack-menu-button,.layer-sound'))return;if(entry.ref==='scenes'){selectTimelineIds(entry.groups.flatMap(group=>group.clip_ids),event.metaKey||event.ctrlKey||event.shiftKey);return;}if(entry.clip){state.activeLayer=entry.layer.id;selectTimelineIds([entry.clip.id],event.metaKey||event.ctrlKey||event.shiftKey);}else{const group=entry.groups.find(g=>{const b=groupBounds(g);return state.playhead>=b.start&&state.playhead<b.end;}) || entry.groups[0];selectFrameGroup(group);}});heading.append(button);
}
document.addEventListener('click',event=>{if(!event.target.closest('.stack-context-menu,.stack-menu-button'))closeStackMenu();});
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
  const all=document.createElement('button');all.type='button';all.textContent='Виділити все';all.addEventListener('click',selectEntireTimeline);
  const remove=document.createElement('button');remove.type='button';setTrashButton(remove,'Видалити виділене',true);remove.disabled=state.busy || !(state.selected || state.selectedGroup || state.multiSelection?.length);remove.addEventListener('click',deleteTimelineSelection);
  box.append(all,remove);

  if(!state.expandedGroup)for(const [compact,label] of [[false,'Шари'],[true,'Групи']]){const mode=document.createElement('button');mode.type='button';mode.id=compact?'timeline-mode-frames':'timeline-mode-layers';mode.textContent=label;mode.setAttribute('aria-pressed',String(state.compactTimeline===compact));mode.className='timeline-mode'+(state.compactTimeline===compact?' active':'');mode.addEventListener('click',()=>{state.compactTimeline=compact;state.expandedGroup=null;state.multiSelection=[];renderTimeline();});box.append(mode);}
  if(!state.expandedGroup && (state.multiSelection?.length || 0)>=2 && state.multiSelection.length<=200 && !sceneGroups().some(group=>group.clip_ids.some(id=>state.multiSelection.includes(id)))){const group=document.createElement('button');group.type='button';group.id='group-selection';group.textContent='Згрупувати ('+state.multiSelection.length+')';group.addEventListener('click',()=>createSelectedGroup());box.append(group);}
}

function toggleClipSelection(id){
  state.selectedTransition=null;
  const selected=new Set(state.multiSelection || []);
  if(state.selected)selected.add(state.selected);
  selected.has(id)?selected.delete(id):selected.add(id);state.multiSelection=[...selected];state.selected=null;state.selectedGroup=null;
  renderTimeline();status(`Вибрано елементів: ${selected.size}. Натисніть «Згрупувати».`);
}

function createSelectedGroup(){
  const clipIds=[...(state.multiSelection || [])];if(clipIds.length<2)return;
  modal('Згрупувати кадр','<label>Назва кадру<input id="new-frame-name" value="Новий кадр" maxlength="120"></label>',[{label:'Скасувати',run:closeModal},{label:'Згрупувати',primary:true,run:async()=>{try{await action('group_clips',{clip_ids:clipIds,title:$('new-frame-name').value},'Кадр згруповано.');state.multiSelection=[];state.compactTimeline=true;closeModal();renderTimeline();}catch(error){status(error.message,true);}}}]);
}

function selectFrameGroup(group){clearTransitionSelection();state.selectedStack=null;state.selected=null;state.selectedGroup=group.id;state.playhead=groupBounds(group).start;state.multiSelection=[];renderGroupingControls();for(const node of document.querySelectorAll('[data-group-id]'))node.classList.toggle('selected',node.dataset.groupId===group.id);renderInspector();renderPreview();}
function expandFrameGroup(group){
  state.selectedTransition=null;
  if(!state.expandedGroup)state.groupPreviousZoom=state.zoom;
  state.compositionTabs=state.compositionTabs || [];if(!state.compositionTabs.includes(group.id))state.compositionTabs.push(group.id);
  stopPlayback();state.expandedGroup=group.id;state.selectedGroup=group.id;state.selected=null;state.compactTimeline=true;
  const bounds=groupBounds(group);state.playhead=bounds.start;state.zoom=1;renderTimeline();
  document.querySelector('.timeline-scroll').scrollLeft=0;document.querySelector('.timeline-scroll').scrollTop=0;
  renderInspector();renderPreview();
}

function groupLane(title,groups,ref){
  const row=document.createElement('div');row.className='track-row universal-row grouped-row';
  const label=document.createElement('div');label.className='layer-heading group-heading';label.textContent=title;
  if(ref)enableStackReorder(label,ref);
  if(ref)addStackTools(label,{ref,groups,title});
  const lane=document.createElement('div');lane.className='track-lane universal-lane frame-group-lane';lane.style.width=timelineWidth()+'px';
  const occupied=[];
  for(const group of groups){
    const bounds=groupBounds(group),members=groupMembers(group);if(!members.length)continue;
    let slot=occupied.findIndex(end=>end<=bounds.start+.001);if(slot<0)slot=occupied.length;occupied[slot]=bounds.end;
    const button=document.createElement('button');button.type='button';button.draggable=true;button.className='frame-group-clip'+(state.selectedGroup===group.id?' selected':'');button.dataset.groupId=group.id;
    button.classList.add(members.some(c=>c.kind==='animation'&&c.content_type==='image')?'group-animation':'group-text');
    Object.assign(button.style,{left:(bounds.start/timelineSpan()*100)+'%',width:((bounds.end-bounds.start)/timelineSpan()*100)+'%',top:(2+slot*29)+'px'});
    const number=group.title.match(/\d+/)?.[0];button.textContent=(bounds.end-bounds.start)/timelineSpan()*timelineWidth()<22?'':number || group.title;button.title=`${group.title} · ${clock(bounds.start)} - ${clock(bounds.end)} · ${members.length} елементів. Подвійний клік відкриває кадр.`;
    button.setAttribute('aria-label',`${group.title}, ${members.length} елементів`);if(group.id===state.selectedGroup || group.clip_ids.every(id=>state.multiSelection?.includes(id)))button.classList.add('selected');
    button.addEventListener('click',event=>{event.stopPropagation();if(event.metaKey||event.ctrlKey||event.shiftKey){selectTimelineIds(group.clip_ids,true);return;}selectFrameGroup(group);});button.addEventListener('dblclick',()=>expandFrameGroup(group));
    button.addEventListener('dragstart',event=>{event.dataTransfer.setData('application/x-videostudio-group',group.id);event.dataTransfer.effectAllowed='move';});lane.append(button);
  }
  lane.style.height=(Math.max(1,occupied.length)*29+2)+'px';
  if(ref==='scenes'){const sorted=[...groups].sort((a,b)=>groupBounds(a).start-groupBounds(b).start);for(let i=1;i<sorted.length;i++){const previous=groupBounds(sorted[i-1]),next=groupBounds(sorted[i]);if(Math.abs(previous.end-next.start)<=1/Number(state.project.fps || 25)+.001){const nearby=Math.min(previous.end-previous.start,next.end-next.start)*timelineWidth()/timelineSpan();const width=Math.max(2,Math.min(12,nearby*.9));transitionJoinMarker(lane,'group:'+sorted[i-1].id,'group:'+sorted[i].id,previous.end,width);}}}
  lane.addEventListener('click',event=>{if(event.target!==lane)return;clearTransitionSelection();state.playhead=layerTime(event,lane);state.selected=null;state.selectedGroup=null;renderPreview();renderInspector();});
  lane.addEventListener('dragover',event=>{if(event.dataTransfer.types.includes('application/x-videostudio-group'))event.preventDefault();});
  lane.addEventListener('drop',event=>{event.preventDefault();const id=event.dataTransfer.getData('application/x-videostudio-group');if(id)action('move_group',{group_id:id,start:layerTime(event,lane)},'Кадр перенесено з усіма елементами.').catch(()=>{});});
  row.append(label,lane);return row;
}

function renderGroupedTimeline(){
  const previousIndex=groupedRenderIndex;
  groupedRenderIndex=new Map();
  universalClips().forEach((clip,order)=>{const entries=groupedRenderIndex.get(clip.id) || [];entries.push({clip,order});groupedRenderIndex.set(clip.id,entries);});
  try{return renderGroupedTimelineWithIndex();}finally{groupedRenderIndex=previousIndex;}
}

function renderGroupedTimelineWithIndex(){
  const ruler=$('time-ruler'),tracks=$('timeline-tracks');ruler.replaceChildren();tracks.replaceChildren();ruler.className='time-ruler universal-ruler';
  const label=document.createElement('div');label.className='track-label';ruler.append(label);
  const marks=document.createElement('div');marks.className='time-ruler-marks';marks.style.width=timelineWidth()+'px';
  renderTimelineRulerMarks(marks,timelineSpan(),timelineWidth());ruler.append(marks);
  const scenes=sceneGroups().filter(g=>g.role!=='overlay').sort((a,b)=>groupBounds(a).start-groupBounds(b).start);
  const index=new Map();layers().forEach((layer,i)=>{for(const c of layer.clips || [])index.set(c.id,i);});
  const rows=[];
  if(scenes.length)rows.push({title:'\u041a\u0430\u0434\u0440\u0438 \u00b7 '+scenes.length,groups:scenes,ref:'scenes',z:Math.max(...scenes.flatMap(g=>g.clip_ids.map(id=>index.get(id) ?? -1)))});
  for(const group of sceneGroups().filter(g=>g.role==='overlay'))rows.push({title:group.title,groups:[group],ref:'group:'+group.id,z:Math.max(...group.clip_ids.map(id=>index.get(id) ?? -1))});
  const grouped=new Set(sceneGroups().flatMap(g=>g.clip_ids));
  for(const layer of layers())for(const clip of layer.clips || [])if(!grouped.has(clip.id))rows.push({title:clipLabel(clip),clip,layer,ref:'layer:'+layer.id,z:index.get(clip.id)});
  rows.sort((a,b)=>b.z-a.z);
  for(const entry of rows){
    if(entry.groups){tracks.append(groupLane(entry.title,entry.groups,entry.ref));continue;}
    const {clip,layer}=entry,row=document.createElement('div');row.className='track-row universal-row';const label=document.createElement('div');label.className='layer-heading group-heading';label.textContent=entry.title;enableStackReorder(label,entry.ref);addStackTools(label,entry);
    const lane=document.createElement('div');lane.className='track-lane universal-lane';lane.style.width=timelineWidth()+'px';
    const button=document.createElement('button');button.type='button';button.className='track-clip universal-clip kind-'+clip.kind;button.dataset.clipId=clip.id;if(state.selected===clip.id)button.classList.add('selected');if(state.multiSelection?.includes(clip.id))button.classList.add('multi-selected');button.textContent=clipLabel(clip);button.title=clipLabel(clip);Object.assign(button.style,{left:(Number(clip.start)/timelineSpan()*100)+'%',width:(Number(clip.duration)/timelineSpan()*100)+'%'});button.addEventListener('click',event=>{state.activeLayer=layer.id;if(event.metaKey||event.ctrlKey||event.shiftKey){selectTimelineIds([clip.id],true);return;}state.multiSelection=[];state.selectedGroup=null;selectUniversalClip(clip.id);});if(clip.kind==='audio')drawAudioWaveform(button,clip);lane.append(button);row.append(label,lane);tracks.append(row);
  }
}

function prepareTimelineMenu(){
  if($('timeline-add-menu'))return;
  const toolbar=document.querySelector('.timeline-toolbar');
  const menu=document.createElement('details');menu.id='timeline-add-menu';menu.className='timeline-add-menu';
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
  $('delete-frame').addEventListener('click',()=>modal('Прибрати кадр',`<p>Прибрати «${esc(group.title)}» та його ${members.length} елементів? Дію можна скасувати.</p>`,[{label:'Залишити',run:closeModal},{label:'Прибрати',primary:true,run:async()=>{try{await action('delete_group',{group_id:group.id},'Кадр прибрано.');state.selectedGroup=null;state.expandedGroup=null;closeModal();renderTimeline();renderInspector();}catch(error){status(error.message,true);}}}]));
}

function selectTimelineIds(ids,append=false){
  clearTransitionSelection();state.selectedGroup=null;state.selectedStack=null;
  const chosen=new Set(append?[...(state.multiSelection || []),...(state.selected?[state.selected]:[])]:[]);
  for(const id of ids)chosen.add(id);
  state.selected=null;state.multiSelection=[...chosen];
  renderTimeline();renderInspector();
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
  if(event.button!==0 || state.view!=='editor' || state.busy || !event.target.closest('#timeline-content') || event.target.closest('button,.layer-heading,.time-ruler,.track-clip,.frame-group-clip,#timeline-playhead'))return;
  const viewport=document.querySelector('.timeline-scroll').getBoundingClientRect();
  const labelWidth=parseFloat(getComputedStyle(document.querySelector('.timeline-scroll')).getPropertyValue('--timeline-label-width')) || 142;
  if(event.clientX<viewport.left+labelWidth)return;
  event.preventDefault();
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
  const viewport=document.querySelector('.timeline-scroll').getBoundingClientRect();
  const ids=new Set(drag.base);
  for(const node of document.querySelectorAll('#timeline-tracks [data-clip-id],#timeline-tracks [data-group-id]')){
    const rect=node.getBoundingClientRect();
    const hit=rect.right>Math.max(left,viewport.left) && rect.left<Math.min(right,viewport.right) && rect.bottom>Math.max(top,viewport.top) && rect.top<Math.min(bottom,viewport.bottom);
    const members=node.dataset.groupId?sceneGroups().find(g=>g.id===node.dataset.groupId)?.clip_ids || []:[node.dataset.clipId];
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
