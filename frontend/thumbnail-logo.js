// The channel's logo laid by hand on a thumbnail (user, 17 November 2026: «біля неї кнопку… логотип… вона зразу додає
// логотип на картинку, яку я можу пересовувати… видалити… зменшити, збільшити»). «Логотип» beside «Порівняти» puts the
// logo on the picture at once: drag it, resize it by a dot on its left corners, take it off with ×. «Зберегти» makes a
// new version with the logo and makes it the cover (backend/thumbnail_logo.place); the picture it came from stays.
// The size last used for the channel comes back next time, so only the place is left to choose; a click beside the
// logo hides its frame to see the picture as it will be (user, 18 November 2026).
function bindThumbnailLogo(section,project,data,saved){
  const frame=section.querySelector('.thumb-view-frame'),logo=data.channel_logo;
  const button=document.createElement('button');button.type='button';button.className='outline thumb-logo-toggle';button.hidden=true;
  StudioUI.action(button,{label:'Логотип',icon:'image'});button.setAttribute('aria-pressed','false');
  button.title=logo?'Додати логотип каналу на прев’ю':'Спершу додайте логотип у налаштуваннях каналу';
  let item=null,layer=null,bar=null,place=null,saving=false,outside=null;
  const sizeKey='thumbLogoWidth:'+(project.channel_id||'');
  const lastWidth=()=>{try{const v=Number(localStorage.getItem(sizeKey));return v>=.03&&v<=.8?v:.14;}catch{return .14;}};
  const keepWidth=()=>{try{if(place)localStorage.setItem(sizeKey,String(place.width));}catch{}};
  const picture=()=>frame.querySelector(':scope>img');
  // where the picture is drawn inside its box (it keeps its shape in the middle of the frame)
  const box=()=>{
    const img=picture(),f=frame.getBoundingClientRect(),r=img.getBoundingClientRect();
    const ratio=(img.naturalWidth&&img.naturalHeight)?img.naturalWidth/img.naturalHeight:16/9;
    let w=r.width,h=r.height;if(w/h>ratio)w=h*ratio;else h=w/ratio;
    return {left:r.left-f.left+(r.width-w)/2,top:r.top-f.top+(r.height-h)/2,width:w,height:h};
  };
  const heightShare=b=>place.width*b.width*logo.height/logo.width/b.height;
  const clamp=()=>{
    const b=box();place.width=Math.min(.8,Math.max(.03,place.width));
    place.x=Math.min(Math.max(0,place.x),1-place.width);place.y=Math.min(Math.max(0,place.y),Math.max(0,1-heightShare(b)));
  };
  const paint=()=>{
    if(!layer)return;const b=box(),w=place.width*b.width;
    Object.assign(layer.style,{left:`${b.left+place.x*b.width}px`,top:`${b.top+place.y*b.height}px`,width:`${w}px`,height:`${w*logo.height/logo.width}px`});
  };
  const close=()=>{if(outside)document.removeEventListener('pointerdown',outside,true);outside=null;layer?.remove();bar?.remove();layer=bar=place=null;frame.classList.remove('is-placing-logo');button.setAttribute('aria-pressed','false');};
  // resize from a left corner: the right edge stays; from the top-left the bottom edge stays too
  const drag=(event,resize)=>{
    event.preventDefault();event.stopPropagation();
    const b=box(),pointer={x:event.clientX,y:event.clientY},start={...place},target=event.currentTarget,startH=heightShare(b);target.setPointerCapture?.(event.pointerId);
    const move=e=>{
      const dx=(e.clientX-pointer.x)/b.width,dy=(e.clientY-pointer.y)/b.height;
      if(resize==='right'){place.width=Math.min(.8,Math.max(.03,start.width+dx));}   // the bottom-right dot: left and top edges stay
      else if(resize){
        place.width=Math.min(.8,Math.max(.03,start.width-dx));place.x=start.x+start.width-place.width;
        if(resize==='top')place.y=start.y+startH-heightShare(b);
      }else{place.x=start.x+dx;place.y=start.y+dy;}
      clamp();paint();
    };
    const up=()=>{if(resize)keepWidth();target.removeEventListener('pointermove',move);target.removeEventListener('pointerup',up);target.removeEventListener('pointercancel',up);};
    target.addEventListener('pointermove',move);target.addEventListener('pointerup',up);target.addEventListener('pointercancel',up);
  };
  const save=async()=>{
    if(!place||saving)return;saving=true;bar.querySelectorAll('button').forEach(b=>b.disabled=true);
    try{
      const result=await api(`/api/projects/${encodeURIComponent(project.id)}/thumbnail/logo`,'POST',{base:item.name,x:place.x,y:place.y,width:place.width});
      keepWidth();close();status('Логотип додано: нова версія прев’ю стала обкладинкою.');saved(result.name);
    }catch(error){status(error.message,true);bar?.querySelectorAll('button').forEach(b=>b.disabled=false);}
    finally{saving=false;}
  };
  const open=()=>{
    if(!logo||!item?.name||!picture())return;
    close();place={x:.03,y:.04,width:lastWidth()};
    layer=document.createElement('div');layer.className='thumb-logo-layer';layer.title='Перетягніть логотип; точка ліворуч змінює розмір';
    layer.innerHTML=`<img src="${logo.url}" alt="Логотип каналу" draggable="false"><span class="thumb-logo-resize top" aria-hidden="true"></span><span class="thumb-logo-resize bottom" aria-hidden="true"></span><span class="thumb-logo-resize right" aria-hidden="true"></span><button type="button" class="thumb-logo-remove" title="Прибрати логотип" aria-label="Прибрати логотип">×</button>`;
    layer.addEventListener('pointerdown',event=>{layer.classList.remove('quiet');if(!event.target.closest('.thumb-logo-remove,.thumb-logo-resize'))drag(event,false);});
    layer.querySelector('.thumb-logo-resize.top').addEventListener('pointerdown',event=>drag(event,'top'));
    layer.querySelector('.thumb-logo-resize.bottom').addEventListener('pointerdown',event=>drag(event,'bottom'));
    layer.querySelector('.thumb-logo-resize.right').addEventListener('pointerdown',event=>drag(event,'right'));
    // a click anywhere beside the logo hides its frame, dots and ×; a click on the logo brings them back
    outside=event=>{if(layer&&!event.target.closest('.thumb-logo-layer,.thumb-logo-bar,.thumb-logo-toggle'))layer.classList.add('quiet');};
    document.addEventListener('pointerdown',outside,true);
    layer.querySelector('.thumb-logo-remove').addEventListener('click',close);
    bar=document.createElement('div');bar.className='thumb-logo-bar';
    bar.innerHTML='<button type="button" class="primary thumb-logo-save">Зберегти</button>';
    bar.querySelector('.thumb-logo-save').addEventListener('click',save);
    frame.append(layer,bar);frame.classList.add('is-placing-logo');button.setAttribute('aria-pressed','true');
    clamp();paint();
  };
  button.addEventListener('click',()=>{if(layer)close();else if(logo)open();else status('Спершу додайте логотип у налаштуваннях каналу.',true);});
  if(typeof ResizeObserver==='function')new ResizeObserver(()=>{if(layer){clamp();paint();}}).observe(frame);
  return next=>{
    if(item?.key!==next.key)close();item=next;
    // only the episode's own versions: a translated thumbnail has its own versions in «Мови»
    const tools=frame.querySelector('.thumb-preview-tools');
    if(tools){const compare=tools.querySelector('.thumb-compare-toggle');if(compare){if(compare.nextSibling!==button)compare.after(button);}else if(button.parentNode!==tools)tools.prepend(button);}
    button.hidden=!(next.code==='original'&&next.name);
  };
}
