// Keep the existing controls mounted while arranging them into a small settings workspace.
const channelSettingsPaths={
  projects:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M8 4v5M8 13h3m-3 3h7"/>',
  script:'<path d="M5 3h10l4 4v14H5ZM14 3v5h5M8 12h8m-8 4h6"/>',
  look:'<path d="M12 3a9 9 0 1 0 0 18h1a2 2 0 0 0 1-3.7 1.4 1.4 0 0 1 .8-2.6h2A4.2 4.2 0 0 0 21 10.5 8.5 8.5 0 0 0 12 3Z"/><circle cx="7.5" cy="10" r=".7"/><circle cx="11" cy="6.7" r=".7"/><circle cx="15.5" cy="7.5" r=".7"/>',
  montage:'<path d="M4 5h16M4 12h16M4 19h16M8 2v6m8 1v6m-6 1v6"/>',
  voice:'<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8"/>',
  sound:'<path d="M9 18V5l12-2v13M9 9l12-2"/><ellipse cx="6" cy="18" rx="3" ry="2"/><ellipse cx="18" cy="16" rx="3" ry="2"/>',
  competitors:'<circle cx="8" cy="8" r="3"/><circle cx="17" cy="9" r="2.5"/><path d="M2 21v-2a6 6 0 0 1 12 0v2m2-7a5 5 0 0 1 6 5v2"/>',
  languages:'<path d="M3 5h11M8 3v2M5 5c0 5 4 9 8 10M12 5c0 4-3 8-8 11m10 5 4-11 4 11m-6.5-4h5"/>',
  thumbnails:'<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8" cy="9" r="1.5"/><path d="m3 17 5-5 4 4 3-3 6 6"/>',
  formats:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  accents:'<path d="m4 20 10-10 3 3L7 23ZM12 12l3 3M5 3v4M3 5h4m12-6v4m-2-2h4m-1 10v4m-2-2h4"/>',
  opening:'<path d="m9 7 8 5-8 5Z"/><rect x="3" y="3" width="18" height="18" rx="3"/>',
  sentences:'<path d="M5 5h14M5 10h14M5 15h8M5 20h10"/>',
  memory:'<path d="M8 4h8v3h3v10h-3v3H8v-3H5V7h3Zm1 6h6v4H9ZM3 10h2m-2 4h2m14-4h2m-2 4h2"/>',
  output:'<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8m-4-4v4m-3-10 2 2 4-4"/>',
  hero:'<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
  wishes:'<path d="M4 4h16v13H9l-5 4Zm4 5h8m-8 4h5"/>'
};
function channelSettingsIcon(name){return `<svg class="channel-settings-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${channelSettingsPaths[name]||channelSettingsPaths.projects}</svg>`;}

// Labels and summaries are derived from the mounted controls; each setting has one editor.
function channelFormatIcon(key){
  const paths={
    stock_video:'<rect x="3" y="5" width="13" height="14" rx="2"/><path d="m16 10 5-3v10l-5-3Z"/>',
    generated_video:'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m10 9 5 3-5 3ZM6 2v4M4 4h4"/>',
    stock_photo:'<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 6-6 4 4 3-3 5 5"/>',
    generated_photo:'<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5ZM20 2v4m-2-2h4"/>',
    animation:'<circle cx="7" cy="7" r="4"/><rect x="13" y="13" width="8" height="8" rx="1"/><path d="m7 15 2 4H5Z"/>',
    razgon_2d:'<path d="m12 3 9 5-9 5-9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5"/>',
    host:'<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    text:'<path d="M4 5h16M12 5v15m-4 0h8"/>'
  };
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[key]||paths.text}</svg>`;
}
function channelSettingsSummary(values,limit=3){
  const active=values.filter(item=>Number(item.amount)>0).sort((a,b)=>b.amount-a.amount);
  return active.slice(0,limit).map(item=>`${item.label} ${item.amount}%`).join(' · ')+(active.length>limit?` · +${active.length-limit}`:'');
}
function channelSettingsEditable(field){
  return !field.closest('.voice-player,.channel-competitors,.channel-translation-audition');
}
function channelSettingsResetAnchor(field){
  const anchor=field.closest('.tempo-scale')?.nextElementSibling||field.nextElementSibling;
  return field.type==='range'&&channelSettingsEditable(field)&&anchor?.matches('output')?anchor:null;
}
function channelSettingsFieldValue(field){
  if(field.matches('button'))return field.getAttribute('aria-checked')??field.getAttribute('aria-pressed');
  return ['checkbox','radio'].includes(field.type)?String(field.checked):field.value;
}
function channelSettingsDirty(baseline){
  return [...baseline].some(([field,before])=>field.isConnected&&channelSettingsEditable(field)&&channelSettingsFieldValue(field)!==before);
}
function organizeChannelSettings(channel){
  const body=$('modal-body'),backdrop=$('modal-backdrop');
  backdrop.classList.add('channel-settings-open');
  const workspace=document.createElement('div');workspace.className='channel-settings-workspace';
  const nav=document.createElement('nav');nav.className='channel-settings-nav';nav.setAttribute('aria-label','Розділи налаштувань каналу');nav.setAttribute('role','tablist');nav.setAttribute('aria-orientation','vertical');
  const content=document.createElement('div');content.className='channel-settings-content';
  workspace.append(nav,content);body.append(workspace);
  const definitions=[
    ['projects','Основне','Для нових проєктів','Основне'],
    ['script','Сценарій','Зачини та повний текст'],
    ['look','Оформлення','Стиль і плашка'],
    ['voice','Озвучка','Голос і зразок'],
    ['thumbnails','Прев’ю','Герой і побажання'],
    ['sound','Звук','Музика й ефекти','Додаткове'],
    ['languages','Переклад','Голоси інших мов'],
    ['advanced','Розширене','Формат відео й правила','Розширене'],
    ['competitors','Конкуренти','Канали для майбутніх ідей']
  ];
  const panels={},tabs={},summaries=new Map();
  const preferenceKey=`channel-settings-panel:${channel.id}`;
  function select(key,focus=false){
    const sectionKey=['script','look','voice','thumbnails'].includes(key)?key:null;
    if(sectionKey)key='projects';
    if(!panels[key])key='projects';
    for(const [name,panel] of Object.entries(panels)){
      const active=name===key;panel.hidden=!active;tabs[name].setAttribute('aria-selected',String(active));tabs[name].tabIndex=active?0:-1;
      if(!active)panel.querySelectorAll('audio,video').forEach(media=>media.pause());
    }
    try{sessionStorage.setItem(preferenceKey,key);}catch{}
    if(sectionKey){const group=body.querySelector('[data-main-section="'+sectionKey+'"]');if(group){group.open=true;group.scrollIntoView({block:'nearest'});}}
    if(focus)tabs[key].focus();
  }
  for(const [key,label,note,group] of definitions){
    if(group){const heading=document.createElement('span');heading.className='channel-settings-nav-label';heading.textContent=group;nav.append(heading);}
    const tab=document.createElement('button');tab.type='button';tab.id=`channel-settings-tab-${key}`;tab.dataset.settingsTab=key;tab.setAttribute('role','tab');tab.setAttribute('aria-controls',`channel-settings-panel-${key}`);
    tab.innerHTML=`${channelSettingsIcon(key==='advanced'?'output':key)}<span>${label}</span>`;tab.addEventListener('click',()=>select(key));tabs[key]=tab;nav.append(tab);
    const panel=document.createElement('section');panel.className='channel-settings-panel';panel.id=`channel-settings-panel-${key}`;panel.dataset.settingsPanel=key;panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby',tab.id);
    const heading=document.createElement('header');heading.className='channel-settings-panel-head';heading.innerHTML=`<h3>${label}</h3>`;panel.append(heading);panels[key]=panel;content.append(panel);
  }
  nav.addEventListener('keydown',event=>{
    const keys=definitions.map(item=>item[0]),index=keys.findIndex(key=>tabs[key]===event.target);
    if(index<0)return;
    const next=event.key==='Home'?0:event.key==='End'?keys.length-1:['ArrowDown','ArrowRight'].includes(event.key)?(index+1)%keys.length:['ArrowUp','ArrowLeft'].includes(event.key)?(index+keys.length-1)%keys.length:null;
    if(next!==null){event.preventDefault();select(keys[next],true);}
  });
  const move=(selector,panel,{fold=false,icon='projects',title=null,open=false}={})=>{
    const section=body.querySelector(selector);if(!section)return;
    const heading=section.querySelector('h3');
    if(!fold){
      if(heading){if(title)heading.textContent=title;heading.insertAdjacentHTML('afterbegin',channelSettingsIcon(icon));heading.classList.add('channel-settings-section-title');}
      panels[panel].append(section);return section;
    }
    const details=document.createElement('details');details.className='channel-settings-group';details.open=open;
    for(const name of ['regular-only','animated-only','planned-only'])if(section.classList.contains(name))details.classList.add(name);
    const summary=document.createElement('summary');summary.innerHTML=`${channelSettingsIcon(icon)}<span><strong>${title||heading?.textContent||''}</strong><small class="settings-choice-summary"></small></span><svg class="channel-settings-chevron" viewBox="0 0 20 20" aria-hidden="true"><path d="m7 4 6 6-6 6"/></svg>`;
    const inner=document.createElement('div');inner.className='channel-settings-group-body';details.append(summary,inner);inner.append(section);if(heading)heading.hidden=true;panels[panel].append(details);
    summaries.set(selector,summary.querySelector('small'));return details;
  };
  // Keep common project and director choices visible on the main panel.
  const defaults=body.querySelector('.channel-project-defaults'),kind=defaults.querySelector('.channel-kind-section');
  const kindSection=document.createElement('section');kindSection.className='settings-section settings-project-kind';kindSection.innerHTML='<h3>Тип роликів</h3>';kindSection.append(kind);kind.querySelector('h4').hidden=true;panels.projects.append(kindSection);
  const directorGroup=move('.channel-project-defaults','projects',{fold:true,title:'Робота режисера',icon:'projects'});
  const quick=document.createElement('div');quick.className='settings-quick-grid';
  for(const [key,title,icon] of [['voice','Озвучка','voice'],['look','Оформлення','look']]){
    const button=document.createElement('button');button.type='button';button.className='settings-quick-card';button.dataset.quick=key;
    button.innerHTML=`<span class="settings-quick-visual">${channelSettingsIcon(icon)}</span><span class="settings-quick-copy"><strong>${title}</strong><span class="settings-quick-value">Завантажуємо…</span></span><span class="settings-quick-arrow" aria-hidden="true">›</span>`;
    button.addEventListener('click',()=>select(key,true));quick.append(button);
  }
  panels.projects.append(quick);
  move('.settings-visual-formats','projects',{fold:true,icon:'formats',title:'Формати кадрів'});
  const strip=document.createElement('div');strip.className='settings-format-preview';strip.setAttribute('aria-hidden','true');
  summaries.get('.settings-visual-formats')?.after(strip);
  move('.settings-output','advanced',{fold:true,icon:'output'});
  move('.settings-opening','advanced',{fold:true,icon:'opening'});
  move('.settings-sentences','advanced',{fold:true,icon:'sentences'});
  move('.settings-agent-memory','projects',{fold:true,icon:'memory',title:'Правила Агентів'});
  move('.settings-script-wishes','script',{icon:'script'});
  move('.channel-look','look',{icon:'look'});
  move('.logo-section','look',{fold:true,icon:'thumbnails',title:'Плашка'});
  move('.settings-accents','look',{fold:true,icon:'accents'});
  const automation=document.createElement('div');automation.className='settings-voice-automation';
  automation.innerHTML=`<label><input type="checkbox" id="settings-auto-narration" ${channel.settings?.auto_narration?'checked':''} disabled><span><strong>Автоозвучка</strong><small>Після готового сценарію</small></span></label><label><input type="checkbox" id="settings-auto-montage" ${channel.settings?.auto_montage?'checked':''} disabled><span><strong>Автомонтаж</strong><small>Після готової озвучки</small></span></label>`;
  const voiceSlot=document.createElement('div');voiceSlot.id='channel-voice-settings';panels.voice.append(voiceSlot);quick.after(automation);automation.after(directorGroup);
  move('.settings-sound','sound',{icon:'sound'});
  move('#channel-voices','languages',{icon:'languages'});
  move('.hero-reference-section','thumbnails',{icon:'hero',title:'Головний герой'});
  move('.settings-thumbnail-wishes','thumbnails',{icon:'wishes'});
  for(const [key,label,icon] of [['script','Сценарій','script'],['voice','Озвучка','voice'],['look','Оформлення','look'],['thumbnails','Герой і прев’ю','thumbnails']]){
    const group=document.createElement('details');group.className='channel-settings-group';group.dataset.mainSection=key;
    group.innerHTML=`<summary>${channelSettingsIcon(icon)}<span><strong>${label}</strong></span><svg class="channel-settings-chevron" viewBox="0 0 20 20" aria-hidden="true"><path d="m7 4 6 6-6 6"/></svg></summary><div class="channel-settings-group-body channel-main-group"></div>`;
    const inner=group.lastElementChild;
    for(const child of [...panels[key].children])if(!child.classList.contains('channel-settings-panel-head'))inner.append(child);
    panels.projects.append(group);tabs[key].remove();
  }
  const fontSection=document.createElement('section');fontSection.className='settings-section settings-montage-fonts';
  fontSection.innerHTML=`<h3>${channelSettingsIcon('script')}Шрифти монтажу</h3><div class="settings-two-column"><label>Основний текст<select id="settings-text-font">${studioFontOptionsHtml()}</select></label><label>Акценти й підписи<select id="settings-accent-font">${studioFontOptionsHtml()}</select></label></div><small>Текстові вставки, підписи й плашки</small>`;
  fontSection.querySelector('#settings-text-font').value=channel.settings?.typography?.font_family||'Golos';
  fontSection.querySelector('#settings-accent-font').value=channel.settings?.typography?.accent_font_family||channel.settings?.typography?.font_family||'Golos';
  const rules=body.querySelector('.settings-agent-memory').closest('.channel-settings-group');
  panels.projects.append(fontSection,rules);

  // Keep deletion away from ordinary Save/Cancel actions.
  const danger=$('modal-actions').querySelector('.danger');
  if(danger){const area=document.createElement('div');area.className='settings-danger-zone';danger.classList.add('settings-remove-channel');area.append(danger);panels.advanced.append(area);}
  for(const selector of ['.settings-opening>p','.settings-agent-memory>p:first-of-type',
    '.settings-output>p','.settings-accents>p','.settings-thumbnail-wishes>p']){
    const note=body.querySelector(selector);if(!note)continue;
    const help=document.createElement('details');help.className='settings-inline-help';help.innerHTML='<summary>Як це працює</summary>';note.before(help);help.append(note);
  }
  for(const id of ['settings-purpose','settings-weights-purpose'])$(id).hidden=true;
  const text=(selector,value)=>{const el=typeof selector==='string'?body.querySelector(selector):selector;if(el&&el.textContent!==value)el.textContent=value;};
  const selected=id=>{const el=$(id);return el?.selectedOptions?.[0]?.textContent||'';};
  const value=id=>$(id)?.value||'';
  const fields='input:not([type=file]),select:not(#settings-source-channel):not(.heygen-voice-list),textarea,button[data-position],button.style-thumb[data-style]';
  const baseline=new Map(),resets=new Map();let ready=false,weightsValid=true,scheduled=false;
  const save=$('modal-actions').querySelector('.primary');
  const hint=document.createElement('button');hint.type='button';hint.className='settings-save-hint';hint.disabled=true;hint.addEventListener('click',()=>{select('projects');const field=body.querySelector('[data-weight]');const group=field.closest('details');group.open=true;field.scrollIntoView({block:'nearest'});field.focus();});$('modal-actions').prepend(hint);
  function refresh(){
    if(!workspace.isConnected)return;
    const weights=[...body.querySelectorAll('[data-weight]')].map(input=>({label:input.getAttribute('aria-label').replace(', відсотків',''),amount:Number(input.value)}));
    text(summaries.get('.settings-visual-formats'),channelSettingsSummary(weights)||'Оберіть формати');
    strip.replaceChildren(...[...$('settings-bar').children].map(el=>{const part=el.cloneNode(false);part.title=el.title;return part;}));
    const wishes=body.querySelector('.generated-image-preferences');if(wishes)wishes.hidden=!(Number(body.querySelector('[data-weight=generated_photo]')?.value)>0);
    text(summaries.get('.channel-project-defaults'),`${selected('settings-plan-mode')} · ${selected('settings-director-model')} · ${selected('settings-claude-effort')}`);
    text(summaries.get('.settings-output'),`${value('settings-video-size').replace('x',' × ')} · ${value('settings-video-fps')} кадрів/с · ${selected('settings-video-quality')}`);
    text(summaries.get('.settings-opening'),`${selected('settings-first-format')} · ${value('settings-first-count')} кадр.`);
    text(summaries.get('.settings-sentences'),`До ${value('settings-max-sentences')} речень на кадр`);
    text(summaries.get('.settings-agent-memory'),$('channel-agent-memory').disabled?'Завантажуємо…':value('channel-agent-memory').trim()?'Власні правила':'Не додано');
    text(summaries.get('.logo-section'),$('logo-tile-image').hidden?'Не додано':!$('logo-enabled').checked?'Вимкнено':`${body.querySelector('.logo-position[aria-pressed=true]')?.title||''} · ${value('logo-size')}%`);
    text(summaries.get('.settings-accents'),$('settings-accents').checked?'Режисер додає за змістом':'Вимкнено');
    const voice=body.querySelector('.channel-voice-lab'),provider=voice?.querySelector('[name=provider]');
    const source=voice?.querySelector('.voice-lab-reference-player');
    const idField={heygen:'heygen_voice_id',fishaudio:'fish_voice_id',elevenlabs:'eleven_voice_id'}[provider?.value];
    const hasVoice=!!(idField&&voice?.querySelector(`[name=${idField}]`)?.value)||!!source?.querySelector('audio');
    for(const field of automation.querySelectorAll('input')){field.disabled=!hasVoice&&!field.checked;field.closest('label').title=hasVoice?'':'Спочатку додайте голос';}
    text('[data-quick=voice] .settings-quick-value',provider?(hasVoice?`${provider.selectedOptions[0].textContent} · ${voice.querySelector('[name=speed]').value}%`:'Готове аудіо · голос не додано'):'Завантажуємо…');
    const style=body.querySelector('.style-thumb[aria-checked=true] span')?.textContent;
    text('[data-quick=look] .settings-quick-value',style?`${style} · ${value('style-title-font')}`:'Оберіть стиль');
    const visual=body.querySelector('[data-quick=look] .settings-quick-visual');
    if(visual.style.backgroundImage!==$('logo-preview').style.backgroundImage)visual.style.backgroundImage=$('logo-preview').style.backgroundImage;
    visual.classList.toggle('has-preview',!!visual.style.backgroundImage);
    // New async controls get their own baseline; unchanged loading is never an author edit.
    for(const field of body.querySelectorAll(fields))if(!field.disabled&&channelSettingsEditable(field)&&!baseline.has(field))baseline.set(field,channelSettingsFieldValue(field));
    for(const field of baseline.keys())if(!field.isConnected){baseline.delete(field);resets.delete(field);}
    for(const [field,before] of baseline){
      const anchor=channelSettingsResetAnchor(field);if(!anchor)continue;
      if(!resets.has(field)){
        const reset=document.createElement('button');reset.type='button';reset.className='settings-field-reset';reset.textContent='↺';reset.title='Повернути збережене значення';reset.setAttribute('aria-label',reset.title);
        reset.addEventListener('click',()=>{field.value=before;field.dispatchEvent(new Event('input',{bubbles:true}));field.dispatchEvent(new Event('change',{bubbles:true}));});
        anchor.after(reset);resets.set(field,reset);
      }
      resets.get(field).hidden=channelSettingsFieldValue(field)===before;
    }
    const dirty=ready&&channelSettingsDirty(baseline);
    const valid=weightsValid;
    body.querySelector('.settings-visual-formats').closest('details').classList.toggle('settings-invalid-weights',!valid);
    save.disabled=!dirty||!valid||save.getAttribute('aria-busy')==='true';
    hint.disabled=valid;hint.hidden=!dirty&&valid;
    text(hint,!valid?'Перевірити пропорції ↗':dirty?'Є незбережені зміни':'');
    tabs.projects.classList.toggle('has-settings-error',!valid);
  }
  let refreshFrame;
  const schedule=()=>{if(!scheduled){scheduled=true;refreshFrame=requestAnimationFrame(()=>{scheduled=false;refresh();});}};
  body.addEventListener('input',schedule);body.addEventListener('change',schedule);body.addEventListener('click',schedule);
  const observer=new MutationObserver(records=>{
    if(!workspace.isConnected){observer.disconnect();return;}
    if(records.some(record=>(record.type==='attributes'&&(record.attributeName!=='style'||record.target.id==='logo-preview'))||[...record.addedNodes].some(node=>node.nodeType===1&&(node.matches(fields)||node.querySelector(fields)))||record.target.closest?.('#style-caption,.voice-lab-reference-player,#style-strip')))schedule();
  });
  observer.observe(body,{subtree:true,childList:true,attributes:true,attributeFilter:['disabled','aria-checked','aria-pressed','src','style']});
  body.channelSettingsCleanup=()=>{observer.disconnect();cancelAnimationFrame(refreshFrame);body.removeEventListener('input',schedule);body.removeEventListener('change',schedule);body.removeEventListener('click',schedule);body.channelSettingsCleanup=null;};
  let previous='projects';try{previous=sessionStorage.getItem(preferenceKey)||previous;}catch{}select(previous);
  return {select,refresh:schedule,setValidity(value){weightsValid=value;schedule();},ready(){baseline.clear();refresh();ready=true;refresh();},reveal(element){
    const panel=element?.closest('.channel-settings-panel');if(!panel)return;
    select(panel.dataset.settingsPanel);
    for(let parent=element.parentElement;parent&&parent!==panel;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true;
    element.scrollIntoView({block:'nearest'});element.focus();
  }};
}
