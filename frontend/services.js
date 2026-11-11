function serviceKeyMarkup(){
  return `<section class="settings-section"><h3>API-ключі сервісів</h3><p>Для кожного сервісу своє поле. Ключі приховані та зберігаються у зв’язці ключів macOS.</p><div id="service-key-list" class="service-key-list"></div><details class="custom-service"><summary>Додати власний сервіс</summary><label>Назва сервісу<input id="service-key-name" type="text" maxlength="60" autocomplete="off"></label><label>API Key<input id="service-key-value" type="password" autocomplete="new-password" spellcheck="false" placeholder="Вставте ключ"></label><button id="service-key-save" type="button" class="secondary">Додати сервіс</button></details><p id="service-key-feedback" role="status" aria-live="polite"></p></section>`;
}

async function initServiceKeys(){
  const list=$('service-key-list'),feedback=$('service-key-feedback'),customButton=$('service-key-save');
  const mask='••••••••••••••••';
  const licenses={pixabay:{url:'https://pixabay.com/service/license-summary/',label:'Фото та відео'},pexels:{url:'https://www.pexels.com/legal-pages/license/',label:'Фото та відео'},unsplash:{url:'https://unsplash.com/license',label:'Фото за Unsplash License'}};
  function notice(message,error=false){feedback.textContent=message;feedback.classList.toggle('invalid',error);}
  async function refresh(){
    const result=await api('/api/service-keys');
    if($('service-key-list')!==list)return;
    list.replaceChildren();
    // Pexels and Unsplash are not used by the studio yet: they show only when a key was saved before
    for(const provider of (result.providers || []).filter(item=>!['pexels','unsplash'].includes(item.id)||item.configured===true)){
      const row=document.createElement('div');row.className='service-key-panel';
      const header=document.createElement('div');header.className='service-key-row';
      const name=document.createElement('strong');name.textContent=provider.name;
      const status=document.createElement('span');status.className=provider.configured?'configured':'';status.textContent=provider.configured===true?'Ключ збережено':provider.configured===false?'Додайте ключ':'Зв’язка ключів недоступна';header.append(name,status);row.append(header);
      const label=document.createElement('label');label.textContent='Ключ доступу';
      const input=document.createElement('input');input.type='password';input.autocomplete='new-password';input.spellcheck=false;input.placeholder='Вставте ключ';input.setAttribute('aria-label',`${provider.name} ${label.textContent}`);if(provider.configured)input.value=mask;
      input.addEventListener('focus',()=>{if(input.value===mask)input.select();});label.append(input);
      input.dataset.provider=provider.id;input.dataset.providerName=provider.name;
      const button=document.createElement('button');button.type='button';button.className='secondary';button.textContent=provider.configured?'Оновити ключ':'Зберегти ключ';button.disabled=true;button.hidden=true;
      const field=document.createElement('div');field.className='service-key-field';
      const copy=document.createElement('button');copy.type='button';copy.className='icon-button service-key-copy';copy.title=copy.ariaLabel=`Скопіювати ключ ${provider.name}`;
      copy.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></svg>';
      function copyState(){copy.disabled=provider.configured!==true&&(!input.value.trim()||input.value===mask);}
      copyState();field.append(input,copy);label.append(field);
      input.addEventListener('input',()=>{button.disabled=!input.value.trim() || input.value===mask;button.hidden=button.disabled;copyState();});
      copy.addEventListener('click',async()=>{
        copy.disabled=true;
        try{
          const readKey=async()=>input.value!==mask&&input.value.trim()?input.value.trim():(await api('/api/service-keys/copy','POST',{provider_id:provider.id})).key;
          // Promise-backed ClipboardItem retains the click gesture in WebKit too.
          if(typeof ClipboardItem!=='undefined'&&navigator.clipboard?.write){
            await navigator.clipboard.write([new ClipboardItem({'text/plain':readKey().then(key=>new Blob([key],{type:'text/plain'}))})]);
          }else{await navigator.clipboard.writeText(await readKey());}
          notice(`Ключ ${provider.name} скопійовано.`);
        }catch(error){notice('Не вдалося скопіювати ключ. Перевірте доступ до буфера обміну та зв’язки ключів.',true);}
        finally{copyState();}
      });
      button.addEventListener('click',async()=>{
        if(input.value===mask || !input.value.trim())return;
        button.disabled=true;
        try{await api('/api/service-keys','POST',{provider_id:provider.id,key:input.value});input.value='';await refresh();notice(`Ключ ${provider.name} збережено.`);}
        catch(error){button.disabled=false;notice(error.message,true);}
      });
      row.append(label,button);
      if(licenses[provider.id]){const details=document.createElement('div');details.className='service-license';const type=document.createElement('span');type.textContent=licenses[provider.id].label;const link=document.createElement('a');link.href=licenses[provider.id].url;link.target='_blank';link.rel='noopener noreferrer';link.textContent='Ліцензія';details.append(type,link);row.append(details);}
      list.append(row);
    }
  }
  customButton.addEventListener('click',async()=>{
    customButton.disabled=true;
    try{const key=$('service-key-value').value,name=$('service-key-name').value.trim();if(!key.trim() || !name)throw new Error('Введіть назву сервісу та ключ.');await api('/api/service-keys','POST',{provider_id:'custom',name,key});$('service-key-value').value='';$('service-key-name').value='';await refresh();notice('Сервіс додано.');}
    catch(error){notice(error.message,true);}
    finally{customButton.disabled=false;}
  });
  try{await refresh();}catch(error){notice(error.message,true);}
}

// The window's own «Зберегти» saves a key typed in but not saved with its row's button, instead of dropping it.
async function saveTypedServiceKeys(){
  const mask='••••••••••••••••';
  const nameField=$('service-key-name'),keyField=$('service-key-value');
  const name=nameField?.value.trim(),custom=keyField?.value.trim();
  if(!!name!==!!custom)throw new Error(name?'Вставте ключ власного сервісу.':'Вкажіть назву власного сервісу.');
  const pending=[...document.querySelectorAll('#service-key-list input[data-provider]')].map(input=>({input,key:input.value.trim()})).filter(({input,key})=>key&&input.value!==mask);
  for(const {input,key} of pending){
    await api('/api/service-keys','POST',{provider_id:input.dataset.provider,key});
    // A later failure must not submit already saved credentials again on Retry.
    if(input.value.trim()===key)input.value=mask;
  }
  if(name&&custom){
    await api('/api/service-keys','POST',{provider_id:'custom',name,key:custom});
    if(nameField.value.trim()===name&&keyField.value.trim()===custom){nameField.value='';keyField.value='';}
  }
}
