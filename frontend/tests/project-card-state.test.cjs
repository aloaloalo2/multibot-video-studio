const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'..','app.js'),'utf8');
const stateSource=source.slice(source.indexOf('function projectProductionCardState('),source.indexOf('function renderOverview()'));
const exportSource=source.slice(source.indexOf('function updateOverviewExports()'),source.indexOf('let overviewExportRequest='));
const activitySource=source.slice(source.indexOf('function renderProjectActivities()'),source.indexOf('async function pollChannelActivity()'));

test('recognition and director status is replaced once and cleared when work ends',()=>{
  const classes=new Set(),children=[],actions=[],attributes={},activities=new Map([['p','розпізнавання озвучки']]);
  const open={insertBefore:node=>children.push(node),querySelector:()=>({})};
  const card={dataset:{projectId:'p'},classList:{toggle:(key,on)=>on?classes.add(key):classes.delete(key),contains:key=>classes.has(key)},
    setAttribute:(key,value)=>attributes[key]=value,querySelector:s=>s==='.project-actions'?{append:n=>actions.push(n)}:open,querySelectorAll:()=>[...children,...actions]};
  const document={querySelectorAll:()=>[card],createElement:()=>({setAttribute(){},remove(){const list=actions.includes(this)?actions:children;list.splice(list.indexOf(this),1);}})};
  const c=vm.createContext({document,projectActivities:activities,exportSpinner:'spinner'});
  vm.runInContext(activitySource,c);
  const render=()=>vm.runInContext('renderProjectActivities()',c);
  render();render();
  assert.equal(children.length,1);assert.equal(classes.has('stage-working'),true);assert.equal(attributes['aria-busy'],'true');
  assert.match(children[0].innerHTML,/Розпізнаємо озвучку/);
  activities.set('p','режисура');render();assert.equal(children.length,1);assert.match(children[0].innerHTML,/Режисер складає план/);
  activities.set('p',{kind:'озвучення сценарію',progress:42});render();assert.match(children[0].innerHTML,/Озвучуємо сценарій · 42%/);
  activities.set('p','створення сценарію');render();assert.equal(children.length,1);assert.match(children[0].innerHTML,/spinner/);assert.match(children[0].innerHTML,/Opus пише сценарій/);
  assert.equal(actions.length,1);render();assert.equal(actions.length,1);
  activities.set('p','створення зачинів');render();assert.match(children[0].innerHTML,/Opus готує зачини/);
  activities.clear();render();assert.equal(children.length,0);assert.equal(actions.length,0);assert.equal(classes.has('stage-working'),false);assert.equal(attributes['aria-busy'],'false');
  classes.add('exporting');render();assert.equal(attributes['aria-busy'],'true');
});

test('an old failed job with every frame made no longer shows a stopped warning',()=>{
  const c=vm.createContext({});vm.runInContext(stateSource,c);
  const read=r=>JSON.parse(JSON.stringify(vm.runInContext(`projectProductionCardState(${JSON.stringify(r)})`,c)));
  assert.equal(read({status:'failed',frames:107,made:107}).stopped,false);
  assert.equal(read({status:'failed',frames:107,made:86}).stopped,true);
  assert.equal(read({status:'failed',frames:107,made:107,quality:{passed:false}}).stopped,true);
  assert.equal(read({status:'in_progress',frames:107,made:107}).working,true);
});
test('export progress takes the single status slot and restores production status when export ends',()=>{
  const making={hidden:false},control={hidden:false},box={hidden:true,replaceChildren(){this.innerHTML='';}},classes=new Set(['production-stopped']);
  const card={dataset:{projectId:'p'},classList:{toggle:(key,on)=>on?classes.add(key):classes.delete(key),contains:key=>classes.has(key)},
    setAttribute(){},querySelectorAll:()=>[],querySelector:selector=>({'.project-making':making,'.project-production-control':control,'.project-export-state':box})[selector]};
  const jobs=new Map([['p',{status:'running',stage:'razgon_frames',razgon_completed:0,razgon_total:107,progress:0}]]);
  const c=vm.createContext({$:()=>({querySelectorAll:()=>[card]}),state:{projectExports:jobs},exportSpinner:'spinner'});
  vm.runInContext(exportSource,c);vm.runInContext('updateOverviewExports()',c);
  assert.equal(making.hidden,true);assert.equal(control.hidden,true);assert.equal(box.hidden,false);
  assert.match(box.innerHTML,/Експорт · 0\/107/);
  jobs.clear();vm.runInContext('updateOverviewExports()',c);
  assert.equal(making.hidden,false);assert.equal(control.hidden,false);assert.equal(box.hidden,true);
});

test('export leaves thumbnail creation available while destructive card actions stay locked',()=>{
  const buttons=['thumbnail','delete','space','rename'].map(kind=>({kind,disabled:false,classList:{contains:name=>name===kind}}));
  const box={replaceChildren(){}};
  const card={dataset:{projectId:'p'},classList:{toggle(){},contains:()=>false},setAttribute(){},
    querySelectorAll:()=>buttons,querySelector:s=>s==='.project-export-state'?box:null};
  const jobs=new Map([['p',{status:'queued',queue_position:1}]]);
  const c=vm.createContext({$:()=>({querySelectorAll:()=>[card]}),state:{projectExports:jobs},exportSpinner:'spinner',exportQueueLabel:()=> 'У черзі'});
  vm.runInContext(exportSource,c);c.updateOverviewExports();
  assert.equal(buttons[0].disabled,false);
  assert.ok(buttons.slice(1).every(button=>button.disabled));
  jobs.clear();c.updateOverviewExports();
  assert.ok(buttons.every(button=>!button.disabled));
});

test('completion marks use gray for work and gold for export, with no mark after acknowledgement',()=>{
  const block=source.slice(source.indexOf('function completionMark('),source.indexOf('async function markProjectSeen('));
  const c=vm.createContext({});vm.runInContext(block,c);
  assert.equal(c.completionMark({}), '');
  assert.match(c.completionMark({completion_notice:{kind:'process'}}),/Роботу завершено/);
  assert.doesNotMatch(c.completionMark({completion_notice:{kind:'process'}}),/is-exported/);
  assert.match(c.completionMark({completion_notice:{kind:'export'}}),/is-exported/);
});


test('opening consumes only a notice the overview actually showed, never a newer completion',async()=>{
  const project={id:'p'},calls=[],state={projects:[project]};let release;
  const block=source.slice(source.indexOf('async function markProjectSeen('),source.indexOf('function projectCardHeading('));
  const c=vm.createContext({state,console,api:(...args)=>{calls.push(args);return new Promise(resolve=>release=resolve);}});
  vm.runInContext(block,c);await c.markProjectSeen('p');assert.equal(calls.length,0);
  project.completion_notice={kind:'process',at:10};const pending=c.markProjectSeen('p');
  assert.equal(calls[0][2].through,10);
  project.completion_notice={kind:'export',at:20};release({seen:true});await pending;
  assert.equal(project.completion_notice.kind,'export');
  const next=c.markProjectSeen('p');release({seen:true});await next;
  assert.equal(project.completion_notice,null);
});

test('automatic export polling never acknowledges a result before its card is shown',async()=>{
  const block=source.slice(source.indexOf('async function pollJob('),source.indexOf("\n$('add-channel')",source.indexOf('async function pollJob(')));
  let seen=0;
  const c=vm.createContext({state:{job:{id:'job',project_id:'p'},project:{id:'p'},poll:null},jobPollInFlight:false,jobPollFailures:0,
    api:async()=>({job:{id:'job',project_id:'p',status:'complete'}}),updateExportLock(){},$:()=>null,
    status(){},markProjectSeen:()=>seen++,clearTimeout(){},scheduleJobPoll(){}});
  vm.runInContext(block,c);await c.pollJob();assert.equal(seen,0);
});


test('a newer successful export takes priority over an old failed production card without erasing its review',()=>{
  const c=vm.createContext({});vm.runInContext(stateSource,c);
  const request={status:'failed',frames:66,made:66,finished_at:100,quality:{passed:false}};
  assert.equal(c.projectProductionCardState(request,110).stopped,false);
  assert.equal(c.projectProductionCardState(request,90).stopped,true);
  assert.equal(c.projectProductionCardState({...request,finished_at:120},110).stopped,true);
  assert.equal(c.projectProductionCardState({...request,status:'in_progress'},110).working,true);
  assert.equal(request.quality.passed,false);
});

test('delete follows live project work and unlocks only after all known activity ends',()=>{
  const button={},classes=new Set(),activities=new Map();
  const card={dataset:{projectId:'p'},classList:{contains:name=>classes.has(name)},querySelector:()=>button};
  const helper=source.slice(source.indexOf('function updateProjectDeleteButton('),source.indexOf('async function pollChannelActivity('));
  const c=vm.createContext({projectActivities:activities,card});vm.runInContext(helper,c);
  for(const kind of ['створення сценарію','озвучення сценарію','розпізнавання озвучки','режисура',"прев'ю",'музика й ефекти','мови']){
    activities.set('p',kind);button.disabled=false;c.updateProjectDeleteButton(card);
    assert.equal(button.disabled,true);assert.match(button.title,/Видалення доступне/);
  }
  activities.clear();classes.add('exporting');c.updateProjectDeleteButton(card);assert.equal(button.disabled,true);
  classes.clear();classes.add('thumb-running');c.updateProjectDeleteButton(card);assert.equal(button.disabled,true);
  classes.clear();c.updateProjectDeleteButton(card);assert.equal(button.disabled,false);assert.equal(button.title,'Видалити випуск');
});
