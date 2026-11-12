/* Saved competitor identities, independent of the channel settings form. */
function bindChannelCompetitors(channel){
  const panel=document.querySelector('[data-settings-panel="competitors"]');if(!panel)return;
  const root=document.createElement('section');root.className='settings-section channel-competitors';
  root.innerHTML='<p>Збережіть канали конкурентів для майбутнього пошуку ідей.</p><form class="competitor-add"><label><span class="sr-only">Посилання на канал конкурента</span><input type="text" inputmode="url" autocomplete="off" placeholder="https://www.youtube.com/@channel" aria-label="Посилання на канал конкурента" required></label><button type="submit" class="secondary">Додати</button></form><p class="competitor-feedback muted" role="status" aria-live="polite">Завантажуємо список…</p><div class="competitor-list"></div>';
  panel.append(root);
  const form=root.querySelector('form'),input=form.querySelector('input'),add=form.querySelector('button'),feedback=root.querySelector('.competitor-feedback'),list=root.querySelector('.competitor-list');
  const endpoint=`/api/channels/${channel.id}/competitors`;
  let busy=false,items=[];
  function render(){
    if(!root.isConnected)return;
    list.innerHTML=items.map(item=>{
      const image=typeof item.icon_url==='string'&&/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(item.icon_url)?`<img src="${item.icon_url}" alt="" width="44" height="44">`:'<span class="competitor-avatar-placeholder" aria-hidden="true">▶</span>';
      const url=/^https:\/\/www\.youtube\.com\/channel\/UC[A-Za-z0-9_-]{22}$/.test(item.url)?item.url:'#';
      return `<div class="competitor-row">${image}<a href="${esc(url)}" target="_blank" rel="noopener noreferrer"><strong>${esc(item.name)}</strong><small>${esc(item.source_url||item.url)}</small></a><button type="button" class="icon-button competitor-remove" data-id="${esc(item.id)}" title="Видалити конкурента" aria-label="Видалити ${esc(item.name)}" ${busy?'disabled':''}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg></button></div>`;
    }).join('');
    list.querySelectorAll('.competitor-remove').forEach(button=>button.onclick=()=>mutate('DELETE',endpoint+'/'+encodeURIComponent(button.dataset.id)));
  }
  async function mutate(method,url,body){
    if(busy)return;busy=true;add.disabled=true;input.disabled=true;
    feedback.textContent=method==='POST'?'Отримуємо назву й логотип…':'Видаляємо…';render();
    try{
      const result=await api(url,method,body);
      if(!root.isConnected)return;
      items=result.competitors||[];feedback.textContent=items.length?'Збережено':'Додайте перший канал конкурента';
      if(method==='POST')input.value='';
    }catch(error){if(root.isConnected)feedback.textContent=error.message;}
    finally{busy=false;if(root.isConnected){add.disabled=false;input.disabled=false;render();}}
  }
  form.onsubmit=event=>{event.preventDefault();const url=input.value.trim();if(url)mutate('POST',endpoint,{url});};
  add.disabled=true;input.disabled=true;
  api(endpoint).then(result=>{if(!root.isConnected)return;items=result.competitors||[];feedback.textContent=items.length?'':'Додайте перший канал конкурента';render();}).catch(error=>{if(root.isConnected)feedback.textContent=error.message;}).finally(()=>{if(root.isConnected){add.disabled=false;input.disabled=false;}});
}
