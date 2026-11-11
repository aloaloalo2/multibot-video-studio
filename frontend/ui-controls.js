// Shared, dependency-free controls. Preferences contain UI choices only.
const StudioUI=(()=>{
  const paths={
    image:'<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 5-5 4 4 3-3 6 6"/>',
    compare:'<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M12 2v20M6 12h3m6 0h3"/>',
    deepseek:'<path d="M3 12c3-6 8-6 11-2l6-3-2 6c-2 7-11 7-15-1Z"/><path d="M7 11h.01M13 16l2 3"/>',
    trending:'<path d="m8 6-6 6 6 6m8-12 6 6-6 6m-3-14-2 16"/>',
    claude:'<path d="m12 2 1 7 5-5-3 6 7-1-6 3 5 4-7-2 2 7-4-6-3 7 1-8-7 4 5-6-7-1 8-1-5-5 6 3z"/>',
    check:'<path d="m5 12 4 4L19 6"/>',
    refresh:'<path d="M3 10a9 9 0 1 1 1 7M3 4v6h6"/>',
  };
  const icon=name=>`<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name]||paths.image}</svg>`;
  function preference(key,allowed,fallback){try{const value=localStorage.getItem('videokey-ui:'+key);return allowed.includes(value)?value:fallback;}catch{return fallback;}}
  function remember(key,value){try{localStorage.setItem('videokey-ui:'+key,value);}catch{}}
  function action(button,{label,icon:mark,variant}={}){
    button.classList.add('ui-action');
    if(variant){button.classList.remove('primary','secondary','outline','danger');button.classList.add(variant);}
    if(label!==undefined){button.replaceChildren();if(mark)button.insertAdjacentHTML('beforeend',icon(mark));const span=document.createElement('span');span.textContent=label;button.append(span);}
    return button;
  }
  function choice(root,{id,label,items,value,onChange}){
    const box=document.createElement('label');box.className='ui-choice';
    const picture=document.createElement('span');picture.setAttribute('aria-hidden','true');
    const select=document.createElement('select');select.id=id;select.setAttribute('aria-label',label);
    for(const item of items){const option=document.createElement('option');option.value=item.value;option.textContent=item.label;select.append(option);}
    select.value=items.some(item=>item.value===value)?value:items[0]?.value||'';
    const paint=()=>{picture.innerHTML=icon(select.value);};paint();
    select.addEventListener('change',()=>{paint();onChange?.(select.value);});box.append(picture,select);root.append(box);return select;
  }
  const groups=new WeakSet();
  function enhance(root){
    if(!root)return;
    for(const button of root.querySelectorAll('button.primary,button.secondary,button.outline,button.danger'))button.classList.add('ui-action');
    for(const group of root.querySelectorAll('.episode-entry-options,[data-ui-segments]')){
      if(groups.has(group))continue;groups.add(group);group.classList.add('ui-segments');
      group.addEventListener('keydown',event=>{
        if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
        const buttons=[...group.querySelectorAll('button')].filter(button=>!button.disabled),index=buttons.indexOf(event.target);if(index<0)return;
        event.preventDefault();const next=event.key==='Home'?0:event.key==='End'?buttons.length-1:(index+(event.key==='ArrowLeft'?-1:1)+buttons.length)%buttons.length;
        buttons[next].focus();buttons[next].click();
      });
    }
  }
  return Object.freeze({icon,preference,remember,action,choice,enhance});
})();
