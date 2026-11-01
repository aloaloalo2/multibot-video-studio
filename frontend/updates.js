/* Check for a new Studio version without interrupting the current project. */
const updateButton = document.getElementById('studio-update');
// The button wears a download mark (an arrow into a tray); a stopped update shows a warning mark instead.
const updateIcons={download:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11m0 0-4.5-4.5M12 15l4.5-4.5M5 15v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3"/></svg>',
  reload:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 12a8 8 0 1 1-2.34-5.66M20 4v5h-5"/></svg>',
  warning:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4 2.8 19.5h18.4L12 4zM12 10v4.5M12 17.2v.3"/></svg>'};
function setUpdateLabel(text,icon){updateButton.innerHTML=`${updateIcons[icon] || ''}<span>${text}</span>`;}
let updateBoot = null, updateWaiting = false, updatePageOutdated = false, updateTimer = null, updateBlocked = null;

// Why a new version cannot arrive, in plain words, and what to do (backend/updater.py names the files or the branch).
function updateReasonHtml(state){
  const files=(state.files||[]).map(name=>`<li><code>${esc(name)}</code></li>`).join('')+(state.more?`<li>і ще ${state.more}</li>`:'');
  const after='<p>Після цього кнопка «Оновити студію» з’явиться сама.</p>';
  if(state.status==='local_changes')return `<p>На GitHub є нова версія студії. Оновлення зупинилося, бо в папці студії на цьому комп’ютері є змінені або зайві файли, і студія не хоче їх затерти.</p><ul>${files}</ul><p>Попросіть агента переглянути ці файли: потрібне зберегти в Git, зайве прибрати.</p>${after}`;
  if(state.status==='diverged')return `<p>На GitHub є нова версія студії, а на цьому комп’ютері є свої зміни коду, яких на GitHub немає. Студія не змішує їх сама.</p><p>Попросіть агента об’єднати ці зміни з версією на GitHub.</p>${after}`;
  if(state.status==='unsafe_update')return `<p>Нова версія студії замінила б файл, якого немає в Git:</p><ul>${files}</ul><p>Перенесіть цей файл з папки студії в інше місце або попросіть агента розібратися.</p>${after}`;
  if(state.status==='other_branch')return `<p>Папка студії стоїть на гілці «${esc(state.branch||'')}», тому нові версії з main сюди не приходять. Так буває, коли агент перемкнув папку на свою гілку для роботи.</p><p>Коли агент закінчить, попросіть його злити гілку в main і повернути папку на main.</p>${after}`;
  if(state.status==='update_failed')return `<p>На GitHub є нова версія студії, але на цьому комп’ютері вона не запустилася, тому студія лишилась на попередній версії і працює як раніше.</p><p>Найчастіше нової версії бракує якогось пакета. Попросіть агента: «перевір студію командою python3 tools/doctor.py і встанови, чого бракує».</p>${state.error?`<details><summary>Технічна причина</summary><pre>${esc(state.error)}</pre></details>`:''}${after}`;
  return '';
}

function scheduleUpdatePoll(delay){clearTimeout(updateTimer);updateTimer=setTimeout(pollStudioUpdates,delay);}

async function pollStudioUpdates(){
  try{
    const response=await fetch('/api/update',{cache:'no-store'});
    if(!response.ok)throw new Error('Студія недоступна');
    const result=await response.json();
    if(updateBoot && result.boot!==updateBoot){
      if(updateWaiting){location.reload();return;}
      updatePageOutdated=true;
      updateButton.hidden=false;updateButton.disabled=false;setUpdateLabel('Перезавантажити студію','reload');
      return;
    }
    updateBoot=result.boot;
    // the server holds a queued update: the button says so, even on a page opened after the click
    if(!updateWaiting && !updatePageOutdated && (result.queued || updateQueued)){
      if(result.queued)showQueued(true);
      else if(result.restarting){updateWaiting=true;showQueued(false);setUpdateLabel('Студія оновлюється…','reload');updateButton.classList.add('updating');}
      else showQueued(false);
    }
    if(!updateWaiting && !updatePageOutdated && !updateQueued){
      updateBlocked=updateReasonHtml(result)?result:null;
      updateButton.hidden=result.status!=='available'&&!updateBlocked;
      setUpdateLabel(updateBlocked?'Оновлення зупинене':'Оновити студію',updateBlocked?'warning':'download');
      updateButton.classList.toggle('update-blocked',!!updateBlocked);
    }
  }catch{}
  finally{scheduleUpdatePoll(updateWaiting?2000:updateQueued?5000:30000);}
}
// A short note by the button, never the red banner over the page (user, 1 November 2026: «збоку легенько»).
let updateNoteTimer=null;
function updateNote(text){
  let note=document.getElementById('studio-update-note');
  if(!note){note=document.createElement('div');note.id='studio-update-note';note.className='update-note';note.setAttribute('role','status');document.body.append(note);}
  const box=updateButton.getBoundingClientRect();
  note.textContent=text;note.style.top=`${Math.round(box.bottom+8)}px`;note.style.right=`${Math.round(window.innerWidth-box.right)}px`;
  note.classList.add('shown');clearTimeout(updateNoteTimer);updateNoteTimer=setTimeout(()=>note.classList.remove('shown'),6000);
}
// While an agent or an export works, the server keeps the click (app.queue_update) and updates once the work ends;
// the button shows it after a reload too, from the update state's «queued».
let updateQueued=false;
function showQueued(on){
  updateQueued=on;updateButton.classList.toggle('update-queued',on);updateButton.disabled=false;
  if(on){updateButton.hidden=false;setUpdateLabel('Оновлю після роботи','reload');}
}
async function applyStudioUpdate(){
  updateButton.disabled=true;
  try{
    const result=await api('/api/update/apply','POST',{});
    if(result.status==='queued'){showQueued(true);updateNote(`${result.reason}. Оновлю студію, щойно закінчиться.`);scheduleUpdatePoll(5000);return;}
    showQueued(false);
    updateWaiting=true;setUpdateLabel('Студія оновлюється…','reload');updateButton.classList.add('updating');
    scheduleUpdatePoll(1500);
  }catch(error){showQueued(false);setUpdateLabel('Оновити студію','download');updateNote(error.message);}
}
updateButton.addEventListener('click',()=>{
  if(updatePageOutdated){location.reload();return;}
  if(updateBlocked){modal('Оновлення зупинене',updateReasonHtml(updateBlocked),[{label:'Зрозуміло',primary:true,run:closeModal}]);return;}
  if(updateQueued){updateNote('Оновлення почнеться саме, щойно робота закінчиться.');return;}
  applyStudioUpdate();
});
pollStudioUpdates();
