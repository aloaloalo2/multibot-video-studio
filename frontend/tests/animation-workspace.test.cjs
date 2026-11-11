const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const director=fs.readFileSync(path.join(__dirname,'../director.js'),'utf8');
const plan=fs.readFileSync(path.join(__dirname,'../plan.js'),'utf8');

test('universal creation progress refreshes without replacing timeline edits or selection',async()=>{
  const tracks=[{id:'local-edit'}],request={status:'in_progress',frames:45};let refreshed=0,drawn=0;
  const state={view:'editor',project:{id:'p',tracks,production_request:{status:'requested'}},selected:'clip-a'};
  const c=vm.createContext({state,api:async()=>({project:{id:'p',tracks:[{id:'server-copy'}],production_request:request,production:{plan_ready:true}}}),
    projectAnimated:()=>false,directMontage:()=>false,refreshEpisode(){},loadDrawn:()=>drawn++,renderMontageMake:()=>refreshed++});
  vm.runInContext(director.slice(director.indexOf('const productionPolls='),director.indexOf('async function startDirector(')),c);
  await c.pollProduction('p');
  assert.equal(state.project.tracks,tracks);assert.equal(state.selected,'clip-a');assert.equal(state.project.production_request,request);
  assert.equal(refreshed,1);assert.equal(drawn,1);
});

test('a response arriving after switching projects does not update the new animation',async()=>{
  let release;const pending=new Promise(resolve=>release=resolve),state={view:'editor',project:{id:'p'}};
  const c=vm.createContext({state,api:()=>pending,refreshEpisode(){},projectAnimated:()=>true,directMontage:()=>false,
    loadDrawn:()=>assert.fail('Old project must not refresh'),renderMontageMake:()=>assert.fail('Old project must not render')});
  vm.runInContext(director.slice(director.indexOf('const productionPolls='),director.indexOf('async function startDirector(')),c);
  const run=c.pollProduction('p');state.project={id:'new'};release({project:{id:'p'}});await run;assert.equal(state.project.id,'new');
});

test('newly created frames and media reach the montage without reloading or moving the playhead',async()=>{
  const app=fs.readFileSync(path.join(__dirname,'../app.js'),'utf8'),calls=[];
  const incoming={id:'p',revision:2,tracks:[{id:'new-frame'}],production_request:{status:'in_progress'}};
  const state={view:'editor',navigation:1,project:{id:'p',revision:1,tracks:[]},assets:[],playhead:7,selected:'clip-a'};
  const c=vm.createContext({state,api:async url=>{calls.push(url);return url.endsWith('/assets')?{assets:[{id:'image'}]}:{project:incoming}},
    buildAudioNodes(){},renderProject(){},loadDrawn(){},renderMontageMake(){},refreshEpisode(){}});
  vm.runInContext(app.slice(app.indexOf('async function refreshCurrentProject('),app.indexOf('async function useAsset(')),c);
  vm.runInContext(director.slice(director.indexOf('const productionPolls='),director.indexOf('async function startDirector(')),c);
  await c.pollProduction('p');
  assert.equal(state.project.tracks[0].id,'new-frame');assert.equal(state.assets[0].id,'image');
  assert.equal(state.playhead,7);assert.equal(state.selected,'clip-a');
  assert.deepEqual(calls,['/api/projects/p','/api/projects/p/assets']);
  await c.pollProduction('p');assert.equal(calls.filter(x=>x.endsWith('/assets')).length,1);
});

test('production reads join while pending and recover after a temporary failure',async()=>{
  let reject,calls=0,refreshes=0;const state={view:'editor',navigation:1,project:{id:'p',revision:1}};
  const c=vm.createContext({state,api:()=>{calls++;return new Promise((_,fail)=>reject=fail)},refreshEpisode:()=>refreshes++,console:{warn(){}}});
  vm.runInContext(director.slice(director.indexOf('const productionPolls='),director.indexOf('async function startDirector(')),c);
  const first=c.pollProduction('p');await c.pollProduction('p');assert.equal(calls,1);
  reject(Error('Connection lost'));await first;assert.equal(refreshes,1);
  const retry=c.pollProduction('p');assert.equal(calls,2);reject(Error('Still offline'));await retry;
});

test('an empty animation can open the combined audio, plan and montage workspace',()=>{
  const state={channels:[],project:null};const c=vm.createContext({state,projectAnimated:p=>p?.project_kind==='animated'});
  vm.runInContext(plan.slice(0,plan.indexOf('const editorLockedHint=')),c);
  assert.equal(c.editorUnlocked({project_kind:'animated',tracks:[]}),true);
  assert.equal(c.editorUnlocked({project_kind:'regular',tracks:[]}),true);
  assert.equal(c.editorUnlocked(null),false);
  assert.equal(c.editorUnlocked({project_kind:'regular',plan_mode:'direct',tracks:[]}),true);
});

test('an imported plan without an audio asset ID uses the original narration on the timeline',()=>{
  const c=vm.createContext({});
  vm.runInContext(director.slice(director.indexOf('function voiceAssetId('),director.indexOf('function voicePlayer(')),c);
  assert.equal(c.voiceAssetId({timing:{audio:{duration:815}}},{audio_gain:{original:1}}),'original');
  assert.equal(c.voiceAssetId({timing:{audio:{asset_id:'saved'}}},{assets:[{id:'saved'}],audio_gain:{original:1}}),'saved');
  assert.equal(c.voiceAssetId({timing:{audio:{duration:815}}},{}),null);
  assert.equal(c.voiceAssetId({timing:{}},{audio_gain:{music:1}}),null);
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


test('planned frames remain visible before media exists and disappear when their intervals are filled',()=>{
  const groups=fs.readFileSync(path.join(__dirname,'../groups.js'),'utf8');
  const state={plan:{frames:[{number:1,start:0,end:5},{number:2,start:5,end:10}]}},c=vm.createContext({state,directMontage:()=>false});
  vm.runInContext(groups.slice(groups.indexOf('function plannedTimelineFrames('),groups.indexOf('function appendPlannedFrames(')),c);
  assert.equal(c.plannedTimelineFrames().length,2);
  assert.equal(c.missingPlannedFrames(state.plan.frames,[]).length,2);
  assert.equal(c.missingPlannedFrames(state.plan.frames,[{start:0,end:5}])[0].number,2);
  assert.equal(c.missingPlannedFrames(state.plan.frames,[{start:0,end:10}]).length,0);
  c.directMontage=()=>true;assert.equal(c.plannedTimelineFrames().length,0);
});

test('Whisper progress replaces the ready label and prevents starting another analysis',()=>{
  const header={},range={value:'90'},planButton={},controls=[range,planButton],note={textContent:'Озвучка готова'},text={};
  const ready={dataset:{speed:'90'},attrs:{},setAttribute(k,v){this.attrs[k]=v},getAttribute(k){return this.attrs[k]},removeAttribute(k){delete this.attrs[k]},
    querySelector(s){return s.includes('strong')?header:s==='input'?range:planButton},querySelectorAll(){return controls}};
  const panel={querySelector(s){return s==='.narration-ready'?ready:s==='textarea'?text:note}};
  const state={analysis:{job:{project_id:'p',status:'running',stage:'recognizing',progress:43}}};
  const c=vm.createContext({state,exportSpinner:'<i>spinner</i>',speechStageNames:{recognizing:'Розпізнаємо озвучку'},esc:s=>s});
  vm.runInContext(plan.slice(plan.indexOf('function renderNarrationAnalysis('),plan.indexOf('function appendReadyNarration(')),c);
  assert.equal(c.renderNarrationAnalysis(panel,'p'),true);
  assert.match(header.innerHTML,/Whisper.*43%/);assert.equal(planButton.disabled,true);assert.equal(note.textContent,'');
  state.analysis.job.status='failed';state.analysis.job.error='Recognition stopped';
  assert.equal(c.renderNarrationAnalysis(panel,'p'),false);assert.equal(planButton.disabled,false);assert.equal(text.readOnly,false);
  assert.equal(note.textContent,'Recognition stopped');
  state.analysis={job:{project_id:'p',status:'complete'},report:{status:'needs_review',applied:false,phrases:[{number:36,issues:['low_phrase_match']}]}};
  assert.equal(c.renderNarrationAnalysis(panel,'p'),false);assert.match(note.textContent,/фрази 36/);
  state.analysis.report.sequence_verification={source:'generated_takes'};
  state.analysis.report.phrases=[{number:7,issues:['out_of_order']},{number:36,issues:['low_phrase_match']}];
  c.renderNarrationAnalysis(panel,'p');assert.match(note.textContent,/фрази 7$/);
  state.analysis.report.applied=true;c.renderNarrationAnalysis(panel,'p');assert.equal(note.textContent,'');
});

test('Create video submits one combined action and rejects an older server before starting work',async()=>{
  const calls=[],c=vm.createContext({directMontage:()=>false,api:async(path,method,body)=>{calls.push({path,method,body});return path==='/api/health'?{create_video:true}:{job:{id:'j'}};}});
  vm.runInContext(plan.slice(plan.indexOf('function videoCreationCopy('),plan.indexOf('function narrationChoices(')),c);
  assert.equal(c.videoCreationCopy().label,'Створити відео');
  assert.equal(c.videoCreationCopy().note,'');
  await c.startVideoCreation('p',{asset_id:'voice',script:'text'});
  assert.equal(calls.length,2);assert.equal(calls[1].path,'/api/projects/p/create-video');assert.equal(calls[1].body.asset_id,'voice');
  calls.length=0;c.api=async path=>{calls.push(path);return {};};
  await assert.rejects(c.startVideoCreation('p',{asset_id:'voice'}),/перезапуску/);assert.equal(calls.length,1);
  c.directMontage=()=>true;calls.length=0;await c.startVideoCreation('p',{asset_id:'voice'});
  assert.equal(calls[0],'/api/projects/p/plan/analyze');
});


test('speed confirmation estimates duration from the applied speed without compounding it',()=>{
  const c=vm.createContext({});vm.runInContext(plan.slice(plan.indexOf('function narrationSpeedPreview('),plan.indexOf('function openNarrationSpeed(')),c);
  let preview=c.narrationSpeedPreview(1000,.9,100);assert.equal(preview.duration,900);assert.equal(preview.delta,-100);
  preview=c.narrationSpeedPreview(900,1,90);assert.equal(preview.duration,1000);assert.equal(preview.delta,100);
  preview=c.narrationSpeedPreview(945.821,.91,91);assert.ok(Math.abs(preview.delta)<.000001);
});

test('speed settings preview changes locally and apply audio only after confirmation',async()=>{
  let action,changed,requests=0,refreshed=0,closed=0;
  const range={value:'91',addEventListener:(name,fn)=>changed=fn},apply={},value={},summary={},error={},planButton={},gear={};
  const ready={isConnected:true,querySelector:s=>s==='audio'?{duration:945.821,pause(){}}:s==='.narration-plan-action'?planButton:gear,remove(){}};
  const output={},control=(value,checked=false)=>({value,checked,addEventListener(){},closest:()=>({querySelector:()=>output})});
  const controls={'[data-reverb=enabled]':control('',false),'[data-reverb=preset]':control('office'),'[data-reverb=amount]':control('25'),'[data-noise=enabled]':control('',false),'[data-noise=amount]':control('35'),'[data-noise=preset]':control('office'),'.voice-reverb-options':{},'.voice-noise-options':{},'.voice-local-preview':{append(){}}};
  const body={querySelector:key=>controls[key],querySelectorAll:()=>[]};
  const elements={'modal-body':body,'narration-speed-range':range,'narration-speed-value':value,'narration-speed-summary':summary,'narration-speed-error':error,'modal-actions':{querySelector:()=>apply}};
  const c=vm.createContext({state:{project:{id:'p'}},$:id=>elements[id],clock:s=>`${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`,
    modal:(title,body,actions)=>action=actions[0],closeModal:()=>closed++,api:async(url,method,body)=>{requests++;assert.equal(url,'/api/projects/p/narration/speed');assert.equal(body.speed,1);}});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../channel-voice-lab.js'),'utf8').split('// Compare the parameters')[0],c);
  c.esc=String;
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../audio-effects.js'),'utf8'),c);
  c.voicePlayer=()=>({querySelector:()=>({})});c.attachVoiceEffects=()=>({update(){},dispose(){}});
  let stoppedNoise=0;c.bindVoiceNoisePreview=()=>({dispose(){stoppedNoise++}});
  vm.runInContext(plan.slice(plan.indexOf('function narrationSpeedPreview('),plan.indexOf('function appendReadyNarration(')),c);
  c.openNarrationSpeed('p',{speed:.91,duration:945.821},ready,async()=>refreshed++);
  assert.equal(apply.disabled,true);range.value='100';changed();assert.equal(requests,0);assert.equal(apply.disabled,false);assert.match(summary.textContent,/14:21/);
  apply.disabled=true; // the shared modal wrapper locks the clicked button before invoking its action
  await action.run();assert.equal(requests,1);assert.equal(refreshed,1);assert.equal(closed,1);
  body.channelSettingsCleanup();assert.equal(stoppedNoise,1);
});

test('reopening the same project starts its own status read and ignores the earlier visit',async()=>{
  const replies=[];let renders=0;const state={view:'editor',navigation:1,project:{id:'p',revision:1}};
  const c=vm.createContext({state,api:()=>new Promise(resolve=>replies.push(resolve)),loadDrawn(){},renderMontageMake:()=>renders++,refreshEpisode(){}});
  vm.runInContext(director.slice(director.indexOf('const productionPolls='),director.indexOf('async function startDirector(')),c);
  const first=c.pollProduction('p');state.navigation++;
  const reopened=c.pollProduction('p');assert.equal(replies.length,2);
  replies[1]({project:{id:'p',revision:1,production_request:{status:'done'}}});await reopened;
  replies[0]({project:{id:'p',revision:1,production_request:{status:'in_progress'}}});await first;
  assert.equal(state.project.production_request.status,'done');assert.equal(renders,1);
});
