function channelHeyGenAvatars(channel){
  const section=document.createElement('details');
  section.className='channel-settings-group heygen-avatar-gallery';
  section.innerHTML=`<summary><span class="heygen-avatar-cover heygen-avatar-badge">${channelSettingsIcon('hero')}</span><span><strong class="heygen-avatar-brand"><img src="/heygen-symbol.png" alt="" width="15" height="15">HeyGen</strong><small>Мій аватар не вибрано</small></span><svg class="channel-settings-chevron" viewBox="0 0 20 20" aria-hidden="true"><path d="m7 4 6 6-6 6"/></svg></summary>`;
  const body=document.createElement('div');
  body.className='channel-settings-group-body';
  section.append(body);
  const endpoint=`/api/channels/${encodeURIComponent(channel.id)}/heygen-avatars`;
  const galleryTitle=section.querySelector('summary');
  const badge=galleryTitle.querySelector('.heygen-avatar-badge');
  const summary=galleryTitle.querySelector('small');
  const primary=document.createElement('button');
  primary.type='button';primary.className='heygen-avatar-primary';
  const groups=document.createElement('div');
  const selectionField=document.createElement('input');
  selectionField.type='hidden';
  body.append(selectionField,primary,groups);
  let selected=channel.settings?.heygen_avatar||null, preview=null, badgeUrl=null;
  let browsing=true, initialAvatarId=selected?.id;
  section.avatarSelection=()=>selected;
  section.avatarPreview=()=>preview;

  function addPhoto(cover, url, loading='lazy'){
    if(!url)return;
    const photo=document.createElement('img');
    photo.alt='';photo.loading=loading;photo.decoding='async';photo.referrerPolicy='no-referrer';
    photo.addEventListener('error',()=>photo.remove(),{once:true});
    photo.src=url;
    cover.append(photo);
  }

  function portrait(parent, avatar){
    const cover=document.createElement('span');
    cover.className='heygen-avatar-cover';
    cover.innerHTML=channelSettingsIcon('hero');
    addPhoto(cover,avatar.preview_image_url);
    const name=document.createElement('strong');
    name.textContent=avatar.name||'Без назви';
    parent.append(cover,name);
    return cover;
  }

  function showSelection(){
    summary.textContent=selected?`Мій аватар: ${selected.name}`:'Мій аватар не вибрано';
    if(badgeUrl!==preview){
      badgeUrl=preview;
      badge.querySelector('img')?.remove();
      addPhoto(badge,preview,'eager');
      section.dispatchEvent(new Event('heygen-avatar-preview',{bubbles:true}));
    }
    if(!selected)return;
    primary.replaceChildren();
    portrait(primary,{...selected,preview_image_url:preview});
    const name=primary.lastElementChild;
    const label=document.createElement('span'), note=document.createElement('small');
    note.textContent=selected.look?.name||'Образ не вибрано';
    label.append(name,note);primary.append(label);
  }

  function showBrowseMode(){
    primary.hidden=browsing;
    groups.hidden=!browsing;
    if(browsing&&section.open)loadAvatars();
  }

  function revealGallery(){
    if(!browsing||!section.open||!section.getClientRects().length)return;
    const panel=section.closest('.channel-settings-panel');
    const target=section.offsetHeight+16<=panel.clientHeight?section:galleryTitle;
    target.scrollIntoView({block:'nearest',inline:'nearest'});
  }

  function avatarIdentity(avatar){
    return {id:avatar.id,name:avatar.name?.trim().slice(0,200)||'Без назви'};
  }

  function updateField(notify=false){
    selectionField.value=JSON.stringify([selected?.id,selected?.look?.id]);
    if(notify)selectionField.dispatchEvent(new Event('change',{bubbles:true}));
  }

  let requestedPreview=false;
  section.loadSelectedPortrait=async()=>{
    if(!selected||preview||requestedPreview)return;
    requestedPreview=true;
    const id=selected.id;
    try{
      const {avatar}=await api(`${endpoint}/selected`);
      if(section.isConnected&&selected?.id===id&&avatar?.id===id&&!preview){
        preview=avatar.preview_image_url||null;
        showSelection();
      }
    }catch{} // Try the catalogue if this avatar has a cover there.
    if(section.isConnected&&selected?.id===id&&!preview)loadAvatars();
  };

  function pagedList(root, {groupId, row, empty, onFirstPage}){
    const list=document.createElement('div'), status=document.createElement('p'), more=document.createElement('button');
    list.className=groupId?'heygen-avatar-looks':'heygen-avatar-groups';
    status.className='heygen-avatar-status';status.setAttribute('role','status');
    more.type='button';more.className='secondary';more.hidden=true;
    root.append(list,status,more);
    let loaded=false, loading=false, token=null;
    const seen=new Set();
    const load=async()=>{
      if(loading)return;
      loading=true;more.hidden=true;
      status.classList.add('is-loading');
      status.innerHTML='<span class="export-spinner" aria-hidden="true"></span><span>Завантажуємо з HeyGen…</span>';
      const query=new URLSearchParams();
      if(groupId)query.set('group_id',groupId);
      if(token)query.set('token',token);
      try{
        const suffix=query.toString();
        const {items,next_token}=await api(suffix?`${endpoint}?${suffix}`:endpoint);
        if(!root.isConnected)return;
        for(const avatar of items){
          if(seen.has(avatar.id))continue;
          list.append(row(avatar));seen.add(avatar.id);
        }
        const firstPage=!loaded;
        token=next_token;loaded=true;
        status.classList.remove('is-loading');
        status.textContent=seen.size||token?'':empty;
        more.textContent='Показати ще';more.hidden=!token;
        if(firstPage)onFirstPage?.();
      }catch(error){
        if(!root.isConnected)return;
        status.classList.remove('is-loading');
        status.textContent=error.httpStatus===404&&error.message==='Невідомий запит'
          ?'Щоб підключити галерею HeyGen, перезапустіть VideoKey Studio.'
          :error.message;
        more.textContent='Повторити';more.hidden=false;
      }finally{loading=false;}
    };
    more.addEventListener('click',load);
    return ()=>{if(!loaded)load();};
  }


  const loadAvatars=pagedList(groups,{
    onFirstPage:revealGallery,
    row:avatar=>{
      const group=document.createElement('details'), title=document.createElement('summary');
      group.className='heygen-avatar-details';
      group.name='heygen-avatar-groups';
      portrait(title,avatar);group.append(title);
      if(avatar.id===selected?.id&&avatar.preview_image_url&&!preview){
        preview=avatar.preview_image_url;
        showSelection();
      }
      const loadLooks=pagedList(group,{
        groupId:avatar.id,
        empty:'Для цього аватара HeyGen не повернув образів.',
        onFirstPage:()=>{if(group.open)revealGallery();},
        row:look=>{
          const button=document.createElement('button');
          button.type='button';button.className='heygen-avatar-look';
          const cover=portrait(button,look);
          cover.insertAdjacentHTML('beforeend','<span class="heygen-avatar-look-action" aria-hidden="true">Вибрати</span><span class="heygen-avatar-look-star" aria-hidden="true">★</span>');
          button.setAttribute('aria-pressed',String(selected?.id===avatar.id&&selected.look?.id===look.id));
          button.addEventListener('click',()=>{
            groups.querySelector('.heygen-avatar-look[aria-pressed=true]')?.setAttribute('aria-pressed','false');
            button.setAttribute('aria-pressed','true');
            preview=avatar.preview_image_url||(selected?.id===avatar.id?preview:null);
            selected={...avatarIdentity(avatar),look:avatarIdentity(look)};
            showSelection();updateField(true);
          });
          return button;
        }
      });
      group.addEventListener('toggle',()=>{
        if(group.open)loadLooks();
        revealGallery();
      });
      if(avatar.id===initialAvatarId){
        initialAvatarId=null;
        group.open=true;
      }
      return group;
    },
    empty:'У підключеному акаунті HeyGen немає власних аватарів.'
  });
  primary.addEventListener('click',()=>{
    browsing=true;
    showBrowseMode();
    (groups.querySelector('summary')||galleryTitle).focus({preventScroll:true});
    revealGallery();
  });
  section.addEventListener('toggle',()=>{
    if(!section.open)return;
    showBrowseMode();
    revealGallery();
  });
  showSelection();showBrowseMode();updateField();
  return section;
}
