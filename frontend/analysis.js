const speechStageNames={queued:'У черзі',preparing:'Підготовка звуку',loading_model:'Завантаження локальної моделі',recognizing:'Розпізнавання мовлення',comparing:'Зіставлення зі сценарієм',complete:'Обробку завершено',failed:'Обробку зупинено'};
const speechIssueNames={text_difference:'Розбіжність тексту',missing_boundary:'Не знайдено межу фрази',uncertain_boundary:'Сумнівний час фрази',low_recognition_confidence:'Низька впевненість розпізнавання',out_of_order:'Прозвучала не на своєму місці',repeated_speech:'Прозвучала кілька разів'};

function appendSpeechReport(target,report,{transcript:withTranscript=true}={}){
  const box=document.createElement('section');box.className='speech-report';
  const title=document.createElement('h3');title.textContent=report.applied?'Таймінги застосовано':'Потрібна перевірка';box.append(title);
  const counts=document.createElement('div');counts.className='speech-report-counts';
  counts.innerHTML=`<span><strong>${Number(report.word_match_percent).toFixed(1)}%</strong> слів зіставлено</span><span><strong>${report.matched_phrases} з ${report.phrase_count}</strong> фраз без зауважень</span>`;box.append(counts);
  const source=document.createElement('p');source.className='plan-note';source.textContent=report.source.name;box.append(source);
  if(report.status==='script_changed' || report.status==='source_changed'){
    const warning=document.createElement('p');warning.className='speech-warning';warning.textContent=report.status==='script_changed'?'Сценарій змінився під час обробки. Повторіть аналіз.':'Медіафайл змінився під час обробки. Повторіть аналіз.';box.append(warning);
  }
  const help=document.createElement('p');help.className='plan-note';help.textContent='Збіг слів показує відповідність сценарію. Автоматичні часові межі та сумнівні фрази перевіряються окремо.';box.append(help);
  const issues=(report.phrases || []).filter(phrase=>phrase.issues.length);
  if(issues.length){
    const details=document.createElement('details');details.className='speech-issues';
    const summary=document.createElement('summary');summary.textContent=report.applied?`Дрібні розбіжності, виправлені за сценарієм: ${issues.length}`:`Фрази для перевірки: ${issues.length}`;details.append(summary);
    const list=document.createElement('div');
    for(const phrase of issues){const item=document.createElement('article');item.innerHTML=`<strong>Фраза ${phrase.number}</strong><p>${esc(phrase.issues.map(issue=>speechIssueNames[issue] || issue).join(' · '))}</p><p><b>Сценарій:</b> ${esc(phrase.text)}</p><p><b>Розпізнано:</b> ${esc(phrase.recognized || 'Не знайдено відповідного фрагмента')}</p>`;list.append(item);}details.append(list);box.append(details);
  }
  // A voice said out of order or with a piece twice is the author's to fix (backend/speech_order.py): it shows open,
  // above the folded details, and the studio cuts or moves nothing in it.
  const order=(report.differences || []).filter(difference=>difference.note);
  if(order.length){
    const moved=order.some(difference=>difference.kind==='moved'),repeated=order.some(difference=>difference.kind==='repeated');
    const warn=document.createElement('div');warn.className='speech-order';
    const title=document.createElement('strong');title.textContent=moved&&repeated?'Озвучка йде не по порядку сценарію і має повтори':moved?'Озвучка йде не по порядку сценарію':'В озвучці є повтори';warn.append(title);
    for(const difference of order){const line=document.createElement('p');line.textContent=difference.note;warn.append(line);}
    const hint=document.createElement('small');hint.textContent='Виправте озвучку й додайте її знову. Студія нічого в ній не ріже й не переставляє.';warn.append(hint);
    box.append(warn);
  }
  const words=(report.differences || []).filter(difference=>!difference.note);
  if(words.length){
    const details=document.createElement('details');details.className='speech-issues';const summary=document.createElement('summary');summary.textContent='Пропущені, додані та змінені слова';details.append(summary);
    for(const difference of words){const item=document.createElement('p');item.textContent=`Фрази ${difference.sentences.join(', ')}. Сценарій: ${difference.expected || 'немає'}. Розпізнано: ${difference.recognized || 'немає'}.`;details.append(item);}box.append(details);
  }
  if(withTranscript){  const transcript=document.createElement('details');transcript.className='speech-issues';const label=document.createElement('summary');label.textContent='Повна розшифровка';const text=document.createElement('p');text.textContent=report.recognized_text;transcript.append(label,text);box.append(transcript);}target.append(box);
}

// The recognition report lives folded at the bottom of the plan (director.js «Текст озвучки й розпізнавання»): once the
// analysis arrives it fills that fold and the voice line.
function renderSpeechReport(panel){
  const episode=panel?.querySelector('.episode');
  if(!episode || state.analysis?.job?.project_id!==state.project?.id)return;
  const slot=episode.querySelector('.episode-report'),heard=episode.querySelector('.episode-heard'),report=state.analysis.report;
  if(report&&heard)heard.textContent=report.recognized_text || '';
  if(slot&&!slot.children.length&&report)appendSpeechReport(slot,report,{transcript:false});
  refreshEpisode(episode);
}

async function openMediaTimingImport(){
  if(!state.project || !state.plan)return;
  const project=state.project,plan=state.plan;
  let candidate=null,busy=false;
  const media=state.assets.filter(asset=>asset.kind==='audio' || asset.kind==='video');
  const replacing=!!project.production?.plan_ready;
  modal(replacing?'Замінити озвучку':'Додати озвучку / таймінги',`<p>${replacing?'Нова озвучка замінить поточну. Студія розпізнає її локально через Whisper і зіставить зі сценарієм, а якщо текст змінився, режисер заново розіб’є кадри. Можна також додати готовий JSON із таймінгами.':'Аудіо або відео буде розпізнано локально через Whisper та зіставлено зі сценарієм. Також можна додати готовий JSON із таймінгами.'}</p><label>Аудіо, відео або таймінги<input id="plan-import-file" type="file" accept="audio/*,video/*,.json,.mkv,.aiff,.aif,.flac,.opus"></label>${media.length?`<details class="speech-existing"><summary>Вибрати медіа проєкту</summary><label>Матеріал<select id="speech-existing-asset"><option value="">Оберіть файл</option>${media.map(asset=>`<option value="${esc(asset.id)}">${esc(asset.name)}</option>`).join('')}</select></label></details>`:''}<p id="plan-import-feedback" role="status"></p><div id="speech-analysis-state" aria-live="polite"></div>`,[{label:'Закрити',run:closeModal},{label:'Обробити файл',primary:true,run:submit}]);
  const root=$('speech-analysis-state'),feedback=$('plan-import-feedback'),input=$('plan-import-file'),button=$('modal-actions').querySelector('.primary');button.disabled=true;
  function current(){return $('speech-analysis-state')===root;}
  function controls(disabled){input.disabled=disabled;const select=$('speech-existing-asset');if(select)select.disabled=disabled;button.disabled=disabled || !candidate;}
  input.addEventListener('change',async()=>{
    try{const file=input.files[0];candidate=null;if(!file){controls(false);return;}
      if(file.name.toLowerCase().endsWith('.json')){const data=JSON.parse(await file.text());if(!data || !Array.isArray(data.sentences) || typeof data.duration!=='number' || data.duration<=0)throw new Error('У файлі потрібні тривалість озвучки та таймінги фраз.');candidate={kind:'timings',timings:data};button.textContent='Застосувати таймінги';}
      else {candidate={kind:'file',file};button.textContent='Розпізнати та зіставити';}
      if($('speech-existing-asset'))$('speech-existing-asset').value='';feedback.textContent=file.name;controls(false);
    }catch(error){feedback.textContent=error.message;controls(false);}
  });
  $('speech-existing-asset')?.addEventListener('change',event=>{input.value='';candidate=event.target.value?{kind:'asset',asset_id:event.target.value}:null;button.textContent='Розпізнати та зіставити';feedback.textContent='';controls(false);});
  async function submit(){
    if(!candidate || busy)return;busy=true;controls(true);feedback.textContent='';
    try{
      if(candidate.kind==='timings'){
        const script=plan.script || plan.frames.flatMap(frame=>frame.sentences || []).join(' ');
        const result=await api(`/api/projects/${encodeURIComponent(project.id)}/plan/generate`,'POST',{script,hints:plan.hints,timings:candidate.timings});closeModal();await selectProject(result.project.id,{view:'plan'});status('Таймінги плану оновлено.');return;
      }
      let assetId=candidate.asset_id;
      if(candidate.kind==='file'){
        feedback.textContent='Завантаження файлу до локальної студії…';
        const response=await fetch(`/api/projects/${encodeURIComponent(project.id)}/assets/upload`,{method:'POST',headers:{'Content-Type':'application/octet-stream','X-File-Name':encodeURIComponent(candidate.file.name)},body:candidate.file});
        const result=await response.json();if(!response.ok)throw new Error(result.error || 'Не вдалося додати файл');assetId=result.asset.id;
      }
      await api(`/api/projects/${encodeURIComponent(project.id)}/plan/analyze`,'POST',{asset_id:assetId});feedback.textContent='Можна закрити вікно. Обробка продовжиться у студії.';await poll();
    }catch(error){if(current()){feedback.textContent=error.message;busy=false;controls(false);}}
  }
  async function poll(){
    if(!current())return;
    try{
      const result=await api(`/api/projects/${encodeURIComponent(project.id)}/analysis`);state.analysis=result;
      if(!current())return;
      const job=result.job;root.replaceChildren();
      if(!job)return;
      if(job.status==='failed'){feedback.textContent=job.error;busy=false;controls(false);return;}
      if(job.status==='complete'){
        busy=false;controls(false);feedback.textContent='Обробку завершено.';
        if(state.project?.id===project.id)await selectProject(project.id,{view:'plan'});
        if(current() && result.report)appendSpeechReport(root,result.report);return;
      }
      busy=true;controls(true);
      const stage=document.createElement('p');stage.textContent=`${speechStageNames[job.stage] || 'Обробка'}: ${job.progress}%`;
      const progress=document.createElement('progress');progress.max=100;progress.value=job.progress;root.append(stage,progress);setTimeout(poll,1200);
    }catch(error){if(current()){feedback.textContent=error.message;busy=false;controls(false);}}
  }
  try{const result=await api(`/api/projects/${encodeURIComponent(project.id)}/analysis`);state.analysis=result;if(result.job?.status==='queued' || result.job?.status==='running')await poll();else if(result.report)appendSpeechReport(root,result.report);}catch(error){feedback.textContent=error.message;}
}
