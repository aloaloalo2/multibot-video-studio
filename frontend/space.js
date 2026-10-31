// space.js — «Звільнити місце» on a project card: how much the extra copies of the episode's frames take, and one button
// that frees it (backend/space.py). The window says what goes and what stays before anything is removed.
const spaceIcon='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 14h16v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1zM4 14l2.4-8.3A1 1 0 0 1 7.4 5h9.2a1 1 0 0 1 1 .7L20 14M7.5 17h.01M12 7v4.5m-2.2-2.2L12 11.5l2.2-2.2"/></svg>';

function spaceSize(bytes){return bytes>=1e9?`${(bytes/1e9).toFixed(1).replace('.',',')} ГБ`:bytes<5e5?'менше 1 МБ':`${Math.round(bytes/1e6)} МБ`;}

async function openSpace(project){
  modal('Звільнити місце','<p class="space-note">Рахуємо, скільки займають зайві копії кадрів…</p>',[{label:'Скасувати',run:closeModal}]);
  let data;
  try{data=await api(`/api/projects/${encodeURIComponent(project.id)}/space`);}
  catch(error){$('modal-body').innerHTML=`<p class="space-note">${esc(error.message)}</p>`;return;}
  if(!data.total){modal('Звільнити місце','<p class="space-note">У цього випуску немає зайвих копій кадрів.</p>',[{label:'Добре',primary:true,run:closeModal}]);return;}
  const rows=[data.build?`<li><b>${spaceSize(data.build)}</b><span>Робочі файли рендеру Razgon: кожен кадр окремим відео, звук без стиснення, ролик без звуку, смуги перевірки стиків.</span></li>`:'',
    data.old_renders?`<li><b>${spaceSize(data.old_renders)}</b><span>Старі версії кадрів (${data.old_count}), які лишались тільки для кнопки «Скасувати». Ці кроки скасування зникнуть разом із ними.</span></li>`:''].join('');
  const blocked=data.busy || (data.exporting?'Зараз іде експорт':'');
  modal(`Звільнити ${spaceSize(data.total)}?`,`<ul class="space-list">${rows}</ul>
    <p class="space-note">Ролик у студії лишиться таким, як є. Кадри на таймлайні, озвучка, сцени й готове відео в папці випуску не видаляються. Наступний експорт перемалює кадри заново, тому триватиме довше.</p>
    ${blocked?`<p class="space-busy">${esc(blocked)}. Звільнити місце можна, коли робота закінчиться.</p>`:''}`,
    [{label:'Скасувати',run:closeModal},{label:`Звільнити ${spaceSize(data.total)}`,icon:'trash',danger:true,run:async()=>{
      const button=$('modal-actions').querySelector('.danger');button.disabled=true;
      try{
        const result=await api(`/api/projects/${encodeURIComponent(project.id)}/space`,'POST',{});
        closeModal();status(`Звільнено ${spaceSize(result.freed)} у випуску «${project.name}».`);
      }catch(error){button.disabled=false;status(error.message,true);}
    }}]);
  if(blocked)$('modal-actions').querySelector('.danger').disabled=true;
}
