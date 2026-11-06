// The sidebar order belongs to Studio and survives browser reloads.
let channelOrderSaving=false;
function wireChannelOrder(list){
  let dragged=null,target=null,after=false;
  const clear=()=>{
    for(const row of list.querySelectorAll('.channel-item'))row.classList.remove('channel-dragging','channel-drop-before','channel-drop-after');
    dragged=null;target=null;
  };
  for(const row of list.querySelectorAll('.channel-item')){
    row.draggable=!channelOrderSaving;
    const button=row.querySelector('.channel-select');if(button)button.draggable=!channelOrderSaving;
    row.addEventListener('dragstart',event=>{
      if(channelOrderSaving){event.preventDefault();return;}
      dragged=row;event.dataTransfer.effectAllowed='move';
      event.dataTransfer.setData('application/x-videokey-channel',row.dataset.channelId);
      row.classList.add('channel-dragging');
    });
    row.addEventListener('dragover',event=>{
      if(!dragged||dragged===row)return;
      event.preventDefault();event.dataTransfer.dropEffect='move';
      target=row;
      const rect=row.getBoundingClientRect(),horizontal=getComputedStyle(list).display==='flex';
      after=horizontal?event.clientX>rect.left+rect.width/2:event.clientY>rect.top+rect.height/2;
      for(const item of list.querySelectorAll('.channel-item'))item.classList.remove('channel-drop-before','channel-drop-after');
      row.classList.add(after?'channel-drop-after':'channel-drop-before');
    });
    row.addEventListener('drop',async event=>{
      if(!dragged||!target||target===dragged)return;
      event.preventDefault();event.stopPropagation();
      const previous=state.channels.map(channel=>channel.id),ids=previous.filter(id=>id!==dragged.dataset.channelId);
      ids.splice(ids.indexOf(target.dataset.channelId)+(after?1:0),0,dragged.dataset.channelId);
      clear();
      if(ids.every((id,index)=>id===previous[index]))return;
      const records=new Map(state.channels.map(channel=>[channel.id,channel]));
      state.channels=ids.map(id=>records.get(id));channelOrderSaving=true;renderChannels();
      try{
        const result=await api('/api/channels/order','PATCH',{ids});
        state.channels=result.channels;renderChannels();
      }catch(error){
        const current=new Map(state.channels.map(channel=>[channel.id,channel]));
        state.channels=previous.map(id=>current.get(id)).filter(Boolean);renderChannels();status(error.message,true);
      }finally{channelOrderSaving=false;for(const item of list.querySelectorAll('.channel-item,.channel-select'))item.draggable=true;}
    });
    row.addEventListener('dragend',clear);
  }
}
