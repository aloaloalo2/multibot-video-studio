/* Shared competitor ideas; late reads stay scoped to the current page. */
function trendingCard(video, icons={}){
  const number=value=>new Intl.NumberFormat('uk-UA',{notation:'compact',maximumFractionDigits:1}).format(value);
  if(!/^[A-Za-z0-9_-]{11}$/.test(video.id))return '';
  const days=Math.max(0,Math.floor((Date.now()-new Date(video.published_at).getTime())/86400000));
  const date=days===0?'сьогодні':Number.isFinite(days)?new Intl.RelativeTimeFormat('uk-UA',{numeric:'always'}).format(-days,'day'):'';
  const icon=icons?.[video.competitor_id];
  const avatar=typeof icon==='string'&&/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(icon)?`<img class="trend-channel-avatar" src="${icon}" alt="" width="20" height="20" loading="lazy">`:'';
  return `<article class="project-card has-cover cover-ready trend-card"><img class="project-cover" src="https://i.ytimg.com/vi/${video.id}/hqdefault.jpg" loading="lazy" alt=""><a class="project-open trend-open" href="https://www.youtube.com/watch?v=${video.id}" target="_blank" rel="noopener noreferrer" aria-label="Відкрити відео ${esc(video.title)}"><div class="project-title-spacer" aria-hidden="true"></div><div class="project-meta"><strong class="trend-views" title="Перегляди"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg><span>${number(video.views)}</span></strong><span class="trend-score" title="Перегляди на день відносно медіани інших недавніх відео цього каналу схожої тривалості">↑ ${esc(video.score)}×</span><span class="project-duration">${Math.floor(video.duration/60)}:${String(video.duration%60).padStart(2,'0')}</span></div></a><div class="project-actions"><button type="button" class="project-action trend-use-idea" data-use-idea="${video.id}" title="Використати ідею" aria-label="Використати ідею «${esc(video.title)}»"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18h6m-6 3h6M8 14a6 6 0 1 1 8 0c-1 .8-1 2-1 2H9s0-1.2-1-2Z"/></svg></button></div><h2><a class="project-title-rename" title="${esc(video.title)}" href="https://www.youtube.com/watch?v=${video.id}" target="_blank" rel="noopener noreferrer">${esc(video.title)}</a></h2><div class="trend-details">${video.title_uk?`<p class="trend-title-uk" lang="uk" title="${esc(video.title_uk)}">${esc(video.title_uk)}</p>`:''}<div class="trend-channel-row"><a class="trend-channel" href="https://www.youtube.com/channel/${encodeURIComponent(video.competitor_id)}" target="_blank" rel="noopener noreferrer">${avatar}<span>${esc(video.competitor_name)}</span></a><span>${video.subscribers===null?'':number(video.subscribers)+' підписників'}</span></div><div class="trend-source-row"><span>${video.for_channels.map(c=>esc(c.name)).join(' · ')}</span><span>${esc(date)}</span></div></div></article>`;
}
function openTrendingVideos({updateUrl=true}={}){
  cancelLocationRestore();++state.navigation;stopPlayback();
  if(state.poll){clearTimeout(state.poll);state.poll=null;}
  if(state.exportWatch){clearInterval(state.exportWatch);state.exportWatch=null;}
  if(state.channel)state.trendingPreviousChannel=state.channel.id;
  state.channel=null;state.project=null;state.projects=[];state.assets=[];state.pixabay=[];state.selected=null;state.selectedTransition=null;state.selectedTrack=null;state.view='trending';
  closeModal();renderChannels();renderProject();status('');if(updateUrl)syncRoute();
  const root=$('trending-page');
  root.innerHTML='<div class="overview-top trend-top"><div class="overview-heading trend-heading"><h1 id="trending-title">Зараз у тренді</h1><button type="button" class="outline trend-refresh" title="Оновити" aria-label="Оновити"><svg class="project-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M3 4v6h6M4 9a8 8 0 1 1-1 7"/></svg></button></div><div class="overview-actions"><select class="trend-filter" aria-label="Ідеї для каналу"><option value="">Усі наші канали</option></select></div></div><section class="trending-view"><p class="trend-feedback" role="status">Завантажуємо…</p><div class="overview-projects trend-grid"></div></section>';
  const navigation=state.navigation;
  const live=()=>root.isConnected&&state.navigation===navigation&&state.view==='trending'&&!root.hidden;
  const select=root.querySelector('select'),button=root.querySelector('.trend-refresh'),feedback=root.querySelector('.trend-feedback'),grid=root.querySelector('.trend-grid');
  let data=null,timer=null;
  const schedule=()=>{clearTimeout(timer);if(live())timer=setTimeout(load,2000);};
  function render(){
    if(!live()||!data)return;
    const filtered=data.videos.filter(v=>!select.value||v.for_channels.some(c=>c.id===select.value));
    grid.innerHTML=filtered.map(video=>trendingCard(video,data.competitor_icons)).join('');
    button.disabled=data.running;
    feedback.textContent=[data.running?'Перевіряємо конкурентів…':'',...data.errors,...data.warnings,!data.competitors?'Додайте конкурентів у налаштуваннях каналу.':!data.checked&&!data.running?'Натисніть ↻, щоб отримати добірку.':!filtered.length&&!data.running?'Нових популярних відео поки немає.':''].filter(Boolean).join(' · ');
    feedback.hidden=!feedback.textContent;
  }
  async function load(){
    if(!live())return;
    try{
      const result=await api('/api/trending-videos');if(!live())return;data=result;
      const value=select.value;
      select.innerHTML='<option value="">Усі наші канали</option>'+data.channels.map(c=>`<option value="${esc(c.id)}">${esc(c.name)}</option>`).join('');select.value=value;
      render();if(data.running)schedule();
    }catch(error){if(live()){feedback.hidden=false;feedback.textContent=error.httpStatus===404?'Розділ підготовлено. Він стане доступним після безпечного перезапуску студії, коли поточні роботи завершаться.':error.message;if(error.httpStatus===404)button.disabled=true;}}
  }
  select.onchange=render;
  grid.onclick=event=>{
    const button=event.target.closest('[data-use-idea]');if(!button||!live())return;
    const video=data?.videos.find(video=>video.id===button.dataset.useIdea);
    if(video)openTrendingIdea(video,select.value);
  };
  button.onclick=async()=>{
    button.disabled=true;
    try{const result=await api('/api/trending-videos/refresh','POST',{});if(!live())return;await load();if(result.running)schedule();else if(result.retry_after){feedback.hidden=false;feedback.textContent=`Спробуйте за ${result.retry_after} с`;}}
    catch(error){if(live()){feedback.hidden=false;feedback.textContent=error.message;}}
    finally{if(live())button.disabled=!!data?.running;}
  };
  load();
}
document.getElementById('trending-videos').addEventListener('click',()=>openTrendingVideos());


function openTrendingIdea(video, preferredChannel=''){
  const channels=state.channels||[];
  const selected=channels.find(c=>c.id===preferredChannel)||channels.find(c=>video.for_channels.some(own=>own.id===c.id))||channels[0];
  const navigation=state.navigation,requestId=crypto.randomUUID();
  let generation,root,submit,ready=false,sending=false,wordsEdited=false,channelRead=0;
  const live=()=>root?.isConnected&&state.modalGeneration===generation&&state.navigation===navigation&&!$('modal-backdrop').hidden;
  const valid=()=>ready&&!sending&&!!root?.querySelector('[name="channel"]').value&&!!root?.querySelector('[name="title"]').value.trim();
  modal('Використати ідею',`<div class="trend-idea-form"><label>Канал<select name="channel" aria-label="Канал для ідеї">${channels.map(c=>`<option value="${esc(c.id)}" ${c.id===selected?.id?'selected':''}>${esc(c.name)}</option>`).join('')}</select></label><label>Заголовок<input name="title" aria-label="Заголовок випуску" type="text" maxlength="100" value="${esc(video.title)}"></label>${video.title_uk?`<p class="trend-title-uk">${esc(video.title_uk)}</p>`:''}<img class="trend-idea-preview" src="https://i.ytimg.com/vi/${video.id}/hqdefault.jpg" alt="Прев’ю конкурента"><label class="trend-idea-check"><input name="use_thumbnail" type="checkbox" checked><span>Використовувати прев’ю конкурента</span></label><label class="episode-word-count">Обсяг сценарію <input name="words" aria-label="Обсяг сценарію" type="number" min="200" max="15000" step="1" value="2000"> слів</label><p class="trend-idea-feedback muted" role="status" hidden></p></div>`,[{
    label:'Створити зачини',primary:true,enabled:valid,run:async()=>{
      if(!live()||!valid())return;
      const cid=root.querySelector('[name="channel"]').value,title=root.querySelector('[name="title"]').value.trim();
      const count=Number(root.querySelector('[name="words"]').value);
      const note=root.querySelector('.trend-idea-feedback');
      if(!Number.isInteger(count)||count<200||count>15000){note.hidden=false;note.textContent='Вкажіть обсяг від 200 до 15 000 слів';return;}
      if(title.length>100){note.hidden=false;note.textContent='Скоротіть заголовок до 100 символів';return;}
      const useThumbnail=root.querySelector('[name="use_thumbnail"]').checked;
      sending=true;note.hidden=true;root.querySelectorAll('input,select').forEach(field=>field.disabled=true);
      try{
        const draft=await api('/api/trending-videos/use','POST',{channel_id:cid,video_id:video.id,title,target_words:count,use_thumbnail:useThumbnail,request_id:requestId});
        if(!live())return;
        closeModal();
        if(await selectChannel(cid))await selectProject(draft.project_id);
      }catch(error){if(live()){note.hidden=false;note.textContent=error.message;}}
      finally{sending=false;if(live()){root.querySelectorAll('input,select').forEach(field=>field.disabled=false);submit.disabled=!valid();}}
    }
  }]);
  generation=state.modalGeneration;root=$('modal-body').querySelector('.trend-idea-form');submit=$('modal-actions').querySelector('button');submit.disabled=true;
  root.querySelector('[name="title"]').oninput=()=>{submit.disabled=!valid();};
  root.querySelector('[name="words"]').oninput=()=>{wordsEdited=true;};
  async function recommendation(){
    const version=++channelRead,cid=root.querySelector('[name="channel"]').value;
    if(!cid)return;
    try{
      const data=await api(`/api/channels/${encodeURIComponent(cid)}/episode-ideas?view=topics`);
      if(live()&&version===channelRead&&!sending&&!wordsEdited&&Number.isInteger(data.target_words))root.querySelector('[name="words"]').value=data.target_words;
    }catch(error){/* The editable default remains available when a recommendation cannot be read. */}
  }
  root.querySelector('[name="channel"]').onchange=()=>{submit.disabled=!valid();recommendation();};
  api('/api/health').then(health=>{
    if(!live())return;ready=health.trending_use_idea===true;submit.disabled=!valid();
    if(!ready){const note=root.querySelector('.trend-idea-feedback');note.hidden=false;note.textContent='Оновлення стане доступним після безпечного перезапуску студії';}
  }).catch(error=>{if(live()){const note=root.querySelector('.trend-idea-feedback');note.hidden=false;note.textContent=error.message;}});
  recommendation();
}
