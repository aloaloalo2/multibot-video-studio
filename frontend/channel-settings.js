// Keep the existing controls mounted while arranging them into a small settings workspace.
const channelSettingsPaths={
  projects:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M8 4v5M8 13h3m-3 3h7"/>',
  look:'<path d="M12 3a9 9 0 1 0 0 18h1a2 2 0 0 0 1-3.7 1.4 1.4 0 0 1 .8-2.6h2A4.2 4.2 0 0 0 21 10.5 8.5 8.5 0 0 0 12 3Z"/><circle cx="7.5" cy="10" r=".7"/><circle cx="11" cy="6.7" r=".7"/><circle cx="15.5" cy="7.5" r=".7"/>',
  voice:'<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8"/>',
  sound:'<path d="M9 18V5l12-2v13M9 9l12-2"/><ellipse cx="6" cy="18" rx="3" ry="2"/><ellipse cx="18" cy="16" rx="3" ry="2"/>',
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

function organizeChannelSettings(){
  const body=$('modal-body'),backdrop=$('modal-backdrop');
  backdrop.classList.add('channel-settings-open');
  const workspace=document.createElement('div');workspace.className='channel-settings-workspace';
  const nav=document.createElement('nav');nav.className='channel-settings-nav';nav.setAttribute('aria-label','Розділи налаштувань каналу');nav.setAttribute('role','tablist');nav.setAttribute('aria-orientation','vertical');
  const content=document.createElement('div');content.className='channel-settings-content';
  workspace.append(nav,content);body.append(workspace);
  const definitions=[
    ['projects','Проєкти','Налаштування проєктів за замовчуванням'],
    ['look','Оформлення','Логотип, стиль анімації та шрифти'],
    ['voice','Озвучка','Голос для озвучення сценаріїв'],
    ['sound','Звук ролика','Музика, переходи й монтажні акценти'],
    ['languages','Переклад','Голоси для мов перекладу'],
    ['thumbnails','Прев’ю','Герой і побажання до обкладинок']
  ];
  const panels={},tabs={};
  function select(key,focus=false){
    for(const [name,panel] of Object.entries(panels)){
      const active=name===key;panel.hidden=!active;tabs[name].setAttribute('aria-selected',String(active));tabs[name].tabIndex=active?0:-1;
      if(!active)panel.querySelectorAll('audio,video').forEach(media=>media.pause());
    }
    if(focus)tabs[key].focus();
  }
  for(const [key,label,note] of definitions){
    const tab=document.createElement('button');tab.type='button';tab.id=`channel-settings-tab-${key}`;tab.dataset.settingsTab=key;tab.setAttribute('role','tab');tab.setAttribute('aria-controls',`channel-settings-panel-${key}`);
    tab.innerHTML=`${channelSettingsIcon(key)}<span>${label}</span>`;tab.addEventListener('click',()=>select(key));tabs[key]=tab;nav.append(tab);
    const panel=document.createElement('section');panel.className='channel-settings-panel';panel.id=`channel-settings-panel-${key}`;panel.dataset.settingsPanel=key;panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby',tab.id);
    const heading=document.createElement('header');heading.className='channel-settings-panel-head';heading.innerHTML=`<h3>${label}</h3><p>${note}</p>`;panel.append(heading);panels[key]=panel;content.append(panel);
  }
  nav.addEventListener('keydown',event=>{
    const keys=definitions.map(item=>item[0]),index=keys.findIndex(key=>tabs[key]===event.target);
    if(index<0)return;
    const next=event.key==='Home'?0:event.key==='End'?keys.length-1:['ArrowDown','ArrowRight'].includes(event.key)?(index+1)%keys.length:['ArrowUp','ArrowLeft'].includes(event.key)?(index+keys.length-1)%keys.length:null;
    if(next!==null){event.preventDefault();select(keys[next],true);}
  });
  const move=(selector,panel,{fold=false,icon='projects',title=null,note=''}={})=>{
    const section=body.querySelector(selector);if(!section)return;
    const heading=section.querySelector('h3');
    if(!fold){
      if(heading){if(title)heading.textContent=title;heading.insertAdjacentHTML('afterbegin',channelSettingsIcon(icon));heading.classList.add('channel-settings-section-title');}
      panels[panel].append(section);return;
    }
    const details=document.createElement('details');details.className='channel-settings-group';
    for(const name of ['regular-only','animated-only','planned-only'])if(section.classList.contains(name))details.classList.add(name);
    const summary=document.createElement('summary');summary.innerHTML=`${channelSettingsIcon(icon)}<span><strong>${title||heading?.textContent||''}</strong>${note?`<small>${note}</small>`:''}</span><svg class="channel-settings-chevron" viewBox="0 0 20 20" aria-hidden="true"><path d="m7 4 6 6-6 6"/></svg>`;
    const inner=document.createElement('div');inner.className='channel-settings-group-body';details.append(summary,inner);inner.append(section);if(heading)heading.hidden=true;panels[panel].append(details);
  };
  move('.channel-project-defaults','projects',{fold:true,title:'Режим і тип проєкту',icon:'projects',note:'План кадрів, тип ролика й рівень зусиль'});
  move('.settings-output','projects',{fold:true,icon:'output',note:'Роздільність, частота кадрів і якість'});
  move('.settings-visual-formats','projects',{fold:true,icon:'formats',note:'Пропорції форматів і стиль створених зображень'});
  move('.settings-accents','projects',{fold:true,icon:'accents',note:'Підписи, плашки, стрілки й виділення'});
  move('.settings-opening','projects',{fold:true,icon:'opening',note:'Формат і тривалість початкових кадрів'});
  move('.settings-sentences','projects',{fold:true,icon:'sentences',note:'Як розподіляти речення між кадрами'});
  move('.settings-agent-memory','projects',{fold:true,icon:'memory',title:'Пам’ять режисера',note:'Постійні правила монтажу для цього каналу'});
  move('.logo-section','look',{icon:'thumbnails'});
  move('.channel-look','look',{icon:'look'});
  const voiceSlot=document.createElement('div');voiceSlot.id='channel-voice-settings';panels.voice.append(voiceSlot);
  move('.settings-sound','sound',{icon:'sound'});
  move('#channel-voices','languages',{icon:'languages'});
  move('.hero-reference-section','thumbnails',{icon:'hero'});
  move('.settings-thumbnail-wishes','thumbnails',{icon:'wishes'});
  // Its explanation now lives beside the formats it describes.
  const purpose=$('settings-purpose'),formats=body.querySelector('.settings-visual-formats');
  if(purpose&&formats)formats.prepend(purpose);
  select('projects');
  return {select,reveal(element){
    const panel=element?.closest('.channel-settings-panel');if(!panel)return;
    select(panel.dataset.settingsPanel);
    for(let parent=element.parentElement;parent&&parent!==panel;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true;
    element.scrollIntoView({block:'nearest'});element.focus();
  }};
}
