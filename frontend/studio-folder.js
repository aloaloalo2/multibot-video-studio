// The selected YouTube directory is global. Choosing a path stages it until Save.
const studioFolderIcon='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7V5a1 1 0 0 1 1-1h5l2 2h9a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7Zm0 2h18"/></svg>';

function studioFolderMarkup(){
  return `<section class="settings-section studio-folder" id="studio-folder"><h3>${studioFolderIcon}Папка YouTube</h3><p>Канали, випуски, відео, прев’ю, переклади й метадані.</p><div class="studio-folder-field"><input id="studio-folder-path" type="text" aria-label="Папка YouTube" placeholder="Завантажуємо шлях…" autocomplete="off" spellcheck="false" disabled><button type="button" id="studio-folder-pick" class="secondary" title="Вибрати папку" aria-label="Вибрати папку" disabled>${studioFolderIcon}</button></div><p class="studio-folder-note" id="studio-folder-feedback" aria-live="polite">Зміна папки не переміщує наявні файли.</p></section>`;
}

async function fillStudioFolder(){
  const section=$('studio-folder');if(!section)return;
  const input=section.querySelector('#studio-folder-path'),pick=section.querySelector('#studio-folder-pick'),feedback=section.querySelector('#studio-folder-feedback');
  try{
    const data=await api('/api/settings');if(!section.isConnected)return;
    input.value=data.settings.youtube_root;input.dataset.saved=input.value;
    input.disabled=false;pick.disabled=false;
    pick.onclick=async()=>{
      pick.disabled=true;
      try{
        const chosen=await api('/api/settings/youtube-root/pick','POST',{});if(!section.isConnected)return;
        input.value=chosen.path;feedback.textContent='Натисніть «Зберегти», щоб підключити цю папку.';feedback.classList.remove('invalid');
      }catch(error){if(section.isConnected&&error.message!=='Папку не вибрано'){feedback.textContent=error.message;feedback.classList.add('invalid');}}
      finally{pick.disabled=false;}
    };
  }catch(error){if(section.isConnected){feedback.textContent=error.message;feedback.classList.add('invalid');}}
}

async function saveStudioFolder(){
  const input=$('studio-folder-path'),feedback=$('studio-folder-feedback');
  if(!input || input.disabled)throw new Error('Не вдалося прочитати папку YouTube. Відкрийте налаштування ще раз.');
  const path=input.value.trim();if(path===input.dataset.saved)return false;
  try{
    const data=await api('/api/settings','PATCH',{settings:{youtube_root:path}});
    input.value=data.settings.youtube_root;input.dataset.saved=input.value;
    return true;
  }catch(error){if(input.isConnected){feedback.textContent=error.message;feedback.classList.add('invalid');}throw error;}
}
