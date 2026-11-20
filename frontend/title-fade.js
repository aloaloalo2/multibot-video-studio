// A long episode title fills both lines and its second line fades out to the right instead of ending in «…» (user,
// 18 November 2026: «щоб воно не через точки пропадало, а через тінь… вниз не треба… лише справа»). The first line
// wraps as usual; the rest goes on one line that runs to the card's edge and fades there.
(function(){
  const SELECTOR='.project-card .project-title-rename';
  const sized=new ResizeObserver(entries=>{for(const e of entries)lay(e.target);});
  const seen=new WeakSet();
  function lay(button){
    // a leading language box of a trend card («EN», «FR») stays in front of the title (it had been flattened away)
    const badge=button.querySelector(':scope > .trend-language');
    const text=[...button.childNodes].filter(n=>n!==badge).map(n=>n.textContent).join('');
    const key=(badge?badge.textContent:'')+'|'+text+'|'+button.clientWidth;
    if(button._laid===key&&button.querySelector(':scope > .title-head'))return;   // the app may put the bare text back
    // the words sit in a span, so only they light up on hover, not the empty room beside a short title
    const node=document.createTextNode(text),head=document.createElement('span');head.className='title-head';head.append(node);
    button.replaceChildren(...(badge?[badge]:[]),head);
    const line=parseFloat(getComputedStyle(button).lineHeight)||20;
    if(button.scrollHeight>line*2+2){
      const range=document.createRange(),top=button.getBoundingClientRect().top;
      let low=0,high=text.length;   // the first character that sits below the first line
      while(low<high){const mid=(low+high)>>1;range.setStart(node,mid);range.setEnd(node,mid+1);
        const rect=range.getClientRects()[0];if(rect&&rect.top-top>line*0.6)high=mid;else low=mid+1;}
      if(low>0&&low<text.length){
        const tail=document.createElement('span');tail.className='title-tail';tail.textContent=text.slice(low);
        node.textContent=text.slice(0,low);button.append(tail);
      }
    }
    button._laid=key;
  }
  function scan(){for(const button of document.querySelectorAll(SELECTOR)){
    if(!seen.has(button)){seen.add(button);sized.observe(button);}lay(button);}}
  let queued=false;
  new MutationObserver(()=>{if(!queued){queued=true;requestAnimationFrame(()=>{queued=false;scan();});}})
    .observe(document.body,{childList:true,subtree:true,characterData:true});
  scan();
})();
