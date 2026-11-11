/* Portable saved channel preferences. No episode or service key is transferred. */
function bindChannelTransfer(channel){
  const panel=document.querySelector('[data-settings-panel="advanced"]');
  if(!panel)return;
  const icon=kind=>`<svg class="channel-settings-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">${kind==='trash'?'<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>':kind==='restore'?'<path d="M3 4v6h6M4 9a8 8 0 1 1-1 7"/>':`<path d="M5 16v5h14v-5M12 ${kind==='export'?'16V4m-4 4 4-4 4 4':'3v12m-4-4 4 4 4-4'}"/>`}</svg>`;
  const section=document.createElement('section');section.className='settings-section channel-transfer';
  section.innerHTML=`<h3>${icon('export')}Перенесення каналу</h3><p>Оформлення, голоси, побажання й правила. Без випусків.</p><div class="channel-transfer-actions"><button type="button" class="secondary" data-transfer="export">${icon('export')}Експортувати ZIP</button><button type="button" class="secondary" data-transfer="import">${icon('import')}Імпортувати ZIP</button><input type="file" accept=".zip,application/zip" hidden data-transfer="file"></div><div class="channel-transfer-review" hidden><p data-transfer="filename"></p><p>Поточні налаштування буде замінено. Резервна копія збережеться автоматично.</p><button type="button" class="primary" data-transfer="apply">${icon('import')}Імпортувати й замінити</button></div><p class="channel-transfer-note">Ключі сервісів додаються окремо в налаштуваннях студії. Для того самого голосу потрібен той самий акаунт сервісу.</p><p role="status" aria-live="polite" data-transfer="feedback"></p><details class="channel-transfer-backups"><summary>Резервні копії <span data-transfer="size"></span></summary><div data-transfer="backups"></div></details>`;
  const group=document.createElement('details');group.className='channel-settings-group';
  const summary=document.createElement('summary');summary.innerHTML=`${icon('export')}<span><strong>Перенесення каналу</strong><small>Експорт, імпорт і резервні копії</small></span><svg class="channel-settings-chevron" viewBox="0 0 20 20" aria-hidden="true"><path d="m7 4 6 6-6 6"/></svg>`;
  const inner=document.createElement('div');inner.className='channel-settings-group-body';section.querySelector('h3').hidden=true;inner.append(section);group.append(summary,inner);
  const danger=panel.querySelector('.settings-danger-zone');panel.insertBefore(group,danger);
  const find=key=>section.querySelector(`[data-transfer="${key}"]`),base=`/api/channels/${encodeURIComponent(channel.id)}`;
  const generation=state.modalGeneration;
  let file=null,busy=false;
  const bytes=n=>n<1024*1024?`${Math.ceil(n/1024)} КБ`:`${(n/1024/1024).toFixed(1)} МБ`;
  const feedback=(message,error=false)=>{find('feedback').textContent=message;find('feedback').classList.toggle('error',error);};
  const run=async action=>{if(busy)return;busy=true;section.querySelectorAll('button').forEach(el=>el.disabled=true);try{await action();}catch(error){feedback(error.message,true);}finally{busy=false;section.querySelectorAll('button').forEach(el=>el.disabled=false);}};
  const refreshChannel=async result=>{
    const next=result.channel;state.channels=state.channels.map(item=>item.id===channel.id?next:item);
    if(state.channel?.id===channel.id)state.channel=next;
    if(!section.isConnected||state.modalGeneration!==generation){renderChannels();return;}
    closeModal();renderChannels();renderProject();openChannelSettings(next);
    document.querySelector('[data-settings-panel="advanced"]')?.getAttribute('aria-labelledby')&&document.getElementById(document.querySelector('[data-settings-panel="advanced"]').getAttribute('aria-labelledby'))?.click();
    status('Налаштування каналу перенесено. Поточні випуски збережено.');
  };
  async function backups(){
    const data=await api(base+'/settings-backups');if(!section.isConnected)return;
    const total=data.backups.reduce((n,item)=>n+item.bytes,0);find('size').textContent=total?`· ${bytes(total)}`:'';
    const list=find('backups');list.replaceChildren();
    if(!data.backups.length){list.textContent='Копій поки немає';return;}
    for(const item of data.backups){
      const row=document.createElement('div');row.className='channel-transfer-backup';
      const label=document.createElement('span');label.textContent=new Date(item.created_at*1000).toLocaleString('uk-UA',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})+` · ${bytes(item.bytes)}`;row.append(label);
      for(const kind of ['restore','trash']){
        const button=document.createElement('button');button.type='button';button.className='icon-button';button.innerHTML=icon(kind);button.title=kind==='restore'?'Відновити налаштування':'Видалити резервну копію';button.setAttribute('aria-label',button.title);
        button.addEventListener('click',()=>run(async()=>{
          if(kind==='restore')await refreshChannel(await api(base+`/settings-backups/${item.id}/restore`,'POST',{}));
          else{await api(base+`/settings-backups/${item.id}`,'DELETE');feedback('Резервну копію видалено.');await backups();}
        }));row.append(button);
      }list.append(row);
    }
  }
  find('export').addEventListener('click',()=>run(async()=>{
    feedback('Готуємо архів…');const response=await fetch(base+'/settings-export');
    if(!response.ok)throw new Error((await response.json()).error||'Не вдалося створити архів');
    const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');link.href=url;link.download=`${channel.name.replace(/[\\/:*?"<>|]/g,'_')} - налаштування.zip`;link.click();setTimeout(()=>URL.revokeObjectURL(url),30000);feedback('Архів збережених налаштувань готовий.');
  }));
  find('import').addEventListener('click',()=>find('file').click());
  find('file').addEventListener('change',()=>{
    file=find('file').files[0]||null;find('file').value='';
    if(file&&file.size>128*1024*1024){file=null;feedback('Оберіть ZIP до 128 МБ',true);}
    section.querySelector('.channel-transfer-review').hidden=!file;
    find('filename').textContent=file?file.name:'';
  });
  find('apply').addEventListener('click',()=>run(async()=>{
    if(!file)return;feedback('Переносимо налаштування…');
    const response=await fetch(base+'/settings-import',{method:'POST',headers:{'Content-Type':'application/zip'},body:file});const result=await response.json();
    if(!response.ok)throw new Error(result.error||'Не вдалося перенести налаштування');await refreshChannel(result);
  }));
  backups().catch(error=>feedback(error.message,true));
}
