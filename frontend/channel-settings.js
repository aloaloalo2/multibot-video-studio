// Keep the existing controls mounted while arranging them into a small settings workspace.
const channelSettingsPaths={
  publish:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4m8-4v4"/>',
  projects:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M8 4v5M8 13h3m-3 3h7"/>',
  script:'<path d="M5 3h10l4 4v14H5ZM14 3v5h5M8 12h8m-8 4h6"/>',
  look:'<path d="M12 3a9 9 0 1 0 0 18h1a2 2 0 0 0 1-3.7 1.4 1.4 0 0 1 .8-2.6h2A4.2 4.2 0 0 0 21 10.5 8.5 8.5 0 0 0 12 3Z"/><circle cx="7.5" cy="10" r=".7"/><circle cx="11" cy="6.7" r=".7"/><circle cx="15.5" cy="7.5" r=".7"/>',
  montage:'<path d="M4 5h16M4 12h16M4 19h16M8 2v6m8 1v6m-6 1v6"/>',
  voice:'<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8"/>',
  sound:'<path d="M9 18V5l12-2v13M9 9l12-2"/><ellipse cx="6" cy="18" rx="3" ry="2"/><ellipse cx="18" cy="16" rx="3" ry="2"/>',
  spending:'<rect x="3" y="6" width="18" height="13" rx="2"/><path d="M3 10h18M16 15h2M7 6V4h10v2"/>',
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
    // the channel's host and voice in one place, under «Основне», before «Побажання» (user, 16 November 2026)
    ['avatar','Аватар і голос','Головний герой і озвучка'],
    // every wish of the channel in one place, under «Основне» (user, 15 November 2026)
    ['wishes','Побажання','Сценарій, прев’ю, монтаж'],
    // every automatic step of an episode in one place, after «Побажання» (user, 19 November 2026)
    ['automation','Автоматика','Озвучка, монтаж, публікація'],
    ['script','Сценарій','Зачини та повний текст'],
    ['look','Оформлення','Стиль і плашка'],
    ['voice','Озвучка','Голос і зразок'],
    ['thumbnails','Прев’ю','Герой і побажання'],
    ['sound','SFX','Музика й ефекти','Додаткове'],
    ['languages','Переклад','Голоси інших мов'],
    ['advanced','Розширене','Формат відео й правила','Розширене'],
    // what the channel's paid services cost, today and this month, deleted projects included (user, 25 November 2026:
    // «додай… ці витрати також в налаштування каналу, там, де розширене, під ним… навіть якщо я видаляю проект»)
    ['spending','Витрати','Сьогодні й цей місяць'],
    ['competitors','Конкуренти','Канали для майбутніх ідей']
  ];
  const panels={},tabs={},summaries=new Map();
  const preferenceKey=`channel-settings-panel:${channel.id}`;
  function select(key,focus=false){
    const sectionKey=['script','look','voice','thumbnails'].includes(key)?key:null;
    if(sectionKey)key=sectionKey==='voice'?'avatar':'projects';
    if(!panels[key])key='projects';
    for(const [name,panel] of Object.entries(panels)){
      const active=name===key;panel.hidden=!active;tabs[name].setAttribute('aria-selected',String(active));tabs[name].tabIndex=active?0:-1;
      if(!active)panel.querySelectorAll('audio,video').forEach(media=>media.pause());
    }
    try{sessionStorage.setItem(preferenceKey,key);}catch{}
    if(key==='avatar'||key==='projects')heygenAvatars.loadSelectedPortrait();
    if(key==='spending')loadChannelSpending();
    if(sectionKey){const group=body.querySelector('[data-main-section="'+sectionKey+'"]');if(group){group.open=true;group.scrollIntoView({block:'nearest'});}}
    if(focus)tabs[key].focus();
  }
  for(const [key,label,note,group] of definitions){
    if(group){const heading=document.createElement('span');heading.className='channel-settings-nav-label';heading.textContent=group;nav.append(heading);}
    const tab=document.createElement('button');tab.type='button';tab.id=`channel-settings-tab-${key}`;tab.dataset.settingsTab=key;tab.setAttribute('role','tab');tab.setAttribute('aria-controls',`channel-settings-panel-${key}`);
    tab.innerHTML=`${channelSettingsIcon(key==='advanced'?'output':key==='avatar'?'hero':key)}<span>${label}</span>`;tab.addEventListener('click',()=>select(key));tabs[key]=tab;nav.append(tab);
    const panel=document.createElement('section');panel.className='channel-settings-panel';panel.id=`channel-settings-panel-${key}`;panel.dataset.settingsPanel=key;panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby',tab.id);
    const heading=document.createElement('header');heading.className='channel-settings-panel-head';heading.innerHTML=`<h3>${label}</h3>`;panel.append(heading);panels[key]=panel;content.append(panel);
  }
  async function loadChannelSpending(){
    const panel=panels.spending;if(!panel)return;
    let box=panel.querySelector('.channel-spend');
    if(!box){box=document.createElement('div');box.className='channel-spend';panel.append(box);}
    if(!box.childElementCount)box.innerHTML='<p class="channel-spend-note"><span class="export-spinner" aria-hidden="true"></span> Рахуємо витрати…</p>';
    try{
      const data=await api(`/api/channels/${encodeURIComponent(channel.id)}/spending`);
      const money=v=>Number.isFinite(v)?'$'+(v<10?v.toFixed(2):v.toFixed(0)):'—';
      const rows=[['claude_code','Claude ≈'],['openrouter','OpenRouter'],['heygen','HeyGen'],['elevenlabs','ElevenLabs'],['fishaudio','Fish Audio']]
        .filter(([k])=>data.services[k]&&(data.services[k].month||data.services[k].day));
      const cell=v=>`<td>${money(v)}</td>`;
      box.innerHTML=`<table class="ai-spend channel-spend-table"><thead><tr><th></th><th>Сьогодні</th><th>Місяць</th></tr></thead><tbody>`
        +(rows.length?rows.map(([k,name])=>`<tr><th>${name}</th>${cell(data.services[k].day)}${cell(data.services[k].month)}</tr>`).join(''):'<tr><th>Цього місяця витрат ще немає</th><td></td><td></td></tr>')
        +`<tr class="ai-spend-total"><th>Усього</th>${cell(data.total.day)}${cell(data.total.month)}</tr></tbody></table>`;   // no explanation under it (user, 25 November 2026: «удали це»)
    }catch(error){box.innerHTML=`<p class="channel-spend-note">${error.message}</p>`;}
  }
  const avatarIcon=tabs.avatar.firstElementChild;
  let avatarUrl, avatarPhoto;
  function refreshAvatar(){
    const url=channel.hero_reference?.url;
    if(url===avatarUrl)return;
    avatarUrl=url;
    avatarPhoto?.replaceWith(avatarIcon);
    avatarPhoto=null;
    if(!url)return;

    const photo=document.createElement('img');
    avatarPhoto=photo;
    photo.className='channel-settings-icon channel-settings-avatar';
    photo.alt='';
    photo.addEventListener('load',()=>{
      if(avatarPhoto===photo)avatarIcon.replaceWith(photo);
    },{once:true});
    photo.src=url;
  }
  refreshAvatar();
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
  quick.hidden=true;panels.projects.append(quick);   // «Озвучка» and «Оформлення» showed twice (user, 15 November 2026): their blocks below carry the summary now
  const formatsGroup=move('.settings-visual-formats','projects',{fold:true,icon:'formats',title:'План кадрів'});
  directorGroup.before(formatsGroup);
  const strip=document.createElement('div');strip.className='settings-format-preview';strip.setAttribute('aria-hidden','true');
  summaries.get('.settings-visual-formats')?.after(strip);
  move('.settings-output','advanced',{fold:true,icon:'output'});
  const openingGroup=move('.settings-opening','projects',{fold:true,icon:'opening'});
  formatsGroup.after(openingGroup);
  move('.settings-sentences','advanced',{fold:true,icon:'sentences'});
  move('.settings-script-wishes','wishes',{fold:true,icon:'script',title:'Сценаристу'});
  move('.settings-thumbnail-wishes','wishes',{fold:true,icon:'thumbnails',title:'До прев’ю'});
  move('.settings-agent-memory','wishes',{fold:true,icon:'memory',title:'До плану кадрів і монтажу'});
  // ready sections to fill in, so it is clear what can be set here (user, 15 November 2026: «шоб вже було розписано що там
  // можна настроїти»); only the missing headings are added at the end, the author's text stays as it is
  {const field=body.querySelector('#channel-agent-memory'),add=document.createElement('button');
    add.type='button';add.className='secondary settings-memory-sections';add.textContent='Додати розділи';
    add.title='Додати в кінець заголовки розділів, яких ще немає: план кадрів, стиль кадрів, люди, рух, текст і підписи';
    add.addEventListener('click',()=>{
      const names=['План кадрів','Стиль кадрів','Люди й персонажі','Рух','Текст і підписи'];
      const have=new Set([...field.value.matchAll(/^#{1,3}\s*(.+?)\s*$/gm)].map(m=>m[1].toLowerCase()));
      const missing=names.filter(name=>!have.has(name.toLowerCase()));
      if(!missing.length){add.textContent='Усі розділи вже є';setTimeout(()=>add.textContent='Додати розділи',1600);return;}
      const text=field.value.replace(/\s+$/,'');
      field.value=(text?text+'\n\n':'')+missing.map(name=>'# '+name+'\n').join('\n');
      field.dispatchEvent(new Event('input',{bubbles:true}));field.focus();field.setSelectionRange(field.value.length,field.value.length);
    });
    field?.after(add);}
  const imageWishes=body.querySelector('.generated-image-preferences');
  if(imageWishes){const section=document.createElement('section');section.className='settings-section regular-only settings-image-wishes';section.innerHTML='<h3>Створені зображення</h3>';section.append(imageWishes);body.append(section);move('.settings-image-wishes','wishes',{fold:true,icon:'formats',title:'До створених зображень'});}
  // the plate leads «Оформлення», open, the logo on the left and its place on the right (user, 20 November 2026:
  // «Плашка на самому верху має бути… не скрита… по ліву сторону прев'ю, по праву настройки»)
  // «Оформлення» in one order (user, 20 November 2026: «наведи тут порядок… базар»): the «Плашка» row, then the style's
  // picture with the plate on it, the styles under it and «Налаштування стилю»
  move('.channel-look','look',{icon:'look'});
  {const look=body.querySelector('.channel-look'),plate=body.querySelector('.logo-section');
   if(look&&plate)look.before(plate);}   // the plate first, above the style (user, 20 November 2026)
  const automation=document.createElement('div');automation.className='settings-voice-automation';
  automation.innerHTML=`<label><input type="checkbox" id="settings-auto-narration" ${channel.settings?.auto_narration?'checked':''} disabled><span><strong>Автоозвучка</strong><small>Після готового сценарію</small></span></label><label><input type="checkbox" id="settings-auto-montage" ${channel.settings?.auto_montage?'checked':''} disabled><span><strong>Автомонтаж</strong><small>Після готової озвучки</small></span></label><label><input type="checkbox" id="settings-auto-opening" ${channel.settings?.auto_opening?'checked':''}><span><strong>Автовибір зачину</strong><small>DeepSeek обирає найкращий</small></span></label><label><input type="checkbox" id="settings-auto-export" ${channel.settings?.auto_export?'checked':''}><span><strong>Автоекспорт</strong><small>Після готових кадрів, з якістю каналу</small></span></label><label><input type="checkbox" id="settings-auto-publish" ${channel.settings?.auto_publish?'checked':''}><span><strong>Автопублікація</strong><small>Після експорту, на YouTube за розкладом</small></span></label>`;
  const voiceSlot=document.createElement('div');voiceSlot.id='channel-voice-settings';panels.voice.append(voiceSlot);quick.after(directorGroup);panels.automation.append(automation);
  move('.settings-sound','sound',{icon:'sound'});
  move('#channel-voices','languages',{icon:'languages'});
  // the voiced script goes on to the translations and their voices by itself (user, 16 November 2026)
  const translationAuto=document.createElement('div');translationAuto.className='settings-voice-automation settings-translation-automation';
  translationAuto.innerHTML=`<label><input type="checkbox" id="settings-auto-translation" ${channel.settings?.auto_translation?'checked':''}><span><strong>Автопереклад</strong><small>Після готової озвучки сценарію</small></span></label><label><input type="checkbox" id="settings-auto-translation-voice" ${channel.settings?.auto_translation_voice?'checked':''}><span><strong>Автоозвучка перекладу</strong><small>Після перевіреного перекладу</small></span></label>`;
  panels.automation.append(translationAuto);   // the translations' boxes live with the other automatic steps
  // «Автоматика» as the episode's assembly line (user, 19 November 2026: «інтерактивніше… зі значком… розділити по
  // групам»): four steps in the order the work goes, each switch with its own icon; the inputs keep their ids for saving
  {
    const flow=document.createElement('div');flow.className='auto-flow';
    const svg=d=>`<svg viewBox="0 0 24 24" aria-hidden="true">${d}</svg>`;
    const icons={
      script:svg('<path d="M7 3h8l4 4v14H7z"/><path d="M15 3v4h4M10 12h6M10 16h6"/>'),
      opening:svg('<path d="M12 3l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.4l-5.2 2.7 1-5.8L3.5 9.2l5.9-.9z"/>'),
      voice:svg('<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M6 11a6 6 0 0 0 12 0M12 17v4"/>'),
      montage:svg('<rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="M3 10h18M8 5v5M16 5v5"/>'),
      export:svg('<path d="M12 4v11M8 11l4 4 4-4M5 19h14"/>'),
      publish:svg('<rect x="3" y="6" width="18" height="12" rx="3.5"/><path d="m10.5 9.5 4 2.5-4 2.5z" fill="currentColor"/>'),
      translate:svg('<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>'),
      dub:svg('<path d="M4 10v4h4l5 4V6L8 10z"/><path d="M16.5 9a4 4 0 0 1 0 6M19 6.5a8 8 0 0 1 0 11"/>'),
    };
    const groups=[
      ['Сценарій',icons.script,[['settings-auto-opening',icons.opening]]],
      ['Озвучка й монтаж',icons.voice,[['settings-auto-narration',icons.voice],['settings-auto-montage',icons.montage]]],
      ['Готовий ролик',icons.export,[['settings-auto-export',icons.export],['settings-auto-publish',icons.publish]]],
      ['Переклад',icons.translate,[['settings-auto-translation',icons.translate],['settings-auto-translation-voice',icons.dub]]],
    ];
    for(const [title,icon,items] of groups){
      const group=document.createElement('section');group.className='auto-step';
      group.innerHTML=`<header class="auto-step-head"><span class="auto-step-icon">${icon}</span><h4>${title}</h4></header><div class="auto-step-items"></div>`;
      const list=group.querySelector('.auto-step-items');
      for(const [id,itemIcon] of items){
        const label=$(id)?.closest('label');if(!label)continue;
        label.classList.add('auto-switch');label.insertAdjacentHTML('afterbegin',`<span class="auto-switch-icon">${itemIcon}</span>`);
        label.append(label.querySelector('input'));   // the switch on the right
        list.append(label);
      }
      flow.append(group);
    }
    automation.remove();translationAuto.remove();panels.automation.append(flow);
  }
  move('.hero-reference-section','thumbnails',{icon:'hero',title:'Головний герой'});
  // «Логотип на прев’ю» is switched off (user, 16 November 2026: «цю функцію варто прибрати»): its fields stay hidden
  // in the page so the saved value goes back unchanged, but nothing shows it
  {const logoSection=body.querySelector('.thumbnail-logo-section');if(logoSection){const keep=document.createElement('div');keep.hidden=true;keep.append(logoSection);body.append(keep);}}
  // «Головний герой» and «Побажання до прев’ю» are two blocks of their own, after «Оформлення» (user, 14 November 2026)
  for(const [key,label,icon,only] of [['script','Сценарій','script'],['voice','Голос','voice'],['look','Оформлення','look'],['thumbnails','Головний герой','hero','.hero-reference-section'],['thumbnails','Побажання до прев’ю','thumbnails']]){
    if(only==='.hero-reference-section'){
      // «Головний герой» is always open in «Аватар», a plain card with the picture on the left (user, 16 November 2026)
      const section=panels[key].querySelector(only);
      if(section){section.classList.add('avatar-hero-card');section.dataset.mainSection='hero';const heading=section.querySelector('h3');if(heading){heading.hidden=false;heading.textContent='Аватар';}panels.avatar.append(section);}
      continue;
    }
    const group=document.createElement('details');group.className='channel-settings-group';group.dataset.mainSection=only?(only==='.hero-reference-section'?'hero':'thumbnail-logo'):key;
    group.innerHTML=`<summary>${channelSettingsIcon(icon)}<span><strong>${label}</strong>${only?'':`<small class="settings-choice-summary" data-main-summary="${key}"></small>`}</span><svg class="channel-settings-chevron" viewBox="0 0 20 20" aria-hidden="true"><path d="m7 4 6 6-6 6"/></svg></summary><div class="channel-settings-group-body channel-main-group"></div>`;
    const inner=group.lastElementChild;
    for(const child of [...panels[key].children])if(!child.classList.contains('channel-settings-panel-head')&&(!only||child.matches(only)))inner.append(child);
    if(!inner.children.length){if(!only)tabs[key].remove();continue;}   // its wishes went to «Побажання»
    if(key==='thumbnails')for(const section of inner.querySelectorAll(':scope>.settings-section')){const heading=section.querySelector('h3');if(heading)heading.hidden=true;}   // the block's own title says it
    (key==='voice'||only==='.hero-reference-section'?panels.avatar:panels.projects).append(group);if(!only)tabs[key].remove();
  }
  {const hero=panels.avatar.querySelector('[data-main-section=hero]');if(hero)panels.avatar.insertBefore(hero,panels.avatar.querySelector('details,section:not(.avatar-hero-card)'));}   // «Головний герой» first, then «Озвучка»
  const heygenAvatars=channelHeyGenAvatars(channel);
  panels.avatar.append(heygenAvatars);
  if(typeof channelTransitionSection==='function')panels.projects.append(channelTransitionSection(channel));
  move('.settings-accents','projects',{fold:true,icon:'accents'});
  // «Публікація»: what the card's «Опублікувати» follows; for now only the days between videos (user, 20 November 2026:
  // «єдину цифру в основне засунь… По дефолту завжди один день»)
  const days=Math.min(10,Math.max(1,Number(channel.settings?.publish_interval_days)||1));
  const dayWord=n=>n===1?'день':n<5?'дні':'днів';
  const publishGroup=document.createElement('details');publishGroup.className='channel-settings-group settings-publish';
  publishGroup.innerHTML=`<summary>${channelSettingsIcon('publish')}<span><strong>Публікація</strong><small class="settings-choice-summary"></small></span><svg class="channel-settings-chevron" viewBox="0 0 20 20" aria-hidden="true"><path d="m7 4 6 6-6 6"/></svg></summary><div class="channel-settings-group-body"><section class="settings-section"><label class="settings-publish-interval">Інтервал між роликами <input id="settings-publish-interval" type="number" min="1" max="10" step="1" value="${days}"><span class="settings-publish-unit"></span></label><small>Кнопка «Опублікувати» ставить новий ролик на стільки днів після останнього запланованого</small></section></div>`;
  const intervalInput=publishGroup.querySelector('#settings-publish-interval');
  const paintInterval=()=>{const n=Math.min(10,Math.max(1,Math.round(Number(intervalInput.value)||1)));publishGroup.querySelector('.settings-publish-unit').textContent=dayWord(n);publishGroup.querySelector('summary small').textContent=n===1?'Щодня':`Раз на ${n} ${dayWord(n)}`;};
  intervalInput.addEventListener('input',paintInterval);paintInterval();
  panels.projects.append(publishGroup);

  // Keep deletion away from ordinary Save/Cancel actions.
  const danger=$('modal-actions').querySelector('.danger');
  if(danger){const area=document.createElement('div');area.className='settings-danger-zone';danger.classList.add('settings-remove-channel');area.append(danger);panels.advanced.append(area);}
  // «Як це працює» is gone from the channel's settings (user, 25 November 2026: «взагалі прибери»)
  for(const selector of ['.settings-agent-memory>p:first-of-type','.settings-output>p','.settings-thumbnail-wishes>p']){const note=body.querySelector(selector);if(note)note.hidden=true;}
  for(const id of ['settings-purpose','settings-weights-purpose'])$(id).hidden=true;
  const text=(selector,value)=>{const el=typeof selector==='string'?body.querySelector(selector):selector;if(el&&el.textContent!==value)el.textContent=value;};
  const selected=id=>{const el=$(id);return el?.selectedOptions?.[0]?.textContent||'';};
  const value=id=>$(id)?.value||'';
  const fields='input:not([type=file]),select:not(#settings-source-channel):not(.heygen-voice-list),textarea,button[data-position],button[data-weight-auto],button.style-thumb[data-style]';
  const baseline=new Map(),resets=new Map();let ready=false,weightsValid=true,scheduled=false;
  const save=$('modal-actions').querySelector('.primary');
  const hint=document.createElement('button');hint.type='button';hint.className='settings-save-hint';hint.disabled=true;hint.addEventListener('click',()=>{select('projects');const field=body.querySelector('[data-weight]');const group=field.closest('details');group.open=true;field.scrollIntoView({block:'nearest'});field.focus();});$('modal-actions').prepend(hint);
  function refresh(){
    if(!workspace.isConnected)return;
    const hostIcon=body.querySelector('[data-weight="host"]')?.closest('.weight-row')?.querySelector('.weight-format-icon');
    if(hostIcon){
      const url=heygenAvatars.avatarPreview();
      const old=hostIcon.querySelector('img.heygen-weight-photo');
      if(old?.src!==url){
        old?.remove();
        if(url){const photo=document.createElement('img');photo.className='heygen-weight-photo';photo.alt='';photo.referrerPolicy='no-referrer';photo.addEventListener('error',()=>photo.remove(),{once:true});photo.src=url;hostIcon.append(photo);}
      }
    }
    refreshAvatar();
    const weights=[...body.querySelectorAll('[data-weight]')].map(input=>({label:input.getAttribute('aria-label').replace(', відсотків',''),amount:Number(input.value)}));
    text(summaries.get('.settings-visual-formats'),channelSettingsSummary(weights)||'Оберіть формати');
    strip.replaceChildren(...[...$('settings-bar').children].map(el=>{const part=el.cloneNode(false);part.title=el.title;return part;}));
    const wishes=body.querySelector('.generated-image-preferences')?.closest('.channel-settings-group');if(wishes)wishes.hidden=!(Number(body.querySelector('[data-weight=generated_photo]')?.value)>0||body.querySelector('[data-weight-auto=generated_photo]')?.getAttribute('aria-pressed')==='true');
    text(summaries.get('.channel-project-defaults'),`${selected('settings-plan-mode')} · ${selected('settings-director-model')} · ${selected('settings-claude-effort')}`);
    text(summaries.get('.settings-output'),`${value('settings-video-size').replace('x',' × ')} · ${value('settings-video-fps')} кадрів/с · ${selected('settings-video-quality')}`);
    text(summaries.get('.settings-opening'),[1,2,3].every(n=>value(`settings-open-${n}`)==='auto')?'Авто':[1,2,3].map(n=>selected(`settings-open-${n}`)).join(' · '));
    text(summaries.get('.settings-sentences'),`Коротке речення до ${value('settings-short')} слів`);
    // a filled wish shows a grey check by its title (user, 15 November 2026: «якщо є побажання то галочка нада сіра»)
    for(const [selector,id] of [['.settings-script-wishes','settings-script-wishes'],['.settings-thumbnail-wishes','settings-thumbnail-wishes'],
      ['.settings-image-wishes','settings-generated-image-style'],['.settings-agent-memory','channel-agent-memory']]){
      const note=summaries.get(selector);if(!note)continue;
      const loading=$(id)?.disabled&&id==='channel-agent-memory',filled=!loading&&!!value(id).trim();
      text(note,loading?'Завантажуємо…':filled?'':'Не додано');note.hidden=filled;
      const title=note.previousElementSibling;let mark=title?.querySelector('.wish-filled');
      if(filled&&!mark&&title){mark=document.createElement('span');mark.className='wish-filled';mark.title='Побажання додано';mark.innerHTML=StudioUI.icon('check');title.append(mark);}
      if(!filled&&mark)mark.remove();
    }
    text(summaries.get('.logo-section'),$('logo-tile-image').hidden?'Не додано':!$('logo-enabled').checked?'Вимкнено':`${body.querySelector('.logo-position[aria-pressed=true]')?.title||''} · ${value('logo-size')}%`);
    text(summaries.get('.settings-accents'),[$('settings-accents').checked&&'На фото',$('settings-host-graphics')?.checked&&'Над ведучим'].filter(Boolean).join(' · ')||'Вимкнено');
    const voice=body.querySelector('.channel-voice-lab'),provider=voice?.querySelector('[name=provider]');
    const source=voice?.querySelector('.voice-lab-reference-player');
    const idField={heygen:'heygen_voice_id',fishaudio:'fish_voice_id',elevenlabs:'eleven_voice_id'}[provider?.value];
    const hasVoice=!!(idField&&voice?.querySelector(`[name=${idField}]`)?.value)||!!source?.querySelector('audio');
    for(const field of body.querySelectorAll('#settings-auto-narration, #settings-auto-montage')){field.disabled=!hasVoice&&!field.checked;field.closest('label').title=hasVoice?'':'Спочатку додайте голос';}
    text('[data-main-summary=voice]',provider?(hasVoice?`${provider.selectedOptions[0].textContent} · ${voice.querySelector('[name=speed]').value}%`:'Готове аудіо · голос не додано'):'Завантажуємо…');
    text('[data-quick=voice] .settings-quick-value',provider?(hasVoice?`${provider.selectedOptions[0].textContent} · ${voice.querySelector('[name=speed]').value}%`:'Готове аудіо · голос не додано'):'Завантажуємо…');
    const style=body.querySelector('.style-thumb[aria-checked=true] span')?.textContent;
    text('[data-main-summary=look]',style?`${style} · ${value('style-title-font')}`:'Оберіть стиль');
    text('[data-quick=look] .settings-quick-value',style?`${style} · ${value('style-title-font')}`:'Оберіть стиль');
    const visual=body.querySelector('[data-quick=look] .settings-quick-visual');
    if(visual.style.backgroundImage!==$('logo-preview').style.backgroundImage)visual.style.backgroundImage=$('logo-preview').style.backgroundImage;
    visual.classList.toggle('has-preview',!!visual.style.backgroundImage);
    // New async controls get their own baseline; unchanged loading is never an author edit.
    for(const field of body.querySelectorAll(fields))if(!field.disabled&&channelSettingsEditable(field)&&!baseline.has(field))baseline.set(field,channelSettingsFieldValue(field));
    for(const field of baseline.keys())if(!field.isConnected){baseline.delete(field);resets.delete(field);}
    // no ↺ «Повернути збережене значення» beside the fields any more (user, 20 November 2026: «прибери взагалі, воно не
    // потрібно»): it appeared and vanished while a slider moved, and the row jumped
    const dirty=ready&&channelSettingsDirty(baseline);
    const valid=weightsValid;
    body.querySelector('.settings-visual-formats').closest('details').classList.toggle('settings-invalid-weights',!valid);
    save.disabled=!dirty||!valid||save.getAttribute('aria-busy')==='true';
    hint.disabled=valid;hint.hidden=!dirty&&valid;
    text(hint,!valid?'Перевірити пропорції ↗':dirty?'Є незбережені зміни':'');
    tabs.projects.classList.toggle('has-settings-error',!valid);
    paintAvatarTab();
  }
  // «Аватар і голос» shows the channel's host in its circle (user, 25 November 2026): the «Аватар» photo first, else the
  // HeyGen avatar's picture, else the plain icon
  function paintAvatarTab(){
    const hero=$('hero-reference-image'),heroUrl=hero&&!hero.hidden&&hero.getAttribute('src');
    const url=heroUrl||heygenAvatars.avatarPreview?.()||'';
    const tab=tabs.avatar;if(!tab||tab.dataset.avatarUrl===url)return;
    tab.dataset.avatarUrl=url;
    const icon=tab.querySelector('svg,.settings-tab-avatar');
    if(url){const img=document.createElement('img');img.className='settings-tab-avatar';img.alt='';img.src=url;img.referrerPolicy='no-referrer';
      img.addEventListener('error',()=>{img.replaceWith(document.createRange().createContextualFragment(channelSettingsIcon('hero')));},{once:true});icon?.replaceWith(img);}
    else if(icon?.matches('.settings-tab-avatar'))icon.replaceWith(document.createRange().createContextualFragment(channelSettingsIcon('hero')));
  }
  let refreshFrame;
  const schedule=()=>{if(!scheduled){scheduled=true;refreshFrame=requestAnimationFrame(()=>{scheduled=false;refresh();});}};
  body.addEventListener('input',schedule);body.addEventListener('change',schedule);body.addEventListener('click',schedule);
  heygenAvatars.addEventListener('heygen-avatar-preview',schedule);
  const observer=new MutationObserver(records=>{
    if(!workspace.isConnected){observer.disconnect();return;}
    if(records.some(record=>(record.type==='attributes'&&(record.attributeName!=='style'||record.target.id==='logo-preview'))||[...record.addedNodes].some(node=>node.nodeType===1&&(node.matches(fields)||node.querySelector(fields)))||record.target.closest?.('#style-caption,.voice-lab-reference-player,#style-strip')))schedule();
  });
  observer.observe(body,{subtree:true,childList:true,attributes:true,attributeFilter:['disabled','aria-checked','aria-pressed','src','style']});
  body.channelSettingsCleanup=()=>{observer.disconnect();cancelAnimationFrame(refreshFrame);body.removeEventListener('input',schedule);body.removeEventListener('change',schedule);body.removeEventListener('click',schedule);body.channelSettingsCleanup=null;};
  let previous='projects';try{previous=sessionStorage.getItem(preferenceKey)||previous;}catch{}select(previous);
  return {select,heygenAvatar:heygenAvatars.avatarSelection,refresh:schedule,setValidity(value){weightsValid=value;schedule();},ready(){baseline.clear();refresh();ready=true;refresh();},reveal(element){
    const panel=element?.closest('.channel-settings-panel');if(!panel)return;
    select(panel.dataset.settingsPanel);
    for(let parent=element.parentElement;parent&&parent!==panel;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true;
    element.scrollIntoView({block:'nearest'});element.focus();
  }};
}
