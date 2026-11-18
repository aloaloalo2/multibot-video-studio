/* Shared competitor ideas; late reads stay scoped to the current page. */
const trendDays = new Intl.NumberFormat('uk-UA', {style:'unit', unit:'day', unitDisplay:'long'});
function trendingCard(video, icons={}, sort='x'){
  const number=value=>new Intl.NumberFormat('uk-UA',{notation:'compact',maximumFractionDigits:1}).format(value);
  if(!/^[A-Za-z0-9_-]{11}$/.test(video.id))return '';
  const days=Math.max(0,Math.floor((Date.now()-Date.parse(video.published_at))/86400000));
  const period=days===0?'сьогодні':Number.isFinite(days)?`за ${trendDays.format(days)}`:'';
  const icon=icons?.[video.competitor_id];
  const code=typeof video.title_language==='string'?video.title_language.toLowerCase():'';
  const language=/^[a-z]{2,3}$/.test(code)&&!['uk','ru'].includes(code)?`<span class="trend-language" title="Мова заголовка: ${code.toUpperCase()}">${code.toUpperCase()}</span> `:'';

  const avatar=typeof icon==='string'&&(/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(icon)||/^\/api\/trending-videos\/icon\/[A-Za-z0-9_-]+\?v=[0-9a-f]{12}$/.test(icon))?`<img class="trend-channel-avatar" src="${icon}" alt="" width="20" height="20" loading="lazy">`:'';
  const subscribers=video.subscribers==null?'':`<span class="trend-subscribers" title="Підписники" aria-label="${esc(number(video.subscribers))} підписників"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m20 0v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/><circle cx="9" cy="7" r="4"/></svg><span>${number(video.subscribers)}</span></span>`;
  return `<article class="project-card has-cover cover-ready trend-card"><img class="project-cover" src="https://i.ytimg.com/vi/${video.id}/hqdefault.jpg" loading="lazy" alt=""><button type="button" class="project-open trend-open" data-use-idea="${video.id}" aria-label="Використати ідею ${esc(video.title)}"><div class="project-title-spacer" aria-hidden="true"></div><div class="project-meta"><strong class="trend-views" title="Перегляди"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg><span>${number(video.views)}</span>${period?`<small class="trend-date">${period}</small>`:''}</strong>${sort==='hourly'||video.score==null?`<span class="trend-score" title="Перегляди за годину: ${esc(number(video.views))} поділити на години від публікації${video.score==null?'':` · ${esc(video.score)}× до медіани каналу`}">${esc(number(video.hourly??0))}/год</span>`:`<span class="trend-score" title="Перегляди на день відносно медіани інших недавніх відео цього каналу схожої тривалості · ${esc(number(video.hourly??0))} за годину">↑ ${esc(video.score)}×</span>`}<span class="project-duration">${Math.floor(video.duration/60)}:${String(video.duration%60).padStart(2,'0')}</span></div></button><div class="project-actions"><button type="button" class="project-action trend-dismiss" data-dismiss-video="${video.id}" title="Більше не пропонувати" aria-label="Більше не пропонувати «${esc(video.title)}»"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18M8 6V4h8v2m-9 0 1 14h8l1-14M10 10v6m4-6v6"/></svg></button></div><h2><a class="trend-youtube" href="https://www.youtube.com/watch?v=${video.id}" target="_blank" rel="noopener noreferrer" title="Відкрити відео на YouTube" aria-label="Відкрити «${esc(video.title)}» на YouTube"><svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M23 7.2a3 3 0 0 0-2.1-2.1C19 4.6 12 4.6 12 4.6s-7 0-8.9.5A3 3 0 0 0 1 7.2 31 31 0 0 0 .5 12 31 31 0 0 0 1 16.8a3 3 0 0 0 2.1 2.1c1.9.5 8.9.5 8.9.5s7 0 8.9-.5a3 3 0 0 0 2.1-2.1 31 31 0 0 0 .5-4.8 31 31 0 0 0-.5-4.8ZM9.7 15V9l5.8 3-5.8 3Z"/></svg></a><a class="project-title-rename trend-title-link" href="https://www.youtube.com/watch?v=${video.id}" target="_blank" rel="noopener noreferrer" title="Відкрити на YouTube: ${esc(video.title)}">${language}${esc(video.title)}</a></h2><div class="trend-details">${video.title_uk?`<p class="trend-title-uk" lang="uk" title="${esc(video.title_uk)}">${esc(video.title_uk)}</p>`:''}<div class="trend-channel-row"><a class="trend-channel" href="https://www.youtube.com/channel/${encodeURIComponent(video.competitor_id)}" target="_blank" rel="noopener noreferrer">${avatar}<span>${esc(video.competitor_name)}</span></a>${subscribers}</div><div class="trend-source-row"><span>${video.for_channels.map(c=>esc(c.name)).join(' · ')}</span></div></div></article>`;
}
function openTrendingVideos({updateUrl=true}={}){
  cancelLocationRestore();++state.navigation;stopPlayback();
  if(state.poll){clearTimeout(state.poll);state.poll=null;}
  if(state.exportWatch){clearInterval(state.exportWatch);state.exportWatch=null;}
  if(state.channel)state.trendingPreviousChannel=state.channel.id;
  state.channel=null;state.project=null;state.projects=[];state.assets=[];state.pixabay=[];state.selected=null;state.selectedTransition=null;state.selectedTrack=null;state.view='trending';
  closeModal();renderChannels();renderProject();status('');if(updateUrl)syncRoute();
  const root=$('trending-page');
  root.innerHTML='<div class="overview-top trend-top"><div class="overview-heading trend-heading"><h1 id="trending-title">Зараз у тренді</h1><button type="button" class="history-button outline channel-settings-button trend-refresh" title="Оновити" aria-label="Оновити"><svg class="project-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M3 4v6h6M4 9a8 8 0 1 1-1 7"/></svg></button></div><div class="overview-actions"><div class="trend-sort" role="group" aria-label="Сортування"><button type="button" data-trend-sort="x" title="Найвищий X: перегляди на день відносно звичайних відео цього каналу">X</button><button type="button" data-trend-sort="hourly" title="Найбільше переглядів за годину: перегляди поділені на години від публікації">За годину</button></div><select class="trend-filter" aria-label="Ідеї для каналу"><option value="">Усі наші канали</option></select></div></div><section class="trending-view"><p class="trend-feedback" role="status">Завантажуємо…</p><div class="overview-projects trend-grid"></div></section>';
  const navigation=state.navigation;
  const live=()=>root.isConnected&&state.navigation===navigation&&state.view==='trending'&&!root.hidden;
  const select=root.querySelector('select'),button=root.querySelector('.trend-refresh'),feedback=root.querySelector('.trend-feedback'),grid=root.querySelector('.trend-grid');
  const sortBox=root.querySelector('.trend-sort');   // taken before the heading moves to the toolbar above
  $('trending-toolbar').replaceChildren(root.querySelector('.trend-top'));
  let data=null,timer=null,readVersion=0,readFailures=0,refreshing=false,cardMarkup='';const used=new Set();
  // the sort the author picked last stays for the next visit (user, 16 November 2026: «перемикач… по іксу… за годину»)
  let sort='x';try{if(localStorage.getItem('trend-sort')==='hourly')sort='hourly';}catch{}
  const paintSort=()=>sortBox?.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.trendSort===sort)));
  if(sortBox)sortBox.onclick=event=>{const pick=event.target.closest('[data-trend-sort]');if(!pick||pick.dataset.trendSort===sort)return;sort=pick.dataset.trendSort;try{localStorage.setItem('trend-sort',sort);}catch{}paintSort();render();};
  paintSort();
  const ordered=list=>sort==='hourly'?[...list].sort((a,b)=>(b.hourly??0)-(a.hourly??0)):list;   // the server sends the X order
  const readAt=()=>{if(data?.retry_after>0)readyAt=Math.max(readyAt,Date.now()+data.retry_after*1000);};
  const schedule=(delay=2000)=>{clearTimeout(timer);if(live())timer=setTimeout(load,delay);};
  let readyAt=0,coolTimer=null;   // the button stays grey while a refresh runs, for the minute after one, and on the key's daily limit
  const clock=t=>new Date(t*1000).toLocaleString('uk-UA',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});
  function setRunning(running){
    const now=Date.now()/1000,limited=!!data?.limit_until&&data.limit_until>now,cooling=readyAt>Date.now();
    button.disabled=running||limited||cooling;button.classList.toggle('is-loading',running);button.setAttribute('aria-busy',String(running));
    const last=data?.last_refresh?`Оновлено ${clock(data.last_refresh)}.`:'';
    const why=running?'Оновлюємо добірку…':limited?`${data.limit_note||'Ліміт YouTube'}. Можна знову після ${clock(data.limit_until)}.`:cooling?`Можна оновити за ${Math.ceil((readyAt-Date.now())/1000)} с.`:'Оновити зараз.';
    button.title=[why,last].filter(Boolean).join(' ');button.setAttribute('aria-label',button.title);
    clearTimeout(coolTimer);
    if(!running&&live()&&(cooling||limited))coolTimer=setTimeout(()=>{if(live())setRunning(refreshing||!!data?.running);},Math.min(60000,Math.max(1000,cooling?readyAt-Date.now()+50:(data.limit_until-now)*1000)));
  }
  function render(){
    if(!live()||!data)return;
    const filtered=data.videos.filter(v=>!used.has(v.id)&&(!select.value||v.for_channels.some(c=>c.id===select.value)));
    const markup=ordered(filtered).map(video=>trendingCard(video,data.competitor_icons,sort)).join('');
    if(markup!==cardMarkup){cardMarkup=markup;grid.innerHTML=markup;}
    const running=refreshing||data.running;
    setRunning(running);
    feedback.textContent=running?'Оновлюємо добірку…':!data.competitors?'Додайте конкурентів у налаштуваннях каналу.':!data.checked&&data.errors?.length?'Не вдалося оновити добірку. Спробуйте ще раз.':!data.checked?'Натисніть ↻, щоб отримати добірку.':!filtered.length?'Нових відео за три тижні поки немає.':'';
    feedback.hidden=!feedback.textContent;
  }
  async function load(){
    if(!live())return;
    clearTimeout(timer);const version=++readVersion;
    try{
      const result=await api('/api/trending-videos');if(!live()||version!==readVersion)return;data=result;readFailures=0;readAt();
      const value=select.value;
      select.innerHTML='<option value="">Усі наші канали</option>'+data.channels.map(c=>`<option value="${esc(c.id)}">${esc(c.name)}</option>`).join('');select.value=value;
      render();if(data.running)schedule();
    }catch(error){if(live()&&version===readVersion){feedback.hidden=false;feedback.textContent=error.httpStatus===404?'Розділ підготовлено. Він стане доступним після безпечного перезапуску студії, коли поточні роботи завершаться.':error.message;if(error.httpStatus===404)button.disabled=true;else schedule(Math.min(15000,2000*2**readFailures++));}}
  }
  select.onchange=render;
  grid.onclick=event=>{
    const trash=event.target.closest('[data-dismiss-video]');
    if(trash&&live()){
      // the author does not want this one: it leaves the suggestions for good (POST /api/trending-videos/dismiss)
      const id=trash.dataset.dismissVideo,video=data?.videos.find(v=>v.id===id);trash.disabled=true;
      api('/api/trending-videos/dismiss','POST',{video_id:id,title:video?.title||''}).then(()=>{used.add(id);render();})
        .catch(error=>{trash.disabled=false;feedback.hidden=false;feedback.textContent=error.message;});
      return;
    }
    const button=event.target.closest('[data-use-idea]');if(!button||!live())return;
    const video=data?.videos.find(video=>video.id===button.dataset.useIdea);
    if(video)openTrendingIdea(video,select.value,()=>{used.add(video.id);render();});
  };
  button.onclick=async()=>{
    if(refreshing||data?.running)return;
    refreshing=true;readVersion++;clearTimeout(timer);setRunning(true);feedback.hidden=false;feedback.textContent='Оновлюємо добірку…';let refreshNote='';
    try{const result=await api('/api/trending-videos/refresh','POST',{});if(!live())return;await load();if(result.running)schedule();else if(result.limit_until){data={...data,...result};}else if(result.retry_after){readyAt=Date.now()+result.retry_after*1000;}}
    catch(error){refreshNote=error.message;}
    finally{refreshing=false;if(live()){if(data)render();else setRunning(false);if(refreshNote){feedback.hidden=false;feedback.textContent=refreshNote;}}}
  };
  load();
}
document.getElementById('trending-videos').addEventListener('click',()=>openTrendingVideos());


function openTrendingIdea(video, preferredChannel='', onUsed=()=>{}){
  const channels=state.channels||[];
  // the channel comes first and alone; the rest of the form opens once it is chosen (user, 18 November 2026: «в першу
  // чергу мені потрібно вибрати канал… лише канал. Потім… вже далі йде основне»)
  const selected=channels.find(c=>c.id===preferredChannel)||null;
  const navigation=state.navigation,requestId=crypto.randomUUID();
  let generation,root,submit,titleTranslator,ready=false,sending=false,translating=false,wordsEdited=false,channelRead=0;
  const live=()=>root?.isConnected&&state.modalGeneration===generation&&state.navigation===navigation&&!$('modal-backdrop').hidden;
  const valid=()=>ready&&!sending&&!translating&&!!root?.querySelector('[name="channel"]').value&&!!root?.querySelector('[name="title"]').value.trim();
  modal('Використати ідею',`<div class="trend-idea-form"><label>Канал<select name="channel" aria-label="Канал для ідеї">${selected?'':'<option value="" selected disabled>Оберіть канал</option>'}${channels.map(c=>`<option value="${esc(c.id)}" ${c.id===selected?.id?'selected':''}>${esc(c.name)}</option>`).join('')}</select></label><div class="trend-idea-rest" ${selected?'':'hidden'}><label>Заголовок<input name="title" aria-label="Заголовок випуску" type="text" maxlength="100" value="${esc(video.title)}"></label>${video.title_uk?`<p class="trend-title-uk">${esc(video.title_uk)}</p>`:''}<img class="trend-idea-preview" src="https://i.ytimg.com/vi/${video.id}/hqdefault.jpg" alt="Прев’ю конкурента"><label class="trend-idea-check"><input name="use_thumbnail" type="checkbox" checked><span>Використовувати прев’ю конкурента</span></label><label class="trend-idea-check" data-hero-choice><input name="use_hero" type="checkbox" ${selected?.hero_reference?'checked':'disabled'}><span>Використати ведучого каналу на прев’ю</span></label><label class="trend-idea-check" data-wishes-choice hidden><input name="use_wishes" type="checkbox"><span>Адаптувати під мій стиль</span></label><label class="episode-word-count">Обсяг сценарію <input name="words" aria-label="Обсяг сценарію" type="number" min="200" max="15000" step="1" value="2000"> слів</label></div><p class="trend-idea-feedback muted" role="status" hidden></p></div>`,[{
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
        await api('/api/trending-videos/use','POST',{channel_id:cid,video_id:video.id,title,target_words:count,use_thumbnail:useThumbnail,use_hero:useThumbnail&&root.querySelector('[name="use_hero"]').checked,use_channel_wishes:useThumbnail&&!root.querySelector('[data-wishes-choice]').hidden&&root.querySelector('[name="use_wishes"]').checked,request_id:requestId});
        onUsed();
        if(!live())return;
        closeModal();
        await selectChannel(cid);   // the channel's page, where the new card shows «Opus готує зачини» (user, 16 November 2026)
      }catch(error){if(live()){note.hidden=false;note.textContent=error.message;}}
      finally{sending=false;if(live()){root.querySelectorAll('input,select').forEach(field=>field.disabled=false);submit.disabled=!valid();titleTranslator.refresh();syncHero();}}
    }
  }]);
  generation=state.modalGeneration;root=$('modal-body').querySelector('.trend-idea-form');
  StudioUI.picker(root.querySelector('[name="channel"]'),{picture:id=>channelIdentityIcon(channels.find(c=>c.id===id))});   // channel logos in the list
  submit=$('modal-actions').querySelector('button');submit.disabled=true;
  root.querySelector('[name="title"]').oninput=()=>{submit.disabled=!valid();};
  titleTranslator=bindTitleTranslation(root.querySelector('[name="title"]'),{channelId:()=>root.querySelector('[name="channel"]').value,live,enabled:()=>!sending,onBusy:value=>{translating=value;if(live())submit.disabled=!valid();}});
  $('modal-body').channelSettingsCleanup=()=>titleTranslator.dispose();
  root.querySelector('[name="words"]').oninput=()=>{wordsEdited=true;};
  const syncHero=()=>{
    const field=root.querySelector('[name="use_hero"]'),hasHero=!!channels.find(channel=>channel.id===root.querySelector('[name="channel"]').value)?.hero_reference;
    field.disabled=sending||!hasHero||!root.querySelector('[name="use_thumbnail"]').checked;
    field.closest('label').hidden=!hasHero;   // a channel without a host shows no host choice at all
    if(!hasHero)field.checked=false;
    field.closest('label').title=hasHero?'':'Додайте ведучого в налаштуваннях каналу';
    // «Адаптувати під мій стиль»: the competitor's idea drawn in our channel's look (our recent thumbnails and wishes)
    const wishes=root.querySelector('[name="use_wishes"]');
    wishes.closest('label').hidden=!root.querySelector('[name="use_thumbnail"]').checked;
    wishes.closest('label').title='Ідея з прев’ю конкурента, а стиль з наших прев’ю й побажань каналу';
    wishes.disabled=sending;
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
  root.querySelector('[name="channel"]').onchange=()=>{root.querySelector('.trend-idea-rest').hidden=!root.querySelector('[name="channel"]').value;submit.disabled=!valid();titleTranslator.refresh();const field=root.querySelector('[name="use_hero"]');field.checked=!!channels.find(channel=>channel.id===root.querySelector('[name="channel"]').value)?.hero_reference;syncHero();recommendation();};
  api('/api/health').then(health=>{
    if(!live())return;ready=health.trending_use_idea===true;submit.disabled=!valid();
    if(!ready){const note=root.querySelector('.trend-idea-feedback');note.hidden=false;note.textContent='Оновлення стане доступним після безпечного перезапуску студії';}
  }).catch(error=>{if(live()){const note=root.querySelector('.trend-idea-feedback');note.hidden=false;note.textContent=error.message;}});
  recommendation();
}
