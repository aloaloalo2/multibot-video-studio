const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'..','thumbnail.js'),'utf8');
const open=source.slice(source.indexOf('async function openThumbnail('),source.indexOf('function showThumbnailState('));
const generation=source.slice(source.indexOf('async function generateThumbnail('),source.indexOf('// While a thumbnail is made'));

test('Codex action sends wishes to trending mode and Claude remains primary on the right',async()=>{
  let actions;const calls=[];let heading;
  const c=vm.createContext({api:async()=>({title:'¿Qué pasaría?',script:'Texto español.'}),thumbnailRuns:new Map(),thumbnailSources:new Map(),
    thumbnailIcon:'<svg/>',modal:(title,body,buttons)=>{heading=title;actions=buttons;},$:id=>id==='modal-actions'?{children:actions.map(item=>({textContent:item.label,classList:{add(){}}}))}:{value:'Make the face large',dataset:{},classList:{add(){}}},projectCostIcons:{claude_code:'<svg/>'},esc:s=>s,
    document:{querySelector:()=>null},showThumbnailState(){},thumbnailBusy:()=>false,
    generateThumbnail:(...args)=>calls.push(args),status(){}});
  vm.runInContext(open,c);await vm.runInContext("openThumbnail({id:'p',name:'Spanish video'})",c);
  assert.equal(heading,'New Preview');assert.equal(actions.length,3);assert.equal(actions[1].label,'Створити з Codex');assert.equal(actions[2].label,'Створити з Claude');assert.equal(actions[2].primary,true);
  actions[1].run();assert.equal(calls[0][1],'trending');assert.equal(calls[0][2],'Make the face large');
});
test('trending request preserves source title/script and creates a new image without a base',async()=>{
  const calls=[];
  const c=vm.createContext({thumbnailSources:new Map([['p',{title:'¿Qué pasaría?',script:'Texto español.'}]]),
    api:async(...args)=>{calls.push(args);return args[1]==='POST'?{job:{status:'running',writer:'trending'}}:{writers:['trending']};},thumbnailRuns:new Map(),
    $:()=>({hidden:true}),showThumbnailState(){},markThumbnailCard(){},pollThumbnail(){},status(){}});
  vm.runInContext(generation,c);await vm.runInContext("generateThumbnail({id:'p'},'trending','More emotion')",c);
  const body=calls.find(args=>args[1]==='POST')[2];assert.equal(body.writer,'trending');assert.equal(body.title,'¿Qué pasaría?');
  assert.equal(body.script,'Texto español.');assert.equal(body.base,undefined);
});
test('an older running server cannot silently launch the normal paid mode for a trending request',async()=>{
  const calls=[];let error;
  const c=vm.createContext({thumbnailSources:new Map(),$:()=>null,api:async(...args)=>{calls.push(args);return {};},status:text=>error=text});
  vm.runInContext(generation,c);await vm.runInContext("generateThumbnail({id:'p'},'trending','Idea')",c);
  assert.equal(calls.length,1);assert.notEqual(calls[0][1],'POST');assert.match(error,/перезапуску/);
});

test('host checkbox sends the explicit per-run choice and is omitted when unavailable',async()=>{
  for(const choice of [true,false,null]){
    let body;
    const c=vm.createContext({thumbnailSources:new Map(),thumbnailRuns:new Map(),
      $:id=>id==='thumb-use-hero'?(choice===null?null:{checked:choice}):{hidden:true},
      api:async(url,method,value)=>{body=value;return {job:{status:'running'}};},
      showThumbnailState(){},markThumbnailCard(){},pollThumbnail(){},status:message=>{throw new Error(message);}});
    vm.runInContext(generation,c);await vm.runInContext("generateThumbnail({id:'p',name:'T'},'claude','Idea')",c);
    assert.equal(body.use_hero,choice===null?undefined:choice);
  }
});


test('clone mode reads the chosen URL once and sends a per-cover reference without changing the episode title',async()=>{
  for(const mode of ['clone','new']){
    const calls=[],backdrop={hidden:true,dataset:{thumbnailProject:'p',thumbnailMode:mode}};
    const c=vm.createContext({state:{channel:{id:'c'}},thumbnailSources:new Map([['p',{title:'Our episode',script:'Our script',reference_selection:true}]]),thumbnailRuns:new Map(),
      $:id=>id==='modal-backdrop'?backdrop:id==='thumb-reference-url'?{value:' https://youtu.be/abcdefghijk '}:null,
      api:async(...args)=>{calls.push(args);return args[0].endsWith('/idea-reference')?{id:'abcdefghijk',url:'https://youtu.be/abcdefghijk'}:{job:{status:'running'}};},
      showThumbnailState(){},markThumbnailCard(){},pollThumbnail(){},status:message=>{throw Error(message);}});
    vm.runInContext(generation,c);await vm.runInContext("generateThumbnail({id:'p',channel_id:'c'},'claude','Wishes')",c);
    assert.equal(calls.length,mode==='clone'?2:1);
    const posted=calls.at(-1);assert.equal(posted[0],'/api/projects/p/thumbnail');
    assert.equal(posted[2].reference_id,mode==='clone'?'abcdefghijk':'');assert.equal(posted[2].title,'Our episode');
    if(mode==='clone')assert.equal(calls[0][2].url,'https://youtu.be/abcdefghijk');
  }
});
test('empty clone URL starts no metadata read or paid generation',async()=>{
  let calls=0,message;
  const c=vm.createContext({thumbnailSources:new Map([['p',{reference_selection:true}]]),
    $:id=>id==='modal-backdrop'?{dataset:{thumbnailProject:'p',thumbnailMode:'clone'}}:id==='thumb-reference-url'?{value:' '}:null,
    api:async()=>{calls++;},status:text=>message=text});
  vm.runInContext(generation,c);await vm.runInContext("generateThumbnail({id:'p'},'claude','')",c);
  assert.equal(calls,0);assert.match(message,/посилання/);
});

test('a displayed matching reference is reused for generation without another metadata read',async()=>{
  const calls=[],backdrop={hidden:true,dataset:{thumbnailProject:'p',thumbnailMode:'clone'}};
  const c=vm.createContext({state:{channel:{id:'c'}},thumbnailSources:new Map([['p',{reference_selection:true,referenceUrl:'https://youtu.be/abcdefghijk',reference:{id:'abcdefghijk'}}]]),thumbnailRuns:new Map(),
    $:id=>id==='modal-backdrop'?backdrop:id==='thumb-reference-url'?{value:'https://youtu.be/abcdefghijk'}:null,
    api:async(...args)=>{calls.push(args);return {job:{status:'running'}};},showThumbnailState(){},markThumbnailCard(){},pollThumbnail(){},status:message=>{throw Error(message);}});
  vm.runInContext(generation,c);await vm.runInContext("generateThumbnail({id:'p',channel_id:'c'},'claude','Wishes')",c);
  assert.equal(calls.length,1);assert.equal(calls[0][2].reference_id,'abcdefghijk');
});

function referenceFixture(data,api){
  const controls={},source={};
  const element=()=>({hidden:false,isConnected:true,value:'',textContent:'',dataset:{},listeners:{},classList:{toggle(){}},addEventListener(event,handler){this.listeners[event]=handler;},removeAttribute(name){delete this[name];},setAttribute(){}});
  for(const id of ['modal-backdrop','thumb-reference-url','thumb-reference-preview','thumb-reference-image','thumb-reference-caption','thumb-reference-field','thumb-brief-layout','thumb-create-wishes','modal-body','thumb-state'])controls[id]=element();
  controls['thumb-reference-url'].value=data.clone_reference?.url||'';
  const buttons=['new','clone'].map(mode=>({...element(),dataset:{thumbMode:mode}}));
  controls['modal-backdrop'].querySelectorAll=selector=>selector==='[data-thumb-mode]'?buttons:[];
  const c=vm.createContext({$:id=>controls[id],state:{channel:{id:'c'}},thumbnailSources:new Map([['p',source]]),thumbnailFrames:2,showThumbnailState(){},api,setTimeout,clearTimeout});
  vm.runInContext(sourceText(),c);
  c.data=data;vm.runInContext("setupThumbnailModes({id:'p',channel_id:'c'},data)",c);
  return {controls,buttons,source};
}
function sourceText(){return source.slice(source.indexOf('function setupThumbnailModes('),source.indexOf('const thumbnailLanguageRuns='));}

test('saved clone preview appears beside wishes on opening without a metadata or model request',()=>{
  const reference={id:'abcdefghijk',url:'https://youtu.be/abcdefghijk',thumbnail_url:'/cached.jpg',title:'Source title'};
  const {controls,source}=referenceFixture({clone_reference:reference},()=>{throw Error('unexpected request');});
  assert.equal(controls['thumb-reference-preview'].hidden,false);
  assert.equal(controls['thumb-reference-image'].src,'/cached.jpg');
  assert.equal(controls['thumb-reference-image'].hidden,false);
  assert.equal(controls['thumb-reference-caption'].textContent,'Прев’ю конкурента');
  assert.equal(controls['thumb-reference-image'].title,'Source title');
  assert.match(controls['thumb-create-wishes'].placeholder,/клонованого/);
  assert.equal(source.reference,reference);
});

test('a late reference response cannot replace the newer pasted URL or a closed modal',async()=>{
  const pending=[];
  const {controls,buttons}=referenceFixture({},()=>new Promise(resolve=>pending.push(resolve)));
  buttons[1].listeners.click();
  const field=controls['thumb-reference-url'];
  field.value='https://youtu.be/abcdefghijk';const first=field.listeners.change();
  field.value='https://youtu.be/12345678901';const second=field.listeners.change();
  pending[1]({id:'new',thumbnail_url:'/new.jpg'});await second;
  pending[0]({id:'old',thumbnail_url:'/old.jpg'});await first;
  assert.equal(controls['thumb-reference-image'].src,'/new.jpg');
  field.value='https://youtu.be/zzzzzzzzzzz';const third=field.listeners.change();
  controls['thumb-reference-preview'].isConnected=false;
  pending[2]({id:'closed',thumbnail_url:'/closed.jpg'});await third;
  assert.equal(controls['thumb-reference-image'].src,'/new.jpg');
});
