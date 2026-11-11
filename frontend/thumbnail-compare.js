// A version owns its comparison source. Changing the episode's reference cannot relabel older pictures.
function thumbnailComparison(item,items,data){
  const comparison=item.comparison;
  if(comparison?.kind==='edit'){
    const before=items.find(other=>other.code===item.code&&other.base===comparison.base&&other.key!==item.key);
    return before?{url:before.url,before:'До правок',after:'Після правок'}:null;
  }
  if(comparison?.kind==='clone'&&comparison.url)return {url:comparison.url,before:'Референс',after:'Результат'};
  if(item.code==='original'&&data.job?.file===item.base&&!data.job.base&&data.clone_reference?.id&&data.job.reference_id===data.clone_reference.id&&data.clone_reference.thumbnail_url)
    return {url:data.clone_reference.thumbnail_url,before:'Референс',after:'Результат'};
  return null;
}
function bindThumbnailComparison(section,project){
  const hero=section.querySelector('.thumb-hero'),frame=section.querySelector('.thumb-view-frame'),meta=section.querySelector('.thumb-preview-meta');
  const box=document.createElement('div');box.className='thumb-comparison';box.hidden=true;
  box.innerHTML='<figure><figcaption></figcaption><img alt="Джерело порівняння"></figure><figure><figcaption></figcaption></figure>';
  hero.insertBefore(box,meta);
  const button=document.createElement('button');button.type='button';button.hidden=true;button.className='outline thumb-compare-toggle';
  StudioUI.action(button,{label:'Порівняти',icon:'compare'});button.setAttribute('aria-pressed','false');meta.append(button);
  const captions=box.querySelectorAll('figcaption'),image=box.querySelector('img');let comparison=null;
  let enabled=StudioUI.preference('thumbnail-compare:'+project.id,['on','off'],'on')==='on';
  const paint=()=>{
    const visible=!!comparison&&enabled;box.hidden=!visible;hero.classList.toggle('is-comparing',visible);button.hidden=!comparison;button.setAttribute('aria-pressed',String(visible));
    if(visible){box.lastElementChild.append(frame);if(image.getAttribute('src')!==comparison.url){image.hidden=false;image.src=comparison.url;}}
    else hero.insertBefore(frame,box);
  };
  image.addEventListener('error',()=>{image.hidden=true;captions[0].textContent='Джерело недоступне';});
  button.addEventListener('click',()=>{enabled=!enabled;StudioUI.remember('thumbnail-compare:'+project.id,enabled?'on':'off');paint();});
  return (item,items,data)=>{
    comparison=thumbnailComparison(item,items,data);
    if(comparison){captions[0].textContent=comparison.before;captions[1].textContent=comparison.after;image.alt=comparison.before;}
    paint();
  };
}
