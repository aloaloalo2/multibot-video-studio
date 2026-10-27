const graphicTransitionPresets={};
const graphicTransitionReady=fetch('/graphic-transitions.json').then(response=>{if(!response.ok)throw new Error('Не вдалося завантажити переходи');return response.json();}).then(data=>{Object.assign(graphicTransitionPresets,data);return data;});
function graphicShapes(style,p,w,h){
  const config=graphicTransitionPresets[style];if(!config||p<=0||p>=1)return [];
  const colors=config.colors,kind=config.kind,enter=p<=.5,phase=Math.max(0,Math.min(1,enter?p/.42:(1-p)/.42)),out=[];
  const rect=(x,y,width,height,color)=>out.push({kind:'rect',x,y,w:width,h:height,color});
  if(p>=.42&&p<=.58)rect(0,0,w,h,colors.at(-1));
  const progress=delay=>easedProgress((phase-delay)/(1-delay),'ease_in_out');
  if(kind==='sweep'||kind==='bands'){
    const count=config.count||1,axis=config.axis||'x',band=(axis==='x'?w:h)/count;
    for(let i=0;i<count;i++){const reverse=!!config.reverse!== (!!config.alternate&&i%2===1);
      colors.forEach((color,k)=>{const q=progress((config.stagger||0)*i/Math.max(1,count-1)+k*.07);
        if(kind==='sweep'){const extent=(axis==='x'?w:h)*q,offset=enter!==reverse?0:(axis==='x'?w:h)-extent;axis==='x'?rect(offset,0,extent,h,color):rect(0,offset,w,extent,color);}
        else if(axis==='x'){const extent=h*q,offset=enter!==reverse?0:h-extent;rect(i*band,offset,band+1,extent,color);}
        else{const extent=w*q,offset=enter!==reverse?0:w-extent;rect(offset,i*band,extent,band+1,color);}
      });
    }
  }else if(kind==='gate'){
    colors.forEach((color,k)=>{const q=progress(k*.1),reverse=!!config.reverse;if(config.axis==='x'){if(enter!==reverse)rect(w*(1-q)/2,0,w*q,h,color);else{rect(0,0,w*q/2,h,color);rect(w*(1-q/2),0,w*q/2,h,color);}}else if(enter!==reverse)rect(0,h*(1-q)/2,w,h*q,color);else{rect(0,0,w,h*q/2,color);rect(0,h*(1-q/2),w,h*q/2,color);}});
  }else if(kind==='tiles'||kind==='dots'){
    const cols=config.cols,rows=config.rows,cw=w/cols,ch=h/rows;
    for(let row=0;row<rows;row++)for(let col=0;col<cols;col++){const order=config.checker?((row+col)%2)*.6+(col/cols+row/rows)*.2:(row*cols+col)/(rows*cols),q=progress((config.stagger||.3)*order),color=colors[(row+col)%colors.length];if(kind==='dots')out.push({kind:'circle',x:(col+.5)*cw,y:(row+.5)*ch,r:Math.hypot(cw,ch)/2*q+.01,color});else rect((col+.5)*cw-cw*q/2,(row+.5)*ch-ch*q/2,q?cw*q+1:0,q?ch*q+1:0,color);}
  }else if(kind==='paper'||kind==='wave'){
    colors.forEach((color,k)=>{const q=progress(k*.09),points=[];for(let i=0;i<65;i++){const y=i/64*h,wave=kind==='paper'?Math.sin(i*1.9)+Math.sin(i*.73)*.45:Math.sin(i/64*Math.PI*4+p*3)+.3*Math.sin(i/64*Math.PI*8-p*2),edge=(enter?w*q:w*(1-q))+wave*w*.035*Math.sin(q*Math.PI);points.push([edge,y]);}out.push({kind:'polygon',points:enter?[[0,0],[0,h],...points.reverse()]:[[w,0],...points,[w,h]],color});});
  }else if(kind==='rings'||kind==='frames'){
    colors.forEach((color,k)=>{const q=progress(k*.09);if(kind==='rings')out.push({kind:enter?'circle':'ring',x:w*.5,y:h*.5,r:Math.hypot(w,h)*.55*(enter?q:1),inner:enter?0:Math.hypot(w,h)*.55*(1-q),color});else if(enter)rect(w*(1-q)/2,h*(1-q)/2,w*q,h*q,color);else{const x=w*q/2,y=h*q/2;rect(0,0,w,y,color);rect(0,h-y,w,y,color);rect(0,y,x,h-2*y,color);rect(w-x,y,x,h-2*y,color);}});
  }else if(kind==='cards'){
    const count=config.count||4;for(let i=0;i<count;i++)colors.forEach((color,k)=>{const q=progress((config.stagger||.2)*i/Math.max(1,count-1)+k*.06),band=h/count,extent=w*q,offset=enter?0:w-extent;rect(offset,i*band,extent,band+1,color);});
  }
  return out;
}
function paintGraphicTransition(canvas,style,p,clear=true){
  const ctx=canvas.getContext('2d'),w=canvas.width,h=canvas.height;if(clear)ctx.clearRect(0,0,w,h);
  const config=graphicTransitionPresets[style];
  if(config?.kind==='cinematic'){
    if(p<=0||p>=1)return;
    const envelope=Math.sin(Math.PI*p)**2;
    for(const lobe of config.lobes){
      const cx=(lobe.x+lobe.dx*(p-.5))*w,cy=(lobe.y+lobe.dy*(p-.5))*h;
      const rgb=lobe.color.slice(1).match(/../g).map(value=>parseInt(value,16));
      const rgba=alpha=>`rgba(${rgb.join(',')},${alpha})`;
      ctx.save();ctx.translate(cx,cy);ctx.scale(lobe.rx*w,lobe.ry*h);
      const gradient=ctx.createRadialGradient(0,0,0,0,0,1),alpha=lobe.opacity*envelope;
      for(const [stop,factor] of [[0,1],[.3,.6],[.7,.13],[1,0]])gradient.addColorStop(stop,rgba(alpha*factor));
      ctx.fillStyle=gradient;ctx.fillRect(-1,-1,2,2);ctx.restore();
    }
    return;
  }
  for(const item of graphicShapes(style,p,w,h)){ctx.fillStyle=item.color;if(item.kind==='rect'&&item.w>0&&item.h>0)ctx.fillRect(Math.round(item.x),Math.round(item.y),Math.round(item.w),Math.round(item.h));else if(item.kind==='polygon'){ctx.beginPath();item.points.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.closePath();ctx.fill();}else if(item.kind==='circle'||item.kind==='ring'){ctx.beginPath();ctx.arc(item.x,item.y,item.r,0,Math.PI*2);if(item.kind==='ring')ctx.arc(item.x,item.y,item.inner,0,Math.PI*2,true);ctx.fill('evenodd');}}
}
function paintTransitionPreview(canvas,type,progress){
  const ctx=canvas.getContext('2d'),w=canvas.width,h=canvas.height,p=easedProgress(progress,'ease_in_out');ctx.clearRect(0,0,w,h);
  const card=(letter,color,x=0,y=0,scale=1,alpha=1)=>{ctx.save();ctx.globalAlpha=alpha;ctx.translate(w/2+x*w,h/2+y*h);ctx.scale(scale,scale);ctx.fillStyle=color;ctx.fillRect(-w/2,-h/2,w,h);ctx.fillStyle='#ffffff24';ctx.fillRect(-w*.38,-h*.3,w*.45,h*.13);ctx.fillRect(-w*.38,h*.18,w*.67,h*.1);ctx.fillStyle='#fff4df';ctx.font='600 '+h*.42+'px Arial';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(letter,w*.12,0);ctx.restore();};
  ctx.fillStyle='#18202b';ctx.fillRect(0,0,w,h);
  if(graphicTransitionPresets[type]){
    if(graphicTransitionPresets[type].kind==='cinematic'){
      card('A','#405866',0,0,1,1-p);
      card('B','#8c604a',0,0,1,p);
    }
    else card(progress<.5?'A':'B',progress<.5?'#405866':'#8c604a');
    paintGraphicTransition(canvas,type,progress,false);return;
  }
  if(type==='cut'){card(progress<.5?'A':'B',progress<.5?'#405866':'#8c604a');return;}
  if(type==='crossfade'){card('A','#405866',0,0,1,1-p);card('B','#8c604a',0,0,1,p);return;}
  if(type.startsWith('slide_')){const sign=['slide_left','slide_up'].includes(type)?1:-1,vertical=['slide_up','slide_down'].includes(type);card('A','#405866',vertical?0:-sign*p,vertical?-sign*p:0);card('B','#8c604a',vertical?0:sign*(1-p),vertical?sign*(1-p):0);return;}
  const zoomIn=type==='zoom_in';card('A','#405866',0,0,zoomIn?1+.12*p:1-.12*p,1-p);card('B','#8c604a',0,0,zoomIn?.88+.12*p:1.12-.12*p,p);
}
function renderGraphicTransitionOverlay(composition,time){
  let canvas=composition.querySelector('.graphic-transition-overlay'),join=(state.project.join_transitions||[]).find(j=>graphicTransitionPresets[j.type]&&time>=j.seam&&time<j.seam+j.duration);
  if(!join){if(canvas)canvas.hidden=true;return;}
  if(!canvas){canvas=document.createElement('canvas');canvas.className='graphic-transition-overlay';canvas.width=960;canvas.height=Math.round(960*state.project.height/state.project.width);const brandIds=new Set(sceneGroups().filter(g=>g.role==='overlay').flatMap(g=>g.clip_ids)),brand=Array.from(composition.children).find(e=>brandIds.has(e.dataset.clipId));composition.insertBefore(canvas,brand||null);}
  const brandIds=new Set(sceneGroups().filter(g=>g.role==='overlay').flatMap(g=>g.clip_ids));const base=Array.from(composition.querySelectorAll('.composition-clip')).filter(e=>!brandIds.has(e.dataset.clipId)&&e.dataset.transitionForeground!=='true').map(e=>Number(e.style.zIndex)||0);canvas.style.zIndex=String(Math.max(0,...base)+1);
  canvas.hidden=false;paintGraphicTransition(canvas,join.type,(time-join.seam)/join.duration);
}
