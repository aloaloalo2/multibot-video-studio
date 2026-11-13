/* Shared competitor ideas; late reads stay scoped to the current page. */
const trendDays = new Intl.NumberFormat('uk-UA', {style:'unit', unit:'day', unitDisplay:'long'});
function trendingCard(video, icons={}){
  const number=value=>new Intl.NumberFormat('uk-UA',{notation:'compact',maximumFractionDigits:1}).format(value);
  if(!/^[A-Za-z0-9_-]{11}$/.test(video.id))return '';
  const days=Math.max(0,Math.floor((Date.now()-Date.parse(video.published_at))/86400000));
  const period=days===0?'сьогодні':Number.isFinite(days)?`за ${trendDays.format(days)}`:'';
  const icon=icons?.[video.competitor_id];
  const code=typeof video.title_language==='string'?video.title_language.toLowerCase():'';
  const language=/^[a-z]{2,3}$/.test(code)&&!['uk','ru'].includes(code)?`<span class="trend-language" title="Мова заголовка: ${code.toUpperCase()}">${code.toUpperCase()}</span> `:'';

  const avatar=typeof icon==='string'&&/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(icon)?`<img class="trend-channel-avatar" src="${icon}" alt="" width="20" height="20" loading="lazy">`:'';
  const subscribers=video.subscribers==null?'':`<span class="trend-subscribers" title="Підписники" aria-label="${esc(number(video.subscribers))} підписників"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m20 0v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/><circle cx="9" cy="7" r="4"/></svg><span>${number(video.subscribers)}</span></span>`;
  return `<article class="project-card has-cover cover-ready trend-card"><img class="project-cover" src="https://i.ytimg.com/vi/${video.id}/hqdefault.jpg" loading="lazy" alt=""><button type="button" class="project-open trend-open" data-use-idea="${video.id}" aria-label="Використати ідею ${esc(video.title)}"><div class="project-title-spacer" aria-hidden="true"></div><div class="project-meta"><strong class="trend-views" title="Перегляди"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg><span>${number(video.views)}</span>${period?`<small class="trend-date">${period}</small>`:''}</strong><span class="trend-score" title="Перегляди на день відносно медіани інших недавніх відео цього каналу схожої тривалості">↑ ${esc(video.score)}×</span><span class="project-duration">${Math.floor(video.duration/60)}:${String(video.duration%60).padStart(2,'0')}</span></div></button><div class="project-actions"><button type="button" class="project-action trend-use-idea" data-use-idea="${video.id}" title="Використати ідею" aria-label="Використати ідею «${esc(video.title)}»"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18h6m-6 3h6M8 14a6 6 0 1 1 8 0c-1 .8-1 2-1 2H9s0-1.2-1-2Z"/></svg></button></div><h2><button type="button" class="project-title-rename" data-use-idea="${video.id}" title="${esc(video.title)}">${language}${esc(video.title)}</button></h2><div class="trend-details">${video.title_uk?`<p class="trend-title-uk" lang="uk" title="${esc(video.title_uk)}">${esc(video.title_uk)}</p>`:''}<div class="trend-channel-row"><a class="trend-channel" href="https://www.youtube.com/channel/${encodeURIComponent(video.competitor_id)}" target="_blank" rel="noopener noreferrer">${avatar}<span>${esc(video.competitor_name)}</span></a>${subscribers}</div><div class="trend-source-row"><span>${video.for_channels.map(c=>esc(c.name)).join(' · ')}</span></div></div></article>`;
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
  $('trending-toolbar').replaceChildren(root.querySelector('.trend-top'));
  let data=null,timer=null,readVersion=0,readFailures=0,refreshing=false,cardMarkup='';const used=new Set();
  const schedule=(delay=2000)=>{clearTimeout(timer);if(live())timer=setTimeout(load,delay);};
  function setRunning(running){button.disabled=running;button.classList.toggle('is-loading',running);button.setAttribute('aria-busy',String(running));}
  function render(){
    if(!live()||!data)return;
    const filtered=data.videos.filter(v=>!used.has(v.id)&&(!select.value||v.for_channels.some(c=>c.id===select.value)));
    const markup=filtered.map(video=>trendingCard(video,data.competitor_icons)).join('');
    if(markup!==cardMarkup){cardMarkup=markup;grid.innerHTML=markup;}
    const running=refreshing||data.running;
    setRunning(running);
    feedback.textContent=running?'Оновлюємо добірку…':!data.competitors?'Додайте конкурентів у налаштуваннях каналу.':!data.checked&&data.errors?.length?'Не вдалося оновити добірку. Спробуйте ще раз.':!data.checked?'Натисніть ↻, щоб отримати добірку.':!filtered.length?'Нових популярних відео поки немає.':'';
    feedback.hidden=!feedback.textContent;
  }
  async function load(){
    if(!live())return;
    clearTimeout(timer);const version=++readVersion;
    try{
      const result=await api('/api/trending-videos');if(!live()||version!==readVersion)return;data=result;readFailures=0;
      const value=select.value;
      select.innerHTML='<option value="">Усі наші канали</option>'+data.channels.map(c=>`<option value="${esc(c.id)}">${esc(c.name)}</option>`).join('');select.value=value;
      render();if(data.running)schedule();
    }catch(error){if(live()&&version===readVersion){feedback.hidden=false;feedback.textContent=error.httpStatus===404?'Розділ підготовлено. Він стане доступним після безпечного перезапуску студії, коли поточні роботи завершаться.':error.message;if(error.httpStatus===404)button.disabled=true;else schedule(Math.min(15000,2000*2**readFailures++));}}
  }
  select.onchange=render;
  grid.onclick=event=>{
    const button=event.target.closest('[data-use-idea]');if(!button||!live())return;
    const video=data?.videos.find(video=>video.id===button.dataset.useIdea);
    if(video)openTrendingIdea(video,select.value,()=>{used.add(video.id);render();});
  };
  button.onclick=async()=>{
    if(refreshing||data?.running)return;
    refreshing=true;readVersion++;clearTimeout(timer);setRunning(true);feedback.hidden=false;feedback.textContent='Оновлюємо добірку…';let refreshNote='';
    try{const result=await api('/api/trending-videos/refresh','POST',{});if(!live())return;await load();if(result.running)schedule();else if(result.retry_after)refreshNote=`Спробуйте за ${result.retry_after} с`;}
    catch(error){refreshNote=error.message;}
    finally{refreshing=false;if(live()){if(data)render();else setRunning(false);if(refreshNote){feedback.hidden=false;feedback.textContent=refreshNote;}}}
  };
  load();
}
document.getElementById('trending-videos').addEventListener('click',()=>openTrendingVideos());


function openTrendingIdea(video, preferredChannel='', onUsed=()=>{}){
  const channels=state.channels||[];
  const selected=channels.find(c=>c.id===preferredChannel)||channels.find(c=>video.for_channels.some(own=>own.id===c.id))||channels[0];
  const navigation=state.navigation,requestId=crypto.randomUUID();
  let generation,root,submit,titleTranslator,ready=false,sending=false,translating=false,wordsEdited=false,channelRead=0;
  const live=()=>root?.isConnected&&state.modalGeneration===generation&&state.navigation===navigation&&!$('modal-backdrop').hidden;
  const valid=()=>ready&&!sending&&!translating&&!!root?.querySelector('[name="channel"]').value&&!!root?.querySelector('[name="title"]').value.trim();
  modal('Використати ідею',`<div class="trend-idea-form"><label>Канал<select name="channel" aria-label="Канал для ідеї">${channels.map(c=>`<option value="${esc(c.id)}" ${c.id===selected?.id?'selected':''}>${esc(c.name)}</option>`).join('')}</select></label><label>Заголовок<input name="title" aria-label="Заголовок випуску" type="text" maxlength="100" value="${esc(video.title)}"></label>${video.title_uk?`<p class="trend-title-uk">${esc(video.title_uk)}</p>`:''}<img class="trend-idea-preview" src="https://i.ytimg.com/vi/${video.id}/hqdefault.jpg" alt="Прев’ю конкурента"><label class="trend-idea-check"><input name="use_thumbnail" type="checkbox" checked><span>Використовувати прев’ю конкурента</span></label><label class="trend-idea-check" data-hero-choice><input name="use_hero" type="checkbox" ${selected?.hero_reference?'checked':'disabled'}><span>Використати ведучого каналу на прев’ю</span></label><label class="episode-word-count">Обсяг сценарію <input name="words" aria-label="Обсяг сценарію" type="number" min="200" max="15000" step="1" value="2000"> слів</label><p class="trend-idea-feedback muted" role="status" hidden></p></div>`,[{
    label:'Створити зачини',primary:true,enabled:valid,run:async()=>{
      if(!live()||!valid())return;
      const cid=root.querySelector('[name="channel"]').value,title=root.querySelector('[name="title"]').value.trim();
      const count=Number(root.querySelector('[name="words"]').value);
      const note=root.querySelector('.trend-idea-feedback');
      if(!Number.isInteger(count)||count<200||count>15000){note.hidden=false;note.textContent='Вкажіть обсяг від 200 до 15 000 слів';return;}
      if(title.length>100){note.hidden=false;note.textContent='Скоротіть заголовок до 100 символів';return;}
      const useThumbnail=root.querySelector('[name="use_thumbnail"]').checked;
      sending=true;note.hidden=true;root.querySelectorAll('input,select').forEach(field=>field.disabled=true);titleTranslator.refresh();
      try{
        const draft=await api('/api/trending-videos/use','POST',{channel_id:cid,video_id:video.id,title,target_words:count,use_thumbnail:useThumbnail,use_hero:useThumbnail&&root.querySelector('[name="use_hero"]').checked,request_id:requestId});
        onUsed();
        if(!live())return;
        closeModal();
        if(await selectChannel(cid))await selectProject(draft.project_id);
      }catch(error){if(live()){note.hidden=false;note.textContent=error.message;}}
      finally{sending=false;if(live()){root.querySelectorAll('input,select').forEach(field=>field.disabled=false);submit.disabled=!valid();titleTranslator.refresh();syncHero();}}
    }
  }]);
  generation=state.modalGeneration;root=$('modal-body').querySelector('.trend-idea-form');submit=$('modal-actions').querySelector('button');submit.disabled=true;
  root.querySelector('[name="title"]').oninput=()=>{submit.disabled=!valid();};
  titleTranslator=bindTitleTranslation(root.querySelector('[name="title"]'),{channelId:()=>root.querySelector('[name="channel"]').value,live,enabled:()=>!sending,onBusy:value=>{translating=value;if(live())submit.disabled=!valid();}});
  $('modal-body').channelSettingsCleanup=()=>titleTranslator.dispose();
  root.querySelector('[name="words"]').oninput=()=>{wordsEdited=true;};
  const syncHero=()=>{
    const field=root.querySelector('[name="use_hero"]'),hasHero=!!channels.find(channel=>channel.id===root.querySelector('[name="channel"]').value)?.hero_reference;
    field.disabled=sending||!hasHero||!root.querySelector('[name="use_thumbnail"]').checked;
    if(!hasHero)field.checked=false;
    field.closest('label').title=hasHero?'':'Додайте ведучого в налаштуваннях каналу';
  };
  root.querySelector('[name="use_thumbnail"]').onchange=syncHero;
  syncHero();
  async function recommendation(){
    const version=++channelRead,cid=root.querySelector('[name="channel"]').value;
    if(!cid)return;
    try{
      const data=await api(`/api/channels/${encodeURIComponent(cid)}/episode-ideas?view=topics`);
      if(live()&&version===channelRead&&!sending&&!wordsEdited&&Number.isInteger(data.target_words))root.querySelector('[name="words"]').value=data.target_words;
    }catch(error){/* The editable default remains available when a recommendation cannot be read. */}
  }
  root.querySelector('[name="channel"]').onchange=()=>{submit.disabled=!valid();titleTranslator.refresh();const field=root.querySelector('[name="use_hero"]');field.checked=!!channels.find(channel=>channel.id===root.querySelector('[name="channel"]').value)?.hero_reference;syncHero();recommendation();};
  api('/api/health').then(health=>{
    if(!live())return;ready=health.trending_use_idea===true;submit.disabled=!valid();
    if(!ready){const note=root.querySelector('.trend-idea-feedback');note.hidden=false;note.textContent='Оновлення стане доступним після безпечного перезапуску студії';}
  }).catch(error=>{if(live()){const note=root.querySelector('.trend-idea-feedback');note.hidden=false;note.textContent=error.message;}});
  recommendation();
}
