/* One explicit title translator shared by clone and Trends dialogs. */
const titleTranslationIcon='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 5h12M7 2v3m-3 3 6 8m1-11c0 5-3 9-8 12m10 4 5-11 5 11m-8-4h6"/></svg>';
function titleTranslationOptions(){
  return api('/api/title-translation').then(data=>data.languages);
}
function bindTitleTranslation(input,{channelId,live,available=()=>true,enabled=()=>true,context=()=>'',onBusy=()=>{}}){
  const wrap=document.createElement('div');wrap.className='title-translation-field';input.before(wrap);wrap.append(input);
  const button=document.createElement('button');button.type='button';button.className='title-translate icon-button';button.innerHTML=titleTranslationIcon;
  button.title=button.ariaLabel='Перекласти заголовок';button.setAttribute('aria-haspopup','menu');button.setAttribute('aria-expanded','false');wrap.append(button);
  const note=document.createElement('small');note.className='title-translation-note';note.setAttribute('role','status');note.hidden=true;wrap.append(note);
  let menu=null,serial=0,busy=false,disposed=false,applying=false,loading=false,lastContext='',lastResult=null;
  const usable=()=>!disposed&&input.isConnected&&live()&&available()&&!input.hidden;
  function setBusy(value){busy=value;button.setAttribute('aria-busy',String(value));button.classList.toggle('is-translating',value);onBusy(value);}
  function closeMenu(focus=false){
    menu?.remove();menu=null;button.setAttribute('aria-expanded','false');
    document.removeEventListener('pointerdown',outside,true);document.removeEventListener('keydown',keys,true);window.removeEventListener('resize',position);document.removeEventListener('scroll',position,true);
    if(focus&&usable())button.focus();
  }
  function outside(event){if(menu&&!menu.contains(event.target)&&!button.contains(event.target))closeMenu();}
  function keys(event){
    if(event.key==='Escape'){event.preventDefault();event.stopPropagation();closeMenu(true);return;}
    if(!['ArrowDown','ArrowUp','Home','End'].includes(event.key)||!menu)return;
    event.preventDefault();event.stopPropagation();
    const choices=[...menu.querySelectorAll('button')],index=choices.indexOf(document.activeElement);
    const next=event.key==='Home'?0:event.key==='End'?choices.length-1:(index+(event.key==='ArrowUp'?-1:1)+choices.length)%choices.length;
    choices[next]?.focus();
  }
  function position(){
    if(!menu)return;
    const box=button.getBoundingClientRect(),width=Math.min(300,window.innerWidth-24),below=window.innerHeight-box.bottom-20;
    menu.style.width=width+'px';menu.style.left=Math.max(12,Math.min(box.right-width,window.innerWidth-width-12))+'px';
    menu.style.maxHeight=Math.max(100,Math.min(280,below>=160?below:box.top-20))+'px';
    menu.style.top=(below>=160?box.bottom+6:Math.max(12,box.top-menu.getBoundingClientRect().height-6))+'px';
  }
  function refresh(){
    const current=channelId()+'\0'+context();
    if(current!==lastContext||!usable()){serial++;lastContext=current;note.hidden=true;if(busy)setBusy(false);closeMenu();}
    wrap.hidden=input.hidden;button.hidden=!usable();button.disabled=busy||loading||input.disabled||input.readOnly||!enabled()||!input.value.trim();
  }
  function changed(){if(applying)return;serial++;lastResult=null;note.hidden=true;if(busy)setBusy(false);refresh();}
  async function translate(language){
    closeMenu();if(!usable()||busy||!enabled()||input.disabled)return;
    const source=input.value.trim(),cid=channelId(),stamp=context();
    if(!source||lastResult?.title===source&&lastResult.language===language)return;
    const version=++serial;note.hidden=true;setBusy(true);refresh();
    try{
      const result=await api('/api/title-translation','POST',{channel_id:cid,title:source,language});
      if(!usable()||version!==serial||input.value.trim()!==source||channelId()!==cid||context()!==stamp)return;
      if(typeof result.title!=='string'||!result.title.trim())throw new Error('Перекладач не повернув заголовок');
      applying=true;input.value=result.title;input.dispatchEvent(new Event('input',{bubbles:true}));applying=false;
      lastResult={title:result.title,language};try{localStorage.setItem('title-translation-language',language);}catch{}
    }catch(error){if(usable()&&version===serial){note.hidden=false;note.textContent=error.httpStatus===404?'Переклад стане доступним після оновлення студії.':error.message;}}
    finally{applying=false;if(version===serial){setBusy(false);refresh();}}
  }
  async function open(){
    if(menu){closeMenu();return;}if(button.disabled||!usable())return;
    note.hidden=true;loading=true;refresh();const version=serial;
    try{
      const languages=await titleTranslationOptions();
      if(!usable()||version!==serial)return;
      if(!languages.length){note.hidden=false;note.textContent='Спершу налаштуйте мову голосу свого каналу.';return;}
      menu=document.createElement('div');menu.className='title-language-menu';menu.setAttribute('role','menu');menu.setAttribute('aria-label','Мова заголовка');
      let preferred='';try{preferred=localStorage.getItem('title-translation-language')||'';}catch{}
      for(const language of languages){
        const choice=document.createElement('button');choice.type='button';choice.setAttribute('role','menuitem');choice.dataset.language=language.code;
        choice.textContent=(typeof langFlags!=='undefined'&&langFlags[language.code]?langFlags[language.code]+' ':'')+language.name;
        choice.title='Мова перекладу: '+language.label;choice.onclick=()=>translate(language.code);menu.append(choice);
      }
      document.body.append(menu);button.setAttribute('aria-expanded','true');position();
      document.addEventListener('pointerdown',outside,true);document.addEventListener('keydown',keys,true);window.addEventListener('resize',position);document.addEventListener('scroll',position,true);
      (menu.querySelector(`[data-language="${preferred.replace(/[^a-z]/g,'')}"]`)||menu.querySelector('button'))?.focus();
    }catch(error){if(usable()&&version===serial){note.hidden=false;note.textContent=error.httpStatus===404?'Переклад стане доступним після оновлення студії.':error.message;}}
    finally{loading=false;refresh();}
  }
  button.addEventListener('click',open);input.addEventListener('input',changed);
  const observer=new MutationObserver(refresh);observer.observe(input,{attributes:true,attributeFilter:['hidden','disabled','readonly']});
  refresh();
  return {refresh,get busy(){return busy;},dispose(){disposed=true;serial++;closeMenu();observer.disconnect();button.removeEventListener('click',open);input.removeEventListener('input',changed);if(busy)setBusy(false);}};
}
