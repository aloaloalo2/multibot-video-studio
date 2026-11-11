const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../script-drafts.js'),'utf8');
const settle=()=>new Promise(resolve=>setImmediate(resolve));
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject};}
function fixture({storage=new Map(),session=new Map(),handler}={}){
  const project={id:'p',voice_script:{text:'Accepted script.',sha256:'base'}},calls=[],timers=new Map();let serial=0;
  let head={text:'Accepted script.',version:0,base_sha256:'base',epoch:0,pending:false,sha256:'accepted',history_count:0};
  const context={sessionStorage:{getItem:key=>session.get(key)??null,setItem:(key,value)=>session.set(key,value)},localStorage:{getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},voiceScriptDraft:{},
    setTimeout:(callback,delay)=>{const id=++serial;timers.set(id,{callback,delay});return id;},clearTimeout:id=>timers.delete(id),
    api:async(url,method,body)=>{
      calls.push({url,method,body});if(handler)return handler(url,method,body);
      if(method==='PATCH'){
        if(body.expected_version!==head.version&&head.text!==body.text){const error=Error('Conflict');error.httpStatus=409;throw error;}
        head={...head,text:body.text,version:head.version+1,pending:body.text!=='Accepted script.',sha256:'edited',history_count:1};
      }
      return {...head};
    }};
  vm.createContext(context);vm.runInContext(source,context);
  return {c:context,project,calls,storage,session,timers,head:()=>head,setHead:value=>head=value};
}
test('edits survive an immediate reload before the debounce, including an empty draft',async()=>{
  for(const text of ['', 'Unsaved complete new script.']){
    const first=fixture();await first.c.ensureScriptDraft(first.project);first.c.editScriptDraft(first.project,text);
    assert.equal(first.calls.length,1);assert.equal(JSON.parse(first.storage.values().next().value).text,text);
    const second=fixture({storage:first.storage,session:first.session});assert.equal(second.c.scriptDraftValue(second.project),text);
    await second.c.flushScriptDraft(second.project);assert.equal(second.head().text,text);assert.equal(second.storage.size,0);
  }
});
test('one in-flight save cannot replace a newer edit and the next write uses its acknowledgement',async()=>{
  const reply=deferred();let writes=0;
  const h=fixture({handler:(url,method,body)=>method==='PATCH'?(++writes===1?reply.promise:Promise.resolve({text:body.text,version:2,base_sha256:'base',epoch:0,pending:true,sha256:'b',history_count:2})):Promise.resolve({text:'Accepted script.',version:0,base_sha256:'base',epoch:0,pending:false})});
  await h.c.ensureScriptDraft(h.project);h.c.editScriptDraft(h.project,'First edit.');
  const pending=h.c.saveScriptDraft(h.c.scriptDraftEntry(h.project));h.c.editScriptDraft(h.project,'Newer edit.');
  reply.resolve({text:'First edit.',version:1,base_sha256:'base',epoch:0,pending:true,sha256:'a'});await pending;
  assert.equal(h.c.scriptDraftValue(h.project),'Newer edit.');await h.c.flushScriptDraft(h.project);
  const calls=h.calls.filter(row=>row.method==='PATCH');assert.equal(calls.length,2);assert.equal(calls[1].body.expected_version,1);assert.equal(calls[1].body.text,'Newer edit.');
});
test('typing while the initial read is pending keeps the author text',async()=>{
  const reply=deferred(),h=fixture({handler:()=>reply.promise});const pending=h.c.ensureScriptDraft(h.project);
  h.c.editScriptDraft(h.project,'Typed while loading.');reply.resolve({text:'Older server text.',version:0,base_sha256:'base',epoch:0,pending:false});await pending;
  assert.equal(h.c.scriptDraftValue(h.project),'Typed while loading.');assert.equal(h.c.scriptDraftEntry(h.project).dirty,true);
});
test('reload after a lost acknowledgement rebases only its own earlier saved edit',async()=>{
  const first=fixture();await first.c.ensureScriptDraft(first.project);
  first.c.editScriptDraft(first.project,'First edit.');const entry=first.c.scriptDraftEntry(first.project),writer=entry.writer;
  first.c.editScriptDraft(first.project,'Latest local edit.');
  const reloaded=fixture({storage:first.storage,session:first.session,handler:(url,method,body)=>Promise.resolve(method==='PATCH'?{text:body.text,version:2,base_sha256:'base',epoch:0,pending:true,writer_id:writer,client_sequence:body.client_sequence}:{text:'First edit.',version:1,base_sha256:'base',epoch:0,pending:true,writer_id:writer,client_sequence:1})});
  await reloaded.c.flushScriptDraft(reloaded.project);
  assert.equal(reloaded.c.scriptDraftEntry(reloaded.project).conflict,undefined);
  assert.equal(reloaded.calls.filter(row=>row.method==='PATCH')[0].body.text,'Latest local edit.');
});
test('acknowledging one tab never deletes another tab local recovery copy',async()=>{
  const shared=new Map(),one=fixture({storage:shared}),two=fixture({storage:shared});
  await one.c.ensureScriptDraft(one.project);await two.c.ensureScriptDraft(two.project);
  one.c.editScriptDraft(one.project,'One edit.');two.c.editScriptDraft(two.project,'Other pending edit.');
  assert.equal(shared.size,2);await one.c.flushScriptDraft(one.project);assert.equal(shared.size,1);
  assert.equal(JSON.parse(shared.values().next().value).text,'Other pending edit.');
});
test('failed saves keep local text and bounded retries without launching production',async()=>{
  const h=fixture({handler:(url,method)=>method==='PATCH'?Promise.reject(Error('offline')):Promise.resolve({text:'Accepted script.',version:0,base_sha256:'base',epoch:0,pending:false})});
  await h.c.ensureScriptDraft(h.project);h.c.editScriptDraft(h.project,'Offline edit.');
  await assert.rejects(h.c.flushScriptDraft(h.project),/offline/);
  assert.equal(JSON.parse(h.storage.values().next().value).text,'Offline edit.');assert.equal(h.c.scriptDraftEntry(h.project).error,'offline');
  assert.equal(h.calls.filter(row=>row.method==='PATCH').length,1);assert.ok(h.calls.every(row=>row.url.endsWith('/script-draft')));
  assert.equal([...h.timers.values()].at(-1).delay,2000);
});
test('two-tab conflicts retain local text and require an explicit retry',async()=>{
  const h=fixture();await h.c.ensureScriptDraft(h.project);h.setHead({...h.head(),text:'Another tab.',version:1});
  h.c.editScriptDraft(h.project,'My text.');await assert.rejects(h.c.flushScriptDraft(h.project),/Conflict/);
  const entry=h.c.scriptDraftEntry(h.project);assert.equal(entry.conflict,true);assert.equal(entry.text,'My text.');
  h.c.editScriptDraft(h.project,'My latest text.');assert.equal(entry.conflict,true);assert.equal(entry.error,'Conflict');
  await h.c.retryScriptDraft(h.project);assert.equal(h.head().text,'My latest text.');assert.equal(entry.conflict,false);assert.equal(entry.dirty,false);
});
test('a restarted project never revives the old browser draft',async()=>{
  const h=fixture();await h.c.ensureScriptDraft(h.project);h.c.editScriptDraft(h.project,'Previous episode text.');
  h.project.restarted_at=100;assert.equal(h.c.scriptDraftValue(h.project),undefined);assert.equal(h.c.scriptDraftEntry(h.project).dirty,false);
});
test('accepted narration clears only the matching working text',async()=>{
  const h=fixture();await h.c.ensureScriptDraft(h.project);h.c.editScriptDraft(h.project,'New accepted text.');await h.c.flushScriptDraft(h.project);
  const wrong={text:'Other request.',sha256:'other'};h.c.commitScriptDraft(h.project,wrong);assert.equal(h.c.scriptDraftEntry(h.project).pending,true);
  const record={text:'New accepted text.',sha256:'new'};h.project.voice_script=record;h.c.commitScriptDraft(h.project,record);
  assert.equal(h.c.scriptDraftEntry(h.project).pending,false);assert.equal(h.c.scriptDraftValue(h.project),undefined);
});
test('an old recognition cannot clear a newer uncommitted script',async()=>{
  const h=fixture();await h.c.ensureScriptDraft(h.project);h.c.editScriptDraft(h.project,'New unsaved edit.');
  h.c.acceptRecognizedScriptDraft(h.project.id,{applied:true,script_sha256:'accepted'});
  assert.equal(h.c.scriptDraftValue(h.project),'New unsaved edit.');
});
test('a storage quota failure still permits a successful server save',async()=>{
  const h=fixture();h.c.localStorage.setItem=()=>{throw Error('quota')};await h.c.ensureScriptDraft(h.project);
  h.c.editScriptDraft(h.project,'Server saved text.');assert.equal(h.c.scriptDraftEntry(h.project).localSaved,false);
  await h.c.flushScriptDraft(h.project);assert.equal(h.head().text,'Server saved text.');assert.equal(h.c.scriptDraftEntry(h.project).dirty,false);
  await settle();
});
test('a busy older server keeps recoverable browser drafts without blocking explicit narration',async()=>{
  const unavailable=()=>{const error=Error('Сторінку не знайдено');error.httpStatus=404;throw error;};
  const first=fixture({handler:unavailable});await first.c.ensureScriptDraft(first.project);
  first.c.editScriptDraft(first.project,'While the server is still busy.');await first.c.flushScriptDraft(first.project);
  assert.equal(first.c.scriptDraftValue(first.project),'While the server is still busy.');assert.equal(first.calls.length,1);
  assert.equal(first.storage.size,1);
  const afterRestart=fixture({storage:first.storage,session:first.session});await afterRestart.c.flushScriptDraft(afterRestart.project);
  assert.equal(afterRestart.head().text,'While the server is still busy.');assert.equal(first.storage.size,0);
  first.project.voice_script={text:'While the server is still busy.',sha256:'accepted-new'};
  assert.equal(first.c.scriptDraftValue(first.project),undefined);
});
test('deleted projects and exhausted browser storage remain visible failures on legacy support',async()=>{
  const missing=fixture({handler:()=>{const error=Error('Випуск не знайдено');error.httpStatus=404;throw error;}});
  await assert.rejects(missing.c.ensureScriptDraft(missing.project),/Випуск/);assert.notEqual(missing.c.scriptDraftEntry(missing.project).localOnly,true);
  const h=fixture({handler:()=>{const error=Error('Сторінку не знайдено');error.httpStatus=404;throw error;}});
  h.c.localStorage.setItem=()=>{throw Error('quota')};await h.c.ensureScriptDraft(h.project);h.c.editScriptDraft(h.project,'Unsaved edit.');
  await assert.rejects(h.c.flushScriptDraft(h.project),/Не вдалося зберегти/);assert.equal(h.c.scriptDraftEntry(h.project).dirty,true);
});
