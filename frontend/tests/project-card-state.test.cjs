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
  const classes=new Set(),children=[],attributes={},activities=new Map([['p','розпізнавання озвучки']]);
  const open={insertBefore:node=>children.push(node),querySelector:()=>({})};
  const card={dataset:{projectId:'p'},classList:{toggle:(key,on)=>on?classes.add(key):classes.delete(key),contains:key=>classes.has(key)},
    setAttribute:(key,value)=>attributes[key]=value,querySelector:()=>open,querySelectorAll:()=>[...children]};
  const document={querySelectorAll:()=>[card],createElement:()=>({setAttribute(){},remove(){children.splice(children.indexOf(this),1);}})};
  const c=vm.createContext({document,projectActivities:activities,exportSpinner:'spinner'});
  vm.runInContext(activitySource,c);
  const render=()=>vm.runInContext('renderProjectActivities()',c);
  render();render();
  assert.equal(children.length,1);assert.equal(classes.has('stage-working'),true);assert.equal(attributes['aria-busy'],'true');
  assert.match(children[0].innerHTML,/Розпізнаємо озвучку/);
  activities.set('p','режисура');render();assert.equal(children.length,1);assert.match(children[0].innerHTML,/Режисер складає план/);
  activities.clear();render();assert.equal(children.length,0);assert.equal(classes.has('stage-working'),false);assert.equal(attributes['aria-busy'],'false');
  classes.add('exporting');render();assert.equal(attributes['aria-busy'],'true');
});

test('an old failed job with every frame made no longer shows a stopped warning',()=>{
  const c=vm.createContext({});vm.runInContext(stateSource,c);
  const read=r=>JSON.parse(JSON.stringify(vm.runInContext(`projectProductionCardState(${JSON.stringify(r)})`,c)));
  assert.equal(read({status:'failed',frames:107,made:107}).stopped,false);
  assert.equal(read({status:'failed',frames:107,made:86}).stopped,true);
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
