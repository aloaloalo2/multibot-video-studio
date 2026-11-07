const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const director=fs.readFileSync(path.join(__dirname,'../director.js'),'utf8');
const plan=fs.readFileSync(path.join(__dirname,'../plan.js'),'utf8');

test('animation creation progress refreshes without replacing timeline edits or selection',async()=>{
  const tracks=[{id:'local-edit'}],request={status:'in_progress',frames:45};let refreshed=0,drawn=0;
  const state={view:'editor',project:{id:'p',tracks,production_request:{status:'requested'}},selected:'clip-a'};
  const c=vm.createContext({state,api:async()=>({project:{id:'p',tracks:[{id:'server-copy'}],production_request:request,production:{plan_ready:true}}}),
    projectAnimated:()=>true,directMontage:()=>false,loadDrawn:()=>drawn++,renderMontageMake:()=>refreshed++});
  vm.runInContext(director.slice(director.indexOf('async function pollProduction('),director.indexOf('async function startDirector(')),c);
  await c.pollProduction('p');
  assert.equal(state.project.tracks,tracks);assert.equal(state.selected,'clip-a');assert.equal(state.project.production_request,request);
  assert.equal(refreshed,1);assert.equal(drawn,1);
});

test('a response arriving after switching projects does not update the new animation',async()=>{
  let release;const pending=new Promise(resolve=>release=resolve),state={view:'editor',project:{id:'p'}};
  const c=vm.createContext({state,api:()=>pending,refreshEpisode(){},projectAnimated:()=>true,directMontage:()=>false,
    loadDrawn:()=>assert.fail('Old project must not refresh'),renderMontageMake:()=>assert.fail('Old project must not render')});
  vm.runInContext(director.slice(director.indexOf('async function pollProduction('),director.indexOf('async function startDirector(')),c);
  const run=c.pollProduction('p');state.project={id:'new'};release({project:{id:'p'}});await run;assert.equal(state.project.id,'new');
});

test('an empty animation can open the combined audio, plan and montage workspace',()=>{
  const state={channels:[],project:null};const c=vm.createContext({state,projectAnimated:p=>p?.project_kind==='animated'});
  vm.runInContext(plan.slice(0,plan.indexOf('const editorLockedHint=')),c);
  assert.equal(c.editorUnlocked({project_kind:'animated',tracks:[]}),true);
  assert.equal(c.editorUnlocked({project_kind:'regular',tracks:[]}),false);
  assert.equal(c.editorUnlocked({project_kind:'regular',plan_mode:'direct',tracks:[]}),true);
});

test('an imported plan without an audio asset ID uses the original narration on the timeline',()=>{
  const c=vm.createContext({});
  vm.runInContext(director.slice(director.indexOf('function voiceAssetId('),director.indexOf('function voicePlayer(')),c);
  assert.equal(c.voiceAssetId({timing:{audio:{duration:815}}},{audio_gain:{original:1}}),'original');
  assert.equal(c.voiceAssetId({timing:{audio:{asset_id:'saved'}}},{assets:[{id:'saved'}],audio_gain:{original:1}}),'saved');
  assert.equal(c.voiceAssetId({timing:{audio:{duration:815}}},{}),null);
});

test('starting frames from Animation stays in the combined workspace and sends one request',async()=>{
  const tracks=[{id:'local'}],request={status:'in_progress',frames:2},calls=[];let refreshed=0;
  const state={view:'editor',project:{id:'p',tracks},plan:{frames:[{},{}]},selected:'clip-a'};
  const c=vm.createContext({state,makeCount:{},renderMontageMake:()=>refreshed++,planFrameWord:()=>'',
    api:async(...args)=>{calls.push(args);return {project:{production_request:request,production:{plan_ready:true}}};},
    showProjectList:()=>assert.fail('Starting in Animation must stay in Animation'),status:()=>assert.fail('Unexpected error')});
  vm.runInContext(director.slice(director.indexOf('async function startMaking('),director.indexOf('// The director\'s report belongs')),c);
  const button={disabled:false,closest:selector=>selector==='.episode-make'?{dataset:{floor:'0'}}:{}};
  await c.startMaking(button);
  assert.equal(calls.length,1);assert.equal(calls[0][0],'/api/projects/p/production-request');assert.equal(calls[0][2].frames,2);
  assert.equal(state.project.tracks,tracks);assert.equal(state.project.production_request,request);assert.equal(state.view,'editor');assert.equal(refreshed,1);
});
