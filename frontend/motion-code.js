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
    // a family the page has already (the editor's Inter, its catalog faces) is not added again: a second face of it
    // made the page re-lay its text with a font not yet loaded
    fontsReady=fetch('/fonts/catalog.json').then(r=>r.ok?r.json():[]).then(list=>Promise.all(list.flatMap(entry=>[
      ['regular',400],['bold',700]].filter(([key])=>entry[key]).map(([key,weight])=>{
        const have=[...document.fonts].find(f=>f.family.replace(/^["']|["']$/g,'')===entry.family&&String(f.weight)===String(weight));
        if(have)return have.load().catch(()=>{});
        const face=new FontFace(entry.family,`url(/fonts/${entry[key]})`,{weight:String(weight),display:'block'});
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

  // Smooth text (user, 26 November 2026: «рух тексту… дрожанням… стандарт в студії лише плавний рух»). Chromium's
  // fillText puts letters on whole pixels: text moving 0.1 px a frame stood still and then jumped a pixel, and wobbled
  // sideways, while the photo under it glided. Each line is drawn once at a whole pixel into a small bitmap of its own
  // and the bitmap is laid at the exact, fractional place, as a picture moves: a still line comes out pixel for pixel as
  // before, a moving one glides. Gradient or pattern fills keep the canvas's own text.
  const textBitmaps=new Map();
  const TEXT_STATE=['font','textAlign','textBaseline','direction','letterSpacing','wordSpacing','fontKerning','fontStretch',
    'fontVariantCaps','textRendering','fillStyle','strokeStyle','lineWidth','lineJoin','miterLimit','lineCap'];
  // a line drawn before its font came in would keep the stand-in font for good (26 November 2026: the notebook's Caveat
  // and the label's Unbounded showed as a serif): such a line is drawn natively and not kept, and the bitmaps go once
  // fonts have loaded
  if(global.document?.fonts?.addEventListener)global.document.fonts.addEventListener('loadingdone',()=>textBitmaps.clear());
  function textBitmap(ctx,kind,text,sx,sy,maxWidth){
    try{if(global.document?.fonts&&!global.document.fonts.check(ctx.font,text))return null;}catch{}
    const state=TEXT_STATE.map(key=>ctx[key]);
    const key=[kind,text,sx.toFixed(3),sy.toFixed(3),maxWidth??'',...state].join('\u0001');
    let hit=textBitmaps.get(key);
    if(hit){textBitmaps.delete(key);textBitmaps.set(key,hit);return hit;}
    const size=ctx.measureText(text),squeeze=maxWidth!=null&&size.width>maxWidth&&maxWidth>0?maxWidth/size.width:1;
    const pad=(kind==='stroke'?ctx.lineWidth:0)+2;
    const left=(size.actualBoundingBoxLeft||0)*squeeze+pad,right=(size.actualBoundingBoxRight||size.width)*squeeze+pad;
    const up=(size.actualBoundingBoxAscent||0)+pad,down=(size.actualBoundingBoxDescent||0)+pad;
    const ox=Math.ceil(left*sx)+1,oy=Math.ceil(up*sy)+1;
    const canvas=document.createElement('canvas');
    canvas.width=Math.max(1,ox+Math.ceil(right*sx)+2);canvas.height=Math.max(1,oy+Math.ceil(down*sy)+2);
    const o=canvas.getContext('2d');
    TEXT_STATE.forEach((name,i)=>{try{o[name]=state[i];}catch{}});
    o.setTransform(sx,0,0,sy,ox,oy);
    if(kind==='fill')o.fillText(text,0,0,maxWidth??undefined);else o.strokeText(text,0,0,maxWidth??undefined);
    hit={canvas,ox,oy};
    textBitmaps.set(key,hit);
    if(textBitmaps.size>400)textBitmaps.delete(textBitmaps.keys().next().value);
    return hit;
  }
  function smoothText(ctx){
    const fill=ctx.fillText,stroke=ctx.strokeText;
    const draw=(kind,native)=>function(text,x,y,maxWidth){
      text=String(text);
      const style=kind==='fill'?this.fillStyle:this.strokeStyle;
      if(!text||typeof style!=='string')return native.apply(this,arguments);
      const m=this.getTransform();
      const straight=Math.abs(m.b)<1e-9&&Math.abs(m.c)<1e-9&&m.a>0&&m.d>0;
      let sx=straight?m.a:Math.hypot(m.a,m.b),sy=straight?m.d:Math.hypot(m.c,m.d);
      if(!(sx>0&&sy>0))return native.apply(this,arguments);
      const ux=sx,uy=sy;
      // a font size in fractions (a line that grows by its size, not by scale) is drawn at the whole size above it and
      // brought down as a picture
      const font=this.font,size=/(\d+(?:\.\d+)?)px/.exec(font),wanted=size?Number(size[1]):0;
      const whole=wanted&&Math.abs(wanted-Math.round(wanted))>1e-6?Math.ceil(wanted):0;
      if(whole){const f=wanted/whole;sx*=f;sy*=f;if(maxWidth!=null)maxWidth/=f;this.font=font.replace(size[0],whole+'px');}
      // a growing or shrinking line is drawn at the next quarter of scale and brought down to its size as a picture: drawn
      // anew at every scale, its letters' spacing was rounded anew and wobbled
      const bx=Math.abs(sx-1)<1e-6?1:Math.ceil(sx*4-1e-6)/4,by=Math.abs(sy-1)<1e-6?1:Math.ceil(sy*4-1e-6)/4;
      const bitmap=textBitmap(this,kind,text,bx,by,maxWidth),kx=sx/bx,ky=sy/by;
      if(whole)this.font=font;
      if(!bitmap)return native.apply(this,arguments);
      const dx=m.a*x+m.c*y+m.e,dy=m.b*x+m.d*y+m.f,w=bitmap.canvas.width,h=bitmap.canvas.height;
      this.save();
      this.imageSmoothingEnabled=true;this.imageSmoothingQuality='high';
      if(straight){
        this.setTransform(1,0,0,1,0,0);
        if(kx===1&&ky===1)this.drawImage(bitmap.canvas,dx-bitmap.ox,dy-bitmap.oy);
        else this.drawImage(bitmap.canvas,dx-bitmap.ox*kx,dy-bitmap.oy*ky,w*kx,h*ky);
      }
      else{this.setTransform(m.a/ux,m.b/ux,m.c/uy,m.d/uy,dx,dy);this.drawImage(bitmap.canvas,-bitmap.ox*kx,-bitmap.oy*ky,w*kx,h*ky);}
      this.restore();
    };
    ctx.fillText=draw('fill',fill);ctx.strokeText=draw('stroke',stroke);
  }

  // Pinning to the frame's picture (user, 26 November 2026: «навчи привязувати елементи легко шоб рух повторювався…
  // щоб пришвидшити студію і якість рухів»). options.follow is the picture of the code's frame and options.self the code
  // clip itself, as placed on the timeline (motion_code.follow_of, codeFollow in universal.js): their keyframes are read
  // the way the preview and the export read them, so a pinned element repeats the picture's real zoom, pan and camera
  // instead of a formula that copies it. info.pin(u, v) is the canvas point of the picture's point (u, v) (0–1 of its box)
  // at this moment; info.onPhoto(ctx) maps the film's pixels of the picture at rest (unzoomed, at its own place) onto it,
  // so whatever is drawn after it moves with the picture; info.photo is its centre and drawn size now.
  const eased=(value,mode)=>{const p=Math.max(0,Math.min(1,value));return mode==='ease_in'?p*p*p:mode==='ease_out'?1-Math.pow(1-p,3):mode==='ease_in_out'?p*p*(3-2*p):p;};
  function keyed(c,key,base,t){
    const known=(c.keyframes||[]).filter(p=>key in p&&Number.isFinite(Number(p[key]))).map(p=>({time:Number(p.time),value:Number(p[key])})).sort((a,b)=>a.time-b.time);
    if(!known.length)return base;
    if(known[0].time>1e-9)known.unshift({time:0,value:base});
    if(t<=known[0].time)return known[0].value;
    for(let i=1;i<known.length;i++)if(t<known[i].time){const a=known[i-1],b=known[i];return a.value+(b.value-a.value)*eased((t-a.time)/(b.time-a.time),c.easing);}
    return known.at(-1).value;
  }
  function placeOf(c,t,W,H){
    const x=Number(c.x??.5),y=Number(c.y??.5),scale=Number(c.scale??1);
    return {cx:keyed(c,'x',x,t)*W,cy:keyed(c,'y',y,t)*H,s:keyed(c,'scale',scale,t),rx:x*W,ry:y*H,w:Number(c.width??1)*W,h:Number(c.height??1)*H};
  }
  function pinning(options,t,W,H){
    const follow=options.follow,self=options.self||{};
    const me=placeOf(self,t,W,H),bw=Number(self.width??1),bh=Number(self.height??1);
    // the code's own canvas is laid at its clip's place and zoom: a screen point back on the canvas
    const back=(x,y)=>[(x-me.cx)/(me.s*bw)+W/2,(y-me.cy)/(me.s*bh)+H/2];
    const at=follow?placeOf(follow,t+Number(self.start||0)-Number(follow.start||0),W,H):{cx:W/2,cy:H/2,s:1,rx:W/2,ry:H/2,w:W,h:H};
    const centre=back(at.cx,at.cy);
    return {
      pin:(u,v)=>back(at.cx+(Number(u)-.5)*at.w*at.s,at.cy+(Number(v)-.5)*at.h*at.s),
      onPhoto:ctx=>{const kx=at.s/(me.s*bw),ky=at.s/(me.s*bh);ctx.transform(kx,0,0,ky,centre[0]-at.rx*kx,centre[1]-at.ry*ky);},
      photo:{x:centre[0],y:centre[1],w:at.w*at.s/(me.s*bw),h:at.h*at.s/(me.s*bh),scale:at.s/me.s},
    };
  }

  // one picture of the clip at `t` seconds from its start; returns null or the error text
  function paint(canvas,code,t,options={}){
    const ctx=canvas.getContext('2d');
    ctx.setTransform(1,0,0,1,0,0);ctx.globalAlpha=1;ctx.globalCompositeOperation='source-over';ctx.filter='none';
    ctx.clearRect(0,0,canvas.width,canvas.height);
    delete ctx.fillText;delete ctx.strokeText;smoothText(ctx);
    const program=compile(code);
    if(program.error)return program.error;
    const duration=Number(options.duration)||0;
    const info={w:canvas.width,h:canvas.height,duration,fps:Number(options.fps)||25,progress:duration?clamp(t/duration):0,
                ease,clamp,mix,span,words:options.words||[],seed:options.seed||0,images:images(options.assets),
                ...pinning(options,t,canvas.width,canvas.height)};
    /* check:start (left out of the render cache's key, motion_code.fingerprint: it never changes the drawing) */
    // the text check (backend/motion_text_check.py): the same picture with its letters left out, and every line of text
    // with its box on screen, colour and shadow, to measure each against what lies under it
    const hide=!!options.hideText,log=options.logText?[]:null;
    if(hide||log){
      const fill=ctx.fillText,stroke=ctx.strokeText;
      const note=(context,text,x,y)=>{
        if(!log||!String(text).trim())return;
        const m=context.getTransform(),size=context.measureText(String(text)),width=size.width;
        const left=context.textAlign==='center'?x-width/2:(context.textAlign==='right'||context.textAlign==='end')?x-width:x;
        const ascent=size.actualBoundingBoxAscent||0,descent=size.actualBoundingBoxDescent||0;
        const corners=[[left,y-ascent],[left+width,y-ascent],[left,y+descent],[left+width,y+descent]].map(([px,py])=>[m.a*px+m.c*py+m.e,m.b*px+m.d*py+m.f]);
        const xs=corners.map(c=>c[0]),ys=corners.map(c=>c[1]);
        log.push({text:String(text),box:[Math.min(...xs),Math.min(...ys),Math.max(...xs),Math.max(...ys)],fill:String(context.fillStyle),
                  alpha:context.globalAlpha,font:context.font,scale:Math.hypot(m.a,m.b),shadow:context.shadowBlur>0?String(context.shadowColor):null,
                  shadow_blur:context.shadowBlur});
      };
      ctx.fillText=function(text,x,y){note(this,text,x,y);if(!hide)return fill.apply(this,arguments);};
      ctx.strokeText=function(){if(!hide)return stroke.apply(this,arguments);};
    }
    /* check:end */
    ctx.save();
    try{program.draw(ctx,t,info);}
    catch(error){ctx.restore();ctx.clearRect(0,0,canvas.width,canvas.height);/* check:start */delete ctx.fillText;delete ctx.strokeText;/* check:end */return String(error&&error.message||error);}
    ctx.restore();
    /* check:start */delete ctx.fillText;delete ctx.strokeText;if(log)global.__motionTexts=log;/* check:end */
    return null;
  }

  global.MotionCode={loadFonts,loadImages,compile,paint};
})(window);
