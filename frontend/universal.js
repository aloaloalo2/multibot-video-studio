/* Universal, freely stackable tracks for schema v2 projects. */

function isUniversal(){return Number(state.project?.schema_version)>=2;}
function layers(){return isUniversal()?(state.project.tracks || []).filter(track=>track.type==='universal'):[];}
function universalClips(){return layers().flatMap(layer=>layer.clips || []);}
function universalSelection(){for(const layer of layers()){const clip=(layer.clips || []).find(item=>item.id===state.selected);if(clip)return {clip,layer};}return null;}
function activeLayer(){return layers().find(layer=>layer.id===state.activeLayer) || layers()[layers().length-1];}
function clipKindLabel(kind){return {video:'Відео',image:'Фото',audio:'Аудіо',text:'Текст',animation:'Анімація'}[kind] || 'Кліп';}
function clipLabel(clip){return clip.title || clip.text || assetById(clip.asset_id)?.name || ({video:'Відео',image:'Фото',audio:'Звук',text:'Текст',animation:'Анімація'}[clip.kind] || 'Кліп');}
function clipIsMuted(clip){return layers().find(layer=>layer.clips.some(c=>c.id===clip.id))?.muted===true;}
function addLayerSoundControl(heading,layer){
  if(!layer?.clips.some(c=>c.kind==='audio'||c.kind==='video'))return;
  const button=document.createElement('button');button.type='button';button.className='layer-sound'+(layer.muted?' is-muted':'');button.draggable=false;button.setAttribute('aria-label',(layer.muted?'Увімкнути':'Вимкнути')+' звук доріжки '+layer.name);button.setAttribute('aria-pressed',String(layer.muted===true));button.title=layer.muted?'Доріжку вимкнено':'Звук доріжки ввімкнено';button.innerHTML='<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M11 4 6 8H3v8h3l5 4z"/>'+(layer.muted?'<path d="m16 9 5 6m0-6-5 6"/>':'<path d="M15 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/>')+'</svg>';button.addEventListener('click',event=>{event.stopPropagation();action('set_layer_mute',{layer_id:layer.id,muted:!layer.muted},layer.muted?'Звук доріжки ввімкнено.':'Звук доріжки вимкнено.').catch(()=>{});});heading.append(button);heading.closest('.track-row')?.classList.toggle('sound-muted',layer.muted===true);
}
function layerTime(event,lane){const rect=lane.getBoundingClientRect();return timelineOrigin()+Math.max(0,Math.round(((event.clientX-rect.left)/rect.width)*timelineSpan()*10)/10);}

function selectUniversalClip(id){const chosen=universalClips().find(clip=>clip.id===id);if(!chosen)return;state.selectedTransition=null;state.selectedStack=null;state.selected=id;state.activeLayer=layers().find(layer=>(layer.clips || []).some(clip=>clip.id===id))?.id || state.activeLayer;state.replaceMode=false;state.playhead=seconds(chosen.start);renderTimeline();renderInspector();renderPreview();status(`Вибрано кліп «${clipLabel(chosen)}».`);}

function renderUniversalTimeline(){
  renderGroupingControls();
  if(state.compactTimeline && sceneGroups().length && !state.expandedGroup){renderGroupedTimeline();return;}
  const ruler=$('time-ruler'),tracks=$('timeline-tracks');ruler.replaceChildren();tracks.replaceChildren();
  const total=timelineSpan(),width=timelineWidth();ruler.className='time-ruler universal-ruler';
  const label=document.createElement('div');label.className='track-label';ruler.append(label);
  const marks=document.createElement('div');marks.className='time-ruler-marks';marks.style.width=width+'px';
  renderTimelineRulerMarks(marks,total,width);ruler.append(marks);
  for(const layer of [...layers()].reverse()){
    if(state.expandedGroup && !sceneGroups().find(g=>g.id===state.expandedGroup)?.clip_ids.some(id=>(layer.clips || []).some(c=>c.id===id)))continue;
    const index=layers().findIndex(item=>item.id===layer.id);
    const row=document.createElement('div');row.className='track-row universal-row'+(state.activeLayer===layer.id?' active-layer':'');
    const heading=document.createElement('div');heading.className='layer-heading';
    enableLayerReorder(heading,layer);
    const name=document.createElement('button');name.type='button';name.className='layer-name';name.textContent=layer.name || 'Шар';name.title='Вибрати шар';name.addEventListener('click',()=>{clearTransitionSelection();state.activeLayer=layer.id;state.selectedStack=null;state.selected=null;selectTimelineIds((layer.clips || []).map(clip=>clip.id));status(`Вибрано «${layer.name}».`);});
    const controls=document.createElement('div');controls.className='layer-controls';
    for(const [symbol,title,run] of [['✎','Перейменувати шар',()=>renameUniversalLayer(layer)],['×','Прибрати шар',()=>removeUniversalLayer(layer)]]){
      const button=document.createElement('button');button.type='button';if(symbol==='×')setTrashButton(button,`${title} ${layer.name}`,true);else button.textContent=symbol;button.title=title;button.setAttribute('aria-label',`${title} ${layer.name}`);button.disabled=(symbol==='↑'&&index===layers().length-1)||(symbol==='↓'&&index===0)||(symbol==='×'&&layers().length===1);button.addEventListener('click',run);controls.append(button);
    }
    heading.append(name);addLayerSoundControl(heading,layer);heading.append(controls);
    const lane=document.createElement('div');lane.className='track-lane universal-lane';lane.style.width=width+'px';lane.dataset.layerId=layer.id;
    const occupiedUntil=[];
    for(const clip of [...(layer.clips || [])].sort((a,b)=>seconds(a.start)-seconds(b.start))){
      let slot=occupiedUntil.findIndex(end=>end<=seconds(clip.start));
      if(slot<0)slot=occupiedUntil.length;
      occupiedUntil[slot]=seconds(clip.start)+seconds(clip.duration);
      const button=document.createElement('button');button.type='button';button.draggable=true;button.className=`track-clip universal-clip kind-${clip.kind}${state.selected===clip.id?' selected':''}`;button.dataset.clipId=clip.id;button.style.left=seconds(clip.start)/total*100+'%';button.style.width=seconds(clip.duration)/total*100+'%';button.setAttribute('aria-label',clipLabel(clip));const caption=document.createElement('span');caption.className='clip-title';caption.textContent=clipLabel(clip);button.append(caption);button.title=`${clipKindLabel(clip.kind)}: ${clipLabel(clip)} · ${clock(clip.start)} - ${clock(seconds(clip.start)+seconds(clip.duration))}`;
      button.style.top=(2+slot*27)+'px';button.style.left=((seconds(clip.start)-timelineOrigin())/total*100)+'%';
      button.addEventListener('click',event=>{event.stopPropagation();if(event.metaKey||event.ctrlKey||event.shiftKey){toggleClipSelection(clip.id);return;}state.multiSelection=[];state.selectedGroup=null;selectUniversalClip(clip.id);});
      if(state.multiSelection?.includes(clip.id))button.classList.add('multi-selected');
      button.addEventListener('dragstart',event=>{event.dataTransfer.setData('application/x-videostudio-clip',clip.id);event.dataTransfer.effectAllowed='move';});
      button.addEventListener('dragover',event=>{if(['application/x-videostudio-asset','application/x-videostudio-transition'].some(type=>event.dataTransfer.types.includes(type))){event.preventDefault();button.classList.add('drop-target');}});
      button.addEventListener('dragleave',()=>button.classList.remove('drop-target'));
      button.addEventListener('drop',event=>dropOnUniversalClip(event,clip.id));lane.append(button);
      if(clip.kind==='audio')drawAudioWaveform(button,clip);
      if(clip.transition?.type && clip.transition.type!=='cut'){const marker=document.createElement('span');marker.className='transition-marker';marker.textContent='◊';marker.title=`Плавний перехід ${clip.transition.duration || .3} с`;marker.style.left=(seconds(clip.start)+seconds(clip.duration))/total*100+'%';marker.style.top=(1+slot*47)+'px';lane.append(marker);}
    }
    const visual=[...(layer.clips || [])].filter(c=>c.kind!=='audio').sort((a,b)=>Number(a.start)-Number(b.start));
    for(let i=1;i<visual.length;i++)if(Math.abs(Number(visual[i-1].start)+Number(visual[i-1].duration)-Number(visual[i].start))<=1/Number(state.project.fps||25)+.001)transitionJoinMarker(lane,'clip:'+visual[i-1].id,'clip:'+visual[i].id,Number(visual[i].start));
    lane.style.height=(Math.max(1,occupiedUntil.length)*27+2)+'px';
    lane.addEventListener('click',event=>{if(event.target!==lane)return;clearTransitionSelection();state.activeLayer=layer.id;state.selected=null;state.playhead=layerTime(event,lane);selectTimelineIds((layer.clips || []).map(clip=>clip.id),event.metaKey||event.ctrlKey||event.shiftKey);renderPreview();});
    lane.addEventListener('dragover',event=>{if(['application/x-videostudio-asset','application/x-videostudio-clip'].some(type=>event.dataTransfer.types.includes(type))){event.preventDefault();lane.classList.add('drop-lane');}});
    lane.addEventListener('dragleave',event=>{if(!lane.contains(event.relatedTarget))lane.classList.remove('drop-lane');});
    lane.addEventListener('drop',event=>dropOnUniversalLane(event,lane));
    row.append(heading,lane);tracks.append(row);
  }
}

async function dropOnUniversalLane(event,lane){
  event.preventDefault();lane.classList.remove('drop-lane');
  try{const layerId=lane.dataset.layerId,start=layerTime(event,lane);const moved=event.dataTransfer.getData('application/x-videostudio-clip');if(moved){await action('move_clip',{clip_id:moved,to_layer_id:layerId,start},'Кліп перенесено на шар.');state.selected=moved;state.activeLayer=layerId;renderTimeline();renderInspector();return;}
    const raw=event.dataTransfer.getData('application/x-videostudio-asset');if(raw){const data=JSON.parse(raw),asset=(data.source==='pixabay'?state.pixabay:state.assets).find(item=>item.id===data.id);if(asset)await useAsset(asset,undefined,{layerId,start,autoAdd:true});}
  }catch(error){status(error.message,true);}
}

async function dropOnUniversalClip(event,clipId){
  event.preventDefault();event.stopPropagation();event.currentTarget.classList.remove('drop-target');
  try{const transition=event.dataTransfer.getData('application/x-videostudio-transition');if(transition){status('\u041f\u0435\u0440\u0435\u0445\u0456\u0434 \u0441\u043b\u0456\u0434 \u043f\u0435\u0440\u0435\u0442\u044f\u0433\u043d\u0443\u0442\u0438 \u0441\u0430\u043c\u0435 \u043d\u0430 \u0441\u0442\u0438\u043a \u043a\u0430\u0434\u0440\u0456\u0432.',true);return;}
    const raw=event.dataTransfer.getData('application/x-videostudio-asset');if(raw){const data=JSON.parse(raw),asset=(data.source==='pixabay'?state.pixabay:state.assets).find(item=>item.id===data.id);if(asset)await useAsset(asset,clipId,{replace:true});}
  }catch(error){status(error.message,true);}
}

function moveUniversalLayer(layerId,toIndex){if(toIndex<0||toIndex>=layers().length)return;action('move_layer',{layer_id:layerId,to_index:toIndex},'Порядок шарів оновлено.').catch(()=>{});}
function renameUniversalLayer(layer){modal('Назва шару',`<label>Назва<input id="layer-new-name" type="text" maxlength="80" value="${esc(layer.name)}"></label>`,[{label:'Скасувати',run:closeModal},{label:'Зберегти',primary:true,run:async()=>{try{const name=$('layer-new-name').value.trim();if(!name)throw new Error('Введіть назву шару.');await action('update_layer',{layer_id:layer.id,name},'Назву шару збережено.');closeModal();}catch(error){status(error.message,true);}}}]);}
function removeUniversalLayer(layer){const count=(layer.clips || []).length;modal('Прибрати шар',`<p>Шар «${esc(layer.name)}» містить ${count} кліпів. Дію можна скасувати кнопкою «Скасувати дію» після видалення.</p>`,[{label:'Залишити',run:closeModal},{label:'Прибрати шар',primary:true,run:async()=>{try{await action('remove_layer',{layer_id:layer.id},'Шар прибрано.');state.activeLayer=activeLayer()?.id;state.selected=null;closeModal();renderProject();}catch(error){status(error.message,true);}}}]);}

async function useUniversalAsset(asset, clipId, options={}){
  const target=clipId && universalClips().find(clip=>clip.id===clipId);
  const kind=asset.kind==='photo'?'image':asset.kind;
  if(target && (options.replace || state.replaceMode || target.kind===kind)){
    if(target.kind!==kind){status('Для заміни виберіть матеріал того самого типу. Інший матеріал перетягніть на шар.',true);return;}
    await action('replace_clip_asset',{clip_id:target.id,asset_id:asset.id},`Матеріал кліпу «${clipLabel(target)}» замінено.`);
    state.replaceMode=false;state.selected=target.id;renderInspector();return;
  }
  const layerId=options.layerId || activeLayer()?.id;
  if(!layerId)throw new Error('Спершу створіть шар.');
  const start=Number.isFinite(options.start)?options.start:state.playhead;
  const mediaDuration=Number(asset.duration);
  const clipDuration=Number.isFinite(mediaDuration)&&mediaDuration>.1 ? Math.min(mediaDuration,kind==='audio'?36000:20) : 5;
  const before=new Set(universalClips().map(clip=>clip.id));
  await action('add_clip',{layer_id:layerId,kind,asset_id:asset.id,start,duration:clipDuration,title:asset.name || 'Матеріал'},`Матеріал «${asset.name || 'Кліп'}» додано на універсальний шар.`);
  const added=universalClips().find(clip=>!before.has(clip.id));
  if(added){state.selected=added.id;state.activeLayer=layers().find(layer=>layer.clips.some(clip=>clip.id===added.id))?.id;renderTimeline();renderInspector();}
}

function easedProgress(value,mode){const p=Math.max(0,Math.min(1,value));return mode==='ease_in'?p*p*p:mode==='ease_out'?1-Math.pow(1-p,3):mode==='ease_in_out'?p*p*(3-2*p):p;}

let legacyNeighborToken='',legacyNeighbors=new Map();
function legacyAdjacent(clip){
  const token=state.project?.id+':'+state.project?.revision;
  if(token!==legacyNeighborToken){legacyNeighborToken=token;legacyNeighbors=new Map();const ordered=universalClips().filter(c=>c.kind!=='audio').sort((a,b)=>Number(a.start)-Number(b.start));for(let i=0;i<ordered.length;i++)legacyNeighbors.set(ordered[i].id,{previous:ordered[i-1],next:ordered[i+1]});}
  return legacyNeighbors.get(clip.id)||{};
}

function animatedValues(clip,local){
  const base={x:Number(clip.x ?? .5),y:Number(clip.y ?? .5),scale:Number(clip.scale ?? 1),opacity:Number(clip.opacity ?? 1)};
  const points=[{time:0,...base},...(clip.keyframes || []).map(point=>({...point,time:Number(point.time)}))].sort((a,b)=>a.time-b.time);
  const values={...base};
  for(const key of ['x','y','scale','opacity']){
    const known=points.filter(point=>Number.isFinite(Number(point[key])));
    const after=known.find(point=>point.time>=local);
    if(!after){values[key]=Number(known.at(-1)?.[key] ?? base[key]);continue;}
    const before=[...known].reverse().find(point=>point.time<=local) || known[0];
    const span=after.time-before.time;
    values[key]=span>0?Number(before[key])+(Number(after[key])-Number(before[key]))*easedProgress((local-before.time)/span,clip.easing):Number(after[key]);
  }
  const preset=clip.preset || 'none';const d=Math.max(.1,Number(clip.preset_duration || .6));const length=seconds(clip.duration);
  const incoming=easedProgress(local/d,clip.easing),outgoing=easedProgress((length-local)/d,clip.easing);
  if(preset==='fade_in')values.opacity*=incoming;
  if(preset==='fade_out')values.opacity*=outgoing;
  if(preset==='slide_in')values.x+=1-incoming;
  if(preset==='slide_out')values.x-=1-outgoing;
  if(preset==='zoom_in'&&!clip.keyframes?.some(point=>'scale' in point)){values.scale*=.8+.2*incoming;values.opacity*=easedProgress(local/(d/2),clip.easing);}
  if(preset==='pop'&&!clip.keyframes?.some(point=>'scale' in point)){values.scale*=local<d/2?.7+.42*easedProgress(local/(d/2),clip.easing):1.12-.12*easedProgress((local-d/2)/(d/2),clip.easing);values.opacity*=easedProgress(local/(d/2),clip.easing);}
  const {previous,next}=legacyAdjacent(clip);
  if(previous && previous.transition?.type!=='cut'){
    const d=Math.max(.1,seconds(previous.transition?.duration)),overlap=seconds(previous.start)+seconds(previous.duration)-seconds(clip.start);
    if(overlap>=d-.05 || Math.abs(overlap)<=.05){
      if(previous.transition?.type==='crossfade')values.opacity*=easedProgress(local/d,clip.easing);
      if(previous.transition?.type==='swipe')values.x+=1-easedProgress(local/d,clip.easing);
    }
  }
  if(next && Math.abs(seconds(clip.start)+length-seconds(next.start))<=.05){
    const d=Math.max(.1,seconds(clip.transition?.duration));
    if(clip.transition?.type==='crossfade')values.opacity*=easedProgress((length-local)/d,clip.easing);
    if(clip.transition?.type==='swipe')values.x-=1-easedProgress((length-local)/d,clip.easing);
  }
  return transitionValues(clip,local,values);
}

function renderUniversalPreview(){
  const composition=$('preview-composition'),placeholder=$('preview-placeholder');
  $('preview-video').pause();$('preview-video').hidden=true;$('preview-image').hidden=true;$('preview-overlay').style.display='none';
  const visible=[],prepared=[],{order,spans}=memoForProject('visualSpans',()=>{
    const order=new Map(),spans=[];
    for(const layer of layers())for(const clip of layer.clips || []){
      if(clip.kind==='audio')continue;
      order.set(clip.id,order.size);spans.push({clip,start:clipRenderStart(clip),end:clipRenderEnd(clip)});
    }
    return {order,spans};
  });
  for(const {clip,start,end} of spans){
    if(state.playhead>=start&&state.playhead<end)visible.push(clip);
    if(state.playhead>=start-1.5&&state.playhead<end)prepared.push(clip);
  }
  const needed=new Set(prepared.map(clip=>clip.id)),shown=new Set(visible.map(clip=>clip.id));
  const brandIds=new Set(sceneGroups().filter(g=>g.role==='overlay').flatMap(g=>g.clip_ids));
  const foregroundZ=Math.max(0,...prepared.filter(clip=>!brandIds.has(clip.id)).map(clip=>order.get(clip.id)*4))+2;
  for(const [id,node] of state.previewNodes)if(!needed.has(id)){
    node.querySelectorAll('video').forEach(video=>video.pause());node._trails?.forEach(trail=>trail.node.remove());node.remove();state.previewNodes.delete(id);
  }
  for(const clip of prepared){
      const asset=assetById(clip.asset_id),url=asset?.preview_url || asset?.media_url || asset?.url;
      const sourceSignature=JSON.stringify([clip.kind,clip.content_type,clip.asset_id,url,clip.text,clip.text_words,clip.font_family,clip.font_weight,clip.font_size,clip.word_entrance?.type]);
      let existing=state.previewNodes.get(clip.id);
      if(existing&&existing._sourceSignature!==sourceSignature){existing.querySelectorAll('video').forEach(video=>video.pause());existing._trails?.forEach(trail=>trail.node.remove());existing.remove();state.previewNodes.delete(clip.id);existing=null;}
      if(!existing){
      const wrapper=document.createElement('div');wrapper.className='composition-clip';wrapper.dataset.clipId=clip.id;
      wrapper._sourceSignature=sourceSignature;
      let element;
      const mediaKind=clip.kind==='animation'?(clip.content_type==='image'?'image':clip.content_type==='text'?'text':clip.content_type==='gradient'?'gradient':'shape'):clip.kind;
      if(mediaKind==='gradient'){element=document.createElement('canvas');element.className='composition-gradient';element.width=320;element.height=180;}
      else if(mediaKind==='image'&&url){element=document.createElement('img');element.decoding='async';element.src=url;element.alt='';element.decode().catch(()=>{});}
      else if(mediaKind==='video'&&url){element=document.createElement('video');element.muted=true;element.playsInline=true;element.preload='auto';element.addEventListener('loadedmetadata',()=>{const target=Number(clip.trim_start||0)+Math.max(0,state.playhead-Number(clip.start));if(target>0)element.currentTime=Math.min(target,element.duration);},{once:true});element.src=url;}
      else if(mediaKind==='text'){element=document.createElement('div');element.className='composition-text';element.textContent=clip.text || clip.title || '';element.style.color=clip.color || '#ffffff';}
      else {element=document.createElement('div');element.className='composition-shape';element.style.background=clip.color || '#f0b429';}
      if(mediaKind==='text' && clip.text_words?.length){
        element.replaceChildren();element.style.display='block';element.style.padding='0';element.style.position='relative';element.style.textShadow='none';
        for(const word of timedTextUnits(clip)){const span=document.createElement('span');span.textContent=word.text;span.dataset.wordStart=word.start;Object.assign(span.style,{position:'absolute',left:(word.x*100)+'%',top:(word.y*100)+'%',width:(word.width*100)+'%',height:(word.height*100)+'%',transform:'translate(-50%,-50%)',display:'grid',placeItems:'center',whiteSpace:'pre',opacity:'0'});if(clip.word_entrance?.type.includes('blur')){span.replaceChildren();for(const name of ['sharp','blur']){const child=document.createElement('span');child.className='word-'+name;child.textContent=word.text;Object.assign(child.style,{position:'absolute',inset:'0',display:'grid',placeItems:'center'});span.append(child);}}element.append(span);}
      }
      wrapper.append(element);composition.append(wrapper);state.previewNodes.set(clip.id,wrapper);
      }
      const node=state.previewNodes.get(clip.id),incoming=transitionInfo(clip).incoming;
      const foreground=clip.kind==='text' && clip.text_role==='full_frame' && incoming && state.playhead>=incoming.seam && state.playhead<incoming.seam+incoming.duration;
      node.style.zIndex=String(foreground?foregroundZ:order.get(clip.id)*4);node.hidden=!shown.has(clip.id);
      if(foreground)node.dataset.transitionForeground='true';else delete node.dataset.transitionForeground;
      if(node.hidden){node._trails?.forEach(trail=>trail.node.hidden=true);const video=node.querySelector('video');if(video&&!video.paused)video.pause();}
  }
  composition.hidden=!visible.length;placeholder.hidden=!!visible.length;
  if(!visible.length)placeholder.textContent=duration()?'На цій позиції немає візуального кліпу':'Додайте матеріал на шар';
  for(const clip of visible){
    const wrapper=state.previewNodes.get(clip.id);if(!wrapper)continue;
    const local=state.playhead-seconds(clip.start),values=animatedValues(clip,local);
    wrapper.style.left=(values.x*100)+'%';wrapper.style.top=(values.y*100)+'%';
    wrapper.style.width=(Number(clip.width ?? 1)*100)+'%';wrapper.style.height=(Number(clip.height ?? 1)*100)+'%';
    wrapper.style.opacity=String(Math.max(0,Math.min(1,values.opacity)));
    wrapper.style.transform=`translate(-50%, -50%) scale(${Math.max(.05,values.scale)})`;
    const text=wrapper.querySelector('.composition-text');
    if(text && clip.font_size){text.style.fontSize=(Number(clip.font_size)*composition.clientWidth/Number(state.project.width))+'px';text.style.fontFamily=JSON.stringify(clip.font_family || 'Arial')+', sans-serif';text.style.fontWeight=String(clip.font_weight || 400);text.style.textShadow='none';if(!clip.text_words?.length)text.style.whiteSpace='pre-wrap';}
    if(text && clip.text_words?.length)for(const word of text.children)applyWordEntrance(word,Number(word.dataset.wordStart),clip,local,composition.clientWidth);
    applyGraphicStyle(wrapper,clip,composition.clientWidth);
    renderMotionTrails(wrapper,clip,local,composition);
    const gradientCanvas=wrapper.querySelector('.composition-gradient');if(gradientCanvas)drawGradient(gradientCanvas,clip.gradient,local);
    const video=wrapper.querySelector('video');if(video){const target=seconds(clip.trim_start)+local,drift=target-video.currentTime,running=state.playing&&!video.paused;if(running&&Math.abs(drift)<=.75)video.playbackRate=Math.abs(drift)<.04?1:Math.max(.8,Math.min(1.25,1+drift));else{video.playbackRate=1;if(!video.seeking&&Number.isFinite(video.duration)&&Math.abs(drift)>(running?.75:.2))video.currentTime=Math.min(Math.max(0,target),video.duration);}video.muted=state.monitorMuted || clipIsMuted(clip) || Number(clip.volume ?? 0)===0;video.volume=Math.max(0,Math.min(1,Number(clip.volume ?? 0)*state.monitorVolume));if(state.playing&&video.paused&&!video.seeking)video.play().catch(()=>{});if(!state.playing&&!video.paused)video.pause();}
  }
  $('time-current').textContent=clock(Math.max(0,state.playhead-timelineOrigin()));$('time-total').textContent=clock(timelineSpan());$('seek').value=timelineSpan()?Math.round((state.playhead-timelineOrigin())/timelineSpan()*1000):0;
  updateTimelinePlayhead();
  renderGraphicTransitionOverlay(composition,state.playhead);
  syncStudioAudio();
}

function renderUniversalInspector(){
  if(state.selectedTransition){
    const selected=(state.project?.join_transitions || []).find(join=>join.from_ref===state.selectedTransition.fromRef && join.to_ref===state.selectedTransition.toRef);
    if(selected){renderTransitionInspector(selected);return;}
    state.selectedTransition=null;
  }
  if(state.selectedStack==='scenes'){renderProjectTypography();return;}
  if(state.selectedGroup && !state.selected){renderGroupInspector();return;}
  const box=$('universal-inspector'),selection=universalSelection();
  $('inspector-fields').hidden=true;$('inspector-empty').hidden=true;box.hidden=false;
  if(!selection){box.innerHTML=`<div class="inspector-empty"><strong>${esc(activeLayer()?.name || 'Шар 1')}</strong><p>Універсальний шар для відео, фото, тексту, анімації, озвучки, музики та звукових ефектів. Перетягніть матеріал із медіатеки або виберіть кліп для редагування.</p></div>`;return;}
  const {clip,layer}=selection,visual=clip.kind!=='audio',sound=['audio','video'].includes(clip.kind);
  const transition=clip.transition || {type:'cut',duration:0};
  box.innerHTML=`<div class="universal-properties"><strong>${esc(clipLabel(clip))}</strong><small>${esc(layer.name)} · ${esc(clipKindLabel(clip.kind))}</small>
    <section><h3>Час</h3><div class="property-grid"><label>На таймлайні, с<input id="u-start" type="number" min="0" step="0.1" value="${seconds(clip.start)}"></label><label>Тривалість, с<input id="u-duration" type="number" min="0.1" step="0.1" value="${seconds(clip.duration)}"></label>${clip.asset_id?`<label>Початок у файлі, с<input id="u-trim" type="number" min="0" step="0.1" value="${seconds(clip.trim_start)}"></label>`:''}</div><button id="u-save-time" class="secondary full" type="button">Застосувати час</button></section>
    ${sound?`<section><h3>Звук</h3><label>Гучність <span id="u-volume-value">${Math.round(Number(clip.volume ?? 1)*100)}%</span><input id="u-volume" type="range" min="0" max="150" value="${Math.round(Number(clip.volume ?? 1)*100)}"></label><button id="u-save-volume" class="secondary full" type="button">Застосувати гучність</button></section>`:''}
    ${visual?`<section><h3>Вигляд і анімація</h3>${['text','animation'].includes(clip.kind)&&clip.kind!=='animation'||clip.content_type==='text'?`<label>Текст<input id="u-text" type="text" value="${esc(clip.text || '')}"></label>`:''}<div class="property-grid"><label>Центр X, %<input id="u-x" type="number" min="-200" max="200" step="1" value="${Math.round(Number(clip.x ?? .5)*100)}"></label><label>Центр Y, %<input id="u-y" type="number" min="-200" max="200" step="1" value="${Math.round(Number(clip.y ?? .5)*100)}"></label><label>Ширина, %<input id="u-width" type="number" min="1" max="400" step="1" value="${Math.round(Number(clip.width ?? 1)*100)}"></label><label>Висота, %<input id="u-height" type="number" min="1" max="400" step="1" value="${Math.round(Number(clip.height ?? 1)*100)}"></label><label>Масштаб, %<input id="u-scale" type="number" min="5" max="800" step="1" value="${Math.round(Number(clip.scale ?? 1)*100)}"></label><label>Прозорість, %<input id="u-opacity" type="number" min="0" max="100" step="1" value="${Math.round(Number(clip.opacity ?? 1)*100)}"></label></div><label>Готова анімація<select id="u-preset"><option value="none">Без анімації</option><option value="fade_in">Поява</option><option value="fade_out">Зникнення</option><option value="slide_in">В'їзд</option><option value="slide_out">Виїзд</option><option value="zoom_in">Наближення</option><option value="pop">Пружна поява</option></select></label><label>Тривалість анімації, с<input id="u-preset-duration" type="number" min="0.1" max="5" step="0.1" value="${Number(clip.preset_duration || .6)}"></label><button id="u-save-look" class="secondary full" type="button">Застосувати вигляд</button></section>
    <section><h3>Ключові кадри</h3><p>Задайте положення, масштаб і прозорість у потрібний момент кліпу.</p><div id="u-keyframes"></div><button id="u-add-keyframe" class="secondary full" type="button">＋ Ключ у поточній позиції</button><button id="u-save-keyframes" class="secondary full" type="button">Зберегти ключі</button></section>
    <section><h3>Перехід після кліпу</h3><div class="property-grid"><label>Тип<select id="u-transition"><option value="cut">Склейка</option><option value="crossfade">Плавний</option><option value="swipe">Зсув</option></select></label><label>Тривалість, с<input id="u-transition-duration" type="number" min="0" max="5" step="0.1" value="${seconds(transition.duration)}"></label></div><button id="u-save-transition" class="secondary full" type="button">Застосувати перехід</button></section>`:''}
    <div class="universal-actions"><button id="u-split" type="button">Розділити</button><button id="u-delete" class="danger trash-button" type="button">${trashIcon}<span>Прибрати кліп</span></button></div></div>`;
  $('u-save-time').addEventListener('click',async()=>{try{const start=Number($('u-start').value),duration=Number($('u-duration').value),trim=Number($('u-trim')?.value || 0);if(!Number.isFinite(start)||start<0||!Number.isFinite(duration)||duration<.1||!Number.isFinite(trim)||trim<0)throw new Error('Перевірте час кліпу.');if(start!==Number(clip.start))await action('move_clip',{clip_id:clip.id,start},'Позицію кліпу збережено.');if(duration!==Number(clip.duration)||trim!==Number(clip.trim_start || 0))await action('trim_clip',{clip_id:clip.id,duration,trim_start:trim},'Тривалість кліпу збережено.');}catch(error){status(error.message,true);}});
  if(sound){$('u-volume').addEventListener('input',event=>$('u-volume-value').textContent=event.target.value+'%');$('u-save-volume').addEventListener('click',()=>action('set_clip_volume',{clip_id:clip.id,volume:Number($('u-volume').value)/100},'Гучність збережено.').catch(()=>{}));}
  if(visual){
    $('u-preset').value=clip.preset || 'none';$('u-transition').value=transition.type || 'cut';
    $('u-save-look').addEventListener('click',()=>{const changes={x:Number($('u-x').value)/100,y:Number($('u-y').value)/100,width:Number($('u-width').value)/100,height:Number($('u-height').value)/100,scale:Number($('u-scale').value)/100,opacity:Number($('u-opacity').value)/100,preset:$('u-preset').value,preset_duration:Number($('u-preset-duration').value)};if($('u-text'))changes.text=$('u-text').value;action('update_clip',{clip_id:clip.id,changes},'Вигляд кліпу збережено.').catch(()=>{});});
    renderKeyframeRows(clip);
    $('u-add-keyframe').addEventListener('click',()=>{const t=Math.min(seconds(clip.duration),Math.max(0,state.playhead-seconds(clip.start)));const row=keyframeRow({time:t,x:Number($('u-x').value)/100,y:Number($('u-y').value)/100,scale:Number($('u-scale').value)/100,opacity:Number($('u-opacity').value)/100});$('u-keyframes').append(row);});
    $('u-save-keyframes').addEventListener('click',()=>{try{const points=[...$('u-keyframes').querySelectorAll('.keyframe-row')].map(row=>({time:Number(row.querySelector('[data-key="time"]').value),x:Number(row.querySelector('[data-key="x"]').value)/100,y:Number(row.querySelector('[data-key="y"]').value)/100,scale:Number(row.querySelector('[data-key="scale"]').value)/100,opacity:Number(row.querySelector('[data-key="opacity"]').value)/100}));action('update_clip',{clip_id:clip.id,changes:{keyframes:points}},'Ключові кадри збережено.').catch(()=>{});}catch(error){status(error.message,true);}});
    $('u-save-transition').addEventListener('click',()=>{const type=$('u-transition').value;action('set_transition',{clip_id:clip.id,type,duration:type==='cut'?0:Number($('u-transition-duration').value)},'Перехід збережено.').catch(()=>{});});
  }
  $('u-split').addEventListener('click',()=>{const start=seconds(clip.start),end=start+seconds(clip.duration),at=state.playhead>start+.05&&state.playhead<end-.05?state.playhead:start+seconds(clip.duration)/2;action('split_clip',{clip_id:clip.id,at},'Кліп розділено.').catch(()=>{});});
  $('u-delete').addEventListener('click',()=>action('delete_clip',{clip_id:clip.id},'Кліп прибрано.').then(()=>{state.selected=null;renderTimeline();renderInspector();}).catch(()=>{}));
  renderGraphicControls(clip,box);
  renderGradientControls(clip,box);
  if($('u-transition'))$('u-transition').closest('section').hidden=true;
}

function keyframeRow(point){
  const row=document.createElement('div');row.className='keyframe-row';
  for(const [key,label,scale] of [['time','с',1],['x','X%',100],['y','Y%',100],['scale','Масштаб%',100],['opacity','Видимість%',100]]){
    const field=document.createElement('label');field.textContent=label;const input=document.createElement('input');input.type='number';input.step=key==='time'?'0.1':'1';input.dataset.key=key;input.value=String(Math.round(Number(point[key] ?? (key==='opacity'||key==='scale'?1:0))*scale*10)/10);field.append(input);row.append(field);
  }
  const remove=document.createElement('button');remove.type='button';setTrashButton(remove,'Прибрати ключ',true);remove.addEventListener('click',()=>row.remove());row.append(remove);return row;
}
function renderKeyframeRows(clip){const box=$('u-keyframes');box.replaceChildren();for(const point of clip.keyframes || [])box.append(keyframeRow(point));}

function openUniversalText(){
  const layer=activeLayer();if(!layer){status('Створіть шар.',true);return;}
  modal('Текст на шарі',`<label>Текст<input id="u-new-text" type="text" placeholder="Напишіть фразу"></label><div class="settings-two-column"><label>Початок, с<input id="u-new-start" type="number" min="0" step="0.1" value="${state.playhead.toFixed(1)}"></label><label>Тривалість, с<input id="u-new-duration" type="number" min="0.1" step="0.1" value="4"></label></div><p>Текст з'явиться на «${esc(layer.name)}».</p>`,[{label:'Скасувати',run:closeModal},{label:'Додати',primary:true,run:async()=>{try{const value=$('u-new-text').value.trim();if(!value)throw new Error('Введіть текст.');await action('add_clip',{layer_id:layer.id,kind:'text',text:value,title:value,start:Number($('u-new-start').value),duration:Number($('u-new-duration').value)},'Текст додано.');closeModal();}catch(error){status(error.message,true);}}}]);
}

function openUniversalAnimation(){
  const layer=activeLayer();if(!layer){status('Створіть шар.',true);return;}
  modal('Анімація на шарі',`<label>Що анімувати<select id="u-animation-kind"><option value="shape">Кольорова форма</option><option value="text">Текст</option></select></label><label>Назва або текст<input id="u-animation-title" type="text" placeholder="Наприклад: важливий факт"></label><label>Колір<input id="u-animation-color" type="color" value="#f0b429"></label><div class="settings-two-column"><label>Початок, с<input id="u-animation-start" type="number" min="0" step="0.1" value="${state.playhead.toFixed(1)}"></label><label>Тривалість, с<input id="u-animation-duration" type="number" min="0.1" step="0.1" value="4"></label></div><label>Рух<select id="u-animation-preset"><option value="fade_in">Поява</option><option value="slide_in">В'їзд</option><option value="zoom_in">Наближення</option><option value="pop">Пружна поява</option><option value="none">Без руху</option></select></label>`,[{label:'Скасувати',run:closeModal},{label:'Додати',primary:true,run:async()=>{try{const content_type=$('u-animation-kind').value,title=$('u-animation-title').value.trim() || 'Анімація',text=content_type==='text'?title:'';await action('add_clip',{layer_id:layer.id,kind:'animation',content_type,title,text,color:$('u-animation-color').value,start:Number($('u-animation-start').value),duration:Number($('u-animation-duration').value),preset:$('u-animation-preset').value,width:content_type==='shape'?.3:.8,height:content_type==='shape'?.3:.25},'Анімацію додано.');closeModal();}catch(error){status(error.message,true);}}}]);
}

function openUniversalTransition(){state.libraryTab='transitions';renderLibrary();renderTimeline();status('\u041f\u0435\u0440\u0435\u0442\u044f\u0433\u043d\u0456\u0442\u044c \u043f\u0435\u0440\u0435\u0445\u0456\u0434 \u043d\u0430 \u0441\u0442\u0438\u043a \u0434\u0432\u043e\u0445 \u0441\u0443\u0441\u0456\u0434\u043d\u0456\u0445 \u043a\u0430\u0434\u0440\u0456\u0432.');}

$('add-layer').addEventListener('click',()=>{if(!isUniversal())return;action('add_layer',{},'Шар додано.').then(()=>{state.activeLayer=layers().at(-1)?.id;renderTimeline();renderInspector();}).catch(()=>{});});
$('add-animation').addEventListener('click',()=>{if(isUniversal())openUniversalAnimation();});
