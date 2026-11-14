// A manual sentence edit never starts script authorship or rebuilds the montage.
function addNarrationRevisionButton(fold,pid){
  const button=document.createElement('button');button.type='button';button.className='icon-button narration-revision-edit';
  button.title='Редагувати й переозвучити';button.setAttribute('aria-label',button.title);
  button.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="m15 4 5 5M4 20l5-1L20 8a3.5 3.5 0 0 0-5-5L4 14z"/></svg>';
  button.onclick=event=>{event.preventDefault();event.stopPropagation();openNarrationRevision(pid);};
  fold.querySelector('summary').append(button);
}
function narrationRevisionStage(job){
  if(job.status==='queued')return 'У черзі на переозвучення';
  if(job.status==='cancelling')return 'Зупиняємо переозвучення';
  return ({preparing:'Готуємо аудіо',assembling:'Збираємо оновлену озвучку',saving:'Зберігаємо зміни'})[job.stage]
    || ((job.completed||0)>=(job.total||1)?'Збираємо оновлену озвучку':`Переозвучуємо речення ${Math.min((job.completed||0)+1,job.total||1)} з ${job.total||1}`);
}
function showNarrationRevisionStage(element,job){
  element.classList.add('is-working');element.replaceChildren();
  const spinner=document.createElement('span');spinner.className='export-spinner';spinner.setAttribute('aria-hidden','true');
  const label=document.createElement('span');label.textContent=narrationRevisionStage(job);element.append(spinner,label);
}
async function openNarrationRevision(pid){
  modal('Редагувати й переозвучити','<p>Завантажуємо сценарій…</p>');
  const generation=state.modalGeneration;
  const active=()=>state.project?.id===pid&&state.modalGeneration===generation;
  let saved;
  try{saved=await api(`/api/projects/${pid}/narration/revision`);}catch(error){if(active())$('modal-body').textContent=error.message;return;}
  if(!active())return;
  let requestId=crypto.randomUUID(),submitted=false,timer;
  modal('Редагувати й переозвучити','<div class="narration-revision-form"><textarea aria-label="Ваш сценарій" rows="14"></textarea><p class="narration-revision-note">Переозвучимо лише змінені речення. Тривалість і розташування кадрів збережуться.</p><p role="status" class="narration-revision-status"></p></div>',[
    {label:'Зберегти й переозвучити',icon:'save',primary:true,enabled:()=>!submitted&&!!text.value.trim()&&text.value!==saved.text,run:async()=>{
      submitted=true;text.disabled=true;showNarrationRevisionStage(message,{stage:'preparing'});actionLabel('Переозвучуємо…');
      try{
        await api(`/api/projects/${pid}/narration/revision`,'POST',{text:text.value,expected_sha256:saved.sha256,client_id:requestId});
        if(connected())await poll();
      }catch(error){if(connected()){submitted=false;text.disabled=false;message.classList.remove('is-working');message.textContent=error.message;actionLabel('Зберегти й переозвучити');}}
    }}
  ]);
  const owner=state.modalGeneration,text=$('modal-body').querySelector('textarea'),message=$('modal-body').querySelector('[role=status]'),action=$('modal-actions').querySelector('button');
  const connected=()=>state.project?.id===pid&&state.modalGeneration===owner;
  function actionLabel(label){const span=action.querySelector('span');if(span)span.textContent=label;}
  text.value=saved.text;action.disabled=true;
  text.addEventListener('input',()=>{action.disabled=submitted||text.value===saved.text||!text.value.trim();});
  $('modal-body').channelSettingsCleanup=()=>clearTimeout(timer);
  async function poll(){
    if(!connected())return;
    try{
      const result=await api(`/api/projects/${pid}/narration/revision`);if(!connected())return;
      const job=result.job||{};
      if(['running','queued','cancelling'].includes(job.status)){
        submitted=true;text.disabled=true;action.disabled=true;
        showNarrationRevisionStage(message,job);actionLabel(job.stage==='saving'?'Зберігаємо…':'Переозвучуємо…');
        timer=setTimeout(poll,1500);return;
      }
      if(job.status==='done'){
        showNarrationRevisionStage(message,{stage:'saving'});
        const [project,plan]=await Promise.all([api(`/api/projects/${pid}`),api(`/api/projects/${pid}/plan`)]);
        if(!connected())return;stopPlayback();state.project=project.project;state.plan=sourceForProject(plan);state.assets=state.project.assets||[];
        state.previewNodes.clear();state.previewSignature='';buildAudioNodes();closeModal();renderProject();status('Змінені речення переозвучено.');return;
      }
      submitted=false;text.disabled=false;action.disabled=text.value===saved.text;message.classList.remove('is-working');actionLabel('Зберегти й переозвучити');
      message.textContent=job.error||'Переозвучення не завершене. Попередній звук збережено.';
      requestId=crypto.randomUUID();
    }catch(error){if(connected()){message.textContent=error.message;timer=setTimeout(poll,3000);}}
  }
  if(['running','queued','cancelling'].includes(saved.job?.status))await poll();
}
