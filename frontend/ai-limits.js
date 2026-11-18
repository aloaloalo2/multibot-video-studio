// Five-hour account usage, with dated local receipts when the account is unavailable.
(function(){
  const button=document.getElementById('ai-limits');
  if(!button)return;
  const names={claude:'Claude Code',codex:'Codex'};
  let data=null,panel=null,timer=0,pending=false;
  // «через 40 хв», «через 2 год 5 хв»: how long until the window renews, counted from now
  // «через 40 хв», «через 2 год 5 хв», «через 3 дн 4 год» (a weekly window)
  const until=t=>{const m=Math.max(1,Math.ceil((t-Date.now()/1000)/60)),h=Math.floor(m/60),d=Math.floor(h/24);
    return d?`через ${d} дн${h%24?` ${h%24} год`:''}`:h?`через ${h} год${m%60?` ${m%60} хв`:''}`:`через ${m} хв`;};
  // Claude may have only a weekly window now (user, 15 November 2026); Codex has its 5-hour one
  const span=item=>item&&item.window==='seven_day'?'на тиждень':'на 5 годин';
  const tone=left=>left<=10?'low':left<=30?'mid':'ok';

  // the grey track is the week (user, 16 November 2026: «недільний ліміт… сірий фон… скільки відсотків залишилось»):
  // Codex's colour is its 5 hours and the grey under it what is left of its week; a limit that is itself weekly
  // (Claude) has no grey track at all
  const weekly=item=>item&&item.window==='seven_day';
  const week=item=>item&&item.known&&!weekly(item)&&Number.isFinite(item.week_left)?item.week_left:null;
  // the week comes first (user, 18 November 2026: «нехай в першу чергу недільний показується»; Codex read «full» on its
  // 5 hours while its week was at 0 and it drew nothing): a limit with a weekly window shows the week as its colour and
  // number, its 5 hours as the grey track and the second line
  const main=item=>{const w=week(item);return w===null?item:{...item,left:w,resets_at:item.week_resets_at,window:'seven_day',
    five_left:item.left,five_resets_at:item.resets_at};};
  const five=item=>item&&Number.isFinite(item.five_left)?item.five_left:null;
  // every arc hangs centred on the bottom of its ring and shrinks towards it (user, 16 November 2026: «дуга, щоб була
  // знизу… все по центру донизу»); the ring starts at the top, so the bottom is half way along it
  function arc(circle,share){
    const part=Math.max(0,Math.min(100,share));
    circle.style.strokeDasharray=`${part} ${100-part}`;
    circle.style.strokeDashoffset=`${part/2-50}`;
  }
  function ring(kind,item){
    item=main(item);
    const el=button.querySelector(`.ring-${kind}`),bg=button.querySelector(`.ring-bg-${kind}`);
    const left=item&&item.known?item.left:0;
    arc(el,left);
    el.dataset.tone=item&&item.known?tone(left):'none';
    const rest=five(item);
    arc(bg,rest===null?(weekly(item)?0:100):rest);
  }
  function line(kind,item){
    item=item&&item.known?main(item):item;
    if(!item||!item.known)return `<div class="ai-limit-row"><span class="ai-limit-name ${kind}">${names[kind]}</span><span class="ai-limit-note">${item?.login_expired?(kind==='claude'?'Оновлюємо вхід Claude Code, залишок з’явиться за хвилину.':'Codex давно не запускався, тому його вхід ще не оновлений. Залишок з’явиться з першою роботою Codex.'):item?.reset?'Час оновлення минув. Уточнюємо залишок.':"Актуальних даних поки немає."}</span></div>`;
    const age=Math.max(0,Math.floor((Date.now()/1000-(item.seen_at||0))/60));
    const fresh=item.stale?`Останні дані: ${age} хв тому · `:'';
    const when=fresh+(item.reset?'Очікуємо актуальні дані':`Оновиться ${until(item.resets_at)}`);
    return `<div class="ai-limit-row"><span class="ai-limit-name ${kind}">${names[kind]} <small>${span(item)}</small></span><b class="ai-limit-left" data-tone="${tone(item.left)}"><small>лишилось</small> ${item.left}%</b>
      <div class="ai-limit-bar${five(item)===null?' bare':''}">${five(item)!==null?`<u style="width:${five(item)}%"></u>`:''}<i class="${kind}" style="width:${item.left}%"></i></div>
      <span class="ai-limit-note">${when}${five(item)!==null?` · на 5 годин лишилось ${five(item)}%, оновиться ${until(item.five_resets_at)}`:''}</span></div>`;
  }
  function draw(){
    if(!data)return;
    ring('claude',data.claude);ring('codex',data.codex);
    const text=k=>data[k]&&data[k].known?`${names[k]} ${main(data[k]).left}% ${span(main(data[k]))}`:`${names[k]} немає даних`;
    const label=`Залишок лімітів: ${text('claude')}, ${text('codex')}`;
    button.title=label;button.setAttribute('aria-label',label);
    if(panel)panel.innerHTML=`<h4>Залишок лімітів</h4>${line('claude',data.claude)}${line('codex',data.codex)}`;
  }
  async function load(){
    if(pending)return;pending=true;
    try{data=await api('/api/limits');draw();}catch{if(data)for(const item of Object.values(data))if(item&&typeof item==='object')item.stale=true;draw();}finally{pending=false;}
    clearTimeout(timer);timer=setTimeout(load,document.hidden?60000:15000);
  }
  function place(){
    const box=button.getBoundingClientRect();
    panel.style.left=`${Math.max(8,box.left)}px`;
    panel.style.bottom=`${Math.max(8,window.innerHeight-box.top+8)}px`;
  }
  function close(){if(!panel)return;panel.remove();panel=null;button.classList.remove('active');document.removeEventListener('pointerdown',outside,true);document.removeEventListener('keydown',escape);}
  function outside(event){if(panel&&!panel.contains(event.target)&&!button.contains(event.target))close();}
  function escape(event){if(event.key==='Escape')close();}
  button.addEventListener('click',()=>{
    if(panel){close();return;}
    panel=document.createElement('div');panel.className='ai-limits-panel';panel.setAttribute('role','dialog');panel.setAttribute('aria-label','Ліміти Claude і Codex');
    document.body.appendChild(panel);button.classList.add('active');draw();place();
    if(!data)panel.innerHTML='<h4>Залишок лімітів</h4><p class="ai-limit-note">Рахуємо…</p>';
    document.addEventListener('pointerdown',outside,true);document.addEventListener('keydown',escape);
    load();
  });
  window.addEventListener('focus',()=>load());
  window.addEventListener('resize',()=>{if(panel)place();});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)load();});
  load();
})();
