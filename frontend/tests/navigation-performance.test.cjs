const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../app.js'),'utf8');
const section=(from,to)=>source.slice(source.indexOf(from),source.indexOf(to));

test('editor actions stay hidden in the initial HTML while project data loads',()=>{
  const html=fs.readFileSync(path.join(__dirname,'../index.html'),'utf8');
  for(const id of ['export-open','undo','redo']){
    const button=html.match(new RegExp(`<button\\b[^>]*id="${id}"[^>]*>`))?.[0];
    assert.ok(button,id);assert.match(button,/\bhidden\b/);
  }
});

test('asset lookup reuses its index and follows appended or replaced media lists',()=>{
  let builds=0;
  const observed=items=>new Proxy(items,{get(target,key){if(key==='map')builds++;return Reflect.get(target,key);}});
  const first={id:'a',name:'Original'},assets=observed([first]);
  const context=vm.createContext({state:{assets}});
  vm.runInContext(section('let indexedAssets=','function buildAudioNodes('),context);
  for(let n=0;n<100;n++)assert.equal(context.assetById('a'),first);
  assert.equal(builds,1);
  first.name='Updated';assert.equal(context.assetById('a').name,'Updated');
  const second={id:'b'};assets.push(second);assert.equal(context.assetById('b'),second);
  assert.equal(builds,2);
  const replacement={id:'c'};context.state.assets=observed([replacement]);
  assert.equal(context.assetById('a'),undefined);assert.equal(context.assetById('c'),replacement);
  context.state.assets=[];assert.equal(context.assetById('c'),undefined);
});

test('a slow page restore cannot replace a newer route or its channel list',async()=>{
  for(const change of ['route','generation']){
    let resolveChannels,draws=0;
    const state={channels:[{id:'current'}]},location={pathname:'/old'};
    const context=vm.createContext({state,location,restoreGeneration:0,locationRoute:()=>({channelId:'old'}),
      api:url=>url==='/api/health'?Promise.resolve({api_version:2,layer_mode:'item',plan_workflow:'audio_required'}):new Promise(resolve=>resolveChannels=resolve),
      renderChannels:()=>draws++,selectChannel:()=>assert.fail('Stale restore selected a channel')});
    vm.runInContext(section('async function loadChannels(','function channelIdentityIcon('),context);
    const pending=context.loadChannels(undefined,{restoreLocation:true});
    if(change==='route')location.pathname='/new';else context.restoreGeneration++;
    resolveChannels({channels:[{id:'old'}]});
    assert.equal(await pending,false);assert.equal(draws,0);assert.equal(state.channels[0].id,'current');
  }
});

test('browser navigation invalidates pending project reads before awaiting restore data',async()=>{
  let finish;
  const state={navigation:5,project:{id:'open'}},elements={};
  const context=vm.createContext({state,location:{pathname:'/next'},
    $:id=>elements[id]??=( {} ),clearTimeout(){},locationRoute:()=>({projectId:'next'}),
    loadChannels:()=>new Promise(resolve=>finish=resolve)});
  vm.runInContext(section('let restoreGeneration=','function syncRoute('),context);
  const pending=context.restoreCurrentLocation();
  assert.equal(state.navigation,6);assert.equal(state.restoringProject,true);
  finish();await pending;
});

test('channel selection renders once and ignores an older response',async()=>{
  const requests={},renders=[];
  const state={navigation:0,channels:[{id:'a'},{id:'b'}]};
  const context=vm.createContext({state,cancelLocationRestore(){},stopPlayback(){},
    api:url=>new Promise(resolve=>requests[url]=resolve),renderChannels(){},
    renderProject:()=>renders.push(state.channel.id),syncRoute(){},status(){}});
  vm.runInContext(section('async function selectChannel(','function projectActions('),context);
  const older=context.selectChannel('a'),newer=context.selectChannel('b');
  requests['/api/projects?channel=b']({projects:[{id:'new'}]});assert.equal(await newer,true);
  requests['/api/projects?channel=a']({projects:[{id:'old'}]});assert.equal(await older,false);
  assert.deepEqual(renders,['b']);assert.equal(state.projects[0].id,'new');
});

test('activity polling reads phrase progress only for active narration and prevents overlapping polls',async()=>{
  let resolveStatus;const requests=[];
  const channelActivity=new Set(),projectActivities=new Map(),state={project:{id:'idle'},channels:[{id:'c',name:'Channel'}]};
  const context=vm.createContext({state,channelActivity,projectActivities,channelActivityPending:false,
    document:{hidden:false,querySelectorAll:()=>[]},renderProjectActivities(){},console,
    api:async url=>{
      requests.push(url);
      if(url==='/api/studio/status')return new Promise(resolve=>resolveStatus=resolve);
      return {job:{status:'running',completed:3,total:10}};
    }});
  vm.runInContext(section('async function pollChannelActivity(','(function channelActivityLoop('),context);
  const pending=context.pollChannelActivity();await context.pollChannelActivity();
  assert.deepEqual(requests,['/api/studio/status']);
  resolveStatus({activities:[{project_id:'active',kind:'озвучення сценарію'}],active_channels:['c'],busy:[]});await pending;
  assert.deepEqual(requests,['/api/studio/status','/api/projects/active/narration']);
  assert.equal(projectActivities.get('active').progress,30);assert.ok(channelActivity.has('c'));
  const idle=context.pollChannelActivity();resolveStatus({activities:[],active_channels:[],busy:[]});await idle;
  assert.deepEqual(requests,['/api/studio/status','/api/projects/active/narration','/api/studio/status']);
  assert.equal(projectActivities.size,0);assert.equal(channelActivity.size,0);
});


test('overview discovers director-to-frames handoff and new production without a reload',async()=>{
  const projectActivities=new Map([['p','режисура']]),state={project:null,projects:[{id:'p'}],channels:[]};
  let refreshes=0;
  const context=vm.createContext({state,projectActivities,channelActivity:new Set(),channelActivityPending:false,
    document:{hidden:false,querySelectorAll:()=>[]},renderProjectActivities(){},console,
    api:async()=>({activities:[{project_id:'p',kind:'створення кадрів'}],active_channels:[],busy:[]}),
    refreshProjects:async()=>{refreshes++;state.projects=[{id:'p',production_request:{status:'in_progress'}}];}});
  vm.runInContext(section('async function pollChannelActivity(','(function channelActivityLoop('),context);
  await context.pollChannelActivity();assert.equal(refreshes,1);
  await context.pollChannelActivity();assert.equal(refreshes,1); // normal production polling owns later counts
  state.projects=[{id:'p'}];await context.pollChannelActivity();assert.equal(refreshes,2); // first active snapshot without previous director
  state.project={id:'p'};state.projects=[{id:'p'}];await context.pollChannelActivity();assert.equal(refreshes,2);
});

test('project and media refresh commit together and never overwrite newer navigation or edits',async()=>{
  for(const changed of ['navigation','revision','none']){
    const pending={},state={navigation:1,project:{id:'p',revision:3},assets:[{id:'saved'}]};let renders=0;
    const context=vm.createContext({state,api:url=>new Promise(resolve=>pending[url]=resolve),buildAudioNodes(){},renderProject:()=>renders++});
    vm.runInContext(section('async function refreshCurrentProject(','async function useAsset('),context);
    const refresh=context.refreshCurrentProject();
    assert.equal(Object.keys(pending).length,2);
    pending['/api/projects/p']({project:{id:'p',revision:3}});
    if(changed==='navigation'){state.project={id:'other',revision:10};state.navigation++;}
    if(changed==='revision')state.project={id:'p',revision:4};
    pending['/api/projects/p/assets']({assets:[{id:'incoming'}]});
    assert.equal(await refresh,changed==='none');
    assert.equal(state.assets[0].id,changed==='none'?'incoming':'saved');
    assert.equal(renders,changed==='none'?1:0);
  }
});

test('a downloaded stock asset never lands in a project opened during its import',async()=>{
  let finish,refreshes=0,placements=0;
  const state={navigation:1,project:{id:'p'},libraryTab:'pixabay'};
  const context=vm.createContext({state,api:()=>new Promise(resolve=>finish=resolve),
    refreshCurrentProject:()=>refreshes++,isUniversal:()=>true,useUniversalAsset:()=>placements++});
  vm.runInContext(section('async function useAsset(','function openAddAudio('),context);
  const importing=context.useAsset({id:'stock',kind:'video'},'old-scene');
  state.navigation++;state.project={id:'other'};
  finish({asset:{id:'downloaded'}});await importing;
  assert.equal(refreshes,0);assert.equal(placements,0);
});

test('stock search keeps the latest query and ignores older errors or replies after navigation',async()=>{
  const pending=[],state={navigation:1,search:'old',pixabayKind:'video',pixabay:[]};let renders=0;const messages=[];
  const context=vm.createContext({state,api:()=>new Promise((resolve,reject)=>pending.push({resolve,reject})),renderAssets:()=>renders++,status:text=>messages.push(text)});
  const start=source.indexOf('async function searchPixabay()');
  vm.runInContext(source.slice(start,source.indexOf('\nfunction selectLibraryTab(',start)),context);
  const old=context.searchPixabay();state.search='new';const fresh=context.searchPixabay();
  pending[1].resolve({results:[{id:'latest'}]});await fresh;
  pending[0].reject(Error('Late failure'));await old;
  assert.equal(state.pixabay[0].id,'latest');assert.equal(renders,1);assert.equal(messages.length,1);
  const switched=context.searchPixabay();state.navigation++;
  pending[2].resolve({results:[{id:'old-project'}]});await switched;
  assert.equal(state.pixabay[0].id,'latest');assert.equal(renders,1);
});

test('late edit success or failure cannot overwrite a reopened project or its save state',async()=>{
  for(const failed of [false,true]){
    let resolve,reject;const messages=[],save={textContent:'',classList:{add(){},remove(){}}};
    const state={project:{id:'p',revision:1},navigation:1};
    const c=vm.createContext({state,$:()=>save,api:()=>new Promise((ok,no)=>{resolve=ok;reject=no}),status:(...args)=>messages.push(args),renderProject:()=>assert.fail('Stale render')});
    vm.runInContext(section('async function action(','function openChannelSettings('),c);
    const pending=c.action('trim_scene',{});state.navigation++;state.project={id:'p',revision:50};save.textContent='New page';
    if(failed){reject(Error('Late failure'));await assert.rejects(pending,/Late failure/);}else{resolve({project:{id:'p',revision:2}});await pending;}
    assert.equal(state.project.revision,50);assert.equal(save.textContent,'New page');assert.deepEqual(messages,[]);
  }
});

test('a local file finishes in its original project without refreshing the page opened during upload',async()=>{
  let finish,refreshes=0;const requests=[],messages=[],state={project:{id:'p'},navigation:1};
  const c=vm.createContext({state,fetch:(url,options)=>{requests.push([url,options]);return new Promise(resolve=>finish=resolve)},refreshCurrentProject:()=>refreshes++,status:(...args)=>messages.push(args)});
  vm.runInContext(section('async function uploadLocalMedia(',"$('local-media-file').addEventListener"),c);
  const upload=c.uploadLocalMedia({name:'audio.wav'});state.navigation++;state.project={id:'other'};
  finish({ok:true,json:async()=>({asset:{id:'uploaded'}})});await upload;
  assert.equal(requests[0][0],'/api/projects/p/assets/upload');assert.equal(refreshes,0);assert.equal(messages.length,1);
});
