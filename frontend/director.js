// director.js — the director card on the plan of an animated episode. Once the voice is recognised the Studio hands the
// episode to Claude Opus 5.5 (high effort), which directs it and writes the frame plan back (backend/director.py). The card
// shows where that run stands, refreshes itself while it runs, reloads the plan when the frames arrive, and starts a new
// pass on request.
const directorRuns={};
let directorTimer=null;

function directorAnimated(){return state.channel?.settings?.channel_kind==='animated';}

async function loadDirector(id){
  try{directorRuns[id]=(await api(`/api/projects/${encodeURIComponent(id)}/director`)).director || {status:'none'};}
  catch{directorRuns[id]={status:'none'};}
  return directorRuns[id];
}

function directorTime(seconds){return new Date(seconds*1000).toLocaleTimeString('uk-UA',{hour:'2-digit',minute:'2-digit'});}

function renderDirectorStatus(panel){
  if(!state.project || !directorAnimated())return;
  const id=state.project.id,card=document.createElement('section');card.className='director-card';card.setAttribute('role','status');card.setAttribute('aria-live','polite');
  panel.append(card);
  const run=directorRuns[id];
  if(!run){loadDirector(id).then(()=>{if(state.project?.id===id&&card.isConnected)fillDirector(card,id);});card.textContent='Перевіряємо режисуру...';return;}
  fillDirector(card,id);
}

function fillDirector(card,id){
  const run=directorRuns[id],synced=!!state.project?.production?.plan_ready,directed=state.plan?.frame_source==='razgon-direction'&&!state.plan?.director_stale;
  card.replaceChildren();card.dataset.status=run.status;
  const head=document.createElement('div');head.className='director-head';
  const title=document.createElement('strong');
  const who=document.createElement('span');who.className='director-model';who.textContent='Claude Opus 5.5 · високий';
  head.append(title,who);card.append(head);
  const text=document.createElement('p');card.append(text);
  const button=label=>{const b=document.createElement('button');b.type='button';b.className='secondary';b.textContent=label;b.addEventListener('click',()=>startDirector(id));card.append(b);return b;};
  clearTimeout(directorTimer);
  if(run.status==='queued' || run.status==='running'){
    title.textContent='Режисура йде';
    text.textContent=`Агент ділить озвучку на шоти й пише план кадрів${run.started_at?`, почав о ${directorTime(run.started_at)}`:''}. Сцени він не малює. Сторінку можна закрити.`;
    directorTimer=setTimeout(()=>pollDirector(id),10000);
  }else if(run.status==='done'){
    title.textContent='Режисуру зроблено';
    text.textContent=`${run.frames?`${run.frames} кадрів у плані. `:''}Готово о ${directorTime(run.finished_at)}${run.cost_usd?` · за підпискою, еквівалент $${Number(run.cost_usd).toFixed(2)}`:''}.`;
    if(run.summary){const details=document.createElement('details');const summary=document.createElement('summary');summary.textContent='Звіт режисера';const body=document.createElement('p');body.textContent=run.summary;details.append(summary,body);card.append(details);}
    button('Переробити режисуру');
  }else if(run.status==='failed'){
    title.textContent='Режисура не вдалася';
    text.textContent=run.error || 'Невідома помилка';
    button('Спробувати ще раз');
  }else if(directed){
    title.textContent='План кадрів за режисурою';
    text.textContent='Кадри цього плану вже розбив режисер.';
    button('Переробити режисуру');
  }else{
    title.textContent='Режисура';
    text.textContent=synced?'Озвучка розпізнана. Режисер розіб’є її на шоти й запише план кадрів.':'Режисура почнеться сама, щойно студія розпізнає озвучку.';
    const b=button('Запустити режисуру');b.disabled=!synced;
  }
}

async function pollDirector(id){
  if(state.project?.id!==id)return;
  const before=directorRuns[id]?.status,run=await loadDirector(id);
  if(state.project?.id!==id)return;
  // The frames arrive with the finished run: reload the plan so the new frames show at once.
  if(before!==run.status && run.status==='done' && state.view==='plan'){await setProjectView('plan');return;}
  const card=document.querySelector('.director-card');
  if(card)fillDirector(card,id);
}

async function startDirector(id){
  if(!confirm('Запустити режисуру Claude Opus 5.5? Агент розіб’є озвучку на шоти й перезапише план кадрів цього випуску.'))return;
  try{
    directorRuns[id]=(await api(`/api/projects/${encodeURIComponent(id)}/director`,'POST',{})).director;
    const card=document.querySelector('.director-card');if(card)fillDirector(card,id);
  }catch(error){status(error.message,true);}
}
