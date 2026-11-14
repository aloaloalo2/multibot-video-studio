// ai-limits.js — the round button beside «Налаштування»: two rings show how much of the 5-hour limit Claude Code
// (outer) and Codex (inner) have left; a click opens the numbers and the reset times (backend/ai_limits.py, read from
// the tools' own local logs, so a look costs no limit).
(function(){
  const button=document.getElementById('ai-limits');
  if(!button)return;
  const names={claude:'Claude Code',codex:'Codex'};
  let data=null,panel=null,timer=0;
  const clock=t=>new Date(t*1000).toLocaleTimeString('uk-UA',{hour:'2-digit',minute:'2-digit'});
  const ago=t=>{const m=Math.max(0,Math.round((Date.now()/1000-t)/60));return m<1?'щойно':m<60?`${m} хв тому`:`${Math.floor(m/60)} год ${m%60} хв тому`;};
  const tone=left=>left<=10?'low':left<=30?'mid':'ok';

  function ring(kind,item){
    const el=button.querySelector(`.ring-${kind}`);
    const left=item&&item.known?item.left:0;
    el.style.strokeDasharray=`${left} 100`;
    el.dataset.tone=item&&item.known?tone(left):'none';
  }
  function line(kind,item){
    if(!item||!item.known)return `<div class="ai-limit-row"><span class="ai-limit-name ${kind}">${names[kind]}</span><span class="ai-limit-note">Немає даних. Вони з'являться після першої роботи ${kind==='claude'?'Claude Code у студії':'Codex'}.</span></div>`;
    const when=item.reset?'Ліміт уже оновився':`Оновиться о ${clock(item.resets_at)}`;
    return `<div class="ai-limit-row"><span class="ai-limit-name ${kind}">${names[kind]}</span><b class="ai-limit-left" data-tone="${tone(item.left)}">${item.left}%</b>
      <div class="ai-limit-bar"><i class="${kind}" style="width:${item.left}%"></i></div>
      <span class="ai-limit-note">${when} · дані ${ago(item.seen_at)}</span></div>`;
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
    try{data=await api('/api/limits');draw();}catch{}
    clearTimeout(timer);timer=setTimeout(load,document.hidden?300000:60000);
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
  window.addEventListener('resize',()=>{if(panel)place();});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)load();});
  load();
})();
