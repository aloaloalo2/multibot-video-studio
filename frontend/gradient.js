const defaultGradient={colors:['#eee5d5','#d7c6ae','#eadbc5','#f4ecdf'],points:[[.15,.15],[.85,.15],[.8,.85],[.2,.85]],speed:.05,amplitude:.14,softness:.1};
function drawGradient(canvas,config,time){
  const gradient=config || defaultGradient;if(canvas._gradientTime===time && canvas._gradientConfig===JSON.stringify(gradient))return;
  if(canvas.width!==320){canvas.width=320;canvas.height=180;}
  const context=canvas.getContext('2d'),image=canvas._gradientImage || context.createImageData(320,180);canvas._gradientImage=image;
  const phase=time*gradient.speed*Math.PI*2,points=(gradient.points || defaultGradient.points).map((p,i)=>[Math.max(.02,Math.min(.98,p[0]+gradient.amplitude*Math.sin(phase+i*1.7))),Math.max(.02,Math.min(.98,p[1]+gradient.amplitude*Math.cos(phase*.82+i*1.3)))]),colors=gradient.colors.map(c=>[parseInt(c.slice(1,3),16),parseInt(c.slice(3,5),16),parseInt(c.slice(5,7),16)]);
  for(let y=0;y<180;y++)for(let x=0;x<320;x++){let total=0,r=0,g=0,b=0;for(let i=0;i<4;i++){const dx=x/319-points[i][0],dy=y/179-points[i][1],weight=1/Math.pow(dx*dx+dy*dy+gradient.softness,1.8);total+=weight;r+=weight*colors[i][0];g+=weight*colors[i][1];b+=weight*colors[i][2];}const index=(y*320+x)*4;image.data[index]=Math.round(r/total);image.data[index+1]=Math.round(g/total);image.data[index+2]=Math.round(b/total);image.data[index+3]=255;}
  context.putImageData(image,0,0);canvas._gradientTime=time;canvas._gradientConfig=JSON.stringify(gradient);
}
async function openGradientClip(){
  if(!state.project)return;
  const layer=activeLayer();if(!layer)return;
  const start=state.expandedGroup?timelineOrigin():state.playhead,duration=state.expandedGroup?timelineSpan():5;
  await action('add_clip',{layer_id:layer.id,kind:'animation',content_type:'gradient',title:'Градієнт 4 точки',start,duration,x:.5,y:.5,width:1,height:1,gradient:defaultGradient},'Градієнт додано.');
}
function renderGradientControls(clip,box){
  if(clip.content_type!=='gradient')return;
  const gradient=clip.gradient || defaultGradient,section=document.createElement('section');section.className='gradient-controls';
  section.innerHTML=`<h3>Градієнт 4 точки</h3><div class="gradient-colors">${gradient.colors.map((c,i)=>`<label>Точка ${i+1}<input type="color" id="gradient-color-${i}" value="${c}"></label>`).join('')}</div><div class="property-grid"><label>Швидкість<input id="gradient-speed" type="number" min="0" max="0.5" step="0.01" value="${gradient.speed}"></label><label>Рух<input id="gradient-amplitude" type="number" min="0" max="0.4" step="0.01" value="${gradient.amplitude}"></label><label>М’якість<input id="gradient-softness" type="number" min="0.02" max="0.5" step="0.01" value="${gradient.softness}"></label></div><details><summary>Позиції точок</summary><div class="property-grid">${gradient.points.map((p,i)=>`<label>${i+1} X, %<input id="gradient-x-${i}" type="number" min="0" max="100" value="${Math.round(p[0]*100)}"></label><label>${i+1} Y, %<input id="gradient-y-${i}" type="number" min="0" max="100" value="${Math.round(p[1]*100)}"></label>`).join('')}</div></details><button id="gradient-save" class="secondary full" type="button">Зберегти градієнт</button>`;
  box.querySelector('.universal-properties')?.append(section);
  $('gradient-save').addEventListener('click',()=>action('update_clip',{clip_id:clip.id,patch:{gradient:{colors:[0,1,2,3].map(i=>$('gradient-color-'+i).value),points:[0,1,2,3].map(i=>[Number($('gradient-x-'+i).value)/100,Number($('gradient-y-'+i).value)/100]),speed:Number($('gradient-speed').value),amplitude:Number($('gradient-amplitude').value),softness:Number($('gradient-softness').value)}}},'Градієнт збережено.').catch(()=>{}));
}
