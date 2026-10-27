/* Check for a new Studio version without interrupting the current project. */
const updateButton = document.getElementById('studio-update');
let updateBoot = null, updateWaiting = false, updatePageOutdated = false, updateTimer = null;

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
      updateButton.hidden=result.status!=='available';
      updateButton.textContent='Оновити студію';
    }
  }catch{}
  finally{scheduleUpdatePoll(updateWaiting?2000:30000);}
}
updateButton.addEventListener('click',async()=>{
  if(updatePageOutdated){location.reload();return;}
  updateButton.disabled=true;
  try{
    await api('/api/update/apply','POST',{});
    updateWaiting=true;updateButton.textContent='Студія оновлюється…';
    scheduleUpdatePoll(1500);
  }catch(error){updateButton.disabled=false;status(error.message,true);}
});
pollStudioUpdates();
