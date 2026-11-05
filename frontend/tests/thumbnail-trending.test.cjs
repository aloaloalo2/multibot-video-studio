const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'..','thumbnail.js'),'utf8');
const open=source.slice(source.indexOf('async function openThumbnail('),source.indexOf('function showThumbnailState('));
const generation=source.slice(source.indexOf('async function generateThumbnail('),source.indexOf('// While a thumbnail is made'));

test('third creation action sends the existing wishes to direct Codex trending mode',async()=>{
  let actions;const calls=[];
  const c=vm.createContext({api:async()=>({title:'¿Qué pasaría?',script:'Texto español.'}),thumbnailRuns:new Map(),thumbnailSources:new Map(),
    modal:(title,body,buttons)=>{actions=buttons;},$:()=>({value:'Make the face large',classList:{add(){}}}),
    document:{querySelector:()=>null},showThumbnailState(){},thumbnailBusy:()=>false,
    generateThumbnail:(...args)=>calls.push(args),status(){}});
  vm.runInContext(open,c);await vm.runInContext("openThumbnail({id:'p',name:'Spanish video'})",c);
  assert.equal(actions.length,3);assert.equal(actions[2].label,'Трендове прев’ю');
  actions[2].run();assert.equal(calls[0][1],'trending');assert.equal(calls[0][2],'Make the face large');
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
  const c=vm.createContext({thumbnailSources:new Map(),api:async(...args)=>{calls.push(args);return {};},status:text=>error=text});
  vm.runInContext(generation,c);await vm.runInContext("generateThumbnail({id:'p'},'trending','Idea')",c);
  assert.equal(calls.length,1);assert.notEqual(calls[0][1],'POST');assert.match(error,/перезапуску/);
});
