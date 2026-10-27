function applyGraphicStyle(wrapper,clip,frameWidth){
  const k=frameWidth/Number(state.project.width),image=wrapper.querySelector('img'),shape=wrapper.querySelector('.composition-shape'),text=wrapper.querySelector('.composition-text');
  const effect=clip.visual_effect&&typeof visualEffectPresets!=='undefined'?visualEffectPresets[clip.visual_effect]||{}:{};
  const target=image || shape,radius=Number(clip.corner_radius || 0)*k;
  if(target){target.style.borderRadius=clip.mask==='circle'?'50%':clip.mask==='rounded'?radius+'px':'0';if(image)target.style.objectFit=clip.mask==='circle'?'cover':'contain';}
  const shadow=effect.shadow || clip.shadow;
  if(shadow){const color=shadow.color || '#000000',r=parseInt(color.slice(1,3),16),g=parseInt(color.slice(3,5),16),b=parseInt(color.slice(5,7),16);wrapper.style.filter=`drop-shadow(${shadow.x*k}px ${shadow.y*k}px ${shadow.blur*k}px rgba(${r},${g},${b},${shadow.opacity}))`;}
  else wrapper.style.filter='none';
  const blur=Number(clip.blur||0)+Number(effect.blur||0);if(blur)wrapper.style.filter=(wrapper.style.filter==='none'?'':wrapper.style.filter+' ')+`blur(${blur*k}px)`;
  const media=wrapper.querySelector('img,video,canvas') || shape;if(media)media.style.filter=typeof visualEffectFilter==='function'?visualEffectFilter(effect):'none';
  if(text){text.style.fontFamily=JSON.stringify(clip.font_family || 'Arial')+', sans-serif';text.style.fontWeight=String(clip.font_weight || 400);}
  if(text && !clip.text_words?.length){text.style.lineHeight=String(clip.line_height || 1.28);text.style.textAlign=clip.text_align || 'center';if(clip.text_align && clip.text_align!=='center'){text.style.display='flex';text.style.justifyContent=clip.text_align==='left'?'flex-start':'flex-end';text.style.alignItems='center';text.style.padding='0';}}
}

function renderMotionTrails(wrapper,clip,local,composition){
  const enabled=Number(clip.motion_blur || 0)>0 && wrapper.querySelector('img');
  if(!enabled)return;
  if(!wrapper._trails){wrapper._trails=[.18,.10].map(opacity=>{const node=wrapper.cloneNode(true);node.removeAttribute('data-clip-id');node.classList.add('motion-trail');node.style.pointerEvents='none';wrapper.before(node);return {node,opacity};});}
  const now=animatedValues(clip,local),dt=.5/Number(state.project.fps || 25),past=animatedValues(clip,Math.max(0,local-dt)),speed=Math.hypot((now.x-past.x)*state.project.width,(now.y-past.y)*state.project.height)/dt;
  wrapper._trails.forEach(({node,opacity},index)=>{const values=animatedValues(clip,Math.max(0,local-dt*(index+1)/2));node.hidden=wrapper.hidden;node.style.cssText=wrapper.style.cssText;node.style.left=values.x*100+'%';node.style.top=values.y*100+'%';node.style.transform=`translate(-50%,-50%) scale(${values.scale})`;node.style.opacity=String(speed>180?values.opacity*opacity*clip.motion_blur:0);node.style.filter='blur('+(.6*composition.clientWidth/state.project.width)+'px)';});
}

function studioFontOptionsHtml(){
  const defaults='<optgroup label="У студії"><option value="Golos">Golos Text</option><option value="Literata">Literata</option><option value="Arial">Arial</option></optgroup>';
  const groups=new Map();for(const font of studioFontCatalog){if(!groups.has(font.category))groups.set(font.category,[]);groups.get(font.category).push(font);}
  return defaults+[...groups].map(([category,fonts])=>`<optgroup label="${esc(category)}">${fonts.map(font=>`<option value="${esc(font.family)}">${esc(font.family)}</option>`).join('')}</optgroup>`).join('');
}

function renderProjectTypography(){
  const box=$('universal-inspector');$('inspector-fields').hidden=true;$('inspector-empty').hidden=true;box.hidden=false;
  box.innerHTML=`<div class="universal-properties"><strong>Усі кадри</strong><section><h3>Шрифт проєкту</h3><label>Шрифт для всіх кадрів<select id="project-font">${studioFontOptionsHtml()}</select></label><p>Спочатку перегляньте шрифт. Після застосування він з’явиться в усіх кадрах і нових текстових вставках.</p><div class="project-font-sample">Аа Бб Вв 123 · Guten Tag</div><button id="apply-project-font" class="secondary full" type="button" disabled>Застосувати шрифт</button></section></div>`;
  const select=$('project-font'),sample=box.querySelector('.project-font-sample'),apply=$('apply-project-font');
  select.value=state.project.font_family || 'Golos';sample.style.fontFamily=JSON.stringify(select.value);
  select.addEventListener('change',async()=>{
    const chosen=select.value;apply.disabled=true;
    try{
      const faces=await document.fonts.load('400 32px '+JSON.stringify(chosen));
      if(studioFontCatalog.some(font=>font.family===chosen) && !faces.length)throw new Error('Шрифт не завантажився.');
      if(select.value!==chosen)return;
      sample.style.fontFamily=JSON.stringify(chosen);apply.disabled=chosen===(state.project.font_family || 'Golos');
    }catch(error){status(error.message,true);}
  });
  apply.addEventListener('click',async()=>{
    select.disabled=true;apply.disabled=true;
    try{await action('set_project_font',{font_family:select.value},'Шрифт змінено в усіх кадрах.');}
    catch(error){status(error.message,true);apply.disabled=false;}
    finally{select.disabled=false;}
  });
}

function timedTextUnits(clip){
  if(!clip.word_entrance?.type.startsWith('letters_'))return clip.text_words;
  const canvas=document.createElement('canvas'),context=canvas.getContext('2d'),size=Number(clip.font_size || 54);context.font=`${clip.font_weight || 400} ${size}px ${JSON.stringify(clip.font_family || 'Golos')}`;
  const units=[];for(let i=0;i<clip.text_words.length;i++){const word=clip.text_words[i],chars=Array.from(word.text),width=context.measureText(word.text).width,left=word.x-width/Number(state.project.width)/2,spread=Math.min(.24,Math.max(.04,Number(word.end ?? clip.text_words[i+1]?.start ?? word.start+.25)-word.start)*.7);let prefix='';for(let j=0;j<chars.length;j++){const before=context.measureText(prefix).width;prefix+=chars[j];const after=context.measureText(prefix).width;units.push({...word,text:chars[j],x:left+(before+after)/2/Number(state.project.width),width:(after-before+12)/Number(state.project.width),start:word.start+spread*j/Math.max(1,chars.length-1)});}}return units;
}
function applyWordEntrance(element,start,clip,time,frameWidth){
  const effect=clip.word_entrance;if(!effect){element.style.opacity=time+1e-7>=start?'1':'0';element.style.transform='translate(-50%,-50%)';return;}
  const raw=Math.max(0,Math.min(1,(time-start)/effect.duration)),p=easedProgress(raw,'ease_out'),distance=effect.distance*frameWidth/Number(state.project.width),mode=effect.type.replace('letters_','');let x=0,y=0,scale=1,opacity=p;
  if(mode==='up'||mode==='blur_up')y=distance*(1-p);if(mode==='down')y=-distance*(1-p);if(mode==='left')x=-distance*(1-p);if(mode==='right')x=distance*(1-p);
  if(effect.type==='grow')scale=.88+.12*p;if(effect.type==='shrink')scale=1.1-.1*p;
  if(effect.type==='pop'){if(raw<.66){scale=.82+.22*easedProgress(raw/.66,'ease_out');opacity=easedProgress(raw/.66,'ease_out');}else scale=1.04-.04*easedProgress((raw-.66)/.34,'ease_out');}
  if(mode.includes('blur')){opacity=1;const sharp=element.querySelector('.word-sharp'),blur=element.querySelector('.word-blur');if(sharp)sharp.style.opacity=p;if(blur){blur.style.opacity=raw<.3?.65*easedProgress(raw/.3,'ease_out'):.65*(1-easedProgress((raw-.3)/.7,'ease_out'));blur.style.filter=`blur(${6*frameWidth/Number(state.project.width)}px)`;}}
  element.style.opacity=String(time<start?0:opacity);element.style.transform=`translate(-50%,-50%) translate(${x}px,${y}px) scale(${scale})`;
}

function renderGraphicControls(clip,box){
  const visual=clip.kind!=='audio';if(!visual)return;
  if(clip.visual_effect){const effectBox=document.createElement('section');effectBox.className='graphics-controls';const label=document.createElement('p');label.textContent='Ефект: '+(visualEffectPresets[clip.visual_effect]?.name||clip.visual_effect);const remove=document.createElement('button');remove.type='button';setTrashButton(remove,'Прибрати ефект');remove.addEventListener('click',()=>action('update_clip',{clip_id:clip.id,patch:{visual_effect:null}},'Ефект прибрано.').catch(()=>{}));effectBox.append(label,remove);box.querySelector('.universal-properties')?.append(effectBox);}
  const text=clip.kind==='text'||clip.content_type==='text',image=clip.kind==='image'||clip.content_type==='image'||clip.content_type==='shape';
  const section=document.createElement('section');section.className='graphics-controls';
  section.innerHTML=`<h3>Графіка</h3>${text?`<div class="property-grid"><label>Шрифт проєкту<select id="g-font"><option>Arial</option><option>Golos</option><option>Literata</option></select></label><label>Розмір<input id="g-size" type="number" min="8" max="300" value="${Number(clip.font_size || 54)}"></label><label>Насиченість<select id="g-weight"><option value="400">Звичайна</option><option value="600">Напівжирна</option><option value="700">Жирна</option></select></label></div>`:''}${image?`<div class="property-grid"><label>Маска<select id="g-mask"><option value="none">Без маски</option><option value="circle">Коло</option><option value="rounded">Заокруглення</option></select></label><label>Радіус<input id="g-radius" type="number" min="0" max="200" value="${Number(clip.corner_radius || 8)}"></label></div>`:''}<label class="graphics-checkbox"><input id="g-shadow" type="checkbox" ${clip.shadow?'checked':''}>Тінь</label><div class="property-grid" id="g-shadow-fields"><label>Колір<input id="g-shadow-color" type="color" value="${clip.shadow?.color || '#000000'}"></label><label>Прозорість, %<input id="g-shadow-opacity" type="number" min="0" max="100" value="${Math.round((clip.shadow?.opacity ?? .18)*100)}"></label><label>М’якість<input id="g-shadow-blur" type="number" min="0" max="100" value="${clip.shadow?.blur ?? 12}"></label><label>Зсув X<input id="g-shadow-x" type="number" min="-200" max="200" value="${clip.shadow?.x ?? 0}"></label><label>Зсув Y<input id="g-shadow-y" type="number" min="-200" max="200" value="${clip.shadow?.y ?? 4}"></label></div><button id="g-save" class="secondary full" type="button">Застосувати графіку</button>`;
  box.querySelector('.universal-properties')?.append(section);if(image){const fields=document.createElement('div');fields.className='property-grid';fields.innerHTML=`<label>Розмиття фону, px<input id="g-blur" type="number" min="0" max="80" value="${clip.blur || 0}"></label><label>Motion blur, %<input id="g-motion-blur" type="number" min="0" max="100" value="${Math.round((clip.motion_blur || 0)*100)}"></label>`;section.querySelector('.graphics-checkbox').before(fields);}
  if(text){
    const select=$('g-font');select.innerHTML=studioFontOptionsHtml();
    const sample=document.createElement('div');sample.className='project-font-sample graphic-font-sample';sample.textContent='Аа Бб Вв 123 · Guten Tag';
    select.closest('label').after(sample);
    select.addEventListener('change',async()=>{await document.fonts.load('400 32px '+JSON.stringify(select.value));sample.style.fontFamily=JSON.stringify(select.value);});
    sample.style.fontFamily=JSON.stringify(clip.font_family || 'Arial');
  }
  if(clip.text_words?.length){const words=document.createElement('div');words.className='property-grid';words.innerHTML='<label>Поява слів<select id="g-word-effect"><option value="none">Одразу</option><option value="fade">Прозорість</option><option value="up">Знизу</option><option value="down">Згори</option><option value="left">Зліва</option><option value="right">Справа</option><option value="pop">М’яка пружина</option><option value="grow">Наближення</option><option value="shrink">Віддалення</option><option value="blur">Крізь розмиття</option><option value="blur_up">Розмиття знизу</option><option value="letters_up">Літери знизу</option><option value="letters_fade">Літери поступово</option><option value="letters_blur">Літери крізь розмиття</option></select></label><label>Тривалість, с<input id="g-word-duration" type="number" min="0.05" max="0.6" step="0.01"></label><label>Рух, px<input id="g-word-distance" type="number" min="0" max="80"></label>';section.querySelector('.graphics-checkbox').before(words);$('g-word-effect').value=clip.word_entrance?.type || 'none';$('g-word-duration').value=clip.word_entrance?.duration || .16;$('g-word-distance').value=clip.word_entrance?.distance || 14;}
  if(text){$('g-font').value=clip.font_family || 'Arial';$('g-weight').value=String(clip.font_weight || 400);}
  if(image)$('g-mask').value=clip.mask || 'none';
  const shadowFields=()=>{$('g-shadow-fields').hidden=!$('g-shadow').checked;};$('g-shadow').addEventListener('change',shadowFields);shadowFields();
  $('g-save').addEventListener('click',()=>{const patch={shadow:$('g-shadow').checked?{color:$('g-shadow-color').value,opacity:Number($('g-shadow-opacity').value)/100,blur:Number($('g-shadow-blur').value),x:Number($('g-shadow-x').value),y:Number($('g-shadow-y').value)}:null};if(text)Object.assign(patch,{font_family:$('g-font').value,font_size:Number($('g-size').value),font_weight:Number($('g-weight').value)});if(image)Object.assign(patch,{mask:$('g-mask').value,corner_radius:Number($('g-radius').value),blur:Number($('g-blur').value),motion_blur:Number($('g-motion-blur').value)/100});if($('g-word-effect'))patch.word_entrance=$('g-word-effect').value==='none'?null:{type:$('g-word-effect').value,duration:Number($('g-word-duration').value),distance:Number($('g-word-distance').value)};action('batch',{actions:[...(text?[{type:'set_project_font',payload:{font_family:$('g-font').value}}]:[]),{type:'update_clip',payload:{clip_id:clip.id,patch}}]},'Графіку збережено.').catch(()=>{});});
}
