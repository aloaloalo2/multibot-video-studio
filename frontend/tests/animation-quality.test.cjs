const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const graphics=fs.readFileSync(path.join(__dirname,'../graphics.js'),'utf8');
const player=fs.readFileSync(path.join(__dirname,'../../razgon-plugin/razgon-2d-studio-plugin/skills/make-2d-video/kit/engine/player.js'),'utf8');

test('ordinary captions have zero percentage padding and remain centred inside narrow cards',()=>{
  const ctx=vm.createContext({state:{project:{width:1920}}});
  vm.runInContext(graphics.slice(0,graphics.indexOf('// The share of its box')),ctx);
  for(const align of ['center','left','right']){
    const text={style:{padding:'4%'}};
    const wrapper={style:{},querySelector:s=>s==='.composition-text'?text:null};
    ctx.applyGraphicStyle(wrapper,{font_size:36,text_align:align},960);
    assert.equal(text.style.padding,'0');assert.equal(text.style.display,'flex');assert.equal(text.style.alignItems,'center');
    assert.equal(text.style.justifyContent,align==='left'?'flex-start':align==='right'?'flex-end':'center');
  }
});

for(const modern of [true,false])test(`scene drawing state cannot leak through cuts or a failed scene (${modern?'reset':'fallback'})`,()=>{
  const g={clipActive:false,shadowBlur:0,stack:[],setTransform(){},fillRect(){},save(){this.stack.push(1)},restore(){this.stack.pop()}};
  const reset=()=>{g.clipActive=false;g.shadowBlur=0;g.stack=[]};
  if(modern)g.reset=reset;
  const buf={height:1080,getContext:()=>g};Object.defineProperty(buf,'width',{get:()=>1920,set:reset});
  let seen;
  const ctx=vm.createContext({E:{PX:1,W:1920,H:1080,shots:[]},clamp:n=>Math.max(0,Math.min(1,n)),errors:[],console:{log(){}},FONTS:{ui:'Arial'},text(){},
    getShot:id=>({kind:'2d',draw(){if(id==='broken'){g.clipActive=true;g.shadowBlur=80;g.save();throw Error('scene bug')}
      seen={clip:g.clipActive,shadow:g.shadowBlur,stack:g.stack.length};}})});
  vm.runInContext(player.slice(player.indexOf('function drawShot('),player.indexOf('// motion blur: shot')),ctx);
  ctx.drawShot(buf,{id:'broken',start:0,end:5},4.9);
  ctx.drawShot(buf,{id:'next',start:5,end:10},0);
  assert.deepEqual(seen,{clip:false,shadow:0,stack:1});
});
