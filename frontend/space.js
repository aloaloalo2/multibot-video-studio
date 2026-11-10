// space.js — «Звільнити місце» on a project card: how much the extra copies of the episode's frames take, and one button
// that frees it (backend/space.py). The window says what goes and what stays before anything is removed.
const spaceIcon='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 14h16v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1zM4 14l2.4-8.3A1 1 0 0 1 7.4 5h9.2a1 1 0 0 1 1 .7L20 14M7.5 17h.01M12 7v4.5m-2.2-2.2L12 11.5l2.2-2.2"/></svg>';

function spaceSize(bytes){return bytes===0?'0 МБ':bytes>=1e9?`${(bytes/1e9).toFixed(1).replace('.',',')} ГБ`:bytes<5e5?'менше 1 МБ':`${Math.round(bytes/1e6)} МБ`;}

function studioSpaceMarkup(){
  return `<section class="settings-section studio-space" id="studio-space"><div class="studio-space-row"><div><h3>${spaceIcon}Звільнення місця</h3><p class="space-note" id="studio-space-total" aria-live="polite">Рахуємо кеш усіх проєктів…</p></div><button class="secondary" id="studio-space-open" type="button" disabled>Звільнити місце</button></div><div id="studio-space-review" hidden><p class="space-note">Видалиться кеш рендерів, стоп-кадрів і старих версій кадрів. Відповідні кроки скасування також зникнуть. Сценарії, матеріали, озвучка, кадри на таймлайні й готові відео залишаться. Наступний експорт триватиме довше.</p><div class="studio-space-actions"><button class="secondary" id="studio-space-cancel" type="button">Скасувати</button><button class="danger" id="studio-space-free" type="button">Звільнити місце</button></div></div></section>`;
}

function studioSpaceText(data){
  return `Можна звільнити ${spaceSize(data.total)} · усі канали${data.busy?' · проєкти в роботі пропущено':''}${data.unavailable?' · частину проєктів не вдалося перевірити':''}`;
}

async function fillStudioSpace(){
  const section=$('studio-space');if(!section)return;
  const total=section.querySelector('#studio-space-total'),open=section.querySelector('#studio-space-open'),review=section.querySelector('#studio-space-review'),free=section.querySelector('#studio-space-free');
  section.querySelector('#studio-space-cancel').onclick=()=>{review.hidden=true;open.hidden=false;};
  const showReview=()=>{review.hidden=false;open.hidden=true;};
  open.onclick=showReview;
  async function measure(){
    open.disabled=true;section.setAttribute('aria-busy','true');
    try{
      const data=await api('/api/space');if(!section.isConnected)return;
      total.textContent=studioSpaceText(data);open.disabled=!data.total;open.textContent='Звільнити місце';open.onclick=showReview;free.textContent=`Звільнити ${spaceSize(data.total)}`;
    }catch(error){if(section.isConnected){total.textContent=error.message;open.disabled=false;open.textContent='Перевірити ще раз';open.onclick=measure;}}
    finally{section.removeAttribute('aria-busy');}
  }
  free.onclick=async()=>{
    const label=free.textContent;
    free.disabled=true;free.textContent='Очищуємо…';section.setAttribute('aria-busy','true');
    try{
      const result=await api('/api/space','POST',{});
      status(`Звільнено ${spaceSize(result.freed)}.${result.busy?' Проєкти в роботі пропущено.':''}${result.unavailable?' Частину проєктів не вдалося очистити.':''}`);
      if(!section.isConnected)return;
      review.hidden=true;open.hidden=false;await measure();
    }catch(error){if(section.isConnected){total.textContent=error.message;free.textContent=label;}}
    finally{section.removeAttribute('aria-busy');free.disabled=false;}
  };
  await measure();
}

async function openSpace(project){
  modal('Звільнити місце','<p class="space-note">Рахуємо, скільки займає кеш випуску…</p>',[]);
  let data;
  try{data=await api(`/api/projects/${encodeURIComponent(project.id)}/space`);}
  catch(error){$('modal-body').innerHTML=`<p class="space-note">${esc(error.message)}</p>`;return;}
  if(!data.total){modal('Звільнити місце','<p class="space-note">У цього випуску немає кешу, який можна звільнити.</p>',[{label:'Добре',primary:true,run:closeModal}]);return;}
  const rows=[data.build?`<li><b>${spaceSize(data.build)}</b><span>Робочі файли рендеру Razgon: кожен кадр окремим відео, звук без стиснення, ролик без звуку, смуги перевірки стиків.</span></li>`:'',
    data.cache?`<li><b>${spaceSize(data.cache)}</b><span>Кеш студії: рендери експорту, стоп-кадри й аркуші стоку. Студія зробить їх знову, коли знадобляться.</span></li>`:'',
    data.old_renders?`<li><b>${spaceSize(data.old_renders)}</b><span>Старі версії кадрів (${data.old_count}), які лишались тільки для кнопки «Скасувати». Ці кроки скасування зникнуть разом із ними.</span></li>`:''].join('');
  const blocked=data.busy || (data.exporting?'Зараз іде експорт':'');
  modal(`Звільнити ${spaceSize(data.total)}?`,`<ul class="space-list">${rows}</ul>
    <p class="space-note">Ролик у студії лишиться таким, як є. Кадри на таймлайні, озвучка, сцени й готове відео в папці випуску не видаляються. Наступний експорт перемалює кадри заново, тому триватиме довше.</p>
    ${blocked?`<p class="space-busy">${esc(blocked)}. Звільнити місце можна, коли робота закінчиться.</p>`:''}`,
    [{label:`Звільнити ${spaceSize(data.total)}`,icon:'trash',danger:true,run:async()=>{
      const button=$('modal-actions').querySelector('.danger');button.disabled=true;
      try{
        const result=await api(`/api/projects/${encodeURIComponent(project.id)}/space`,'POST',{});
        closeModal();status(`Звільнено ${spaceSize(result.freed)} у випуску «${project.name}».`);
      }catch(error){button.disabled=false;status(error.message,true);}
    }}]);
  if(blocked)$('modal-actions').querySelector('.danger').disabled=true;
}
