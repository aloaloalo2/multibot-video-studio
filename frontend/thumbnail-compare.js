// A version owns its comparison source. Changing the episode's reference cannot relabel older pictures.
function thumbnailComparison(item,items,data){
  const comparison=item.comparison;
  if(comparison?.kind==='edit'){
    const before=items.find(other=>other.code===item.code&&other.base===comparison.base&&other.key!==item.key);
    return before?{url:before.url,before:'До правок',after:'Після правок'}:null;
  }
  if(comparison?.kind==='clone'&&comparison.url)return {url:comparison.url,before:'Референс',after:'Ваше прев’ю'};
  if(item.code==='original'&&data.job?.file===item.base&&!data.job.base&&data.clone_reference?.id&&data.job.reference_id===data.clone_reference.id&&data.clone_reference.thumbnail_url)
    return {url:data.clone_reference.thumbnail_url,before:'Референс',after:'Ваше прев’ю'};
  return null;
}
function bindThumbnailComparison(section,project){
  const hero=section.querySelector('.thumb-hero'),frame=section.querySelector('.thumb-view-frame'),meta=section.querySelector('.thumb-preview-meta');
  const box=document.createElement('div');box.className='thumb-comparison';box.hidden=true;
  // only the reference is added; your picture never moves (user, 16 November 2026: «нажимаю порівняти, верстка пливе»)
  box.innerHTML='<figure><figcaption></figcaption><img alt="Джерело порівняння"></figure>';
  const button=document.createElement('button');button.type='button';button.hidden=true;button.className='outline thumb-compare-toggle';
  // the button lives on the picture and shows on hover, like «Завантажити»; comparing is off until asked
  // (user, 16 November 2026: «кнопка порівняти має бути на прев'юшці самій при наведенні… по дефолту не включена»)
  StudioUI.action(button,{label:'Порівняти',icon:'compare'});button.setAttribute('aria-pressed','false');button.title='Порівняти з референсом';
  const captions=box.querySelectorAll('figcaption'),image=box.querySelector('img');let comparison=null;
  let enabled=StudioUI.preference('thumbnail-compare-v2:'+project.id,['on','off'],'off')==='on';
  const paint=()=>{
    const tools=frame.querySelector('.thumb-preview-tools');if(tools&&button.parentNode!==tools)tools.prepend(button);
    if(box.parentNode!==frame)frame.append(box);   // the reference sits in a corner of the picture: nothing else moves
    const visible=!!comparison&&enabled;box.hidden=!visible;hero.classList.toggle('is-comparing',visible);button.hidden=!comparison;button.setAttribute('aria-pressed',String(visible));
    if(visible&&image.getAttribute('src')!==comparison.url){image.hidden=false;image.src=comparison.url;}
  };
  image.addEventListener('error',()=>{image.hidden=true;captions[0].textContent='Джерело недоступне';});
  button.addEventListener('click',()=>{enabled=!enabled;StudioUI.remember('thumbnail-compare-v2:'+project.id,enabled?'on':'off');paint();});
  return (item,items,data)=>{
    comparison=thumbnailComparison(item,items,data);
    if(comparison){captions[0].textContent=comparison.before;image.alt=comparison.before;}
    paint();
  };
}
