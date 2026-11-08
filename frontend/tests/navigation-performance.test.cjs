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
