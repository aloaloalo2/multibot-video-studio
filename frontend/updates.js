/* Check for a new Studio version without interrupting the current project. */
const updateButton = document.getElementById('studio-update');
let updateBoot = null, updateWaiting = false, updatePageOutdated = false, updateTimer = null, updateBlocked = null;

// Why a new version cannot arrive, in plain words, and what to do (backend/updater.py names the files or the branch).
function updateReasonHtml(state){
  const files=(state.files||[]).map(name=>`<li><code>${esc(name)}</code></li>`).join('')+(state.more?`<li>і ще ${state.more}</li>`:'');
  const after='<p>Після цього кнопка «Оновити студію» з’явиться сама.</p>';
  if(state.status==='local_changes')return `<p>На GitHub є нова версія студії. Оновлення зупинилося, бо в папці студії на цьому комп’ютері є змінені або зайві файли, і студія не хоче їх затерти.</p><ul>${files}</ul><p>Попросіть агента переглянути ці файли: потрібне зберегти в Git, зайве прибрати.</p>${after}`;
  if(state.status==='diverged')return `<p>На GitHub є нова версія студії, а на цьому комп’ютері є свої зміни коду, яких на GitHub немає. Студія не змішує їх сама.</p><p>Попросіть агента об’єднати ці зміни з версією на GitHub.</p>${after}`;
  if(state.status==='unsafe_update')return `<p>Нова версія студії замінила б файл, якого немає в Git:</p><ul>${files}</ul><p>Перенесіть цей файл з папки студії в інше місце або попросіть агента розібратися.</p>${after}`;
  if(state.status==='other_branch')return `<p>Папка студії стоїть на гілці «${esc(state.branch||'')}», тому нові версії з main сюди не приходять. Так буває, коли агент перемкнув папку на свою гілку для роботи.</p><p>Коли агент закінчить, попросіть його злити гілку в main і повернути папку на main.</p>${after}`;
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
      updateButton.hidden=false;updateButton.disabled=false;updateButton.textContent='Перезавантажити студію';
      return;
    }
    updateBoot=result.boot;
    if(!updateWaiting && !updatePageOutdated){
      updateBlocked=updateReasonHtml(result)?result:null;
      updateButton.hidden=result.status!=='available'&&!updateBlocked;
      updateButton.textContent=updateBlocked?'Оновлення зупинене':'Оновити студію';
      updateButton.classList.toggle('update-blocked',!!updateBlocked);
    }
  }catch{}
  finally{scheduleUpdatePoll(updateWaiting?2000:30000);}
}
updateButton.addEventListener('click',async()=>{
  if(updatePageOutdated){location.reload();return;}
  if(updateBlocked){modal('Оновлення зупинене',updateReasonHtml(updateBlocked),[{label:'Зрозуміло',primary:true,run:closeModal}]);return;}
  updateButton.disabled=true;
  try{
    await api('/api/update/apply','POST',{});
    updateWaiting=true;updateButton.textContent='Студія оновлюється…';
    scheduleUpdatePoll(1500);
  }catch(error){updateButton.disabled=false;status(error.message,true);}
});
pollStudioUpdates();
