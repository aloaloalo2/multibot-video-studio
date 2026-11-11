function studioWordBlacklistMarkup(){
  return `<section class="settings-section studio-word-blacklist" id="studio-word-blacklist"><h3><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="m6 6 12 12"/></svg>Чорний список слів</h3><p>Для сценаріїв і зачинів усіх каналів. Кожен запис з нового рядка. Попередні заборонені форми слів збережено.</p><label><span class="sr-only">Заборонені слова й фрази</span><textarea id="studio-word-blacklist-input" rows="4" placeholder="Слово або фраза" aria-label="Чорний список слів" spellcheck="false" disabled></textarea></label><p id="studio-word-blacklist-feedback" role="status" aria-live="polite"></p></section>`;
}
function studioBlacklistEntries(value){
  const seen=new Set();return value.split(/\r?\n/).map(line=>line.trim().normalize('NFC').replace(/\s+/g,' ')).filter(line=>{const key=line.toLowerCase().replace(/ё/g,'е').replace(/’/g,"'");if(!key||seen.has(key))return false;seen.add(key);return true;});
}
async function fillStudioWordBlacklist(){
  const input=$('studio-word-blacklist-input'),note=$('studio-word-blacklist-feedback');
  try{
    const data=await api('/api/settings');if(!input.isConnected)return;
    if(!Object.prototype.hasOwnProperty.call(data.settings,'word_blacklist')){input.dataset.unavailable='1';note.textContent='Буде доступно після безпечного перезапуску студії.';return;}
    const entries=data.settings.word_blacklist||[];
    input.value=Array.isArray(entries)?entries.join('\n'):String(entries);input.dataset.saved=JSON.stringify(studioBlacklistEntries(input.value));input.disabled=false;
  }catch(error){if(input.isConnected)note.textContent=error.message;}
}
async function saveStudioWordBlacklist(){
  const input=$('studio-word-blacklist-input');if(!input)return;
  if(input.disabled){if(input.dataset.unavailable==='1')return;throw Error('Не вдалося прочитати чорний список. Відкрийте налаштування ще раз.');}
  const entries=studioBlacklistEntries(input.value);if(JSON.stringify(entries)===input.dataset.saved)return;
  try{
    const data=await api('/api/settings','PATCH',{settings:{word_blacklist:entries}});
    if(input.isConnected){input.value=data.settings.word_blacklist.join('\n');input.dataset.saved=JSON.stringify(data.settings.word_blacklist);}
  }catch(error){if(input.isConnected)$('studio-word-blacklist-feedback').textContent=error.message;throw error;}
}
