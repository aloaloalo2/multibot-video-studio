/* Check for a new Studio version without interrupting the current project. */
const updateButton = document.getElementById('studio-update');
// Updating code keeps local edits in a recovery point; the normal action stays a single Update button.
const updateIcons={download:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11m0 0-4.5-4.5M12 15l4.5-4.5M5 15v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3"/></svg>',
  reload:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 12a8 8 0 1 1-2.34-5.66M20 4v5h-5"/></svg>',
  warning:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4 2.8 19.5h18.4L12 4zM12 10v4.5M12 17.2v.3"/></svg>'};
function setUpdateLabel(text,icon){updateButton.innerHTML=`${updateIcons[icon] || ''}<span>${text}</span>`;}
let updateBoot = null, updateWaiting = false, updatePageOutdated = false, updateTimer = null, updateBlocked = null;

// Only genuine personal-data conflicts need an explanation before changing files.
function updateReasonHtml(state){
  const files=(state.files||[]).map(name=>`<li><code>${esc(name)}</code></li>`).join('')+(state.more?`<li>і ще ${state.more}</li>`:'');
  if(state.status==='unsafe_update')return `<p>Ця версія зачепила б особисті дані або ключі доступу. Їх залишено на місці.</p><ul>${files}</ul><p>Потрібно виправити склад оновлення на GitHub.</p>`;
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
      updateButton.hidden=!['available','update_failed','local_changes','diverged','other_branch'].includes(result.status)&&!updateBlocked;
      setUpdateLabel('Оновити студію','download');
      updateButton.title=result.error||'Локальні правки коду буде збережено в резервну копію.';
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
  if(updateBlocked){modal('Не вдалося оновити',updateReasonHtml(updateBlocked),[]);return;}
  if(updateQueued){updateNote('Оновлення почнеться саме, щойно робота закінчиться.');return;}
  applyStudioUpdate();
});
pollStudioUpdates();
