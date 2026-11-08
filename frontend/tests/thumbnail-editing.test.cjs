const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'..','thumbnail.js'),'utf8');
const editing=source.slice(source.indexOf('const thumbnailLanguageRuns='),source.indexOf('async function generateThumbnail('));
function setup(api){
  const context=vm.createContext({api,state:{project:{id:'p'}},thumbnailRuns:new Map(),thumbnailSources:new Map([['p',{title:'Source title',script:'Source text'}]]),
    $:()=>null,thumbnailBusy:()=>false,markThumbnailCard(){},pollThumbnail(){},status:()=>{}});
  vm.runInContext(editing,context);return context;
}
test('editing targets exactly the selected original or translated version',async()=>{
  for(const [code,base] of [['original','Превью v2.png'],['es','v3.png']]){
    const calls=[];const c=setup(async(...args)=>{calls.push(args);return args[1]==='POST'?{job:{status:'running',code}}:{image_editing:true};});
    c.item={code,base,key:base};await vm.runInContext("editThumbnail({id:'p',name:'Project'},item,'  Bigger phone  ')",c);
    const request=calls.find(args=>args[1]==='POST');
    assert.equal(request[0],code==='original'?'/api/projects/p/thumbnail':'/api/projects/p/languages/es/thumbnail');
    assert.equal(request[2].base,base);assert.equal(request[2].wishes,'Bigger phone');
    assert.equal(request[2].use_hero,undefined);assert.equal(request[2].writer,undefined);
    if(code==='original')assert.equal(request[2].script,'Source text');
  }
});
test('older server cannot silently localize the original instead of editing selected translation',async()=>{
  const calls=[];let message;const c=setup(async(...args)=>{calls.push(args);return {};});c.status=text=>message=text;
  await vm.runInContext("editThumbnail({id:'p'},{code:'pl',base:'v1.png'},'Change')",c);
  assert.equal(calls.length,1);assert.match(message,/перезапуску/);
});
test('empty edits and late responses after a project switch do not start paid work',async()=>{
  let posts=0;const c=setup(async(url,method)=>{if(method==='POST')posts++;c.state.project={id:'other'};return {image_editing:true};});
  await vm.runInContext("editThumbnail({id:'p'},{code:'original',base:'Превью v1.png'},' ')",c);
  assert.equal(posts,0);
  await vm.runInContext("editThumbnail({id:'p'},{code:'original',base:'Превью v1.png'},'Change')",c);
  assert.equal(posts,0);
});
test('double submit shares the pending request instead of generating twice',async()=>{
  let release;const calls=[];const wait=new Promise(resolve=>release=resolve);
  const c=setup(async(...args)=>{calls.push(args);if(args[1]==='POST')return {job:{status:'running'}};await wait;return {image_editing:true};});
  const first=vm.runInContext("editThumbnail({id:'p'},{code:'original',base:'Превью v1.png'},'Change')",c);
  await vm.runInContext("editThumbnail({id:'p'},{code:'original',base:'Превью v1.png'},'Change')",c);
  release();await first;assert.equal(calls.filter(args=>args[1]==='POST').length,1);
});
test('an already running image job preserves the draft and does not submit another request',async()=>{
  const calls=[];const c=setup(async(...args)=>{calls.push(args);return {job:{status:'running'}};});
  await vm.runInContext("editThumbnail({id:'p'},{code:'original',base:'Превью v1.png'},'Change')",c);
  assert.equal(calls.filter(args=>args[1]==='POST').length,0);
});
test('completed translated edits select the newly published version',async()=>{
  const c=setup(async()=>({thumbnail_jobs:[{code:'es',status:'done',version:3}]}));
  c.thumbnailPolling=new Set();c.setTimeout=fn=>fn();c.document={querySelector:()=>null,getElementById:()=>null};c.CSS={escape:s=>s};
  vm.runInContext("thumbnailSelection.set('p','es:v1.png');thumbnailLanguageRuns.set('p',[{code:'es',status:'running'}])",c);
  vm.runInContext(source.slice(source.indexOf('async function pollThumbnail('),source.indexOf('// Opening the tab')),c);
  await vm.runInContext("pollThumbnail('p')",c);
  assert.equal(vm.runInContext("thumbnailSelection.get('p')",c),'es:v3.png');
});
