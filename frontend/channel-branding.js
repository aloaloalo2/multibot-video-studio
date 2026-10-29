// channel-branding.js — the top of the channel settings: whether the channel makes regular or animated videos, and how
// the channel looks. One big frame shows the logo in its place; for an animated channel that frame is Razgon's style card
// (the character by a house) in the chosen style, with every template style as a thumbnail underneath and, on request,
// real frames of the channel's latest film. Every frame places the logo with the same rule as the backend
// (backend/channel_branding.py): size and margin are percent of the frame width.
const brandingPositions=[['top-left','Угорі ліворуч'],['top-center','Угорі по центру'],['top-right','Угорі праворуч'],['middle-left','Посередині ліворуч'],null,['middle-right','Посередині праворуч'],['bottom-left','Унизу ліворуч'],['bottom-center','Унизу по центру'],['bottom-right','Унизу праворуч']];
const brandingDefaults={enabled:true,position:'top-right',size:12,margin:3,opacity:100};
const titleFonts=['Fredoka','Nunito','Playfair Display'];
// Ukrainian names for the template Razgon styles; a style the Studio does not know keeps its own name and description.
const styleNames={neon:['Неоновий нуар','Глибокий чорний, рожево-бірюзовий контур, світні вивіски, сильне сяйво.'],
  dusk:['Кіно-сутінки','Лілові тіні, бурштинове світло, кремовий контур, широкоекранні смуги.'],
  doodle:['Дудл у зошиті','Пастель, чорна тремтлива обводка, лінії «киплять», папір.'],
  ink:['Туш','Чорно-біла графіка: сірі тони, чорний контур, без кольору.'],
  cutout:['Аплікація','Пласкі шари кольорового паперу з тінню під кожною фігурою.'],
  chalk:['Крейда','Зелена дошка, білі крейдяні контури, прозорі заливки.'],
  midnight:['Північна синява','Холодний нічний світ, біло-блакитний контур, помаранчеві ліхтарі.'],
  golden:['Золота година','Тепле помаранчево-бірюзове світло, великі сонячні відблиски.'],
  storybook:['Казкова книжка','Світла пастель, м’яка контрастність, лавандові тіні.']};

function brandingSections(channel){
  const settings=channel.settings || {},kind=settings.channel_kind==='animated'?'animated':'regular',logo={...brandingDefaults,...(settings.logo || {})},animation=settings.animation || {};
  const kindCard=(value,title,text)=>`<label class="channel-kind-card"><input type="radio" name="channel-kind" value="${value}" ${kind===value?'checked':''}><span><strong>${title}</strong><small>${text}</small></span></label>`;
  const cells=brandingPositions.map(item=>item?`<button type="button" class="logo-position" data-position="${item[0]}" aria-label="${item[1]}" title="${item[1]}" aria-pressed="${logo.position===item[0]}"></button>`:'<span class="logo-position-gap" aria-hidden="true"></span>').join('');
  const slider=(id,label,min,max,value,unit)=>`<label class="logo-slider">${label}<span><input id="${id}" type="range" min="${min}" max="${max}" step="1" value="${value}"><output for="${id}">${value}${unit}</output></span></label>`;
  return `<section class="settings-section channel-kind-section"><h3>Тип каналу</h3><div class="channel-kind-options" role="radiogroup" aria-label="Тип каналу">${kindCard('regular','Звичайний','Фото, стокове й створене відео, текст')}${kindCard('animated','Анімаційний','Мультфільм Razgon зі своїм стилем')}</div></section>
    <section class="settings-section channel-look"><h3><span class="animated-only">Стиль і логотип</span><span class="regular-only">Логотип каналу</span></h3>
      <div class="logo-preview" id="logo-preview"><img id="logo-preview-image" class="logo-mark" alt=""><span id="logo-preview-empty" class="regular-only">Логотип ще не додано</span><span id="style-stage-state" class="style-stage-state animated-only" role="status" aria-live="polite"></span></div>
      <div class="animated-only"><p id="style-caption" class="style-caption"></p>
        <div id="style-strip" class="style-strip" role="radiogroup" aria-label="Стиль анімації"></div>
        <div class="style-toolbar"><label>Шрифт заголовків<select id="style-title-font">${titleFonts.map(font=>`<option ${(animation.title_font || 'Fredoka')===font?'selected':''}>${font}</option>`).join('')}</select></label>
          <label class="logo-toggle" title="Асети з бібліотеки ролика на кадрах з ролика"><input id="style-assets" type="checkbox" ${animation.assets!==false?'checked':''}> Асети з бібліотеки</label>
          <button id="style-film-toggle" class="secondary" type="button" aria-expanded="false">Показати на кадрах ролика</button></div>
        <div id="style-film" class="style-film" hidden></div></div>
      <div class="logo-controls"><div class="logo-file-row"><label class="secondary logo-file-button">Завантажити логотип<input id="logo-file" type="file" accept="image/png,image/jpeg,image/webp" hidden></label><button id="logo-remove" class="secondary" type="button">Прибрати</button>
          <label class="logo-toggle"><input id="logo-enabled" type="checkbox" ${logo.enabled?'checked':''}> Показувати в роликах</label></div>
        <div class="logo-place"><div class="logo-position-grid" role="group" aria-label="Місце логотипа">${cells}</div>
          <div class="logo-sliders">${slider('logo-size','Розмір',3,40,logo.size,'%')}${slider('logo-margin','Відступ від краю',0,15,logo.margin,'%')}${slider('logo-opacity','Прозорість',10,100,logo.opacity,'%')}</div></div>
        <p id="logo-feedback" role="status" aria-live="polite"></p></div></section>`;
}

function bindBranding(channel){
  const settings=channel.settings || {},logo={...brandingDefaults,...(settings.logo || {})},animation=settings.animation || {};
  const frame=$('logo-preview'),image=$('logo-preview-image'),empty=$('logo-preview-empty'),feedback=$('logo-feedback'),strip=$('style-strip'),film=$('style-film'),stage=$('style-stage-state');
  let version=settings.logo?.version || 0,present=false,styles=null,chosen=animation.style || null,filmStyle=null,request=0,filmRequest=0;
  const kind=()=>document.querySelector('input[name="channel-kind"]:checked')?.value || 'regular';
  const logoUrl=()=>`/api/channels/${encodeURIComponent(channel.id)}/logo?v=${version}`;
  const named=style=>styleNames[style.id] || [style.name,style.desc];
  // The frame is 16:9, so a margin of m% of the width is m*16/9 % of the height.
  const place=mark=>{
    const size=Number($('logo-size').value),margin=Number($('logo-margin').value),[row,col]=logo.position.split('-');
    mark.style.width=size+'%';mark.style.opacity=String(Number($('logo-opacity').value)/100);
    mark.style.left=col==='left'?margin+'%':col==='right'?'auto':'50%';mark.style.right=col==='right'?margin+'%':'auto';
    mark.style.top=row==='top'?(margin*16/9)+'%':row==='middle'?'50%':'auto';mark.style.bottom=row==='bottom'?(margin*16/9)+'%':'auto';
    mark.style.transform=`translate(${col==='center'?'-50%':'0'},${row==='middle'?'-50%':'0'})`;
    mark.hidden=!present||!$('logo-enabled').checked;
  };
  const draw=()=>{
    place(image);empty.hidden=present;$('logo-remove').disabled=!present;
    for(const mark of film.querySelectorAll('.logo-mark')){if(mark.getAttribute('src')!==logoUrl())mark.src=logoUrl();place(mark);}
    for(const id of ['logo-size','logo-margin','logo-opacity'])$(id).nextElementSibling.textContent=$(id).value+'%';
  };
  const load=()=>{image.onload=()=>{present=true;draw();};image.onerror=()=>{present=false;draw();};image.src=logoUrl();};
  // A regular channel shows the logo on a neutral frame; an animated one on the style card of its chosen style.
  const backdrop=()=>{
    const style=kind()==='animated'&&styles?.find(item=>item.id===chosen);
    frame.style.backgroundImage=style?`url("${style.card}")`:'';
    if(style){const [title,text]=named(style);$('style-caption').innerHTML=`<strong>${esc(title)}</strong>${style.id===filmStyle?'<span class="style-badge">Зараз у роликах</span>':''}<span>${esc(text)}</span>`;}
  };
  const choose=id=>{chosen=id;strip.querySelectorAll('.style-thumb').forEach(item=>item.setAttribute('aria-checked',String(item.dataset.style===id)));backdrop();if(!film.hidden)loadFilm();};
  const renderStrip=()=>{
    strip.replaceChildren();
    for(const style of styles){
      const thumb=document.createElement('button');thumb.type='button';thumb.className='style-thumb';thumb.dataset.style=style.id;thumb.setAttribute('role','radio');thumb.setAttribute('aria-checked',String(style.id===chosen));
      thumb.innerHTML=`<img src="${esc(style.card)}" alt=""><span>${esc(named(style)[0])}</span>`;
      thumb.addEventListener('click',()=>choose(style.id));
      strip.append(thumb);
    }
    backdrop();
  };
  const textStyle=()=>({title_font:$('style-title-font').value});
  const loadStyles=async()=>{
    if(kind()!=='animated')return;
    const mine=++request;stage.textContent=styles?'':'Малюємо стилі, перший раз це кілька секунд...';
    try{
      const data=await api(`/api/channels/${encodeURIComponent(channel.id)}/style-cards`,'POST',{animation:textStyle()});
      if(mine!==request||!strip.isConnected)return;
      styles=data.styles;filmStyle=data.film_style;
      if(!styles.some(style=>style.id===chosen))chosen=styles.some(style=>style.id===filmStyle)?filmStyle:styles[0]?.id;
      stage.textContent='';renderStrip();
    }catch(error){if(mine===request&&strip.isConnected)stage.textContent=error.message;}
  };
  // Real frames of the latest film in the chosen style, drawn only when asked for: they take a few seconds per style.
  const loadFilm=async()=>{
    if(!chosen)return;
    const mine=++filmRequest;film.innerHTML='<p class="style-loading">Малюємо кадри ролика в цьому стилі...</p>';
    try{
      const data=await api(`/api/channels/${encodeURIComponent(channel.id)}/style-previews`,'POST',{style:chosen,assets:$('style-assets').checked,animation:textStyle()});
      if(mine!==filmRequest||!film.isConnected)return;
      const style=data.styles[0];
      film.innerHTML=style.frames.map(url=>`<span class="style-frame"><img src="${esc(url)}" alt="" loading="lazy"><img class="logo-mark" alt=""></span>`).join('');
      draw();
    }catch(error){if(mine===filmRequest&&film.isConnected)film.innerHTML=`<p class="style-loading">${esc(error.message)}</p>`;}
  };
  $('style-film-toggle').addEventListener('click',event=>{
    film.hidden=!film.hidden;event.currentTarget.setAttribute('aria-expanded',String(!film.hidden));
    event.currentTarget.textContent=film.hidden?'Показати на кадрах ролика':'Сховати кадри ролика';
    if(!film.hidden)loadFilm();
  });
  $('style-title-font').addEventListener('change',()=>{loadStyles();if(!film.hidden)loadFilm();});
  $('style-assets').addEventListener('change',()=>{if(!film.hidden)loadFilm();});
  for(const button of document.querySelectorAll('.logo-position'))button.addEventListener('click',()=>{logo.position=button.dataset.position;document.querySelectorAll('.logo-position').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));draw();});
  for(const id of ['logo-size','logo-margin','logo-opacity','logo-enabled'])$(id).addEventListener('input',draw);
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
