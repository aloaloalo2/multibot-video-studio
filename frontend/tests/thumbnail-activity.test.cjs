const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'..','thumbnail.js'),'utf8');
const discovery=source.slice(source.indexOf('const thumbnailDiscovering='),source.indexOf('// After a reload'));
test('automatic cover handoff discovers a new run after the initial idle read and shares pending reads',async()=>{
  const runs=new Map([['p',{status:'done'}]]),marked=[],polled=[];
  let release,reads=0;const response=new Promise(resolve=>release=resolve);
  const c=vm.createContext({thumbnailBusy:id=>runs.get(id)?.status==='running',
    api:async url=>{reads++;assert.equal(url,'/api/projects/p/thumbnail');return response;},
    readThumbnailData:(id,data)=>runs.set(id,data.job),markThumbnailCard:id=>marked.push(id),
    thumbnailWorking:id=>runs.get(id)?.status==='running',pollThumbnail:id=>polled.push(id)});
  vm.runInContext(discovery,c);
  const pending=c.discoverThumbnailActivity('p');await c.discoverThumbnailActivity('p');assert.equal(reads,1);
  release({job:{status:'running',stage:'drawing'}});await pending;
  assert.deepEqual(marked,['p']);assert.deepEqual(polled,['p']);
  await c.discoverThumbnailActivity('p');assert.equal(reads,1);
});
test('failed activity discovery can be checked on the next status poll',async()=>{
  let reads=0;
  const c=vm.createContext({thumbnailBusy:()=>false,api:async()=>{reads++;throw Error('offline');},
    readThumbnailData(){},markThumbnailCard(){},thumbnailWorking:()=>false,pollThumbnail(){}});
  vm.runInContext(discovery,c);
  await c.discoverThumbnailActivity('p');await c.discoverThumbnailActivity('p');assert.equal(reads,2);
});

test('clone gallery accepts the server zero-frame requirement while ordinary and busy projects stay gated',()=>{
  const create={dataset:{}},section={dataset:{project:'p'},querySelector:()=>create},tab={classList:{toggle(){}},setAttribute(){}};
  const state={project:{id:'p',episode_path:'/episode',tracks:[]},view:'thumb'},runs=new Map();
  const c=vm.createContext({state,thumbnailRuns:runs,thumbnailBusy:id=>runs.get(id)?.status==='running',
    $:id=>id==='view-thumb'?tab:section});
  vm.runInContext(source.slice(source.indexOf('const thumbnailLanguageRuns='),source.indexOf('function thumbnailWorking(')),c);
  vm.runInContext(source.slice(source.indexOf('function thumbnailFramesMade('),source.indexOf('async function buildThumbView(')),c);
  c.thumbnailFrames=2;
  c.readThumbnailData('p',{pictures:0,min_frames:0});c.renderThumbView();assert.equal(create.disabled,false);
  c.readThumbnailData('p',{pictures:0,min_frames:2});c.renderThumbView();assert.equal(create.disabled,true);assert.match(create.title,/2/);
  c.readThumbnailData('p',{pictures:2,min_frames:2});c.renderThumbView();assert.equal(create.disabled,false);
  c.readThumbnailData('p',{pictures:0,min_frames:0,job:{status:'running'}});c.renderThumbView();assert.equal(create.disabled,true);
});
