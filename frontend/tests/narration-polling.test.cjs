const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../plan.js'),'utf8');
const begin=source.indexOf('  let narrationPollTimer='),end=source.indexOf('  button.onclick=async()=>',begin);
function fixture(api){
  const timers=new Map();let next=0,renders=0;
  const row={},state={project:{id:'p',channel_id:'channel'}},box={isConnected:true,classList:{toggle(){},remove(){}},querySelector:selector=>selector==='.narration-status-row'?row:null};
  const c=vm.createContext({api,state,box,pid:'p',busy:true,requestPending:false,currentJob:{status:'running'},voiceReady:true,quoteTimer:null,quoteVersion:0,
    text:{value:'Full saved script'},button:{setAttribute(){}},info:{},estimate:{},panel:{querySelector:()=>null},voiceScriptDraft:{},exportSpinner:'spinner',
    channelActivity:new Set(),projectActivities:new Map(),
    flushScriptDraft:async()=>{},renderRunning(){renders++},updateScriptWordCount(){},updateScriptHeadingVisibility(){},narrationResultVisible:j=>j?.status==='done',
    priceLabel:()=>'',appendReadyNarration(){renders++;return {dataset:{},hidden:false}},
    setTimeout:(fn,delay)=>{const id=++next;timers.set(id,{fn,delay});return id},clearTimeout:id=>timers.delete(id)});
  vm.runInContext(source.slice(source.indexOf('function narrationScriptValue('),source.indexOf('const createVideoIcon=')),c);
  vm.runInContext(source.slice(source.indexOf("  function actionState(mode='idle')"),source.indexOf('  function renderRunning(job)')),c);
  vm.runInContext(source.slice(begin,end),c);
  vm.runInContext(source.slice(end,source.indexOf('  loadProfile();poll();return box;',end)),c);
  return {c,state,box,timers,renders:()=>renders};
}
test('a late narration status cannot mark another project or channel busy',async()=>{
  let finish;const h=fixture(()=>new Promise(resolve=>finish=resolve));const pending=h.c.poll();
  h.state.project={id:'other',channel_id:'another-channel'};
  finish({job:{status:'running',total:10,completed:2}});await pending;
  assert.equal(h.c.channelActivity.size,0);assert.equal(h.c.projectActivities.size,0);assert.equal(h.renders(),0);assert.equal(h.timers.size,0);
});
test('narration start locks before saving or quoting and repeated clicks cannot submit twice',async()=>{
  let flush;const calls=[];
  const h=fixture(async(url,method)=>{calls.push({url,method});return method==='POST'?{total:271,cached:0,estimated_usd:0}:{job:{status:'running'}};});
  h.c.busy=false;h.c.flushScriptDraft=()=>new Promise(resolve=>flush=resolve);
  const pending=h.c.button.onclick();
  assert.equal(h.c.requestPending,true);assert.equal(h.c.button.disabled,true);assert.equal(h.c.text.readOnly,true);
  await h.c.button.onclick();await h.c.poll();assert.equal(calls.length,0);
  flush();await pending;
  assert.equal(calls.filter(call=>call.url.endsWith('/start')).length,1);
  assert.equal(calls.filter(call=>call.url.endsWith('/quote')).length,1);
  assert.equal(h.c.requestPending,false);assert.equal(h.c.busy,true);assert.equal(h.c.button.disabled,false);
});
test('a failed preparation unlocks an explicit retry without automatically starting speech',async()=>{
  const calls=[];const h=fixture(async(url,method)=>{calls.push({url,method});throw Error('Quote unavailable');});h.c.busy=false;
  await h.c.button.onclick();
  assert.equal(h.c.requestPending,false);assert.equal(h.c.button.disabled,false);assert.equal(h.c.text.readOnly,false);
  assert.equal(h.c.info.textContent,'Quote unavailable');assert.equal(calls.length,1);
  assert.ok(calls[0].url.endsWith('/quote'));
  assert.ok(h.timers.size>0);
});
test('leaving a project while quoting prevents the later paid start',async()=>{
  let finish,quoted;const requested=new Promise(resolve=>quoted=resolve);
  const calls=[];const h=fixture((url)=>{calls.push(url);return new Promise(resolve=>{finish=resolve;quoted();});});h.c.busy=false;
  const pending=h.c.button.onclick();await requested;
  h.state.project={id:'other'};finish({total:271,cached:0,estimated_usd:0});await pending;
  assert.equal(calls.length,1);assert.ok(calls[0].endsWith('/quote'));
});
test('cancellation stays locked during the request and can recover from a connection error',async()=>{
  let fail;const calls=[];const h=fixture(url=>{calls.push(url);return new Promise((_,reject)=>fail=reject);});
  const pending=h.c.button.onclick();await h.c.button.onclick();
  assert.equal(calls.length,1);assert.equal(h.c.button.disabled,true);
  fail(Error('Connection interrupted'));await pending;
  assert.equal(h.c.requestPending,false);assert.equal(h.c.busy,true);assert.equal(h.c.button.disabled,false);
  assert.ok(h.timers.size>0);
});
test('a status read error cannot enable speech for an empty or too-short script',async()=>{
  const h=fixture(async()=>{throw Error('Read unavailable');});h.c.busy=false;h.c.text.value='';
  await h.c.poll();assert.equal(h.c.button.disabled,true);
});
test('an older completed recording cannot hide the action for a newer saved script',async()=>{
  const h=fixture(async()=>({job:{status:'done',script:'Old recorded script.',asset_id:'old',started_at:5}}));h.c.busy=false;
  h.state.project.voice_script={text:'New saved script awaiting narration.',saved_at:10};
  let hasReady=true,ready;
  h.box.classList.toggle=(name,value)=>{if(name==='has-ready-narration')hasReady=value;};
  h.c.appendReadyNarration=()=>{hasReady=true;return ready={dataset:{},hidden:false};};
  await h.c.poll();
  assert.equal(ready.hidden,true);assert.equal(hasReady,false);assert.equal(h.c.button.hidden,false);
  assert.equal(h.c.button.disabled,false);assert.match(h.c.info.textContent,/Сценарій змінено/);
});
test('temporary status failure retries only GET and recovers without another paid start',async()=>{
  const calls=[];let count=0;
  const h=fixture(async(...args)=>{calls.push(args);if(!count++)throw Error('Connection interrupted');return {job:{status:'running',total:10,completed:2}}});
  await h.c.poll();assert.equal(h.timers.size,1);const timer=[...h.timers.values()][0];assert.equal(timer.delay,3000);
  await timer.fn();assert.equal(calls.length,2);assert.ok(calls.every(args=>args.length===1));assert.equal(h.renders(),1);
});
test('concurrent polling joins one read and an empty job releases the busy UI',async()=>{
  let finish,calls=0;const h=fixture(()=>{calls++;return new Promise(resolve=>finish=resolve)});
  const pending=h.c.poll();await h.c.poll();assert.equal(calls,1);
  finish({job:{}});await pending;assert.equal(h.c.busy,false);assert.equal(h.c.currentJob,null);
});
test('a closed narration panel does not retry or display a late error',async()=>{
  let fail;const h=fixture(()=>new Promise((_,reject)=>fail=reject));const pending=h.c.poll();
  h.box.isConnected=false;fail(Error('Late failure'));await pending;assert.equal(h.timers.size,0);assert.equal(h.c.info.textContent,undefined);
});
test('a completed revoice restores its newer script over a nonempty old project field',async()=>{
  const h=fixture(async()=>({job:{status:'done',script:'Edited script used for the new voice.',started_at:20,asset_id:'new'}}));
  h.state.project.voice_script={text:'Earlier script.',saved_at:10};
  await h.c.poll();assert.equal(h.c.text.value,'Edited script used for the new voice.');
});
test('a running job never overwrites a newer local edit or an intentional empty draft',async()=>{
  for(const draft of ['Latest unsaved author edit.','']){
    const h=fixture(async()=>({job:{status:'running',script:'Older voice request.',started_at:10}}));
    h.c.busy=false;h.c.voiceScriptDraft.p=draft;h.c.text.value=draft;
    await h.c.poll();assert.equal(h.c.text.value,draft);
  }
});
test('a response from before a new narration request cannot restore the previous ready voice',async()=>{
  let finish;const h=fixture(()=>new Promise(resolve=>finish=resolve));
  const pending=h.c.poll();vm.runInContext('narrationPollVersion++',h.c);
  h.c.text.value='New submitted script.';
  finish({job:{status:'done',script:'Old completed script.',started_at:5}});await pending;
  assert.equal(h.c.text.value,'New submitted script.');assert.equal(h.renders(),0);
  assert.equal([...h.timers.values()][0].delay,0);
});
