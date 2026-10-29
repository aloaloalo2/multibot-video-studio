// channel-branding.js — the top of the channel settings: whether the channel makes regular or animated videos, the
// channel logo with its place, size and opacity, and for animated channels the Razgon style with real frames of the
// channel's latest film. Every frame here places the logo with the same rule as the backend
// (backend/channel_branding.py): size and margin are percent of the frame width.
const brandingPositions=[['top-left','Угорі ліворуч'],['top-center','Угорі по центру'],['top-right','Угорі праворуч'],['middle-left','Посередині ліворуч'],null,['middle-right','Посередині праворуч'],['bottom-left','Унизу ліворуч'],['bottom-center','Унизу по центру'],['bottom-right','Унизу праворуч']];
const brandingDefaults={enabled:true,position:'top-right',size:12,margin:3,opacity:100};
const titleFonts=['Fredoka','Nunito','Playfair Display'];
// Ukrainian names for the built-in Razgon styles; a style the Studio does not know keeps its own name and description.
const styleNames={dusk:['Кінематографічні сутінки','Лілово-пурпурні тіні, бурштинове світло, кремовий контур, м’яке зерно, широкоекранні смуги.'],
  midnight:['Північна синява','Холодний нічний світ, біло-блакитний контур, помаранчеві ліхтарі, вища контрастність.'],
  golden:['Золота година','Тепле помаранчево-бірюзове світло, великі сонячні відблиски, світліші півтони.'],
  neon:['Неоновий нуар','Глибокий чорний, рожево-бірюзовий контур, світні вивіски, сильне сяйво.'],
  storybook:['Казкова книжка','Світла пастель, м’яка контрастність, лавандові тіні, легке паперове зерно.']};

function brandingSections(channel){
  const settings=channel.settings || {},kind=settings.channel_kind==='animated'?'animated':'regular',logo={...brandingDefaults,...(settings.logo || {})},animation=settings.animation || {};
  const kindCard=(value,title,text)=>`<label class="channel-kind-card"><input type="radio" name="channel-kind" value="${value}" ${kind===value?'checked':''}><span><strong>${title}</strong><small>${text}</small></span></label>`;
  const cells=brandingPositions.map(item=>item?`<button type="button" class="logo-position" data-position="${item[0]}" aria-label="${item[1]}" title="${item[1]}" aria-pressed="${logo.position===item[0]}"></button>`:'<span class="logo-position-gap" aria-hidden="true"></span>').join('');
  const slider=(id,label,min,max,value,unit)=>`<label class="logo-slider">${label}<span><input id="${id}" type="range" min="${min}" max="${max}" step="1" value="${value}"><output for="${id}">${value}${unit}</output></span></label>`;
  return `<section class="settings-section channel-kind-section"><h3>Тип каналу</h3><div class="channel-kind-options" role="radiogroup" aria-label="Тип каналу">${kindCard('regular','Звичайний','Фото, стокове й створене відео, текст')}${kindCard('animated','Анімаційний','Мультфільм Razgon зі своїм стилем')}</div></section>
    <section class="settings-section animated-only"><h3>Стиль анімації</h3><p>Кадри з останнього ролика каналу в кожному стилі. Виберіть стиль, і нові ролики каналу будуть у ньому.</p>
      <div class="style-toolbar"><label class="logo-toggle"><input id="style-assets" type="checkbox" ${animation.assets!==false?'checked':''}> Показувати асети</label>
        <label>Шрифт заголовків<select id="style-title-font">${titleFonts.map(font=>`<option ${(animation.title_font || 'Fredoka')===font?'selected':''}>${font}</option>`).join('')}</select></label>
        <label class="style-accent">Колір акценту<span><input id="style-accent-on" type="checkbox" ${animation.accent?'checked':''} aria-label="Свій колір акценту"><input id="style-accent" type="color" value="${animation.accent || '#ff4fa3'}"></span></label></div>
      <div id="style-gallery" class="style-gallery" aria-live="polite"></div></section>
    <section class="settings-section"><h3>Логотип каналу</h3><p>Логотип з'являється в кадрі в обраному місці. Розмір і відступ рахуються від ширини кадру.</p>
      <div class="logo-editor"><div class="logo-preview" id="logo-preview"><img id="logo-preview-image" class="logo-mark" alt=""><span id="logo-preview-empty">Логотип ще не додано</span></div>
        <div class="logo-controls"><div class="logo-file-row"><label class="secondary logo-file-button">Завантажити логотип<input id="logo-file" type="file" accept="image/png,image/jpeg,image/webp" hidden></label><button id="logo-remove" class="secondary" type="button">Прибрати</button></div>
          <label class="logo-toggle"><input id="logo-enabled" type="checkbox" ${logo.enabled?'checked':''}> Показувати логотип у роликах</label>
          <div class="logo-position-grid" role="group" aria-label="Місце логотипа">${cells}</div>
          ${slider('logo-size','Розмір',3,40,logo.size,'%')}${slider('logo-margin','Відступ від краю',0,15,logo.margin,'%')}${slider('logo-opacity','Прозорість',10,100,logo.opacity,'%')}
          <p id="logo-feedback" role="status" aria-live="polite"></p></div></div></section>`;
}

function bindBranding(channel){
  const settings=channel.settings || {},logo={...brandingDefaults,...(settings.logo || {})},animation=settings.animation || {};
  const frame=$('logo-preview'),image=$('logo-preview-image'),empty=$('logo-preview-empty'),feedback=$('logo-feedback'),gallery=$('style-gallery');
  let version=settings.logo?.version || 0,present=false,styles=null,chosen=animation.style || null,filmStyle=null,request=0;
  const kind=()=>document.querySelector('input[name="channel-kind"]:checked')?.value || 'regular';
  const logoUrl=()=>`/api/channels/${encodeURIComponent(channel.id)}/logo?v=${version}`;
  // The frame is 16:9, so a margin of m% of the width is m*16/9 % of the height.
  const place=mark=>{
    const size=Number($('logo-size').value),margin=Number($('logo-margin').value),[row,col]=logo.position.split('-');
    mark.style.width=size+'%';mark.style.opacity=String(Number($('logo-opacity').value)/100);
    mark.style.left=col==='left'?margin+'%':col==='right'?'auto':'50%';mark.style.right=col==='right'?margin+'%':'auto';
    mark.style.top=row==='top'?(margin*16/9)+'%':row==='middle'?'50%':'auto';mark.style.bottom=row==='bottom'?(margin*16/9)+'%':'auto';
    mark.style.transform=`translate(${col==='center'?'-50%':'0'},${row==='middle'?'-50%':'0'})`;
    mark.hidden=!present||!$('logo-enabled').checked;
  };
  // A regular channel shows the logo on a neutral frame; an animated one on a frame of its chosen style.
  const backdrop=()=>{const style=kind()==='animated'&&styles?.find(item=>item.id===chosen);frame.style.backgroundImage=style?`url("${style.frames[0]}")`:'';};
  const draw=()=>{
    place(image);empty.hidden=present;$('logo-remove').disabled=!present;
    for(const mark of gallery.querySelectorAll('.logo-mark')){if(mark.getAttribute('src')!==logoUrl())mark.src=logoUrl();place(mark);}
    for(const id of ['logo-size','logo-margin','logo-opacity'])$(id).nextElementSibling.textContent=$(id).value+'%';
  };
  const load=()=>{image.onload=()=>{present=true;draw();};image.onerror=()=>{present=false;draw();};image.src=logoUrl();};
  const renderGallery=()=>{
    gallery.replaceChildren();
    for(const style of styles){
      const card=document.createElement('button');card.type='button';card.className='style-card';card.setAttribute('aria-pressed',String(style.id===chosen));
      const [title,text]=styleNames[style.id] || [style.name,style.desc];
      card.innerHTML=`<span class="style-card-head"><strong>${esc(title)}</strong>${title!==style.name?`<span class="style-original">${esc(style.name)}</span>`:''}${style.id===filmStyle?'<span class="style-badge">Зараз у роликах каналу</span>':''}</span><span class="style-frames">${style.frames.map(url=>`<span class="style-frame"><img src="${esc(url)}" alt="" loading="lazy"><img class="logo-mark" alt=""></span>`).join('')}</span><small>${esc(text)}</small>`;
      card.addEventListener('click',()=>{chosen=style.id;gallery.querySelectorAll('.style-card').forEach(item=>item.setAttribute('aria-pressed',String(item===card)));backdrop();});
      gallery.append(card);
    }
    draw();backdrop();
  };
  const textStyle=()=>({title_font:$('style-title-font').value,...($('style-accent-on').checked?{accent:$('style-accent').value}:{})});
  const loadStyles=async()=>{
    if(kind()!=='animated')return;
    const mine=++request;gallery.innerHTML='<p class="style-loading">Малюємо кадри в кожному стилі, це займає кілька секунд...</p>';
    try{
      const data=await api(`/api/channels/${encodeURIComponent(channel.id)}/style-previews`,'POST',{assets:$('style-assets').checked,animation:textStyle()});
      if(mine!==request||!gallery.isConnected)return;
      styles=data.styles;filmStyle=data.film_style;chosen=chosen || filmStyle || styles[0]?.id;renderGallery();
    }catch(error){if(mine===request&&gallery.isConnected)gallery.innerHTML=`<p class="style-loading">${esc(error.message)}</p>`;}
  };
  for(const button of document.querySelectorAll('.logo-position'))button.addEventListener('click',()=>{logo.position=button.dataset.position;document.querySelectorAll('.logo-position').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));draw();});
  for(const id of ['logo-size','logo-margin','logo-opacity','logo-enabled'])$(id).addEventListener('input',draw);
  for(const id of ['style-assets','style-title-font','style-accent-on','style-accent'])$(id).addEventListener('change',loadStyles);
  $('logo-file').addEventListener('change',async event=>{
    const file=event.target.files[0];event.target.value='';if(!file)return;
    if(file.size>6*1024*1024){feedback.textContent='Файл завеликий, оберіть логотип до 6 МБ.';return;}
    feedback.textContent='Завантажуємо логотип...';
    try{
      const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('Не вдалося прочитати файл.'));reader.readAsDataURL(file);});
      await api(`/api/channels/${encodeURIComponent(channel.id)}/logo`,'POST',{data});
      version=Date.now();load();feedback.textContent='Логотип додано. Натисніть «Зберегти», щоб запам’ятати місце й розмір.';
    }catch(error){feedback.textContent=error.message;}
  });
  $('logo-remove').addEventListener('click',async()=>{
    try{await api(`/api/channels/${encodeURIComponent(channel.id)}/logo`,'DELETE');version=Date.now();present=false;draw();feedback.textContent='Логотип прибрано.';}catch(error){feedback.textContent=error.message;}
  });
  const applyKind=()=>{$('modal-backdrop').dataset.channelKind=kind();backdrop();if(kind()==='animated'&&!styles)loadStyles();};
  for(const radio of document.querySelectorAll('input[name="channel-kind"]'))radio.addEventListener('change',applyKind);
  applyKind();draw();load();
  return ()=>({channel_kind:kind(),
    logo:{enabled:$('logo-enabled').checked,position:logo.position,size:Number($('logo-size').value),margin:Number($('logo-margin').value),opacity:Number($('logo-opacity').value),version},
    ...(kind()==='animated'?{animation:{...(chosen?{style:chosen}:{}),assets:$('style-assets').checked,...textStyle()}}:{})});
}
