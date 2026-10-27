/* Reversible, native effects. The same presets are rendered during export. */
const visualEffectPresets={};
function visualEffectFilter(effect){return ['brightness','contrast','saturate','sepia'].filter(k=>k in effect).map(k=>`${k}(${effect[k]})`).join(' ')||'none';}
function effectVisual(clip){return clip.kind==='image'||clip.kind==='video'||clip.kind==='animation'&&['image','gradient','shape'].includes(clip.content_type);}
async function applyVisualEffect(type,clipId,groupId){
  let clips=[];if(groupId){const group=sceneGroups().find(g=>g.id===groupId&&g.role!=='overlay');if(group)clips=groupMembers(group);}else if(clipId){const clip=universalClips().find(c=>c.id===clipId);if(clip)clips=[clip];}
  const brand=new Set(sceneGroups().filter(g=>g.role==='overlay').flatMap(g=>g.clip_ids));clips=clips.filter(c=>effectVisual(c)&&!brand.has(c.id));
  if(!clips.length){status('Виберіть кадр, фото або відео для ефекту.',true);return;}
  await action('batch',{actions:clips.map(c=>({type:'update_clip',payload:{clip_id:c.id,patch:{visual_effect:type}}}))},'Ефект «'+visualEffectPresets[type].name+'» застосовано.');
}
let effectPointerDrag=null,effectSuppressClick=false;
function effectDropTarget(x,y){return document.elementsFromPoint(x,y).map(e=>e.closest('.frame-group-clip,.universal-clip')).find(Boolean);}
document.addEventListener('pointermove',event=>{const drag=effectPointerDrag;if(!drag||event.pointerId!==drag.pointerId)return;if(!drag.moved&&Math.hypot(event.clientX-drag.x,event.clientY-drag.y)<5)return;if(!drag.moved){drag.moved=true;drag.ghost=document.createElement('div');drag.ghost.className='transition-drag-ghost';drag.ghost.textContent=visualEffectPresets[drag.type].name;document.body.append(drag.ghost);}drag.ghost.style.left=event.clientX+14+'px';drag.ghost.style.top=event.clientY-30+'px';document.querySelectorAll('.effect-drop').forEach(e=>e.classList.remove('effect-drop'));effectDropTarget(event.clientX,event.clientY)?.classList.add('effect-drop');});
document.addEventListener('pointerup',event=>{const drag=effectPointerDrag;if(!drag||event.pointerId!==drag.pointerId)return;effectPointerDrag=null;drag.ghost?.remove();document.querySelectorAll('.effect-drop').forEach(e=>e.classList.remove('effect-drop'));if(!drag.moved)return;effectSuppressClick=true;setTimeout(()=>{effectSuppressClick=false;},0);const target=effectDropTarget(event.clientX,event.clientY);if(target)applyVisualEffect(drag.type,target.dataset.clipId,target.dataset.groupId).catch(()=>{});else status('Перетягніть ефект на кадр у таймлайні.',true);});
document.addEventListener('pointercancel',()=>{effectPointerDrag?.ghost?.remove();effectPointerDrag=null;document.querySelectorAll('.effect-drop').forEach(e=>e.classList.remove('effect-drop'));});
function initEffectLibrary(){
  const library=$('effect-library');library.replaceChildren();const hint=document.createElement('p');hint.className='effect-hint';hint.textContent='Перетягніть ефект на кадр або застосуйте до вибраного';library.append(hint);
  for(const [type,effect] of Object.entries(visualEffectPresets)){
    const button=document.createElement('button');button.type='button';button.className='effect-chip';button.dataset.effect=type;const preview=document.createElement('div');preview.className='effect-preview';preview.style.filter=visualEffectFilter(effect)+(effect.blur?' blur(1px)':'');preview.innerHTML='<i></i><b></b><span>Аа</span>';if(effect.shadow)preview.querySelector('b').style.boxShadow='3px 5px 8px #000a';const label=document.createElement('span');label.textContent=effect.name;button.append(preview,label);
    button.addEventListener('pointerdown',event=>{if(event.button!==0)return;event.preventDefault();event.currentTarget.setPointerCapture(event.pointerId);effectPointerDrag={type,pointerId:event.pointerId,x:event.clientX,y:event.clientY,moved:false};});
    button.addEventListener('click',()=>{if(!effectSuppressClick)applyVisualEffect(type,state.selected,state.selectedGroup).catch(()=>{});});library.append(button);
  }
}
fetch('/visual-effects.json').then(r=>{if(!r.ok)throw Error('Не вдалося завантажити ефекти');return r.json();}).then(data=>{Object.assign(visualEffectPresets,data);initEffectLibrary();if(state.project)renderPreview();}).catch(error=>status(error.message,true));
