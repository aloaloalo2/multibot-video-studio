// Project cost receipts are loaded only on hover/focus, cached between card redraws.
const projectCostCache=new Map(),projectCostPending=new Map();
const claudeSubscriptionDivisor=29;
const projectCostIcons={
  openrouter:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12h5m-2-2 2 2-2 2m2-2c5 0 3-7 8-7h5m-3-3 3 3-3 3M8 12c5 0 3 7 8 7h5m-3-3 3 3-3 3"/></svg>',
  claude_code:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 2 1 7 5-5-3 7 7-1-6 4 4 5-7-3-1 6-2-6-6 3 3-6-5-2 7-1-4-6 6 4z"/></svg>',
  elevenlabs:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 4v16m8-16v16" stroke-width="3"/></svg>'
};
function projectCostMoney(amount){return amount==null?'$…':amount>0&&amount<.001?'<$0.001':`$${Number(amount).toFixed(amount>0&&amount<.01?3:2)}`;}
async function loadProjectCosts(id){
  const cached=projectCostCache.get(id);
  if(cached&&Date.now()-cached.at<30000)return cached.data;
  if(projectCostPending.has(id))return projectCostPending.get(id);
  const request=api(`/api/projects/${encodeURIComponent(id)}/costs`).then(data=>{
    projectCostCache.set(id,{at:Date.now(),data});return data;
  }).finally(()=>projectCostPending.delete(id));
  projectCostPending.set(id,request);return request;
}
function projectCostMarkup(data){
  const names={openrouter:'OpenRouter',claude_code:'Claude Code',elevenlabs:'ElevenLabs'};
  return Object.keys(names).map(key=>{
    const item=data?.providers?.[key],rawAmount=item?.usd;
    if(key!=='claude_code'&&item&&item.amount===0&&!item.unknown)return '';
    const amount=key==='claude_code'&&rawAmount!=null?rawAmount/claudeSubscriptionDivisor:rawAmount;
    const approximate=key==='claude_code'||item?.estimated||item?.equivalent||item?.unknown;
    const label=item?`${approximate?'≈ ':''}${projectCostMoney(item.unknown&&!amount?null:amount)}`:'…';
    const detail=key==='claude_code'?`Орієнтовна частка підписки: API-еквівалент ${projectCostMoney(rawAmount)} ÷ ${claudeSubscriptionDivisor}. Коефіцієнт задано користувачем.`:key==='elevenlabs'?`Оцінка за збереженими запитами озвучення. ${data?.elevenlabs_basis||'Курс кредитів ще невідомий.'}`:'Збережені витрати API: переклади, перевірки, агент і зображення.';
    return `<span class="project-cost-item" title="${esc(names[key]+'. '+detail+(item?.unknown?' Частину витрат не підтверджено.':''))}" aria-label="${esc(names[key]+': '+label)}">${projectCostIcons[key]}<span>${label}</span></span>`;
  }).join('');
}
function attachProjectCosts(card,project){
  const box=document.createElement('aside');box.className='project-costs';box.setAttribute('aria-label','Витрати проєкту');
  box.innerHTML=projectCostMarkup(projectCostCache.get(project.id)?.data);card.append(box);
  const show=async()=>{try{box.innerHTML=projectCostMarkup(await loadProjectCosts(project.id));}catch{box.innerHTML='<span class="project-cost-unavailable">Витрати недоступні</span>';}};
  card.addEventListener('mouseenter',show);card.addEventListener('focusin',show);
}
function updateLanguageCostBadge(id){
  const tab=$('view-langs');if(!tab)return;
  let badge=tab.querySelector('.language-total-cost');
  if(!badge){badge=document.createElement('span');badge.className='language-total-cost';tab.append(badge);}
  if(badge.dataset.project!==id){badge.dataset.project=id||'';badge.textContent='';}
  if(!id){badge.textContent='';return;}
  const owner=id;
  loadProjectCosts(id).then(data=>{
    if(state.project?.id!==owner)return;
    const eleven=data.providers?.elevenlabs;
    const amount=(data.languages_usd||0)+(eleven?.usd||0);
    badge.textContent=`${eleven?.requests?'≈ ':''}${projectCostMoney(amount)}`;
    badge.title='Переклади й оцінка вартості озвучення ElevenLabs';
  }).catch(()=>{if(state.project?.id===owner)badge.textContent='';});
}
