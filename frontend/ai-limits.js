// Five-hour account usage, with dated local receipts when the account is unavailable.
(function(){
  const button=document.getElementById('ai-limits');
  if(!button)return;
  const names={claude:'Claude Code',codex:'Codex'};
  let data=null,panel=null,timer=0,pending=false;
  // «через 40 хв», «через 2 год 5 хв»: how long until the window renews, counted from now
  const until=t=>{const m=Math.max(1,Math.ceil((t-Date.now()/1000)/60)),h=Math.floor(m/60);return h?`через ${h} год${m%60?` ${m%60} хв`:''}`:`через ${m} хв`;};
  const tone=left=>left<=10?'low':left<=30?'mid':'ok';

  function ring(kind,item){
    const el=button.querySelector(`.ring-${kind}`);
    const left=item&&item.known?item.left:0;
    el.style.strokeDasharray=`${left} 100`;
    el.dataset.tone=item&&item.known?tone(left):'none';
  }
  function line(kind,item){
    if(!item||!item.known)return `<div class="ai-limit-row"><span class="ai-limit-name ${kind}">${names[kind]}</span><span class="ai-limit-note">${item?.reset?'Час оновлення минув. Уточнюємо залишок.':"Актуальних даних поки немає."}</span></div>`;
    const age=Math.max(0,Math.floor((Date.now()/1000-(item.seen_at||0))/60));
    const fresh=item.stale?`Останні дані: ${age} хв тому · `:'';
    const when=fresh+(item.reset?'Очікуємо актуальні дані':`Оновиться ${until(item.resets_at)}`);
    return `<div class="ai-limit-row"><span class="ai-limit-name ${kind}">${names[kind]}</span><b class="ai-limit-left" data-tone="${tone(item.left)}"><small>лишилось</small> ${item.left}%</b>
      <div class="ai-limit-bar"><i class="${kind}" style="width:${item.left}%"></i></div>
      <span class="ai-limit-note">${when}</span></div>`;
  }
  function draw(){
    if(!data)return;
    ring('claude',data.claude);ring('codex',data.codex);
    const text=k=>data[k]&&data[k].known?`${names[k]} ${data[k].left}%`:`${names[k]} немає даних`;
    const label=`Залишок 5-годинного ліміту: ${text('claude')}, ${text('codex')}`;
    button.title=label;button.setAttribute('aria-label',label);
    if(panel)panel.innerHTML=`<h4>Залишок на 5 годин</h4>${line('claude',data.claude)}${line('codex',data.codex)}`;
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
    if(!data)panel.innerHTML='<h4>Залишок на 5 годин</h4><p class="ai-limit-note">Рахуємо…</p>';
    document.addEventListener('pointerdown',outside,true);document.addEventListener('keydown',escape);
    load();
  });
  window.addEventListener('focus',()=>load());
  window.addEventListener('resize',()=>{if(panel)place();});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)load();});
  load();
})();
