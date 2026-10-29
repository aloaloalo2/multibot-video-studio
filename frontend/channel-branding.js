// channel-branding.js — the top of the channel settings: whether the channel makes regular or animated videos, and the
// channel logo with its place, size and opacity. The preview frame places the logo with the same rule the backend uses
// (backend/channel_branding.py): size and margin are percent of the frame width.
const brandingPositions=[['top-left','Угорі ліворуч'],['top-center','Угорі по центру'],['top-right','Угорі праворуч'],['middle-left','Посередині ліворуч'],null,['middle-right','Посередині праворуч'],['bottom-left','Унизу ліворуч'],['bottom-center','Унизу по центру'],['bottom-right','Унизу праворуч']];
const brandingDefaults={enabled:true,position:'top-right',size:12,margin:3,opacity:100};

function brandingSections(channel){
  const settings=channel.settings || {},kind=settings.channel_kind==='animated'?'animated':'regular',logo={...brandingDefaults,...(settings.logo || {})};
  const kindCard=(value,title,text)=>`<label class="channel-kind-card"><input type="radio" name="channel-kind" value="${value}" ${kind===value?'checked':''}><span><strong>${title}</strong><small>${text}</small></span></label>`;
  const cells=brandingPositions.map(item=>item?`<button type="button" class="logo-position" data-position="${item[0]}" aria-label="${item[1]}" title="${item[1]}" aria-pressed="${logo.position===item[0]}"></button>`:'<span class="logo-position-gap" aria-hidden="true"></span>').join('');
  const slider=(id,label,min,max,value,unit)=>`<label class="logo-slider">${label}<span><input id="${id}" type="range" min="${min}" max="${max}" step="1" value="${value}"><output for="${id}">${value}${unit}</output></span></label>`;
  return `<section class="settings-section channel-kind-section"><h3>Тип каналу</h3><div class="channel-kind-options" role="radiogroup" aria-label="Тип каналу">${kindCard('regular','Звичайний','Фото, стокове й створене відео, текст')}${kindCard('animated','Анімаційний','Мультфільм Razgon зі своїм стилем')}</div></section>
    <section class="settings-section"><h3>Логотип каналу</h3><p>Логотип з'являється в кадрі в обраному місці. Розмір і відступ рахуються від ширини кадру.</p>
      <div class="logo-editor"><div class="logo-preview" id="logo-preview"><img id="logo-preview-image" alt=""><span id="logo-preview-empty">Логотип ще не додано</span></div>
        <div class="logo-controls"><div class="logo-file-row"><label class="secondary logo-file-button">Завантажити логотип<input id="logo-file" type="file" accept="image/png,image/jpeg,image/webp" hidden></label><button id="logo-remove" class="secondary" type="button">Прибрати</button></div>
          <label class="logo-toggle"><input id="logo-enabled" type="checkbox" ${logo.enabled?'checked':''}> Показувати логотип у роликах</label>
          <div class="logo-position-grid" role="group" aria-label="Місце логотипа">${cells}</div>
          ${slider('logo-size','Розмір',3,40,logo.size,'%')}${slider('logo-margin','Відступ від краю',0,15,logo.margin,'%')}${slider('logo-opacity','Прозорість',10,100,logo.opacity,'%')}
          <p id="logo-feedback" role="status" aria-live="polite"></p></div></div></section>`;
}

function bindBranding(channel){
  const settings=channel.settings || {},logo={...brandingDefaults,...(settings.logo || {})};
  const frame=$('logo-preview'),image=$('logo-preview-image'),empty=$('logo-preview-empty'),feedback=$('logo-feedback');
  // A real frame of this channel makes the placement easy to judge; the first project whose cover loads is used.
  const covers=state.channel?.id===channel.id?state.projects.filter(project=>project.cover_asset_id):[];
  const tryCover=index=>{if(index>=covers.length)return;const url=`/api/projects/${encodeURIComponent(covers[index].id)}/cover?v=${encodeURIComponent(covers[index].updated_at || 0)}`,probe=new Image();probe.onload=()=>{frame.style.backgroundImage=`url("${url}")`;};probe.onerror=()=>tryCover(index+1);probe.src=url;};
  tryCover(0);
  let version=settings.logo?.version || 0,present=false;
  const draw=()=>{
    const size=Number($('logo-size').value),margin=Number($('logo-margin').value),[row,col]=logo.position.split('-');
    image.style.width=size+'%';image.style.opacity=String(Number($('logo-opacity').value)/100);
    // The frame is 16:9, so a margin of m% of the width is m*16/9 % of the height.
    image.style.left=col==='left'?margin+'%':col==='right'?'auto':'50%';image.style.right=col==='right'?margin+'%':'auto';
    image.style.top=row==='top'?(margin*16/9)+'%':row==='middle'?'50%':'auto';image.style.bottom=row==='bottom'?(margin*16/9)+'%':'auto';
    image.style.transform=`translate(${col==='center'?'-50%':'0'},${row==='middle'?'-50%':'0'})`;
    image.hidden=!present||!$('logo-enabled').checked;empty.hidden=present;$('logo-remove').disabled=!present;
    for(const id of ['logo-size','logo-margin','logo-opacity'])$(id).nextElementSibling.textContent=$(id).value+'%';
  };
  const load=()=>{image.onload=()=>{present=true;draw();};image.onerror=()=>{present=false;draw();};image.src=`/api/channels/${encodeURIComponent(channel.id)}/logo?v=${version}`;};
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
  const applyKind=()=>{const kind=document.querySelector('input[name="channel-kind"]:checked')?.value || 'regular';$('modal-backdrop').dataset.channelKind=kind;};
  for(const radio of document.querySelectorAll('input[name="channel-kind"]'))radio.addEventListener('change',applyKind);
  applyKind();draw();load();
  return ()=>({channel_kind:document.querySelector('input[name="channel-kind"]:checked')?.value || 'regular',
    logo:{enabled:$('logo-enabled').checked,position:logo.position,size:Number($('logo-size').value),margin:Number($('logo-margin').value),opacity:Number($('logo-opacity').value),version}});
}
