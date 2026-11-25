// Motion design written as code (user, 25 November 2026: «моушен дизайн професійний, який йому дозволяє робити все, що він
// захоче»): a clip of content_type "code" holds the source of `function draw(ctx, t, info) {…}`, Canvas 2D on a transparent
// canvas the size of the film. The preview runs it here, and the export renders the very same runtime on
// /motion-code.html (tools/motion_code_render.mjs), so both draw one picture with the studio's own fonts.
(function(global){
  const compiled=new Map(),pictures=new Map();
  let fontsReady=null;

  // the clip's pictures (PNG props, photos of the project) by the names its code uses: info.images.<name>
  function loadImage(url){
    if(!pictures.has(url))pictures.set(url,new Promise(resolve=>{const image=new Image();image.decoding='async';
      image.onload=()=>resolve(image);image.onerror=()=>resolve(null);image.src=url;}).then(image=>{pictures.set(url,image);return image;}));
    return pictures.get(url);
  }
  function loadImages(map){return Promise.all(Object.values(map||{}).map(loadImage));}
  function images(map){
    const result={};
    for(const [name,url] of Object.entries(map||{})){const found=pictures.get(url);if(found instanceof HTMLImageElement)result[name]=found;else loadImage(url);}
    return result;
  }

  // every font of the studio's catalog, under its catalog name, regular (400) and bold (700)
  function loadFonts(){
    if(fontsReady)return fontsReady;
    fontsReady=fetch('/fonts/catalog.json').then(r=>r.ok?r.json():[]).then(list=>Promise.all(list.flatMap(entry=>[
      ['regular',400],['bold',700]].filter(([key])=>entry[key]).map(([key,weight])=>{
        const face=new FontFace(entry.family,`url(/fonts/${entry[key]})`,{weight:String(weight)});
        return face.load().then(loaded=>{document.fonts.add(loaded);}).catch(()=>{});
      })))).catch(()=>{});
    return fontsReady;
  }

  // the clip's code once compiled: its draw function, or the error it threw
  function compile(code){
    if(compiled.has(code))return compiled.get(code);
    let result;
    try{
      const make=new Function('"use strict";'+code+'\n;if(typeof draw!=="function")throw new Error("Код має оголосити function draw(ctx, t, info)");return draw;');
      result={draw:make()};
    }catch(error){result={error:String(error&&error.message||error)};}
    compiled.set(code,result);
    if(compiled.size>200)compiled.delete(compiled.keys().next().value);
    return result;
  }

  // small helpers every code gets in `info`: easing curves, clamp, mix and a 0–1 window of time
  const ease={
    linear:x=>x,
    inOut:x=>x<.5?2*x*x:1-Math.pow(-2*x+2,2)/2,
    out:x=>1-Math.pow(1-x,3),
    in:x=>x*x*x,
    back:x=>{const c=1.70158,d=c+1;return 1+d*Math.pow(x-1,3)+c*Math.pow(x-1,2);},
    elastic:x=>x===0||x===1?x:Math.pow(2,-10*x)*Math.sin((x*10-.75)*(2*Math.PI)/3)+1,
  };
  const clamp=(x,a=0,b=1)=>Math.min(b,Math.max(a,x));
  const mix=(a,b,x)=>a+(b-a)*x;
  const span=(t,from,to)=>clamp((t-from)/Math.max(1e-6,to-from));

  // one picture of the clip at `t` seconds from its start; returns null or the error text
  function paint(canvas,code,t,options={}){
    const ctx=canvas.getContext('2d');
    ctx.setTransform(1,0,0,1,0,0);ctx.globalAlpha=1;ctx.globalCompositeOperation='source-over';ctx.filter='none';
    ctx.clearRect(0,0,canvas.width,canvas.height);
    const program=compile(code);
    if(program.error)return program.error;
    const duration=Number(options.duration)||0;
    const info={w:canvas.width,h:canvas.height,duration,fps:Number(options.fps)||25,progress:duration?clamp(t/duration):0,
                ease,clamp,mix,span,words:options.words||[],seed:options.seed||0,images:images(options.assets)};
    ctx.save();
    try{program.draw(ctx,t,info);}
    catch(error){ctx.restore();ctx.clearRect(0,0,canvas.width,canvas.height);return String(error&&error.message||error);}
    ctx.restore();
    return null;
  }

  global.MotionCode={loadFonts,loadImages,compile,paint};
})(window);
