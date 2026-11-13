// Keep cards and decoded covers mounted while background jobs update their status.
function reconcileProjectCards(container,projects){
  const previous=new Map([...container.children].filter(node=>node.classList.contains('project-card')).map(node=>[node.dataset.projectId,node]));
  for(const node of [...container.children])if(!node.classList.contains('project-card'))node.remove();
  let position=container.firstElementChild;
  for(const project of projects){
    const card=previous.get(project.id)||createProjectCard(project);previous.delete(project.id);
    updateProjectCard(card,project);
    if(card!==position)container.insertBefore(card,position);
    position=card.nextElementSibling;
  }
  for(const card of previous.values())card.remove();
}

function createProjectCard(project){
  const card=document.createElement('article');card.className='project-card';card.dataset.projectId=project.id;
  const current=()=>card._project;
  const open=document.createElement('button');open.type='button';open.className='project-open';
  open.innerHTML='<div class="project-title-spacer" aria-hidden="true"></div><div class="project-export-state" hidden></div><div class="project-meta"><span class="project-created-group"></span></div>';
  open.addEventListener('click',()=>{
    const latest=current(),count=latest.scene_count??latest.scenes?.length??0;
    selectProject(latest.id,{view:directMontage(latest)||count?'editor':'plan'}).catch(error=>status(error.message,true));
  });
  card.append(open,projectCardHeading(project,current));
  if(typeof attachProjectCosts==='function')attachProjectCosts(card,project);
  return card;
}

function updateProjectCard(card,project){
  card._project=project;
  card.setAttribute('aria-label',`Випуск «${project.name}»`);
  const open=card.querySelector('.project-open'),meta=open.querySelector('.project-meta');
  open.setAttribute('aria-label',`Відкрити випуск «${project.name}»`);
  const title=card.querySelector('.project-title-rename');
  if(title.textContent!==(project.name||'Без назви'))title.textContent=project.name||'Без назви';
  title.setAttribute('aria-label',`Перейменувати випуск «${project.name||'Без назви'}»`);
  const completion=meta.querySelector('.project-created-group'),markup=completionMark(project);
  if(completion._markup!==markup){completion.innerHTML=markup;completion._markup=markup;}
  const count=project.scene_count??project.scenes?.length??0,length=Number(project.voice_duration||(count>0?project.duration:0));
  let duration=meta.querySelector('.project-duration');
  if(Number.isFinite(length)&&length>0){
    if(!duration){duration=document.createElement('span');duration.className='project-duration';duration.title='Тривалість ролика';meta.append(duration);}
    const hours=Math.floor(length/3600),formatted=hours?`${hours}:${String(Math.floor(length/60)%60).padStart(2,'0')}:${String(Math.floor(length)%60).padStart(2,'0')}`:clock(length);
    if(duration.textContent!==formatted)duration.textContent=formatted;
  }else duration?.remove();
  updateProjectCardCover(card,project);
  const making=project.production_request,{total,done,working,stopped}=projectProductionCardState(making,project.last_export_at);
  card.classList.toggle('producing',working);card.classList.toggle('production-stopped',stopped);
  let box=open.querySelector('.project-production-state');
  if(working||stopped){
    if(!box){box=document.createElement('div');box.className='project-making project-production-state';open.insertBefore(box,meta);}
    box.classList.toggle('stopped',stopped);
    box.title=stopped?(making.error||'Відкрийте випуск, щоб продовжити роботу'):'';
    const text=working?`Створюємо кадри · ${done} з ${total}`:`${making.paused?'На паузі':making.limit?'Пауза: закінчився ліміт':'Зупинено'} · ${done} з ${total} ${planFrameWord(total)}`;
    if(box._working!==working){
      box.innerHTML=`<span class="project-export-label">${working?exportSpinner:''}<span class="project-production-label"></span></span>${working?'<span class="project-export-progress" role="progressbar" aria-label="Створення кадрів" aria-valuemin="0"><span></span></span>':''}`;
      box._working=working;
    }
    const label=box.querySelector('.project-production-label');if(label.textContent!==text)label.textContent=text;
    const progress=box.querySelector('[role="progressbar"]');
    if(progress){progress.setAttribute('aria-valuemax',total);progress.setAttribute('aria-valuenow',done);progress.firstElementChild.style.width=`${total?Math.round(done/total*100):0}%`;}
  }else box?.remove();
  const actionsKey=JSON.stringify([!!project.episode_path,!!project.freeable]);
  if(card._actionsKey!==actionsKey){
    const actions=projectActions(project,()=>card._project),old=card.querySelector('.project-actions');
    if(old)old.replaceWith(actions);else card.append(actions);
    card._actionsKey=actionsKey;delete card._activityKey;
  }
  for(const button of card.querySelectorAll('.project-action'))button.setAttribute('aria-label',`${button.title} «${project.name}»`);
  const controlKey=working?'working':stopped&&(making.paused||making.limit||/hit your \w+ limit/i.test(making.error||''))?'paused':'';
  if(card._controlKey!==controlKey){
    card.querySelector('.project-production-control')?.remove();
    if(controlKey){const control=productionControl(project.id,working);control.classList.add('project-production-control');card.append(control);}
    card._controlKey=controlKey;
  }
}

function updateProjectCardCover(card,project){
  const source=project.cover_asset_id||project.preview_mtime?`/api/projects/${encodeURIComponent(project.id)}/cover?v=${encodeURIComponent(project.preview_mtime||project.updated_at||project.revision||0)}`:'';
  if(card._coverSource===source&&(!card._coverRetryAt||Date.now()<card._coverRetryAt))return;
  card._coverSource=source;delete card._coverRetryAt;
  const previous=card.querySelector('.project-cover');
  if(!source){previous?.remove();card.classList.remove('has-cover','cover-ready');card.classList.add('no-cover');return;}
  const cover=document.createElement('img');cover.className='project-cover';cover.alt='';cover.decoding='async';
  // Replacements load offscreen. The previous picture stays visible until the new one is decoded.
  cover.loading=previous?'eager':'lazy';
  cover.addEventListener('load',async()=>{
    try{await cover.decode();}catch{}
    if(card._coverSource!==source){
      if(card.querySelector('.project-cover')===cover&&cover.naturalWidth)card.classList.add('cover-ready');
      return;
    }
    const old=card.querySelector('.project-cover');
    if(old!==cover){if(old)old.replaceWith(cover);else card.append(cover);}
    card.classList.remove('no-cover');card.classList.add('has-cover','cover-ready');
  },{once:true});
  cover.addEventListener('error',()=>{
    if(card._coverSource===source)card._coverRetryAt=Date.now()+30000;
    const visible=card.querySelector('.project-cover');
    if(visible===cover)cover.remove();
    else if(card._coverSource!==source||visible)return;
    card.classList.remove('has-cover','cover-ready');card.classList.add('no-cover');
  },{once:true});
  if(!previous){card.classList.remove('no-cover');card.classList.add('has-cover');card.append(cover);}
  cover.src=source;
}
