// channel-branding.js — the top of the channel settings: whether the channel makes regular or animated videos, and how
// the channel looks. One big frame shows the logo in its place; for an animated channel that frame is Razgon's style card
// (the character by a house) in the chosen style, with every template style as a thumbnail underneath and, on request,
// real frames of the channel's latest film. Every frame places the logo with the same rule as the backend
// (backend/channel_branding.py): size and margin are percent of the frame width.
const brandingPositions=[['top-left','Угорі ліворуч'],['top-center','Угорі по центру'],['top-right','Угорі праворуч'],['middle-left','Посередині ліворуч'],null,['middle-right','Посередині праворуч'],['bottom-left','Унизу ліворуч'],['bottom-center','Унизу по центру'],['bottom-right','Унизу праворуч']];
const razgonDefaultStyle='dusk';   // tools/razgon_bridge.py prepare: the style of a channel that names none
const brandingDefaults={enabled:true,position:'top-right',size:12,margin:3,opacity:100};
const titleFonts=['Fredoka','Baloo 2','Lilita One','Bangers','Bebas Neue','Montserrat','Permanent Marker','Nunito','Playfair Display'];
// Ukrainian names for the template Razgon styles; a style the Studio does not know keeps its own name and description.
const styleNames={neon:['Неоновий нуар','Глибокий чорний, рожево-бірюзовий контур, світні вивіски, сильне сяйво.'],
  dusk:['Кіно-сутінки','Лілові тіні, бурштинове світло, кремовий контур, широкоекранні смуги.'],
  doodle:['Дудл у зошиті','Пастель, чорна тремтлива обводка, лінії «киплять», папір.'],
  ink:['Туш','Чорно-біла графіка: сірі тони, чорний контур, без кольору.'],
  cutout:['Аплікація','Пласкі шари кольорового паперу з тінню під кожною фігурою.'],
  chalk:['Крейда','Зелена дошка, білі крейдяні контури, прозорі заливки.'],
  midnight:['Північна синява','Холодний нічний світ, біло-блакитний контур, помаранчеві ліхтарі.'],
  golden:['Золота година','Тепле помаранчево-бірюзове світло, великі сонячні відблиски.'],
  storybook:['Казкова книжка','Світла пастель, м’яка контрастність, лавандові тіні.'],
  clinic:['Чиста клініка','Світлий медичний світ: біло-блакитні стіни, тонкий синій контур, бірюзові акценти, без зерна.'],
  bluewhite:['Синє на білому','Синій малюнок на білому: п’ять відтінків синього, тонкий темно-синій контур, суцільні заливки, без світіння.'],
  whiteblue:['Біле на синьому','Синій світ і білі лінії: сині заливки, білий контур і білий герой, без світіння.'],
  blueglow:['Синє сяйво','Нічний синій світ із бірюзовим світлом: м’які переливи, світний контур героя, сильне сяйво, без ліній.'],
  care:['Турбота','Дружня аптечна пастель: м’ятні й білі кімнати, коралові акценти, м’які паперові тіні.']};

function brandingSections(channel){
  const settings=channel.settings || {},kind=settings.channel_kind==='animated'?'animated':'regular',logo={...brandingDefaults,...(settings.logo || {})},animation=settings.animation || {};
  const kindCard=(value,title,text)=>`<label class="channel-kind-card"><input type="radio" name="channel-kind" value="${value}" ${kind===value?'checked':''}><span><strong>${title}</strong><small>${text}</small></span></label>`;
  const cells=brandingPositions.map(item=>item?`<button type="button" class="logo-position" data-position="${item[0]}" aria-label="${item[1]}" title="${item[1]}" aria-pressed="${logo.position===item[0]}"></button>`:'<span class="logo-position-gap" aria-hidden="true"></span>').join('');
  const slider=(id,label,min,max,value,unit)=>`<label class="logo-slider">${label}<span><input id="${id}" type="range" min="${min}" max="${max}" step="1" value="${value}"><output for="${id}">${value}${unit}</output></span></label>`;
  return `<section class="settings-section channel-name-section"><label for="channel-name"><h3>Назва каналу</h3></label><input id="channel-name" type="text" maxlength="80" autocomplete="off" value="${esc(channel.name)}"></section>
    <section class="settings-section channel-kind-section"><h3>Тип каналу</h3><div class="channel-kind-options" role="radiogroup" aria-label="Тип каналу">${kindCard('regular','Звичайний','Фото, стокове й створене відео, текст')}${kindCard('animated','Анімаційний','Мультфільм Razgon зі своїм стилем')}</div></section>
    <section class="settings-section logo-section"><h3>Логотип каналу</h3>
      <div class="logo-file">
        <label class="logo-tile" id="logo-tile" title="Завантажити логотип"><input id="logo-file" type="file" accept="image/png,image/jpeg,image/webp" hidden>
          <img id="logo-tile-image" alt="Логотип каналу" hidden>
          <span class="logo-tile-empty" id="logo-tile-empty"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15V4m0 0-4 4m4-4 4 4M5 15v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3"/></svg>Додати</span></label>
        <div class="logo-file-info"><strong id="logo-file-title">Логотип ще не додано</strong>
          <small id="logo-file-meta">Перетягніть картинку в квадрат або натисніть на нього. Найкраще PNG з прозорим фоном, до 6 МБ.</small>
          <div class="logo-file-actions"><button id="logo-replace" class="secondary" type="button" hidden>Замінити</button><button id="logo-remove" class="logo-remove" type="button" hidden>Видалити</button></div></div>
        <label class="logo-switch" id="logo-switch"><input id="logo-enabled" type="checkbox" role="switch" ${logo.enabled?'checked':''}><span aria-hidden="true"></span>Показувати в роликах</label>
      </div>
      <div class="logo-place" id="logo-place" hidden>
        <div class="logo-mini" id="logo-mini" aria-hidden="true"><img class="logo-mark" alt=""></div>
        <div class="logo-place-controls"><div class="logo-place-row"><span class="logo-place-label">Місце</span><div class="logo-position-grid" role="group" aria-label="Місце логотипа">${cells}</div></div>
          <div class="logo-sliders">${slider('logo-size','Розмір',3,40,logo.size,'%')}${slider('logo-margin','Відступ від краю',0,15,logo.margin,'%')}${slider('logo-opacity','Видимість',10,100,logo.opacity,'%')}</div></div>
      </div>
      <p id="logo-feedback" class="logo-feedback" role="status" aria-live="polite"></p></section>
    <section class="settings-section channel-look"><h3><span class="regular-only">Стиль 2D-анімації Razgon</span><span class="animated-only">Стиль анімації</span></h3>
      <p class="regular-only style-note">Як виглядають кадри 2D-анімації Razgon у звичайних роликах каналу.</p>
      <div class="logo-preview" id="logo-preview"><img id="logo-preview-image" class="logo-mark" alt=""><span id="style-stage-state" class="style-stage-state" role="status" aria-live="polite"></span></div>
      <div><p id="style-caption" class="style-caption"></p>
        <div id="style-strip" class="style-strip" role="radiogroup" aria-label="Стиль анімації"></div><input id="style-copy-file" type="file" accept="image/png,image/jpeg,image/webp" hidden>
        <div class="style-toolbar"><label>Шрифт заголовків<select id="style-title-font">${titleFonts.map(font=>`<option ${(animation.title_font || 'Fredoka')===font?'selected':''}>${font}</option>`).join('')}</select></label>
          <label class="logo-toggle" title="Агент бере готові картинки предметів з бібліотеки або замовляє їх у Codex. Вимкнено: усе малюється кодом, фігурами."><input id="style-assets" type="checkbox" ${animation.assets!==false?'checked':''}> Готові картинки предметів</label>
          <button id="style-film-toggle" class="secondary animated-only" type="button" aria-expanded="false">Показати на кадрах ролика</button></div>
        <div id="style-film" class="style-film" hidden></div></div></section>`;
}

function bindBranding(channel){
  const settings=channel.settings || {},logo={...brandingDefaults,...(settings.logo || {})},animation=settings.animation || {};
  const frame=$('logo-preview'),image=$('logo-preview-image'),mini=$('logo-mini'),tileImage=$('logo-tile-image'),feedback=$('logo-feedback'),strip=$('style-strip'),film=$('style-film'),stage=$('style-stage-state');
  let version=settings.logo?.version || 0,present=false,styles=null,cards=null,chosen=animation.style || null,filmStyle=null,request=0,filmRequest=0;
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
  // the file itself in its tile, its size, and the placing controls only while there is a logo to place
  const draw=()=>{
    place(image);
    tileImage.hidden=!present;$('logo-tile-empty').hidden=present;$('logo-tile').classList.toggle('has-logo',present);
    $('logo-replace').hidden=!present;$('logo-remove').hidden=!present;$('logo-place').hidden=!present;$('logo-switch').hidden=!present;
    $('logo-file-title').textContent=present?'Логотип каналу':'Логотип ще не додано';
    $('logo-file-meta').textContent=present?`${tileImage.naturalWidth} × ${tileImage.naturalHeight} пікселів${$('logo-enabled').checked?'':' · у роликах не показується'}`:'Перетягніть картинку в квадрат або натисніть на нього. Найкраще PNG з прозорим фоном, до 6 МБ.';
    $('logo-place').classList.toggle('is-off',!$('logo-enabled').checked);
    for(const mark of [...film.querySelectorAll('.logo-mark'),...mini.querySelectorAll('.logo-mark')]){if(mark.getAttribute('src')!==logoUrl())mark.src=logoUrl();place(mark);}
    for(const id of ['logo-size','logo-margin','logo-opacity'])$(id).nextElementSibling.textContent=$(id).value+'%';
  };
  const load=()=>{tileImage.onload=()=>{present=true;draw();};tileImage.onerror=()=>{present=false;draw();};tileImage.src=logoUrl();image.src=logoUrl();};
  // Every card (style x title font x assets) is drawn ahead of time, so switching a font or the assets only swaps pictures.
  const card=id=>cards?.[$('style-title-font').value]?.[$('style-assets').checked?'1':'0']?.[id] || '';
  // The logo sits on the style card of the chosen Razgon style: an animated channel's films and a regular channel's 2D-animation frames.
  const backdrop=()=>{
    const style=styles?.find(item=>item.id===chosen);
    frame.style.backgroundImage=mini.style.backgroundImage=style?`url("${card(style.id)}")`:'';
    if(style){const [title,text]=named(style);$('style-caption').innerHTML=`<strong>${esc(title)}</strong>${style.id===filmStyle?'<span class="style-badge">Зараз у роликах</span>':''}<span>${esc(text)}</span>`;}
    else if(!styles)$('style-caption').innerHTML='<strong>Завантажуємо стилі…</strong>';
  };
  const choose=id=>{chosen=id;strip.querySelectorAll('.style-thumb').forEach(item=>item.setAttribute('aria-checked',String(item.dataset.style===id)));backdrop();if(!film.hidden)loadFilm();};
  const renderStrip=()=>{
    strip.replaceChildren();
    for(const style of styles){
      const cell=document.createElement('div');cell.className='style-cell';
      const thumb=document.createElement('button');thumb.type='button';thumb.className='style-thumb';thumb.dataset.style=style.id;thumb.setAttribute('role','radio');thumb.setAttribute('aria-checked',String(style.id===chosen));
      thumb.innerHTML=`<img src="${esc(card(style.id))}" alt=""><span>${esc(named(style)[0])}</span>`;
      thumb.addEventListener('click',()=>choose(style.id));
      cell.append(thumb);
      if(style.own){
        const remove=document.createElement('button');remove.type='button';remove.className='style-remove';remove.title=`Видалити стиль «${style.name}»`;remove.setAttribute('aria-label',remove.title);remove.textContent='×';
        remove.addEventListener('click',()=>removeStyle(style));
        cell.append(remove);
      }
      strip.append(cell);
    }
    // The last tile copies a look from any picture: DeepSeek reads it and the channel gets its own style.
    const add=document.createElement('button');add.type='button';add.className='style-thumb style-add';add.disabled=busy;
    add.innerHTML='<span class="style-add-box" aria-hidden="true">+</span><span>Скопіювати стиль</span>';add.title='Завантажте кадр чи ілюстрацію, і DeepSeek зробить з неї стиль каналу';
    add.addEventListener('click',()=>$('style-copy-file').click());
    strip.append(add);
    backdrop();
  };
  let busy=false;
  const removeStyle=async style=>{
    if(!confirm(`Видалити стиль «${style.name}»? Ролики, які вже в ньому, не зміняться.`))return;
    try{
      await api(`/api/channels/${encodeURIComponent(channel.id)}/custom-styles/${encodeURIComponent(style.id)}`,'DELETE');
      styles=styles.filter(item=>item.id!==style.id);
      if(chosen===style.id)chosen=styles.some(item=>item.id===filmStyle)?filmStyle:styles[0]?.id;
      renderStrip();
    }catch(error){stage.textContent=error.message;}
  };
  $('style-copy-file').addEventListener('change',async event=>{
    const file=event.target.files[0];event.target.value='';if(!file||busy)return;
    if(file.size>15*1024*1024){stage.textContent='Картинка завелика, оберіть до 15 МБ.';return;}
    busy=true;renderStrip();stage.textContent='DeepSeek вивчає картинку, це до півхвилини...';
    try{
      const image=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('Не вдалося прочитати файл.'));reader.readAsDataURL(file);});
      const {style}=await api(`/api/channels/${encodeURIComponent(channel.id)}/custom-styles`,'POST',{image});
      chosen=style.id;busy=false;
      stage.textContent=`Стиль «${style.name}» готовий. Малюємо його картки для всіх шрифтів...`;
      await loadStyles(false);
    }catch(error){busy=false;stage.textContent=error.message;renderStrip();}
  });
  const textStyle=()=>({title_font:$('style-title-font').value,assets:$('style-assets').checked});
  const swap=()=>{for(const thumb of strip.querySelectorAll('.style-thumb[data-style]'))thumb.querySelector('img').src=card(thumb.dataset.style);backdrop();};
  const loadStyles=async(announce=true)=>{
    const mine=++request;if(announce)stage.textContent='Готуємо стилі. Студія малює їх один раз, далі вони відкриваються одразу...';
    try{
      const data=await api(`/api/channels/${encodeURIComponent(channel.id)}/style-cards`,'POST',{});
      if(mine!==request||!strip.isConnected)return;
      styles=data.styles;cards=data.cards;filmStyle=data.film_style;
      // A channel without a saved style shows the one its films are drawn in: the latest film's, otherwise Razgon's own
      // default «Кіно-сутінки» (razgon_bridge.py prepare takes dusk when the channel names none), never «не вибрано».
      if(!styles.some(style=>style.id===chosen))chosen=[filmStyle,razgonDefaultStyle].find(id=>styles.some(style=>style.id===id)) || styles[0]?.id || null;
      stage.textContent='';renderStrip();
    }catch(error){
      if(mine!==request||!strip.isConnected)return;
      // the stage line shows only on an animated channel: the caption says why there are no cards on both
      stage.textContent=error.message;
      $('style-caption').innerHTML=`<strong>Стилі анімації зараз недоступні</strong><span>${esc(error.message)}</span>`;
    }
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
  $('style-title-font').addEventListener('change',()=>{swap();if(!film.hidden)loadFilm();});
  $('style-assets').addEventListener('change',()=>{swap();if(!film.hidden)loadFilm();});
  for(const button of document.querySelectorAll('.logo-position'))button.addEventListener('click',()=>{logo.position=button.dataset.position;document.querySelectorAll('.logo-position').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));draw();});
  for(const id of ['logo-size','logo-margin','logo-opacity','logo-enabled'])$(id).addEventListener('input',draw);
  const upload=async file=>{
    if(!file)return;
    if(!/^image\/(png|jpeg|webp)$/.test(file.type)){feedback.textContent='Потрібна картинка PNG, JPG або WebP.';return;}
    if(file.size>6*1024*1024){feedback.textContent='Файл завеликий, оберіть логотип до 6 МБ.';return;}
    feedback.textContent='Завантажуємо логотип...';
    try{
      const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('Не вдалося прочитати файл.'));reader.readAsDataURL(file);});
      await api(`/api/channels/${encodeURIComponent(channel.id)}/logo`,'POST',{data});
      version=Date.now();load();feedback.textContent='Логотип додано. Виберіть місце й розмір і натисніть «Зберегти».';
    }catch(error){feedback.textContent=error.message;}
  };
  $('logo-file').addEventListener('change',event=>{const file=event.target.files[0];event.target.value='';upload(file);});
  $('logo-replace').addEventListener('click',()=>$('logo-file').click());
  const tile=$('logo-tile');
  for(const name of ['dragenter','dragover'])tile.addEventListener(name,event=>{event.preventDefault();tile.classList.add('is-over');});
  for(const name of ['dragleave','drop'])tile.addEventListener(name,()=>tile.classList.remove('is-over'));
  tile.addEventListener('drop',event=>{event.preventDefault();upload(event.dataTransfer.files[0]);});
  $('logo-remove').addEventListener('click',async()=>{
    if(!confirm('Видалити логотип каналу? Нові експорти вийдуть без нього.'))return;
    try{await api(`/api/channels/${encodeURIComponent(channel.id)}/logo`,'DELETE');version=Date.now();present=false;draw();feedback.textContent='Логотип видалено.';}catch(error){feedback.textContent=error.message;}
  });
  const applyKind=()=>{$('modal-backdrop').dataset.channelKind=kind();backdrop();if(!styles)loadStyles();};
  for(const radio of document.querySelectorAll('input[name="channel-kind"]'))radio.addEventListener('change',applyKind);
  applyKind();draw();load();
  // The folder keeps its name (its path is the channel's id); a different name is stored in the settings.
  const displayName=()=>{const name=$('channel-name').value.trim();if(!name)throw new Error('Вкажіть назву каналу.');return name===(channel.folder_name || channel.name)?null:name;};
  return ()=>({display_name:displayName(),channel_kind:kind(),
    logo:{enabled:$('logo-enabled').checked,position:logo.position,size:Number($('logo-size').value),margin:Number($('logo-margin').value),opacity:Number($('logo-opacity').value),version},
    animation:{...(chosen?{style:chosen}:{}),...textStyle()}});
}
