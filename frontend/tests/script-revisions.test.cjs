const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../script-editing.js'),'utf8');
function harness(handler){
 const state={project:{id:'p'},navigation:1,modalGeneration:1},field={value:'',focus(){}},note={},report={hidden:true},action={classList:{add(){}}};
 const root={isConnected:true,querySelector:selector=>selector==='textarea'?field:selector==='#script-revision-note'?note:report};
 const calls=[],entry={text:'The saved working script.',version:3,base_sha256:'accepted',sha256:'working',epoch:0};let actions,closed=0,rendered=0;
 const c=vm.createContext({state,projectCostIcons:{claude_code:'<svg class="opus"></svg>'},flushScriptDraft:async()=>entry,
  modal(title,html,next){actions=next},$:id=>({querySelector:()=>id==='modal-actions'?action:root}),
  crypto:{randomUUID:()=> 'request-id'},api:async(...args)=>{calls.push(args);return handler?handler(...args):{author_revision_supported:true,can_revise:true,available:false}},
  closeModal(){closed++;root.isConnected=false},renderMontageMake(){rendered++},refreshProjects:async()=>{},status(){}});
 vm.runInContext(source,c);return {c,state,field,note,report,action,root,calls,entry,actions:()=>actions,closed:()=>closed,rendered:()=>rendered};
}
test('opening wishes is read-only and submit sends the current saved text identity exactly once',async()=>{
 let finish;const h=harness((url,method)=>method==='POST'?new Promise(resolve=>finish=resolve):({author_revision_supported:true,can_revise:true,available:true}));
 await h.c.openScriptRevision({id:'p'});assert.equal(h.calls.length,1);assert.equal(h.calls[0].length,1);assert.equal(h.action.disabled,true);assert.equal(h.report.hidden,false);
 h.field.value='Add one concrete example.';h.field.oninput();assert.equal(h.action.disabled,false);
 const first=h.actions()[0].run();await new Promise(resolve=>setImmediate(resolve));await h.actions()[0].run();
 const posts=h.calls.filter(call=>call[1]==='POST');assert.equal(posts.length,1);assert.equal(posts[0][2].wishes,h.field.value);assert.equal(posts[0][2].sha256,'working');assert.equal(posts[0][2].expected_version,3);assert.equal(posts[0][2].action,'editing');
 finish({project_id:'p',status:'running',stage:'editing',manual_revision:true});await first;
 assert.equal(h.closed(),1);assert.equal(h.rendered(),1);assert.equal(h.state.episodeDraft.manual_revision,true);
});
test('empty scripts and missing session support cannot start an author',async()=>{
 const empty=harness();empty.entry.text='';await empty.c.openScriptRevision({id:'p'});assert.equal(empty.calls.length,0);
 const missing=harness(()=>({available:true,can_revise:false,revision_reason:'Original session unavailable'}));
 await missing.c.openScriptRevision({id:'p'});missing.field.value='Changes';missing.field.oninput();await missing.actions()[0].run();
 assert.equal(missing.action.disabled,true);assert.equal(missing.calls.length,1);assert.match(missing.note.textContent,/session unavailable/);
});
test('late availability and submit replies stay inside their project and dialog',async()=>{
 let resolve;const h=harness(()=>new Promise(r=>resolve=r));const pending=h.c.openScriptRevision({id:'p'});await new Promise(r=>setImmediate(r));
 h.state.project={id:'other'};resolve({author_revision_supported:true,can_revise:true});await pending;assert.equal(h.action.disabled,true);
 let finish;const sent=harness((url,method)=>method==='POST'?new Promise(r=>finish=r):({author_revision_supported:true,can_revise:true}));
 await sent.c.openScriptRevision({id:'p'});sent.field.value='Changes';sent.field.oninput();const sending=sent.actions()[0].run();await new Promise(r=>setImmediate(r));
 sent.state.project={id:'other'};finish({project_id:'p',status:'running'});await sending;assert.equal(sent.closed(),0);assert.equal(sent.rendered(),0);assert.equal(sent.state.episodeDraft,undefined);
});
test('a failed submit preserves wishes and its request id and shows a visible error',async()=>{
 const h=harness((url,method)=>{if(method==='POST')throw Error('Network unavailable');return {author_revision_supported:true,can_revise:true}});
 await h.c.openScriptRevision({id:'p'});h.field.value='Keep this request.';h.field.oninput();await h.actions()[0].run();
 assert.equal(h.field.value,'Keep this request.');assert.equal(h.note.hidden,false);assert.match(h.note.textContent,/Network unavailable/);assert.equal(h.action.disabled,false);
 await h.actions()[0].run();const posts=h.calls.filter(call=>call[1]==='POST');assert.equal(posts.length,2);assert.equal(posts[0][2].request_id,posts[1][2].request_id);
});
