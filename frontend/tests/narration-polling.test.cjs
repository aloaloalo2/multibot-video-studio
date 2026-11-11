const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../plan.js'),'utf8');
const begin=source.indexOf('  let narrationPollTimer='),end=source.indexOf('  button.onclick=async()=>{if(busy)',begin);
function fixture(api){
  const timers=new Map();let next=0,renders=0;
  const state={project:{id:'p',channel_id:'channel'}},box={isConnected:true,querySelector:()=>null};
  const c=vm.createContext({api,state,box,pid:'p',busy:true,currentJob:{status:'running'},voiceReady:true,quoteTimer:null,quoteVersion:0,
    text:{value:'Full saved script'},button:{},info:{},estimate:{},panel:{},voiceScriptDraft:{},
    channelActivity:new Set(),projectActivities:new Map(),
    actionState(){},renderRunning(){renders++},updateScriptWordCount(){},narrationResultVisible:j=>j?.status==='done',
    priceLabel:()=>'',appendReadyNarration(){renders++;return {dataset:{},hidden:false}},
    setTimeout:(fn,delay)=>{const id=++next;timers.set(id,{fn,delay});return id},clearTimeout:id=>timers.delete(id)});
  vm.runInContext(source.slice(source.indexOf('function narrationScriptValue('),source.indexOf('const createVideoIcon=')),c);
  vm.runInContext(source.slice(begin,end),c);
  return {c,state,box,timers,renders:()=>renders};
}
test('a late narration status cannot mark another project or channel busy',async()=>{
  let finish;const h=fixture(()=>new Promise(resolve=>finish=resolve));const pending=h.c.poll();
  h.state.project={id:'other',channel_id:'another-channel'};
  finish({job:{status:'running',total:10,completed:2}});await pending;
  assert.equal(h.c.channelActivity.size,0);assert.equal(h.c.projectActivities.size,0);assert.equal(h.renders(),0);assert.equal(h.timers.size,0);
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
