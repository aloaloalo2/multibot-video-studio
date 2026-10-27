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
    for(const provider of result.providers || []){
      const row=document.createElement('div');row.className='service-key-panel';
      const header=document.createElement('div');header.className='service-key-row';
      const name=document.createElement('strong');name.textContent=provider.name;
      const status=document.createElement('span');status.className=provider.configured?'configured':'';status.textContent=provider.configured===true?'Ключ збережено':provider.configured===false?'Додайте ключ':'Зв’язка ключів недоступна';header.append(name,status);row.append(header);
      const label=document.createElement('label');label.textContent=provider.id==='unsplash'?'Access Key':'API Key';
      const input=document.createElement('input');input.type='password';input.autocomplete='new-password';input.spellcheck=false;input.placeholder='Вставте ключ';input.setAttribute('aria-label',`${provider.name} ${label.textContent}`);if(provider.configured)input.value=mask;
      input.addEventListener('focus',()=>{if(input.value===mask)input.select();});label.append(input);
      const button=document.createElement('button');button.type='button';button.className='secondary';button.textContent=provider.configured?'Оновити ключ':'Зберегти ключ';button.disabled=true;
      input.addEventListener('input',()=>{button.disabled=!input.value.trim() || input.value===mask;});
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
